from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

SUPPORTED = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "ico", "avif"}


def _remove_solid_background(image: Image.Image, tolerance: int) -> Image.Image:
    if not 0 <= tolerance <= 100:
        raise ValueError("Background tolerance must be between 0 and 100")
    image = image.convert("RGBA")
    width, height = image.size
    border = {(x, 0) for x in range(width)} | {(x, height - 1) for x in range(width)}
    border |= {(0, y) for y in range(height)} | {(width - 1, y) for y in range(height)}
    pixels = image.load()
    for point in border:
        color = pixels[point]
        if color[3]:
            ImageDraw.floodfill(image, point, (*color[:3], 0), thresh=tolerance)
    return image


def convert(input_path: Path, output_path: Path, settings: dict):
    remove_background = bool(settings.get("remove_solid_background", False))
    target_format = output_path.suffix.lower().lstrip(".")
    if remove_background and target_format != "png":
        raise ValueError("Solid background removal requires PNG output to preserve transparency")
    tolerance = int(settings.get("background_tolerance", 24))

    with Image.open(input_path) as image:
        image.load()
        if getattr(image, "n_frames", 1) > 1:
            frames = []
            for frame_index in range(image.n_frames):
                image.seek(frame_index)
                frame = image.convert("RGBA")
                if remove_background:
                    frame = _remove_solid_background(frame, tolerance)
                frames.append(frame)
            if output_path.suffix.lower() == ".gif":
                frames[0].save(output_path, save_all=True, append_images=frames[1:], loop=0, optimize=True)
            else:
                frames[0].save(output_path)
        else:
            image = ImageOps.exif_transpose(image)
            if remove_background:
                image = _remove_solid_background(image, tolerance)
            width = settings.get("width")
            height = settings.get("height")
            if width or height:
                size = (
                    int(width) if width else image.width,
                    int(height) if height else image.height,
                )
                image = image.resize(size, Image.Resampling.LANCZOS)
            target_format = target_format.replace("jpg", "JPEG").replace("jpeg", "JPEG")
            target_format = {"PNG":"PNG", "JPEG":"JPEG", "WEBP":"WEBP", "GIF":"GIF", "BMP":"BMP", "TIFF":"TIFF", "ICO":"ICO", "AVIF":"AVIF"}.get(target_format.upper(), target_format.upper())
            save_kwargs = {}
            if target_format in {"JPEG", "WEBP"}:
                save_kwargs["quality"] = int(settings.get("quality", 90))
            if target_format == "JPEG":
                if image.mode in {"RGBA", "LA"}:
                    image = image.convert("RGB")
            image.save(output_path, format=target_format, **save_kwargs)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Image engine did not create a valid output")
    return {"width": Image.open(output_path).width, "height": Image.open(output_path).height}

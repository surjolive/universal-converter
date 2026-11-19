from pathlib import PurePath
import mimetypes


MIME_FALLBACK = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
    "pdf": "application/pdf", "zip": "application/zip",
    "tar": "application/x-tar", "tar.gz": "application/gzip", "tgz": "application/gzip", "gz": "application/gzip",
    "json": "application/json", "csv": "text/csv", "tsv": "text/tab-separated-values",
}

SIGNATURES = {
    "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",), "gif": (b"GIF87a", b"GIF89a"),
    "pdf": (b"%PDF-",), "zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "tar.gz": (b"\x1f\x8b",), "tgz": (b"\x1f\x8b",), "gz": (b"\x1f\x8b",),
    "bmp": (b"BM",), "webp": (b"RIFF",),
}

TEXT_FORMATS = {
    "txt", "rtf", "html", "htm", "md", "xml", "php", "css", "js", "ts",
    "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "json", "yaml",
    "yml", "toml", "csv", "tsv", "sh", "ps1",
}


def safe_filename(filename: str) -> str:
    name = PurePath(filename).name
    if name in {"", ".", ".."}:
        raise ValueError("Invalid filename")
    return name


def validate_mime_and_signature(filename: str, content_type: str | None, data: bytes) -> str:
    name = safe_filename(filename)
    lower_name = name.lower()
    extension = "tar.gz" if lower_name.endswith(".tar.gz") else "tgz" if lower_name.endswith(".tgz") else name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if not extension:
        raise ValueError("File has no extension")

    if extension == "tgz":
        extension = "tar.gz"
    if data.startswith(b"%PDF-"):
        extension = "pdf"

    signatures = SIGNATURES.get(extension)
    if signatures:
        if not any(data.startswith(signature) for signature in signatures):
            raise ValueError(f"File signature does not match .{extension}")

    if extension == "webp":
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            raise ValueError("File signature does not match .webp")

    expected_mime = MIME_FALLBACK.get(extension)
    if not expected_mime:
        expected_mime = mimetypes.guess_type(name)[0]
    if content_type and expected_mime:
        supplied = content_type.split(";", 1)[0].strip().lower()
        gzip_mimes = {"application/gzip", "application/x-gzip", "application/x-compressed"}
        accepted = {"application/octet-stream", expected_mime}
        if extension in {"gz", "tar.gz"}:
            accepted.update(gzip_mimes)
        if supplied not in accepted:
            raise ValueError(f"MIME type {supplied} does not match .{extension}")

    if extension in TEXT_FORMATS:
        data.decode("utf-8-sig", errors="replace")

    return extension

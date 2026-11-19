from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from uuid import uuid4
from time import perf_counter
from datetime import datetime
import shutil
import subprocess
import zipfile
import mimetypes
import importlib.metadata
import importlib.util
import sys
import threading
import os
import re

from . import config as app_config
from .config import ROOT, RESOURCE_ROOT, UPLOADS, CONVERTED, HOSTED, HOST, PORT
from .database import SessionLocal, Conversion
from .security import safe_filename, validate_mime_and_signature
from .engines.registry import ConverterRegistry
from .engines import image_engine, data_engine, pdf_engine, archive_engine, video_engine, spreadsheet_engine, code_engine

app = FastAPI(title="Universal Converter", version="1.0.0", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"], allow_methods=["*"], allow_headers=["*"])
registry = ConverterRegistry()
INSTALL_JOBS = {}
INSTALL_JOBS_LOCK = threading.Lock()
WINGET_PACKAGES = {
    "php": {"package_id": "PHP.PHP.8.4", "name": "PHP 8.4"},
    "libreoffice": {"package_id": "TheDocumentFoundation.LibreOffice", "name": "LibreOffice"},
    "pandoc": {"package_id": "JohnMacFarlane.Pandoc", "name": "Pandoc"},
    "imagemagick": {"package_id": "ImageMagick.ImageMagick", "name": "ImageMagick"},
    "poppler": {"package_id": "oschwartz10612.Poppler", "name": "Poppler"},
    "winrar": {"package_id": "RARLab.WinRAR", "name": "WinRAR"},
}
ENGINE_INSTALL_URLS = {
    "php": "https://windows.php.net/download/",
    "libreoffice": "https://www.libreoffice.org/download/download-libreoffice/",
    "pandoc": "https://pandoc.org/installing.html",
    "imagemagick": "https://imagemagick.org/script/download.php#windows",
    "poppler": "https://github.com/oschwartz10612/poppler-windows/releases",
    "winrar": "https://www.win-rar.com/start.html?&L=0",
    "ffmpeg": "https://ffmpeg.org/download.html",
    "node": "https://nodejs.org/en/download",
}

# Reusable adapters: format pairs are registered, not implemented one-by-one.
IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "ico", "avif"}
DATA_FORMATS = {"json", "yaml", "yml", "toml", "csv", "tsv"}
CODE_FORMATS = {"php", "html", "css", "js", "ts", "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "xml", "yaml", "toml", "md", "sh", "ps1", "txt"}
MEDIA_FORMATS = {"mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "mp4", "mkv", "avi", "mov", "webm", "gif"}

for source in IMAGE_FORMATS:
    for target in IMAGE_FORMATS:
        if source != target or source == "png":
            registry.register(source, target, "Pillow", image_engine.convert)
for source in DATA_FORMATS:
    for target in DATA_FORMATS:
        if source != target and target != "toml":
            registry.register(source, target, "Data Adapter", data_engine.convert)
for source in CODE_FORMATS:
    registry.register(source, source, "Code Adapter", code_engine.format_text)
for source in CODE_FORMATS:
    registry.register(source, "html", "Code Viewer", code_engine.source_to_html)
    registry.register(source, "pdf", "Source PDF", pdf_engine.text_to_pdf)
for source in {"txt", "md", "php", "html", "css", "js", "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "xml"}:
    registry.register(source, "txt", "Text Adapter", code_engine.format_text)
registry.register("txt", "html", "Text/HTML", pdf_engine.txt_to_html)
registry.register("txt", "pdf", "ReportLab", pdf_engine.text_to_pdf)
registry.register("pdf", "html", "PyMuPDF Text Extraction", pdf_engine.pdf_to_html)
registry.register("pdf", "pdf", "PDF Passthrough", pdf_engine.pdf_passthrough)
registry.register("md", "txt", "Text Adapter", code_engine.format_text)
registry.register("html", "txt", "Text Extraction", code_engine.format_text)
for source in MEDIA_FORMATS:
    for target in MEDIA_FORMATS:
        if source != target:
            registry.register(source, target, "FFmpeg", video_engine.convert)
registry.register("csv", "xlsx", "openpyxl", spreadsheet_engine.convert)
registry.register("xlsx", "csv", "openpyxl", spreadsheet_engine.convert)
registry.register("xlsx", "tsv", "openpyxl", spreadsheet_engine.convert)
registry.register("csv", "tsv", "CSV Adapter", spreadsheet_engine.convert)
registry.register("tsv", "csv", "CSV Adapter", spreadsheet_engine.convert)
ARCHIVE_SOURCE_FORMATS = {"zip", "tar", "tar.gz", "gz"}
ARCHIVE_OUTPUT_FORMATS = ARCHIVE_SOURCE_FORMATS | {"rar"}
ARCHIVE_INPUT_FORMATS = IMAGE_FORMATS | DATA_FORMATS | CODE_FORMATS | MEDIA_FORMATS | {
    "pdf", "rtf", "odt", "docx", "doc", "epub", "xlsx", "xls", "ods", "pptx", "ppt", "odp", "svg",
}
for source in ARCHIVE_INPUT_FORMATS | ARCHIVE_SOURCE_FORMATS:
    for target in ARCHIVE_OUTPUT_FORMATS:
        registry.register(source, target, "Archive Adapter", archive_engine.convert_archive)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_api_key(request: Request):
    if not app_config.API_KEY:
        return
    supplied = request.headers.get("X-API-Key")
    if supplied != app_config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def safe_extension(filename: str) -> str:
    lower_name = Path(filename).name.lower()
    suffix = "tar.gz" if lower_name.endswith((".tar.gz", ".tgz")) else Path(filename).suffix.lower().lstrip(".")
    if not suffix or suffix not in {"pdf", "txt", "rtf", "odt", "docx", "doc", "epub", "html", "htm", "md", "xml", "php", "css", "js", "ts", "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "json", "yaml", "yml", "toml", "tsv", "csv", "xlsx", "xls", "ods", "pptx", "ppt", "odp", "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "svg", "ico", "avif", "mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "mp4", "mkv", "avi", "mov", "webm", "zip", "tar", "tar.gz", "tgz", "gz"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: .{suffix}")
    return suffix

HOSTED_EXTENSIONS = {"html", "htm", "php", "css", "js", "json", "txt", "md", "xml", "svg", "png", "jpg", "jpeg", "gif", "webp", "ico", "bmp", "woff", "woff2", "ttf"}

@app.post("/api/host/upload")
async def host_upload(request: Request, files: list[UploadFile] = File(...)):
    require_api_key(request)
    uploaded = []
    for file in files:
        filename = safe_filename(file.filename or "file")
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in HOSTED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported hosted file: .{extension}")
        if extension in {"php", "html", "htm", "svg"}:
            pass
        destination = HOSTED / filename
        counter = 1
        while destination.exists():
            destination = HOSTED / f"{Path(filename).stem}-{counter}{Path(filename).suffix.lower()}"
            counter += 1
        size = 0
        with destination.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > app_config.MAX_UPLOAD_SIZE:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Upload exceeds maximum file size")
                handle.write(chunk)
        uploaded.append({"filename": destination.name, "extension": extension, "size": size, "url": f"/hosted/{destination.name}"})
    return {"files": uploaded}

@app.get("/api/host/files")
def host_files():
    items = []
    for path in sorted(HOSTED.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_file():
            items.append({"filename": path.name, "extension": path.suffix.lower().lstrip("."), "size": path.stat().st_size, "url": f"/hosted/{path.name}"})
    return {"files": items}

@app.delete("/api/host/files/{filename}")
def delete_host_file(filename: str):
    safe_name = safe_filename(filename)
    path = (HOSTED / safe_name).resolve()
    if not str(path).startswith(str(HOSTED.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="Hosted file not found")
    path.unlink()
    return {"status": "deleted"}

@app.get("/api/settings")
def get_settings():
    settings = app_config.load_settings()
    settings["api_key"] = bool(settings.get("api_key"))
    return settings

@app.put("/api/settings")
def put_settings(payload: dict):
    allowed = set(app_config.DEFAULT_SETTINGS)
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown setting: {sorted(unknown)[0]}")

    max_size = int(payload.get("max_upload_size", app_config.MAX_UPLOAD_SIZE))
    worker_count = int(payload.get("worker_count", 2))
    cleanup_days = int(payload.get("cleanup_days", 7))
    if max_size < 1024 * 1024 or max_size > 10 * 1024 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Maximum upload size must be between 1 MB and 10 GB")
    if worker_count < 1 or worker_count > 8:
        raise HTTPException(status_code=400, detail="Worker count must be between 1 and 8")
    if cleanup_days < 1 or cleanup_days > 365:
        raise HTTPException(status_code=400, detail="Cleanup age must be between 1 and 365 days")

    current = app_config.load_settings()
    current.update({
        "max_upload_size": max_size,
        "api_key": str(payload.get("api_key", current.get("api_key") or "")),
        "worker_count": worker_count,
        "cleanup_enabled": bool(payload.get("cleanup_enabled", current.get("cleanup_enabled", True))),
        "cleanup_days": cleanup_days,
    })
    app_config.save_settings(current)
    app_config.MAX_UPLOAD_SIZE = max_size
    app_config.API_KEY = str(current["api_key"])
    response = dict(current)
    response["api_key"] = bool(response["api_key"])
    return response

@app.post("/api/settings/cleanup")
def cleanup_settings():
    import time
    settings = app_config.load_settings()
    cutoff = time.time() - int(settings.get("cleanup_days", 7)) * 86400
    removed = 0
    for directory in (app_config.TEMP, app_config.UPLOADS):
        for path in directory.iterdir():
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
    return {"removed": removed}

@app.get("/api/settings/diagnostics")
def settings_diagnostics():
    disk = shutil.disk_usage(str(ROOT))
    database_path = app_config.DATABASE / "converter.db"
    return {
        "product": "Universal Converter",
        "python": f"{__import__('sys').version.split()[0]}",
        "ffmpeg": "available" if shutil.which("ffmpeg") else "missing",
        "php": "available" if shutil.which("php") else "missing",
        "libreoffice": "available" if shutil.which("soffice") else "missing",
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "database_bytes": database_path.stat().st_size if database_path.exists() else 0,
        "hosted_files": sum(1 for path in HOSTED.iterdir() if path.is_file()),
    }

@app.get("/api/health")
def health():
    return {"status": "ok", "offline": True, "product": "Universal Converter"}

@app.get("/api/engines")
def engines():
    engines_list = [
        _module_engine("pillow", "Pillow", "Images", "PIL", "Pillow"),
        _module_engine("reportlab", "ReportLab", "PDF", "reportlab", "reportlab"),
        _module_engine("pymupdf", "PyMuPDF", "PDF", "fitz", "PyMuPDF"),
        _module_engine("cairosvg", "CairoSVG", "Images", "cairosvg", "CairoSVG"),
        _module_engine("openpyxl", "openpyxl", "Spreadsheets", "openpyxl", "openpyxl"),
        _binary_engine("ffmpeg", "FFmpeg", "Audio/Video", ["ffmpeg"], ["-version"]),
        _binary_engine("ffprobe", "FFprobe", "Audio/Video", ["ffprobe"], ["-version"]),
        _binary_engine("php", "PHP", "PHP source/runtime", ["php"], ["--version"]),
        _binary_engine("node", "Node.js", "JavaScript runtime", ["node"], ["--version"]),
        _binary_engine("libreoffice", "LibreOffice", "Documents", ["soffice", "libreoffice"], ["--version"]),
        _binary_engine("pandoc", "Pandoc", "Documents", ["pandoc"], ["--version"]),
        _binary_engine("imagemagick", "ImageMagick", "Images", ["magick"], ["-version"]),
        _binary_engine("poppler", "Poppler (pdftoppm)", "PDF tools", ["pdftoppm"], ["-v"]),
        _binary_engine("winrar", "WinRAR RAR CLI", "Archives", ["rar"], ["-?" ]),
        _module_engine("pywebview", "pywebview", "Desktop", "webview", "pywebview"),
        _module_engine("pyinstaller", "PyInstaller", "Desktop packaging", "PyInstaller", "pyinstaller"),
        {"key": "python", "name": "Python", "category": "Runtime", "status": "available", "version": sys.version.split()[0], "installable": False, "install_url": "https://www.python.org/downloads/"},
    ]
    winget = shutil.which("winget")
    for engine in engines_list:
        install = WINGET_PACKAGES.get(engine["key"])
        engine["package_id"] = install["package_id"] if install else None
        engine["installable"] = bool(install and winget and engine["status"] != "available")
        engine["install_url"] = engine.get("install_url") or ENGINE_INSTALL_URLS.get(engine["key"])
    return {"engines": engines_list, "package_manager": {"name": "Windows Package Manager", "status": "available" if winget else "missing"}}


def _module_engine(key, name, category, module, distribution):
    available = importlib.util.find_spec(module) is not None
    try:
        version = importlib.metadata.version(distribution) if available else None
    except importlib.metadata.PackageNotFoundError:
        version = "installed"
    return {"key": key, "name": name, "category": category,
            "status": "available" if available else "missing", "version": version}


def _binary_engine(key, name, category, candidates, version_args):
    binary = next((shutil.which(candidate) for candidate in candidates if shutil.which(candidate)), None)
    if not binary and key in WINGET_PACKAGES:
        winget_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Microsoft" / "WinGet" / "Packages"
        for package_dir in winget_root.glob(f"{WINGET_PACKAGES[key]['package_id']}_*"):
            for candidate in candidates:
                names = {candidate.lower(), f"{candidate}.exe".lower()}
                binary = next((str(path) for path in package_dir.rglob("*") if path.is_file() and path.name.lower() in names), None)
                if binary:
                    break
            if binary:
                break
    if not binary and key == "winrar":
        for program_files in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if program_files:
                candidate_path = Path(program_files) / "WinRAR" / "Rar.exe"
                if candidate_path.is_file():
                    binary = str(candidate_path)
                    break
    version = None
    if binary:
        try:
            result = subprocess.run([binary, *version_args], capture_output=True, text=True, timeout=5, check=False)
            output = (result.stdout or result.stderr).strip().splitlines()
            version = output[0][:160] if output else "installed"
        except (OSError, subprocess.TimeoutExpired):
            version = "installed; version unavailable"
    install = WINGET_PACKAGES.get(key)
    return {"key": key, "name": name, "category": category,
            "status": "available" if binary else "missing", "version": version,
            "path": binary, "package_id": install["package_id"] if install else None,
            "install_url": ENGINE_INSTALL_URLS.get(key)}


def _run_winget_install(job_id, engine_key, winget_path):
    package = WINGET_PACKAGES[engine_key]
    with INSTALL_JOBS_LOCK:
        INSTALL_JOBS[job_id].update({"status": "running", "progress": None, "logs": [], "message": "Starting Winget"})
    command = [winget_path, "install", "--id", package["package_id"], "--exact",
               "--silent", "--accept-source-agreements", "--accept-package-agreements",
               "--disable-interactivity"]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", bufsize=1)

        def capture_output():
            if process.stdout is None:
                return
            for line in process.stdout:
                text = line.strip()
                if not text:
                    continue
                percentage = re.search(r"\b(\d{1,3})\s*%", text)
                with INSTALL_JOBS_LOCK:
                    job = INSTALL_JOBS.get(job_id)
                    if not job:
                        continue
                    logs = job.setdefault("logs", [])
                    logs.append(text[:500])
                    del logs[:-40]
                    job["message"] = text[:500]
                    if percentage:
                        job["progress"] = min(99, int(percentage.group(1)))

        reader = threading.Thread(target=capture_output, daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            reader.join(timeout=2)
            with INSTALL_JOBS_LOCK:
                INSTALL_JOBS[job_id].update({"status": "failed", "message": "Winget install timed out after 15 minutes"})
            return
        reader.join(timeout=2)
        with INSTALL_JOBS_LOCK:
            INSTALL_JOBS[job_id].update({
                "status": "succeeded" if return_code == 0 else "failed",
                "progress": 100 if return_code == 0 else INSTALL_JOBS[job_id].get("progress"),
                "return_code": return_code,
                "message": "Installation completed" if return_code == 0 else f"Winget exited with code {return_code}",
            })
    except OSError as exc:
        with INSTALL_JOBS_LOCK:
            INSTALL_JOBS[job_id].update({"status": "failed", "message": str(exc)})


@app.post("/api/engines/install/{engine_key}")
def install_engine(engine_key: str, request: Request):
    require_api_key(request)
    if request.headers.get("X-UC-Install-Confirm") != "yes":
        raise HTTPException(status_code=400, detail="Explicit install confirmation header is required")
    if engine_key not in WINGET_PACKAGES:
        raise HTTPException(status_code=404, detail="Engine is not in the approved install catalog")
    winget_path = shutil.which("winget")
    if not winget_path:
        raise HTTPException(status_code=503, detail="Windows Package Manager is not installed")
    job_id = uuid4().hex
    with INSTALL_JOBS_LOCK:
        INSTALL_JOBS[job_id] = {"id": job_id, "engine": engine_key, "status": "queued", "progress": 0, "logs": [], "message": "Waiting to start"}
    thread = threading.Thread(target=_run_winget_install, args=(job_id, engine_key, winget_path), daemon=True)
    thread.start()
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})


@app.get("/api/engines/install-jobs/{job_id}")
def engine_install_job(job_id: str):
    with INSTALL_JOBS_LOCK:
        job = INSTALL_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Install job not found")
        return dict(job)

@app.get("/api/formats")
def formats():
    return registry.formats()

@app.post("/api/upload")
async def upload(request: Request, files: list[UploadFile] = File(...)):
    require_api_key(request)
    uploaded = []
    for file in files:
        try:
            filename = safe_filename(file.filename or "upload")
            extension = safe_extension(filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        record_id = uuid4().hex
        destination = UPLOADS / f"{record_id}.{extension}"
        size = 0
        signature_prefix = bytearray()
        with destination.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > app_config.MAX_UPLOAD_SIZE:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Upload exceeds maximum file size")
                handle.write(chunk)
                if len(signature_prefix) < 65536:
                    signature_prefix.extend(chunk[:65536 - len(signature_prefix)])
        try:
            detected_extension = validate_mime_and_signature(filename, file.content_type, bytes(signature_prefix))
        except (ValueError, UnicodeDecodeError) as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc))
        if detected_extension != extension:
            detected_destination = destination.with_suffix(f".{detected_extension}")
            destination.rename(detected_destination)
            destination = detected_destination
            extension = detected_extension
        uploaded.append({"id": record_id, "filename": filename, "extension": extension, "path": str(destination), "size": size})
    return {"files": uploaded}

@app.post("/api/convert")
def convert(request: Request, upload_id: str = Form(...), target: str = Form(...), settings: str = Form("{}"), original_filename: str = Form(""), db=Depends(get_db)):
    require_api_key(request)
    import json
    try:
        options = json.loads(settings)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Settings must be valid JSON")
    source_path = next(UPLOADS.glob(f"{upload_id}.*"), None)
    if not source_path:
        raise HTTPException(status_code=404, detail="Uploaded file not found")
    try:
        original_filename = safe_filename(original_filename) if original_filename else source_path.name
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    source = "tar.gz" if source_path.name.lower().endswith(".tar.gz") else source_path.suffix.lower().lstrip(".")
    target = target.lower().lstrip(".")
    route = registry.get(source, target)
    if not route:
        raise HTTPException(status_code=422, detail=f"Unsupported conversion: {source.upper()} to {target.upper()}")
    engine_name, converter = route
    output_path = CONVERTED / f"{uuid4().hex}.{target}"
    options.update({"source_format": source, "target_format": target, "original_filename": original_filename})
    start = perf_counter()
    record = Conversion(original_filename=original_filename, source_format=source, target_format=target,
                        file_size=source_path.stat().st_size, status="running", engine=engine_name)
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        metadata = converter(source_path, output_path, options)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Conversion engine did not create a valid output")
        record.status = "success"
        record.output_size = output_path.stat().st_size
        record.output_path = str(output_path)
        record.conversion_time = perf_counter() - start
        record.error = ""
        db.commit()
        return {"id": record.id, "status": "success", "download_url": f"/api/download/{record.id}", "metadata": metadata}
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
        record.conversion_time = perf_counter() - start
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/conversion/{id}")
def conversion(id: int, db=Depends(get_db)):
    record = db.get(Conversion, id)
    if not record:
        raise HTTPException(status_code=404, detail="Conversion not found")
    return conversion_dict(record)

@app.get("/api/preview/{id}")
def preview(id: int, db=Depends(get_db)):
    record = db.get(Conversion, id)
    if not record or record.status != "success" or not record.output_path:
        raise HTTPException(status_code=404, detail="Converted file not available")
    path = Path(record.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file was removed")

    target = record.target_format.lower()
    text_targets = {"txt", "md", "html", "htm", "xml", "php", "css", "js", "ts", "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "json", "yaml", "yml", "toml", "csv", "tsv", "rtf", "sh", "ps1"}

    if target in text_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"kind": "html" if target in {"html", "htm"} else "text", "content": text[:500000], "truncated": len(text) > 500000, "target": target}

    if target == "xlsx":
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook.active
            rows = list(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 200), values_only=True))
            table = "<table>" + "".join("<tr>" + "".join(f"<td>{str(value or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</td>" for value in row) + "</tr>" for row in rows) + "</table>"
            return {"kind": "table", "content": table, "truncated": sheet.max_row > 200, "target": target}
        except Exception as exc:
            return {"kind": "metadata", "content": str(exc), "target": target}

    if target == "docx":
        try:
            from docx import Document
            document = Document(path)
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            return {"kind": "text", "content": text[:500000], "truncated": len(text) > 500000, "target": target}
        except Exception as exc:
            return {"kind": "metadata", "content": str(exc), "target": target}

    if target in {"zip", "tar", "tar.gz", "gz", "rar"}:
        try:
            names = archive_engine.archive_members(path, target)[:500]
            return {"kind": "archive", "content": names, "truncated": len(names) == 500, "target": target}
        except Exception as exc:
            return {"kind": "metadata", "content": str(exc), "target": target}

    if target in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "ico", "svg", "avif", "pdf", "mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "mp4", "mkv", "avi", "mov", "webm"}:
        metadata = {"size": path.stat().st_size, "filename": path.name}
        if target in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "ico", "avif"}:
            try:
                from PIL import Image
                with Image.open(path) as image:
                    metadata.update({"width": image.width, "height": image.height, "format": image.format})
            except Exception:
                pass
        if target in {"mp3", "wav", "flac", "aac", "ogg", "m4a", "opus", "mp4", "mkv", "avi", "mov", "webm"}:
            binary = shutil.which("ffprobe")
            if binary:
                try:
                    result = subprocess.run([binary, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, timeout=15, check=False)
                    import json
                    if result.returncode == 0:
                        metadata.update(json.loads(result.stdout))
                except Exception:
                    pass
        kind = "pdf" if target == "pdf" else "image" if target in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff", "ico", "svg", "avif"} else "video" if target in {"mp4", "mkv", "avi", "mov", "webm"} else "audio"
        return {"kind": kind, "content": "", "metadata": metadata, "target": target}

    return {"kind": "download", "content": "", "metadata": {"size": path.stat().st_size, "filename": path.name}, "target": target}

@app.get("/api/preview/{id}/file")
def preview_file(id: int, db=Depends(get_db)):
    record = db.get(Conversion, id)
    if not record or record.status != "success" or not record.output_path:
        raise HTTPException(status_code=404, detail="Converted file not available")
    path = Path(record.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file was removed")

    target = record.target_format.lower()
    media_type = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml",
        "pdf": "application/pdf", "mp4": "video/mp4", "webm": "video/webm",
        "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    }.get(target) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"X-Content-Type-Options": "nosniff"}
    if target in {"html", "htm", "svg"}:
        headers["Content-Security-Policy"] = "default-src 'self' data: blob:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    filename = Path(record.original_filename).stem + "." + target
    return FileResponse(path, media_type=media_type, filename=filename,
                        content_disposition_type="inline", headers=headers)

@app.get("/api/download/{id}")
def download(id: int, db=Depends(get_db)):
    record = db.get(Conversion, id)
    if not record or record.status != "success" or not record.output_path:
        raise HTTPException(status_code=404, detail="Converted file not available")
    path = Path(record.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file was removed")
    original_name = Path(record.original_filename).name
    original_stem = original_name[:-7] if original_name.lower().endswith(".tar.gz") else Path(original_name).stem
    filename = original_stem + "." + record.target_format
    return FileResponse(path, filename=filename)

@app.delete("/api/conversion/{id}")
def delete_conversion(id: int, db=Depends(get_db)):
    record = db.get(Conversion, id)
    if not record:
        raise HTTPException(status_code=404, detail="Conversion not found")
    if record.output_path:
        Path(record.output_path).unlink(missing_ok=True)
    db.delete(record)
    db.commit()
    return {"status": "deleted"}

@app.get("/api/history/export")
def export_history(format: str = "json", db=Depends(get_db)):
    records = db.query(Conversion).order_by(Conversion.created_at.desc()).all()
    items = [conversion_dict(record) for record in records]
    if format.lower() == "csv":
        import csv
        import io
        output = io.StringIO()
        fieldnames = ["id", "original_filename", "source_format", "target_format", "file_size", "output_size", "status", "conversion_time", "created_at", "engine", "error"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)
        return {"format": "csv", "content": output.getvalue(), "filename": "conversion-history.csv"}
    import json
    return {"format": "json", "content": json.dumps(items, ensure_ascii=False, indent=2), "filename": "conversion-history.json"}

@app.get("/api/history")
def history(db=Depends(get_db)):
    records = db.query(Conversion).order_by(Conversion.created_at.desc()).limit(500).all()
    return {"items": [conversion_dict(record) for record in records]}

@app.delete("/api/history")
def clear_history(db=Depends(get_db)):
    records = db.query(Conversion).all()
    for record in records:
        if record.output_path:
            Path(record.output_path).unlink(missing_ok=True)
        db.delete(record)
    db.commit()
    return {"status": "cleared"}

@app.get("/api/conversions")
def conversions(db=Depends(get_db)):
    return history(db=db)


def conversion_dict(record):
    return {"id": record.id, "original_filename": record.original_filename,
            "source_format": record.source_format, "target_format": record.target_format,
            "file_size": record.file_size, "output_size": record.output_size,
            "status": record.status, "conversion_time": record.conversion_time,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "error": record.error, "engine": record.engine}

frontend = RESOURCE_ROOT / "frontend"
images = RESOURCE_ROOT / "images"
app.mount("/hosted", StaticFiles(directory=HOSTED, check_dir=True), name="hosted")
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
if images.exists():
    app.mount("/images", StaticFiles(directory=images), name="images")

@app.get("/")
def index():
    return FileResponse(frontend / "index.html")

@app.get("/{page}.html")
def page(page: str):
    path = frontend / f"{page}.html"
    if path.exists():
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Page not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=False)

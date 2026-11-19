import gzip
import os
import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryDirectory


ARCHIVE_FORMATS = {"zip", "tar", "tar.gz", "gz"}
DEFAULT_MAX_EXTRACT_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10000


def _safe_relative_path(name: str) -> Path:
    normalized = name.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if relative.is_absolute() or PureWindowsPath(name).drive or any(part == ".." for part in relative.parts):
        raise ValueError("Archive path traversal detected")
    if not relative.parts or any(part in {"", "."} for part in relative.parts):
        raise ValueError("Archive contains an invalid path")
    return Path(*relative.parts)


def _destination(root: Path, member_name: str) -> Path:
    root = root.resolve()
    destination = (root / _safe_relative_path(member_name)).resolve()
    if os.path.commonpath((str(root), str(destination))) != str(root):
        raise ValueError("Archive path traversal detected")
    return destination


def _copy_stream(source, destination: Path, budget: list[int], limit: int):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        while chunk := source.read(1024 * 1024):
            budget[0] += len(chunk)
            if budget[0] > limit:
                raise ValueError("Archive exceeds extraction size limit")
            output.write(chunk)


def _extract_zip(input_path: Path, root: Path, budget: list[int], limit: int):
    members = []
    with zipfile.ZipFile(input_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("Archive contains too many entries")
        if sum(info.file_size for info in infos) > limit:
            raise ValueError("Archive exceeds extraction size limit")
        for info in infos:
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValueError("Archive symlinks are not supported")
            destination = _destination(root, info.filename)
            with archive.open(info) as source:
                _copy_stream(source, destination, budget, limit)
            members.append((destination, _safe_relative_path(info.filename)))
    return members


def _extract_tar(input_path: Path, root: Path, budget: list[int], limit: int):
    members = []
    with tarfile.open(input_path, mode="r:*") as archive:
        infos = archive.getmembers()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("Archive contains too many entries")
        if sum(info.size for info in infos if info.isfile()) > limit:
            raise ValueError("Archive exceeds extraction size limit")
        for info in infos:
            if info.isdir():
                continue
            if not info.isfile():
                raise ValueError("Archive links and special files are not supported")
            destination = _destination(root, info.name)
            source = archive.extractfile(info)
            if source is None:
                raise ValueError("Could not read archive member")
            with source:
                _copy_stream(source, destination, budget, limit)
            members.append((destination, _safe_relative_path(info.name)))
    return members


def _extract_gzip(input_path: Path, root: Path, original_filename: str, budget: list[int], limit: int):
    name = Path(original_filename).name
    output_name = name[:-3] if name.lower().endswith(".gz") else name + ".out"
    if not output_name:
        output_name = "decompressed-data"
    relative = _safe_relative_path(output_name)
    destination = _destination(root, output_name)
    with gzip.open(input_path, "rb") as source:
        _copy_stream(source, destination, budget, limit)
    return [(destination, relative)]


def _archive_members(input_path: Path, source_format: str, root: Path, settings: dict):
    limit = int(settings.get("max_extract_bytes", DEFAULT_MAX_EXTRACT_BYTES))
    if limit <= 0:
        raise ValueError("Extraction size limit must be positive")
    budget = [0]
    if source_format == "zip":
        return _extract_zip(input_path, root, budget, limit)
    if source_format in {"tar", "tar.gz"}:
        return _extract_tar(input_path, root, budget, limit)
    if source_format == "gz":
        return _extract_gzip(input_path, root, settings.get("original_filename", input_path.name), budget, limit)
    return [(input_path, _safe_relative_path(settings.get("original_filename", input_path.name)))]


def _rar_binary():
    binary = shutil.which("rar")
    if binary:
        return binary
    for program_files in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if program_files:
            candidate = Path(program_files) / "WinRAR" / "Rar.exe"
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError("RAR conversion requires WinRAR. Install WinRAR, then retry.")


def _run_rar(arguments, **kwargs):
    try:
        result = subprocess.run([_rar_binary(), *arguments], capture_output=True, text=True, timeout=600, check=False, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("WinRAR did not finish within 10 minutes") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"WinRAR failed{': ' + detail if detail else ''}")
    return result


def _write_archive(members, output_path: Path, target_format: str):
    if target_format == "zip":
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, relative in members:
                archive.write(path, relative.as_posix())
    elif target_format in {"tar", "tar.gz"}:
        mode = "w:gz" if target_format == "tar.gz" else "w"
        with tarfile.open(output_path, mode=mode) as archive:
            for path, relative in members:
                archive.add(path, arcname=relative.as_posix(), recursive=False)
    elif target_format == "gz":
        if len(members) != 1:
            raise ValueError("GZ stores one file; select ZIP, TAR, or TAR.GZ for multiple files")
        with members[0][0].open("rb") as source, gzip.open(output_path, "wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
    elif target_format == "rar":
        working_directory = output_path.parent / f".{output_path.stem}-rar-input"
        working_directory.mkdir()
        try:
            names = []
            for path, relative in members:
                staged = _destination(working_directory, relative.as_posix())
                staged.parent.mkdir(parents=True, exist_ok=True)
                if path.resolve() != staged.resolve():
                    shutil.copyfile(path, staged)
                names.append(relative.as_posix())
            _run_rar(["a", "-idq", "--", str(output_path.resolve()), *names], cwd=working_directory)
        finally:
            shutil.rmtree(working_directory, ignore_errors=True)
    else:
        raise ValueError(f"Unsupported archive target: {target_format}")


def convert_archive(input_path: Path, output_path: Path, settings: dict):
    source_format = settings.get("source_format", input_path.suffix.lower().lstrip("."))
    target_format = settings.get("target_format", output_path.suffix.lower().lstrip("."))
    original_filename = settings.get("original_filename", input_path.name)
    settings = {**settings, "original_filename": original_filename}

    with TemporaryDirectory(prefix="uc-archive-") as temporary:
        root = Path(temporary) / "unpacked"
        root.mkdir()
        if source_format in ARCHIVE_FORMATS:
            members = _archive_members(input_path, source_format, root, settings)
        else:
            members = [(input_path, _safe_relative_path(original_filename))]
        _write_archive(members, output_path, target_format)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Archive engine did not create an output file")
    return {"archive_files": len(members), "source": source_format, "target": target_format}


def archive_members(input_path: Path, archive_format: str, limit: int = DEFAULT_MAX_EXTRACT_BYTES):
    names = []
    if archive_format == "zip":
        with zipfile.ZipFile(input_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS or sum(info.file_size for info in infos) > limit:
                raise ValueError("Archive exceeds preview limits")
            for info in infos:
                if not info.is_dir():
                    _safe_relative_path(info.filename)
                    names.append(info.filename)
    elif archive_format in {"tar", "tar.gz"}:
        with tarfile.open(input_path, mode="r:*") as archive:
            infos = archive.getmembers()
            if len(infos) > MAX_ARCHIVE_MEMBERS or sum(info.size for info in infos if info.isfile()) > limit:
                raise ValueError("Archive exceeds preview limits")
            for info in infos:
                if info.isfile():
                    _safe_relative_path(info.name)
                    names.append(info.name)
    elif archive_format == "gz":
        names.append(Path(input_path.name).stem)
    elif archive_format == "rar":
        result = _run_rar(["lb", str(input_path.resolve())])
        for name in result.stdout.splitlines():
            if name.strip():
                names.append(_safe_relative_path(name.strip()).as_posix())
    else:
        raise ValueError(f"Unsupported archive format: {archive_format}")
    return names

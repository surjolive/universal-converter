from html import escape
from pathlib import Path
import json


def format_text(input_path: Path, output_path: Path, settings: dict):
    text = input_path.read_text(encoding="utf-8", errors="replace")
    target = output_path.suffix.lower().lstrip(".")
    if target in {"txt", "php", "html", "css", "js", "ts", "py", "java", "c", "cpp", "cs", "go", "rs", "sql", "xml", "yaml", "toml", "md", "sh", "ps1"}:
        newline = settings.get("line_endings", "LF")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if newline.upper() == "CRLF":
            normalized = normalized.replace("\n", "\r\n")
        if settings.get("minify"):
            normalized = "\n".join(line.strip() for line in normalized.splitlines() if line.strip())
        output_path.write_text(normalized, encoding="utf-8", newline="")
    else:
        raise ValueError(f"Unsupported code target: {target}")
    return {"characters": len(text)}


def source_to_html(input_path: Path, output_path: Path, settings: dict):
    text = input_path.read_text(encoding="utf-8", errors="replace")
    language = input_path.suffix.lower().lstrip(".")
    output_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{margin:0;background:#111827;color:#dbeafe}pre{margin:0;padding:24px;font:14px/1.6 monospace;white-space:pre-wrap}</style>"
        f"</head><body><pre data-language='{escape(language)}'>{escape(text)}</pre></body></html>",
        encoding="utf-8",
    )
    return {"language": language}

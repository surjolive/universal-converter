import csv
import json
import tomllib
from pathlib import Path
import yaml

def convert(input_path: Path, output_path: Path, settings: dict):
    source = input_path.suffix.lower().lstrip(".")
    target = output_path.suffix.lower().lstrip(".")

    if source == "json":
        data = json.loads(input_path.read_text(encoding="utf-8"))
    elif source in {"yaml", "yml"}:
        data = yaml.safe_load(input_path.read_text(encoding="utf-8"))
    elif source == "toml":
        data = tomllib.loads(input_path.read_text(encoding="utf-8"))
    elif source in {"csv", "tsv"}:
        delimiter = "\t" if source == "tsv" else ","
        with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
            data = list(csv.DictReader(handle, delimiter=delimiter))
    else:
        raise ValueError(f"Unsupported data source: {source}")

    if target == "json":
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif target in {"yaml", "yml"}:
        output_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    elif target == "toml":
        raise ValueError("TOML output requires a top-level table; no safe generic adapter is available")
    elif target in {"csv", "tsv"}:
        delimiter = "\t" if target == "tsv" else ","
        if not isinstance(data, list):
            raise ValueError("CSV/TSV output requires a list of records")
        fieldnames = list(data[0].keys()) if data else []
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(data)
    else:
        raise ValueError(f"Unsupported data target: {target}")
    return {"source": source, "target": target}

from pathlib import Path
import csv
from openpyxl import Workbook, load_workbook


def convert(input_path: Path, output_path: Path, settings: dict):
    source = input_path.suffix.lower().lstrip(".")
    target = output_path.suffix.lower().lstrip(".")
    if source == "csv":
        delimiter = "\t" if target == "tsv" else ","
        with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle, delimiter="," if source == "csv" else "\t"))
        if target in {"csv", "tsv"}:
            with output_path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle, delimiter=delimiter).writerows(rows)
        elif target == "xlsx":
            workbook = Workbook()
            sheet = workbook.active
            for row in rows:
                sheet.append(row)
            workbook.save(output_path)
        else:
            raise ValueError(f"Unsupported spreadsheet target: {target}")
    elif source == "xlsx":
        workbook = load_workbook(input_path, read_only=True, data_only=True)
        sheet = workbook.active
        if target == "csv":
            with output_path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(sheet.iter_rows(values_only=True))
        elif target == "tsv":
            with output_path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle, delimiter="\t").writerows(sheet.iter_rows(values_only=True))
        else:
            raise ValueError(f"Unsupported spreadsheet target: {target}")
    else:
        raise ValueError(f"Unsupported spreadsheet source: {source}")
    return {"source": source, "target": target}

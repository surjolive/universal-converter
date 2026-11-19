from io import BytesIO
from pathlib import Path
import zipfile
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

import backend.main as backend_main
from backend.engines import archive_engine
from backend.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["product"] == "Universal Converter"


def test_formats():
    response = client.get("/api/formats")
    assert response.status_code == 200
    assert response.json()["routes"]


def test_engine_inventory_and_install_safety():
    response = client.get("/api/engines")
    assert response.status_code == 200
    payload = response.json()
    keys = {engine["key"] for engine in payload["engines"]}
    assert {"php", "libreoffice", "pandoc", "imagemagick", "poppler", "ffmpeg", "pillow"} <= keys
    assert payload["package_manager"]["name"] == "Windows Package Manager"

    unconfirmed = client.post("/api/engines/install/php")
    assert unconfirmed.status_code == 400
    unknown = client.post("/api/engines/install/arbitrary", headers={"X-UC-Install-Confirm": "yes"})
    assert unknown.status_code == 404


def test_engine_install_job_streams_progress_and_logs(monkeypatch):
    class FakeProcess:
        stdout = iter(("Downloading package 25%\n", "Installing package\n"))

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(backend_main.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    job_id = "test-winget-job"
    backend_main.INSTALL_JOBS[job_id] = {"id": job_id, "engine": "php", "status": "queued", "logs": []}
    try:
        backend_main._run_winget_install(job_id, "php", "winget")
        result = client.get(f"/api/engines/install-jobs/{job_id}")
        assert result.status_code == 200
        assert result.json()["status"] == "succeeded"
        assert result.json()["progress"] == 100
        assert "Downloading package 25%" in result.json()["logs"]
    finally:
        backend_main.INSTALL_JOBS.pop(job_id, None)


def test_image_conversion():
    source = BytesIO()
    Image.new("RGB", (32, 16), "blue").save(source, "PNG")
    response = client.post("/api/upload", files={"files": ("sample.png", source.getvalue(), "image/png")})
    assert response.status_code == 200
    upload_id = response.json()["files"][0]["id"]

    response = client.post("/api/convert", data={"upload_id": upload_id, "target": "jpg", "settings": '{"quality":90}'})
    assert response.status_code == 200
    conversion_id = response.json()["id"]

    download = client.get(f"/api/download/{conversion_id}")
    assert download.status_code == 200
    assert download.content[:2] == b"\xff\xd8"
    preview = client.get(f"/api/preview/{conversion_id}/file")
    assert preview.status_code == 200
    assert preview.headers["content-disposition"].startswith("inline")
    assert preview.headers["content-type"].startswith("image/jpeg")


def test_solid_background_removal_preserves_foreground():
    source = BytesIO()
    image = Image.new("RGB", (16, 16), "white")
    ImageDraw.Draw(image).rectangle((6, 6, 9, 9), fill="black")
    image.save(source, "PNG")
    uploaded = client.post("/api/upload", files={"files": ("logo.png", source.getvalue(), "image/png")})
    assert uploaded.status_code == 200
    upload_id = uploaded.json()["files"][0]["id"]

    conversion = client.post("/api/convert", data={
        "upload_id": upload_id,
        "target": "png",
        "settings": '{"remove_solid_background":true,"background_tolerance":0}',
    })
    assert conversion.status_code == 200, conversion.text
    download = client.get(conversion.json()["download_url"])
    assert download.status_code == 200
    with Image.open(BytesIO(download.content)) as output:
        assert output.mode == "RGBA"
        assert output.getpixel((0, 0))[3] == 0
        assert output.getpixel((8, 8)) == (0, 0, 0, 255)


def test_archive_extensions_and_roundtrips():
    response = client.post("/api/upload", files={"files": ("notes.txt", b"archive payload", "text/plain")})
    assert response.status_code == 200
    upload_id = response.json()["files"][0]["id"]

    outputs = {}
    for target in ("zip", "tar", "tar.gz", "gz"):
        conversion = client.post("/api/convert", data={
            "upload_id": upload_id, "target": target, "original_filename": "notes.txt", "settings": '{}'
        })
        assert conversion.status_code == 200, conversion.text
        downloaded = client.get(conversion.json()["download_url"])
        assert downloaded.status_code == 200
        assert f"notes.{target}" in downloaded.headers["content-disposition"]
        outputs[target] = downloaded.content

    assert outputs["zip"].startswith(b"PK")
    assert outputs["tar"][257:262] == b"ustar"
    assert outputs["tar.gz"].startswith(b"\x1f\x8b")
    assert outputs["gz"].startswith(b"\x1f\x8b")

    tar_gz_upload = client.post("/api/upload", files={"files": ("bundle.tar.gz", outputs["tar.gz"], "application/gzip")})
    assert tar_gz_upload.status_code == 200, tar_gz_upload.text
    assert tar_gz_upload.json()["files"][0]["extension"] == "tar.gz"
    tgz_upload = client.post("/api/upload", files={"files": ("bundle.tgz", outputs["tar.gz"], "application/x-gzip")})
    assert tgz_upload.status_code == 200, tgz_upload.text
    assert tgz_upload.json()["files"][0]["extension"] == "tar.gz"
    repack = client.post("/api/convert", data={
        "upload_id": tar_gz_upload.json()["files"][0]["id"],
        "target": "zip", "original_filename": "bundle.tar.gz", "settings": '{}'
    })
    assert repack.status_code == 200, repack.text
    listing = client.get(f"/api/preview/{repack.json()['id']}")
    assert listing.status_code == 200
    assert listing.json()["content"] == ["notes.txt"]

    zip_upload = client.post("/api/upload", files={"files": ("bundle.zip", outputs["zip"], "application/zip")})
    assert zip_upload.status_code == 200
    zip_repack = client.post("/api/convert", data={
        "upload_id": zip_upload.json()["files"][0]["id"],
        "target": "zip", "original_filename": "bundle.zip", "settings": '{}'
    })
    assert zip_repack.status_code == 200, zip_repack.text
    zip_listing = client.get(f"/api/preview/{zip_repack.json()['id']}")
    assert zip_listing.json()["content"] == ["notes.txt"]


def test_zip_to_rar_uses_winrar_and_supports_preview(tmp_path, monkeypatch):
    source = tmp_path / "bundle.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("folder/notes.txt", "archive payload")
    output = tmp_path / "bundle.rar"

    def fake_run(command, **kwargs):
        if command[1] == "a":
            assert command[2:4] == ["-idq", "--"]
            assert Path(kwargs["cwd"], "folder/notes.txt").read_text() == "archive payload"
            Path(command[4]).write_bytes(b"mock RAR archive")
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        assert command[1] == "lb"
        return type("Result", (), {"returncode": 0, "stdout": "folder/notes.txt\n", "stderr": ""})()

    monkeypatch.setattr(archive_engine, "_rar_binary", lambda: "rar")
    monkeypatch.setattr(archive_engine.subprocess, "run", fake_run)

    metadata = archive_engine.convert_archive(source, output, {
        "source_format": "zip", "target_format": "rar", "original_filename": "bundle.zip"
    })

    assert metadata == {"archive_files": 1, "source": "zip", "target": "rar"}
    assert output.read_bytes() == b"mock RAR archive"
    assert archive_engine.archive_members(output, "rar") == ["folder/notes.txt"]


def test_archive_path_traversal_is_rejected():
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../outside.txt", "must not escape")
    response = client.post("/api/upload", files={"files": ("unsafe.zip", archive.getvalue(), "application/zip")})
    assert response.status_code == 200

    conversion = client.post("/api/convert", data={
        "upload_id": response.json()["files"][0]["id"], "target": "tar", "settings": '{}'
    })
    assert conversion.status_code == 500
    assert "path traversal" in conversion.json()["detail"].lower()


def test_rejects_mislabeled_file():
    response = client.post("/api/upload", files={"files": ("fake.png", b"not an image", "image/png")})
    assert response.status_code == 400


def test_accepts_legacy_encoded_php_source():
    response = client.post("/api/upload", files={"files": ("legacy.php", b"<?php echo \xff; ?>", "application/x-httpd-php")})
    assert response.status_code == 200


def test_text_to_pdf_conversion():
    response = client.post("/api/upload", files={"files": ("notes.txt", b"Offline conversion test", "text/plain")})
    assert response.status_code == 200
    upload_id = response.json()["files"][0]["id"]

    response = client.post("/api/convert", data={"upload_id": upload_id, "target": "pdf", "settings": '{}'})
    assert response.status_code == 200
    download = client.get(f"/api/download/{response.json()['id']}")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")


def test_json_to_yaml_conversion():
    response = client.post("/api/upload", files={"files": ("data.json", b'{"name":"UC","offline":true}', "application/json")})
    assert response.status_code == 200
    upload_id = response.json()["files"][0]["id"]

    response = client.post("/api/convert", data={"upload_id": upload_id, "target": "yaml", "settings": '{}'})
    assert response.status_code == 200
    download = client.get(f"/api/download/{response.json()['id']}")
    assert download.status_code == 200
    assert b"offline: true" in download.content


def test_mislabeled_php_pdf_converts_to_html_and_pdf():
    source = BytesIO()
    document = canvas.Canvas(source)
    document.drawString(72, 720, "Generated PDF fixture")
    document.save()
    response = client.post("/api/upload", files={"files": ("sample.php", source.getvalue(), "application/octet-stream")})
    assert response.status_code == 200
    upload = response.json()["files"][0]
    assert upload["extension"] == "pdf"

    html = client.post("/api/convert", data={"upload_id": upload["id"], "target": "html", "settings": '{}'})
    assert html.status_code == 200
    html_download = client.get(f"/api/download/{html.json()['id']}")
    assert html_download.status_code == 200
    assert b"<!doctype html>" in html_download.content.lower()
    html_preview = client.get(f"/api/preview/{html.json()['id']}/file")
    assert html_preview.status_code == 200
    assert html_preview.headers["content-disposition"].startswith("inline")
    assert "script-src 'none'" in html_preview.headers["content-security-policy"]

    pdf = client.post("/api/convert", data={"upload_id": upload["id"], "target": "pdf", "settings": '{}'})
    assert pdf.status_code == 200
    pdf_download = client.get(f"/api/download/{pdf.json()['id']}")
    assert pdf_download.status_code == 200
    assert pdf_download.content.startswith(b"%PDF-")


def test_advanced_settings_cleanup_diagnostics_and_export():
    settings = client.put("/api/settings", json={"max_upload_size": 104857600, "worker_count": 4, "cleanup_days": 30, "cleanup_enabled": True, "api_key": ""})
    assert settings.status_code == 200
    assert settings.json()["worker_count"] == 4

    current = client.get("/api/settings")
    assert current.status_code == 200
    assert current.json()["max_upload_size"] == 104857600

    diagnostics = client.get("/api/settings/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["product"] == "Universal Converter"

    cleanup = client.post("/api/settings/cleanup")
    assert cleanup.status_code == 200

    csv_export = client.get("/api/history/export?format=csv")
    json_export = client.get("/api/history/export?format=json")
    assert csv_export.status_code == 200
    assert csv_export.json()["format"] == "csv"
    assert json_export.status_code == 200
    assert json_export.json()["format"] == "json"


def test_host_upload_list_preview_and_delete():
    response = client.post("/api/host/upload", files={"files": ("app.html", b"<!doctype html><title>Hosted</title><h1>Offline App</h1>", "text/html")})
    assert response.status_code == 200
    filename = response.json()["files"][0]["filename"]

    listing = client.get("/api/host/files")
    assert listing.status_code == 200
    assert any(item["filename"] == filename for item in listing.json()["files"])

    deletion = client.delete(f"/api/host/files/{filename}")
    assert deletion.status_code == 200


def test_preview_endpoint_for_pdf_and_text():
    text_upload = client.post("/api/upload", files={"files": ("preview.txt", b"Preview body", "text/plain")})
    assert text_upload.status_code == 200
    text_id = text_upload.json()["files"][0]["id"]
    text_conversion = client.post("/api/convert", data={"upload_id": text_id, "target": "pdf", "settings": '{}'})
    assert text_conversion.status_code == 200

    pdf_preview = client.get(f"/api/preview/{text_conversion.json()['id']}")
    assert pdf_preview.status_code == 200
    assert pdf_preview.json()["kind"] == "pdf"

    conversion_id = text_conversion.json()["id"]
    inline_file = client.get(f"/api/preview/{conversion_id}/file")
    download_file = client.get(f"/api/download/{conversion_id}")
    assert inline_file.status_code == 200
    assert inline_file.headers["content-disposition"].startswith("inline")
    assert inline_file.headers["content-type"].startswith("application/pdf")
    assert inline_file.content.startswith(b"%PDF-")
    assert download_file.headers["content-disposition"].startswith("attachment")


def test_source_translation_is_not_advertised():
    response = client.post("/api/upload", files={"files": ("sample.py", b"print('offline')", "text/x-python")})
    assert response.status_code == 200
    upload_id = response.json()["files"][0]["id"]

    response = client.post("/api/convert", data={"upload_id": upload_id, "target": "js", "settings": '{}'})
    assert response.status_code == 422

import importlib
import json

from fastapi.testclient import TestClient


def _build_client(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    firmware_dir = tmp_path / "firmware"
    config_dir.mkdir()
    firmware_dir.mkdir()

    binary_path = firmware_dir / "esp32-sensor-v1.bin"
    elf_path = firmware_dir / "esp32-sensor-v1.elf"
    binary_path.write_bytes(b"sensor-binary-payload")
    elf_path.write_bytes(b"sensor-elf-payload")

    config_path = config_dir / "firmware.jsonl"
    config_path.write_text(
        json.dumps(
            {
                "id": "esp32-sensor-v1",
                "name": "ESP32 Sensor v1",
                "version": "1.0.0",
                "device_family": "esp32",
                "description": "Main sensor firmware",
                "binary_path": "esp32-sensor-v1.bin",
                "elf_path": "esp32-sensor-v1.elf",
                "enabled": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("APP_TITLE", "Test Catalog")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_PORT", "8013")
    monkeypatch.setenv("APP_LOG_LEVEL", "INFO")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_PROTECTED_USERNAME", "admin")
    monkeypatch.setenv("APP_PROTECTED_PASSWORD", "change-me")
    monkeypatch.setenv("APP_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("APP_FIRMWARE_ROOT", str(firmware_dir))
    monkeypatch.delenv("APP_PROTECTED_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("APP_PASSWORD_SALT", "test-salt")

    import app.main as app_module
    import app.config as config_module

    importlib.reload(config_module)
    importlib.reload(app_module)
    return TestClient(app_module.app), config_path, firmware_dir


def test_healthcheck(tmp_path, monkeypatch):
    client, _, _ = _build_client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "Test Catalog"}


def test_public_catalog_and_detail_page(tmp_path, monkeypatch):
    client, _, _ = _build_client(tmp_path, monkeypatch)

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "ESP32 Sensor v1" in index_response.text

    detail_response = client.get("/firmware/esp32-sensor-v1")
    assert detail_response.status_code == 200
    assert "ESP32 Sensor v1" in detail_response.text


def test_protected_download_requires_auth_for_elf_only(tmp_path, monkeypatch):
    client, _, firmware_dir = _build_client(tmp_path, monkeypatch)

    public_response = client.get("/download/esp32-sensor-v1/bin")
    assert public_response.status_code == 200
    assert public_response.content == (firmware_dir / "esp32-sensor-v1.bin").read_bytes()

    protected_response = client.get("/protected/download/esp32-sensor-v1/elf")
    assert protected_response.status_code == 401

    auth_response = client.get("/protected/download/esp32-sensor-v1/elf", auth=("admin", "change-me"))
    assert auth_response.status_code == 200
    assert auth_response.content == (firmware_dir / "esp32-sensor-v1.elf").read_bytes()


def test_upload_firmware_requires_auth_and_persists_metadata(tmp_path, monkeypatch):
    client, config_path, firmware_dir = _build_client(tmp_path, monkeypatch)

    upload_response = client.post(
        "/admin/upload",
        data={
            "name": "ESP32 Sensor v2",
            "version": "2.0.0",
            "device_family": "esp32",
            "description": "Second generation sensor",
        },
        files={
            "binary_file": ("esp32-sensor-v2.bin", b"new-binary-data", "application/octet-stream"),
            "elf_file": ("esp32-sensor-v2.elf", b"new-elf-data", "application/octet-stream"),
        },
    )
    assert upload_response.status_code == 401

    authenticated_response = client.post(
        "/admin/upload",
        data={
            "name": "ESP32 Sensor v2",
            "version": "2.0.0",
            "device_family": "esp32",
            "description": "Second generation sensor",
        },
        files={
            "binary_file": ("esp32-sensor-v2.bin", b"new-binary-data", "application/octet-stream"),
            "elf_file": ("esp32-sensor-v2.elf", b"new-elf-data", "application/octet-stream"),
        },
        auth=("admin", "change-me"),
        follow_redirects=False,
    )
    assert authenticated_response.status_code == 303
    assert "/firmware/" in authenticated_response.headers["location"]

    lines = config_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    uploaded_entry = json.loads(lines[-1])
    assert uploaded_entry["name"] == "ESP32 Sensor v2"
    assert uploaded_entry["version"] == "2.0.0"
    assert (firmware_dir / "esp32-sensor-v2.bin").exists()
    assert (firmware_dir / "esp32-sensor-v2.elf").exists()

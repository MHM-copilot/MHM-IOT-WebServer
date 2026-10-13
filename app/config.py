from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def get_settings() -> dict[str, Any]:
    project_root = Path(__file__).resolve().parent.parent
    config_path = os.getenv("APP_CONFIG_PATH", "config/firmware.jsonl")
    firmware_root = os.getenv("APP_FIRMWARE_ROOT", "firmware")

    if not Path(config_path).is_absolute():
        config_path = str(project_root / config_path)
    if not Path(firmware_root).is_absolute():
        firmware_root = str(project_root / firmware_root)

    return {
        "app_title": os.getenv("APP_TITLE", "MHM IoT Firmware Catalog"),
        "host": os.getenv("APP_HOST", "0.0.0.0"),
        "port": int(os.getenv("APP_PORT", "8000")),
        "log_level": os.getenv("APP_LOG_LEVEL", "INFO"),
        "secret_key": os.getenv("APP_SECRET_KEY", "change-me"),
        "protected_username": os.getenv("APP_PROTECTED_USERNAME", "admin"),
        "protected_password": os.getenv("APP_PROTECTED_PASSWORD", "change-me"),
        "config_path": Path(config_path),
        "firmware_root": Path(firmware_root),
    }


def _safe_path(base_dir: Path, raw_path: str | None) -> Path:
    if not raw_path:
        return base_dir

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _normalize_entry(raw_entry: dict[str, Any], firmware_root: Path) -> dict[str, Any]:
    entry = dict(raw_entry)
    entry.setdefault("id", entry.get("name", "firmware").strip().lower().replace(" ", "-"))
    entry.setdefault("name", entry["id"])
    entry.setdefault("version", "unknown")
    entry.setdefault("device_family", "generic")
    entry.setdefault("description", "")
    entry.setdefault("enabled", True)

    binary_path = _safe_path(firmware_root, str(entry.get("binary_path") or "")).resolve()
    elf_path = _safe_path(firmware_root, str(entry.get("elf_path") or "")).resolve()

    entry["binary_path"] = str(binary_path)
    entry["elf_path"] = str(elf_path)
    entry["binary_exists"] = binary_path.exists()
    entry["elf_exists"] = elf_path.exists()
    entry["enabled"] = bool(entry.get("enabled", True))
    return entry


def load_firmware_entries(config_path: Path | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    config_file = config_path or settings["config_path"]
    firmware_root = settings["firmware_root"]

    if not config_file.exists():
        return []

    entries: list[dict[str, Any]] = []
    with config_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                raw_entry = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover - validation path
                raise ValueError(f"Invalid JSON entry in {config_file}: {exc}") from exc

            if not isinstance(raw_entry, dict):
                continue

            entry = _normalize_entry(raw_entry, firmware_root)
            if entry.get("enabled"):
                entries.append(entry)

    return entries

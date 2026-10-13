from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
import secrets

from app.config import get_settings, load_firmware_entries

settings = get_settings()
app = FastAPI(title=settings["app_title"])
security = HTTPBasic()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def get_firmware_by_id(firmware_id: str) -> dict | None:
    for entry in load_firmware_entries():
        if entry.get("id") == firmware_id:
            return entry
    return None


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected_username = settings["protected_username"]
    expected_password = settings["protected_password"]

    is_valid_user = secrets.compare_digest(credentials.username, expected_username)
    is_valid_password = secrets.compare_digest(credentials.password, expected_password)

    if not (is_valid_user and is_valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm='Firmware access'"},
        )
    return credentials.username


@app.get("/")
async def index(request: Request):
    entries = load_firmware_entries()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": settings["app_title"],
            "entries": entries,
        },
    )


@app.get("/firmware/{firmware_id}")
async def firmware_detail(request: Request, firmware_id: str):
    entry = get_firmware_by_id(firmware_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Firmware not found")

    return templates.TemplateResponse(
        "firmware_detail.html",
        {
            "request": request,
            "title": settings["app_title"],
            "entry": entry,
        },
    )


@app.get("/protected/download/{firmware_id}/{artifact}")
async def protected_download(
    firmware_id: str,
    artifact: str,
    username: str = Depends(verify_credentials),
):
    entry = get_firmware_by_id(firmware_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Firmware not found")

    artifact_key = artifact.lower()
    if artifact_key == "bin":
        file_path = Path(entry["binary_path"])
        filename = Path(file_path).name
    elif artifact_key == "elf":
        file_path = Path(entry["elf_path"])
        filename = Path(file_path).name
    else:
        raise HTTPException(status_code=400, detail="Artifact must be 'bin' or 'elf'")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_key}' not found")

    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        filename=filename,
    )


@app.get("/health")
async def healthcheck():
    return {"status": "ok", "app": settings["app_title"]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings["host"], port=settings["port"], log_level=settings["log_level"].lower())

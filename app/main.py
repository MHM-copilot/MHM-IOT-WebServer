from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app.config import append_firmware_entry, get_settings, load_firmware_entries

settings = get_settings()
app = FastAPI(title=settings["app_title"])
security = HTTPBasic()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
ALLOWED_EXTENSIONS = {".bin": "binary", ".elf": "elf"}


def _derive_password_hash(password: str) -> str:
    salt = settings["password_salt"].encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return digest.hex()


def verify_password(password: str) -> bool:
    configured_hash = settings["protected_password_hash"].strip()
    if configured_hash:
        return hmac.compare_digest(_derive_password_hash(password), configured_hash)
    return secrets.compare_digest(password, settings["protected_password"])


def get_firmware_by_id(firmware_id: str) -> dict | None:
    for entry in load_firmware_entries():
        if entry.get("id") == firmware_id:
            return entry
    return None


def _authorize_credentials(credentials: HTTPBasicCredentials | None) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm='Firmware access'"},
        )

    expected_username = settings["protected_username"]
    is_valid_user = secrets.compare_digest(credentials.username, expected_username)
    is_valid_password = verify_password(credentials.password)

    if not (is_valid_user and is_valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm='Firmware access'"},
        )
    return credentials.username


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    return _authorize_credentials(credentials)


def _slugify(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    sanitized = sanitized.strip("-_.")
    return (sanitized or "firmware").lower()


async def _save_uploaded_file(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    contents = await upload.read()
    with destination.open("wb") as handle:
        handle.write(contents)


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


@app.get("/admin/upload")
async def upload_form(request: Request, username: str = Depends(verify_credentials)):
    del username
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "title": settings["app_title"]},
    )


@app.post("/admin/upload")
async def upload_firmware(
    request: Request,
    name: str = Form(...),
    version: str = Form("unknown"),
    device_family: str = Form("generic"),
    description: str = Form(""),
    binary_file: UploadFile = File(...),
    elf_file: UploadFile = File(...),
    username: str = Depends(verify_credentials),
):
    del username

    binary_name = (binary_file.filename or "").lower()
    elf_name = (elf_file.filename or "").lower()

    if not binary_name.endswith(".bin"):
        raise HTTPException(status_code=400, detail="Binary upload must include a .bin file")
    if not elf_name.endswith(".elf"):
        raise HTTPException(status_code=400, detail="ELF upload must include a .elf file")

    base_name = _slugify(name)
    binary_path = settings["firmware_root"] / f"{base_name}.bin"
    elf_path = settings["firmware_root"] / f"{base_name}.elf"

    await _save_uploaded_file(binary_file, binary_path)
    await _save_uploaded_file(elf_file, elf_path)

    firmware_id = _slugify(f"{name}-{version}")
    entry = {
        "id": firmware_id,
        "name": name,
        "version": version,
        "device_family": device_family,
        "description": description,
        "binary_path": str(binary_path),
        "elf_path": str(elf_path),
        "enabled": True,
    }
    append_firmware_entry(entry)

    return RedirectResponse(url=f"/firmware/{firmware_id}", status_code=status.HTTP_303_SEE_OTHER)


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


def _serve_firmware_artifact(entry: dict, artifact_key: str, require_auth: bool, credentials: HTTPBasicCredentials | None = None) -> FileResponse:
    if artifact_key == "bin":
        file_path = Path(entry["binary_path"])
    elif artifact_key == "elf":
        if require_auth:
            _authorize_credentials(credentials)
        file_path = Path(entry["elf_path"])
    else:
        raise HTTPException(status_code=400, detail="Artifact must be 'bin' or 'elf'")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_key}' not found")

    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        filename=Path(file_path).name,
    )


@app.get("/download/{firmware_id}/bin")
async def public_download_bin(firmware_id: str):
    entry = get_firmware_by_id(firmware_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Firmware not found")
    return _serve_firmware_artifact(entry, "bin", require_auth=False)


@app.get("/protected/download/{firmware_id}/elf")
async def protected_download_elf(
    firmware_id: str,
    credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False)),
):
    entry = get_firmware_by_id(firmware_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Firmware not found")
    return _serve_firmware_artifact(entry, "elf", require_auth=True, credentials=credentials)


@app.get("/protected/download/{firmware_id}/{artifact}")
async def legacy_download(
    firmware_id: str,
    artifact: str,
    credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False)),
):
    entry = get_firmware_by_id(firmware_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Firmware not found")
    artifact_key = artifact.lower()
    if artifact_key == "bin":
        return RedirectResponse(url=f"/download/{firmware_id}/bin", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    if artifact_key == "elf":
        return _serve_firmware_artifact(entry, "elf", require_auth=True, credentials=credentials)
    raise HTTPException(status_code=400, detail="Artifact must be 'bin' or 'elf'")


@app.get("/health")
async def healthcheck():
    return {"status": "ok", "app": settings["app_title"]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings["host"], port=settings["port"], log_level=settings["log_level"].lower())

"""Final exam project platform backend.

This backend is intentionally separate from the general teaching backend.
It gives each student one project space, lets the student define virtual
resources, and serves uploaded static sites for peer review.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException


BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_STUDENTS_FILE = BASE_DIR / "final_students.json"
DEFAULT_TEACHER_KEY = "123456"
ADMIN_USERNAME = "admin"
ADMIN_COOKIE_NAME = "final_admin_session"
STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
RESOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ACCESS_MODES = {"public_read", "public_submit", "private_collect"}
MAX_JSON_BODY_BYTES = int(os.getenv("FINAL_BACKEND_MAX_JSON_BODY_BYTES", str(32 * 1024)))
MAX_STRING_LENGTH = int(os.getenv("FINAL_BACKEND_MAX_STRING_LENGTH", "2000"))
PUBLIC_POST_WINDOW_SECONDS = int(os.getenv("FINAL_BACKEND_PUBLIC_POST_WINDOW_SECONDS", "60"))
PUBLIC_POST_IP_PER_WINDOW = int(os.getenv("FINAL_BACKEND_PUBLIC_POST_IP_PER_WINDOW", "20"))
PUBLIC_POST_SPACE_PER_WINDOW = int(os.getenv("FINAL_BACKEND_PUBLIC_POST_SPACE_PER_WINDOW", "120"))
MAX_RECORDS_PER_SPACE = int(os.getenv("FINAL_BACKEND_MAX_RECORDS_PER_SPACE", "5000"))
MAX_RECORDS_PER_RESOURCE = int(os.getenv("FINAL_BACKEND_MAX_RECORDS_PER_RESOURCE", "1000"))
DEFAULT_PAGE_SIZE = int(os.getenv("FINAL_BACKEND_DEFAULT_PAGE_SIZE", "20"))
MAX_PAGE_SIZE = int(os.getenv("FINAL_BACKEND_MAX_PAGE_SIZE", "50"))
MAX_SITE_ZIP_SIZE = int(os.getenv("FINAL_BACKEND_MAX_SITE_ZIP_SIZE", str(10 * 1024 * 1024)))
MAX_SITE_TOTAL_SIZE = int(os.getenv("FINAL_BACKEND_MAX_SITE_TOTAL_SIZE", str(30 * 1024 * 1024)))
MAX_SITE_FILE_COUNT = int(os.getenv("FINAL_BACKEND_MAX_SITE_FILE_COUNT", "300"))
MAX_STUDENT_FILE_COUNT = int(os.getenv("FINAL_BACKEND_MAX_STUDENT_FILE_COUNT", "100"))
MAX_STUDENT_FILE_TOTAL_BYTES = int(os.getenv("FINAL_BACKEND_MAX_STUDENT_FILE_TOTAL_BYTES", str(50 * 1024 * 1024)))
MAX_IMAGE_FILE_BYTES = int(os.getenv("FINAL_BACKEND_MAX_IMAGE_FILE_BYTES", str(2 * 1024 * 1024)))
MAX_PDF_FILE_BYTES = int(os.getenv("FINAL_BACKEND_MAX_PDF_FILE_BYTES", str(5 * 1024 * 1024)))
MAX_AUDIO_FILE_BYTES = int(os.getenv("FINAL_BACKEND_MAX_AUDIO_FILE_BYTES", str(5 * 1024 * 1024)))
MAX_VIDEO_FILE_BYTES = int(os.getenv("FINAL_BACKEND_MAX_VIDEO_FILE_BYTES", str(20 * 1024 * 1024)))
UPLOAD_CHUNK_BYTES = int(os.getenv("FINAL_BACKEND_UPLOAD_CHUNK_BYTES", str(1024 * 1024)))
ADMIN_SESSION_SECONDS = int(os.getenv("FINAL_BACKEND_ADMIN_SESSION_SECONDS", str(8 * 60 * 60)))
STUDENT_SESSION_SECONDS = int(os.getenv("FINAL_BACKEND_STUDENT_SESSION_SECONDS", str(8 * 60 * 60)))
ADMIN_EXPORT_TOKEN_SECONDS = int(os.getenv("FINAL_BACKEND_ADMIN_EXPORT_TOKEN_SECONDS", "120"))
ALLOWED_SITE_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".json",
    ".txt",
    ".pdf",
    ".mp3",
    ".mp4",
    ".webm",
}
SITE_CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".ico": "image/x-icon",
}
FILE_KIND_EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
    "pdf": {".pdf"},
    "audio": {".mp3"},
    "video": {".mp4", ".webm"},
}
FILE_KIND_MAX_BYTES = {
    "image": MAX_IMAGE_FILE_BYTES,
    "pdf": MAX_PDF_FILE_BYTES,
    "audio": MAX_AUDIO_FILE_BYTES,
    "video": MAX_VIDEO_FILE_BYTES,
}


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    oldPassword: str = Field(..., min_length=1, max_length=200)
    newPassword: str = Field(..., min_length=6, max_length=200)


class StudentCreateIn(BaseModel):
    studentId: str = Field(..., min_length=1, max_length=40)
    password: str | None = Field(default=None, min_length=1, max_length=200)
    displayName: str | None = Field(default=None, max_length=80)
    className: str | None = Field(default=None, max_length=80)
    enabled: bool = True
    note: str | None = Field(default=None, max_length=200)


class StudentUpdateIn(BaseModel):
    displayName: str | None = Field(default=None, max_length=80)
    className: str | None = Field(default=None, max_length=80)
    enabled: bool | None = None
    note: str | None = Field(default=None, max_length=200)


class ResetPasswordIn(BaseModel):
    password: str | None = Field(default=None, min_length=1, max_length=200)


class ResourceCreateIn(BaseModel):
    resourceName: str = Field(..., min_length=1, max_length=40)
    displayName: str | None = Field(default=None, max_length=80)
    accessMode: str = Field(..., min_length=1, max_length=40)


class ResourceUpdateIn(BaseModel):
    displayName: str | None = Field(default=None, max_length=80)
    accessMode: str | None = Field(default=None, min_length=1, max_length=40)


class AdminExportTokenIn(BaseModel):
    studentId: str | None = Field(default=None, max_length=40)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success_response(message: str = "OK", data: Any = None) -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def error_payload(message: str, data: Any = None) -> dict[str, Any]:
    return {"success": False, "message": message, "data": data}


class NonMultipartBodySizeLimitMiddleware:
    def __init__(self, app: Any, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max(1, int(max_body_bytes))

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method", "").upper() not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_type = headers.get(b"content-type", b"").decode("latin1").lower()
        if content_type.startswith("multipart/form-data"):
            await self.app(scope, receive, send)
            return

        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length.decode("latin1")) > self.max_body_bytes:
                    await self._send_too_large(send)
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise HTTPException(status_code=413, detail="请求体过大")
            return message

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except HTTPException as exc:
            if exc.status_code == 413 and not response_started:
                await self._send_too_large(send)
                return
            raise

    async def _send_too_large(self, send: Any) -> None:
        body = json.dumps(error_payload("请求体过大"), ensure_ascii=False).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def env_text(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = env_text(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def normalize_root_path(value: str | None) -> str:
    root_path = (value or "").strip()
    if not root_path or root_path == "/":
        return ""
    if not root_path.startswith("/"):
        root_path = "/" + root_path
    return root_path.rstrip("/")


def normalize_base_url(value: str | None) -> str:
    base_url = (value or "").strip()
    if not base_url:
        return ""
    return base_url.rstrip("/")


def join_public_url(base_url: str, path: str) -> str:
    clean_path = "/" + (path or "").lstrip("/")
    if clean_path == "/":
        return base_url or "/"
    if base_url:
        return base_url.rstrip("/") + clean_path
    return clean_path


def split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def origin_from_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def host_from_value(value: str | None) -> str:
    raw = (value or "").split(",", 1)[0].strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or "").lower()


def is_loopback_host(value: str) -> bool:
    host = host_from_value(value) or (value or "").strip().lower().strip("[]")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_student_id(value: str, label: str = "studentId") -> str:
    student_id = str(value or "").strip()
    if not STUDENT_ID_PATTERN.fullmatch(student_id):
        raise HTTPException(status_code=400, detail=f"{label} 只允许字母、数字、下划线和中划线，长度 1-40")
    return student_id


def validate_resource_name(value: str, label: str = "resourceName") -> str:
    resource_name = str(value or "").strip()
    if not RESOURCE_NAME_PATTERN.fullmatch(resource_name):
        raise HTTPException(status_code=400, detail=f"{label} 只允许字母、数字、下划线和中划线，长度 1-40")
    if resource_name in {"auth", "admin", "student", "resources"}:
        raise HTTPException(status_code=400, detail="该资源名为系统保留名称")
    return resource_name


def validate_file_id(value: str, label: str = "fileId") -> str:
    file_id = str(value or "").strip()
    if not FILE_ID_PATTERN.fullmatch(file_id):
        raise HTTPException(status_code=400, detail=f"{label} 只允许字母、数字、下划线和中划线，长度 1-80")
    return file_id


def validate_access_mode(value: str) -> str:
    access_mode = str(value or "").strip()
    if access_mode not in ACCESS_MODES:
        raise HTTPException(status_code=400, detail="accessMode 只能是 public_read、public_submit 或 private_collect")
    return access_mode


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    digest, _salt = hash_password(password, salt)
    return secrets.compare_digest(digest, password_hash)


def generate_password() -> str:
    return secrets.token_urlsafe(8)


def make_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def content_disposition_header(disposition: str, filename: str) -> str:
    safe = Path(filename or "download.json").name.replace('"', "").replace("\r", "").replace("\n", "")
    fallback = "".join(char if 32 <= ord(char) < 127 else "_" for char in safe) or "download.json"
    encoded = quote(safe, safe="")
    return f'{disposition}; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


def site_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SITE_CONTENT_TYPES:
        return SITE_CONTENT_TYPES[suffix]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def json_response_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def sanitize_student(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("password_hash", None)
    item.pop("password_salt", None)
    return {
        "studentId": item.get("student_id"),
        "displayName": item.get("display_name"),
        "className": item.get("class_name"),
        "enabled": bool(item.get("enabled")),
        "note": item.get("note") or "",
        "mustChangePassword": bool(item.get("password_is_initial", 0)),
        "passwordUpdatedAt": item.get("password_updated_at") or "",
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
    }


def decode_record(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "resourceName": row["resource_name"],
        "data": payload,
        "createdByRole": row["created_by_role"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def normalize_payload_strings(value: Any, path: str = "data") -> Any:
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise HTTPException(status_code=400, detail=f"{path} 字符串过长，最多 {MAX_STRING_LENGTH} 个字符")
        return value
    if isinstance(value, list):
        return [normalize_payload_strings(item, f"{path}[]") for item in value]
    if isinstance(value, dict):
        return {
            str(key): normalize_payload_strings(item, f"{path}.{key}")
            for key, item in value.items()
        }
    return value


async def read_json_object(request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > request.app.state.max_json_body_bytes:
        raise HTTPException(status_code=413, detail="请求体过大")
    try:
        value = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象") from None
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    return normalize_payload_strings(value)


def create_app(data_dir: str | Path | None = None, root_path: str | None = None) -> FastAPI:
    data_path = Path(data_dir or env_text("FINAL_BACKEND_DATA_DIR") or DEFAULT_DATA_DIR).resolve()
    db_path = data_path / "final_exam.sqlite3"
    sites_path = data_path / "sites"
    files_path = data_path / "files"
    backups_path = data_path / "backups"
    tmp_path = data_path / "tmp"
    root_path = normalize_root_path(root_path if root_path is not None else env_text("FINAL_BACKEND_ROOT_PATH"))
    public_base_url = normalize_base_url(env_text("FINAL_BACKEND_PUBLIC_BASE_URL")) or root_path
    site_base_url = normalize_base_url(env_text("FINAL_BACKEND_SITE_BASE_URL"))
    admin_password = env_text("FINAL_BACKEND_ADMIN_PASSWORD") or generate_password()
    cookie_secure = env_bool("FINAL_BACKEND_COOKIE_SECURE", False)
    enable_cors = env_bool("FINAL_BACKEND_ENABLE_CORS", True)
    teacher_key_enabled = env_bool("FINAL_BACKEND_ENABLE_TEACHER_KEY", False)
    teacher_key = env_text("FINAL_BACKEND_TEACHER_KEY") or DEFAULT_TEACHER_KEY
    require_custom_teacher_key = env_bool("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", False)
    if teacher_key_enabled and require_custom_teacher_key and teacher_key == DEFAULT_TEACHER_KEY:
        raise RuntimeError("线上模式要求设置 FINAL_BACKEND_TEACHER_KEY，不能使用默认教师密钥 123456。")
    login_rate_limit_enabled = env_bool("FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED", True)
    login_failure_limit = max(1, env_int("FINAL_BACKEND_LOGIN_FAILURE_LIMIT", 5))
    login_failure_window_seconds = max(1, env_int("FINAL_BACKEND_LOGIN_FAILURE_WINDOW_SECONDS", 5 * 60))
    login_lock_seconds = max(1, env_int("FINAL_BACKEND_LOGIN_LOCK_SECONDS", 5 * 60))
    max_json_body_bytes = max(1, env_int("FINAL_BACKEND_MAX_JSON_BODY_BYTES", MAX_JSON_BODY_BYTES))
    site_sandbox_enabled = env_bool("FINAL_BACKEND_SITE_SANDBOX_ENABLED", False)
    trust_proxy_headers = env_bool("FINAL_BACKEND_TRUST_PROXY_HEADERS", False)
    backend_host = env_text("FINAL_BACKEND_HOST") or "127.0.0.1"
    require_separate_site_origin = env_bool("FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN", False)
    teacher_docs_enabled = env_bool("FINAL_BACKEND_ENABLE_TEACHER_DOCS", True)
    students_file = Path(env_text("FINAL_BACKEND_STUDENTS_FILE") or DEFAULT_STUDENTS_FILE).resolve()
    auto_sync_students = env_bool("FINAL_BACKEND_AUTO_SYNC_STUDENTS", False)
    public_origin = origin_from_url(public_base_url)
    site_origin = origin_from_url(site_base_url)
    public_host = host_from_value(public_base_url)
    site_host = host_from_value(site_base_url)
    if require_separate_site_origin:
        if not public_origin or not site_origin:
            raise RuntimeError("线上模式要求设置 FINAL_BACKEND_PUBLIC_BASE_URL 和 FINAL_BACKEND_SITE_BASE_URL。")
        if public_host == site_host:
            raise RuntimeError("线上模式要求学生作品 SITE_BASE_URL 与后台/API PUBLIC_BASE_URL 使用不同 hostname，不能只依赖不同端口或协议。")

    data_path.mkdir(parents=True, exist_ok=True)
    sites_path.mkdir(parents=True, exist_ok=True)
    files_path.mkdir(parents=True, exist_ok=True)
    backups_path.mkdir(parents=True, exist_ok=True)
    tmp_path.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="期末作品平台后端",
        version="0.1.0",
        root_path=root_path,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(NonMultipartBodySizeLimitMiddleware, max_body_bytes=max_json_body_bytes)

    cors_configured_origins = split_env_list(env_text("FINAL_BACKEND_CORS_ORIGINS"))
    cors_allow_origins = cors_configured_origins or ["*"]
    if enable_cors:
        allow_origins = list(cors_allow_origins)
        if cors_configured_origins:
            for origin in [site_origin, public_origin]:
                if origin and origin not in allow_origins:
                    allow_origins.append(origin)
        cors_allow_origins = allow_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.data_dir = data_path
    app.state.db_path = db_path
    app.state.sites_dir = sites_path
    app.state.files_dir = files_path
    app.state.backups_dir = backups_path
    app.state.tmp_dir = tmp_path
    app.state.backend_host = backend_host
    app.state.enable_cors = enable_cors
    app.state.cors_configured_origins = cors_configured_origins
    app.state.cors_allow_origins = cors_allow_origins
    app.state.root_path = root_path
    app.state.public_base_url = public_base_url
    app.state.site_base_url = site_base_url
    app.state.public_host = public_host
    app.state.site_host = site_host
    app.state.students_file = students_file
    app.state.auto_sync_students = auto_sync_students
    app.state.admin_password = admin_password
    app.state.admin_sessions: dict[str, float] = {}
    app.state.export_tokens: dict[str, tuple[float, str | None]] = {}
    app.state.login_failures: dict[str, list[float]] = {}
    app.state.login_locks: dict[str, float] = {}
    app.state.public_post_by_ip: dict[str, list[float]] = {}
    app.state.public_post_by_space: dict[str, list[float]] = {}
    app.state.public_post_ip_limit = PUBLIC_POST_IP_PER_WINDOW
    app.state.public_post_space_limit = PUBLIC_POST_SPACE_PER_WINDOW
    app.state.public_post_window_seconds = PUBLIC_POST_WINDOW_SECONDS
    app.state.max_json_body_bytes = max_json_body_bytes
    app.state.max_records_per_space = MAX_RECORDS_PER_SPACE
    app.state.max_records_per_resource = MAX_RECORDS_PER_RESOURCE
    app.state.default_page_size = max(1, DEFAULT_PAGE_SIZE)
    app.state.max_page_size = max(app.state.default_page_size, MAX_PAGE_SIZE)
    app.state.max_student_file_count = MAX_STUDENT_FILE_COUNT
    app.state.max_student_file_total_bytes = MAX_STUDENT_FILE_TOTAL_BYTES
    app.state.file_kind_max_bytes = dict(FILE_KIND_MAX_BYTES)
    app.state.upload_chunk_bytes = max(1024, UPLOAD_CHUNK_BYTES)
    app.state.login_rate_limit_enabled = login_rate_limit_enabled
    app.state.login_failure_limit = login_failure_limit
    app.state.login_failure_window_seconds = login_failure_window_seconds
    app.state.login_lock_seconds = login_lock_seconds
    app.state.site_sandbox_enabled = site_sandbox_enabled
    app.state.trust_proxy_headers = trust_proxy_headers
    app.state.require_separate_site_origin = require_separate_site_origin
    app.state.teacher_docs_enabled = teacher_docs_enabled

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def public_url(path: str) -> str:
        return join_public_url(public_base_url, path)

    def student_site_url(student_id: str) -> str:
        valid_id = validate_student_id(student_id)
        if site_base_url:
            return join_public_url(site_base_url, f"/{valid_id}/")
        return public_url(f"/sites/{valid_id}/")

    def student_api_base_url(student_id: str) -> str:
        return public_url(f"/api/{validate_student_id(student_id)}")

    def media_file_url(student_id: str, file_id: str, stored_name: str) -> str:
        valid_id = validate_student_id(student_id)
        valid_file_id = validate_file_id(file_id)
        safe_name = Path(stored_name or "file").name
        path = f"/media/{valid_id}/{valid_file_id}/{safe_name}"
        if site_base_url:
            return join_public_url(site_base_url, path)
        return public_url(path)

    def request_ip(request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        if app.state.trust_proxy_headers and forwarded_for:
            return forwarded_for
        return request.client.host if request.client else "unknown"

    def request_host(request: Request) -> str:
        forwarded_host = request.headers.get("X-Forwarded-Host") if app.state.trust_proxy_headers else ""
        return host_from_value(forwarded_host or request.headers.get("Host", ""))

    def student_site_path_url(student_id: str, file_path: str = "") -> str:
        valid_id = validate_student_id(student_id)
        clean_path = (file_path or "").strip("/")
        base = student_site_url(valid_id)
        if clean_path:
            return join_public_url(base, quote(clean_path, safe="/._-~"))
        return base

    def site_origin_redirect(request: Request, student_id: str, file_path: str = "") -> RedirectResponse | None:
        if not app.state.require_separate_site_origin:
            return None
        if request_host(request) == app.state.site_host:
            return None
        return RedirectResponse(student_site_path_url(student_id, file_path), status_code=308)

    def media_origin_redirect(request: Request, student_id: str, file_id: str, filename: str) -> RedirectResponse | None:
        if not app.state.require_separate_site_origin:
            return None
        if request_host(request) == app.state.site_host:
            return None
        return RedirectResponse(media_file_url(student_id, file_id, filename), status_code=308)

    def normalize_pagination(page: int, page_size: int) -> tuple[int, int, int]:
        if page < 1:
            raise HTTPException(status_code=400, detail="page 必须大于等于 1")
        if page_size < 1:
            raise HTTPException(status_code=400, detail="pageSize 必须大于等于 1")
        if page_size > app.state.max_page_size:
            raise HTTPException(status_code=400, detail=f"pageSize 不能超过 {app.state.max_page_size}")
        return page, page_size, (page - 1) * page_size

    def paginated_response(items: list[dict[str, Any]], total: int, page: int, page_size: int) -> dict[str, Any]:
        return {"items": items, "total": total, "page": page, "pageSize": page_size}

    def login_rate_key(kind: str, username: str, request: Request) -> str:
        return f"{kind}:{request_ip(request)}:{username.strip().lower()}"

    def ensure_login_allowed(kind: str, username: str, request: Request) -> None:
        if not app.state.login_rate_limit_enabled:
            return
        key = login_rate_key(kind, username, request)
        locked_until = app.state.login_locks.get(key, 0)
        now = time.time()
        if locked_until > now:
            raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")
        if locked_until:
            app.state.login_locks.pop(key, None)

    def record_login_failure(kind: str, username: str, request: Request) -> None:
        if not app.state.login_rate_limit_enabled:
            return
        key = login_rate_key(kind, username, request)
        now = time.time()
        window = app.state.login_failure_window_seconds
        events = [item for item in app.state.login_failures.get(key, []) if now - item < window]
        events.append(now)
        if len(events) >= app.state.login_failure_limit:
            app.state.login_locks[key] = now + app.state.login_lock_seconds
            app.state.login_failures[key] = []
            return
        app.state.login_failures[key] = events

    def clear_login_failures(kind: str, username: str, request: Request) -> None:
        if not app.state.login_rate_limit_enabled:
            return
        key = login_rate_key(kind, username, request)
        app.state.login_failures.pop(key, None)
        app.state.login_locks.pop(key, None)

    def init_db() -> None:
        with connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    student_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    initial_password_hash TEXT NOT NULL DEFAULT '',
                    initial_password_salt TEXT NOT NULL DEFAULT '',
                    password_is_initial INTEGER NOT NULL DEFAULT 1,
                    password_updated_at TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL,
                    class_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
            if "initial_password_hash" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN initial_password_hash TEXT NOT NULL DEFAULT ''")
            if "initial_password_salt" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN initial_password_salt TEXT NOT NULL DEFAULT ''")
            if "password_is_initial" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN password_is_initial INTEGER NOT NULL DEFAULT 1")
            if "password_updated_at" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN password_updated_at TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                UPDATE students
                SET initial_password_hash = password_hash
                WHERE initial_password_hash = ''
                """
            )
            conn.execute(
                """
                UPDATE students
                SET initial_password_salt = password_salt
                WHERE initial_password_salt = ''
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resources (
                    student_id TEXT NOT NULL,
                    resource_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    access_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(student_id, resource_name),
                    FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    resource_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_by_role TEXT NOT NULL,
                    created_ip TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(student_id, resource_name)
                        REFERENCES resources(student_id, resource_name) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    file_kind TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_audits (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    backup_path TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'admin',
                    created_ip TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_space ON records(student_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_resource ON records(student_id, resource_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_student ON files(student_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_audits_student ON admin_audits(student_id, created_at)")

    def get_student(student_id: str) -> sqlite3.Row | None:
        with connect() as conn:
            return conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()

    def load_students_from_file() -> list[dict[str, Any]]:
        source_file = app.state.students_file
        if not source_file.exists():
            raise RuntimeError(f"学生名单文件不存在：{source_file}")
        raw_students = json.loads(source_file.read_text(encoding="utf-8"))
        if not isinstance(raw_students, list):
            raise RuntimeError("学生名单文件必须是 JSON 数组")

        students = []
        seen_ids: set[str] = set()
        for raw in raw_students:
            if not isinstance(raw, dict):
                raise RuntimeError("学生名单中的每一项必须是对象")
            student_id = validate_student_id(raw.get("student_id") or raw.get("studentId") or "", "student_id")
            if student_id in seen_ids:
                raise RuntimeError(f"学生名单中存在重复学号：{student_id}")
            seen_ids.add(student_id)
            initial_password = str(
                raw.get("initial_password")
                or raw.get("initialPassword")
                or raw.get("password")
                or raw.get("code")
                or ""
            ).strip()
            if not initial_password:
                raise RuntimeError(f"学生名单中 {student_id} 缺少初始密码或 code")
            students.append(
                {
                    "student_id": student_id,
                    "initial_password": initial_password,
                    "display_name": str(raw.get("display_name") or raw.get("displayName") or student_id).strip() or student_id,
                    "class_name": str(raw.get("class_name") or raw.get("className") or "").strip(),
                    "enabled": bool(raw.get("enabled", True)),
                    "note": str(raw.get("note") or "").strip(),
                }
            )
        return students

    def initial_password_from_file(student_id: str) -> str | None:
        try:
            students = load_students_from_file()
        except RuntimeError:
            return None
        for student in students:
            if student["student_id"] == student_id:
                return student["initial_password"]
        return None

    def sync_students_from_file() -> dict[str, Any]:
        students = load_students_from_file()
        stamp = now_iso()
        inserted = 0
        updated = 0
        current_passwords_preserved = 0
        test_accounts = 0
        with connect() as conn:
            for student in students:
                if student["student_id"].startswith("test_ass45_"):
                    test_accounts += 1
                initial_hash, initial_salt = hash_password(student["initial_password"])
                row = conn.execute(
                    "SELECT * FROM students WHERE student_id = ?",
                    (student["student_id"],),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO students
                        (student_id, password_hash, password_salt, initial_password_hash, initial_password_salt,
                         password_is_initial, password_updated_at, display_name, class_name, enabled, note, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 1, '', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            student["student_id"],
                            initial_hash,
                            initial_salt,
                            initial_hash,
                            initial_salt,
                            student["display_name"],
                            student["class_name"],
                            1 if student["enabled"] else 0,
                            student["note"],
                            stamp,
                            stamp,
                        ),
                    )
                    inserted += 1
                    continue

                if bool(row["password_is_initial"]):
                    conn.execute(
                        """
                        UPDATE students
                        SET password_hash = ?,
                            password_salt = ?,
                            initial_password_hash = ?,
                            initial_password_salt = ?,
                            password_is_initial = 1,
                            password_updated_at = '',
                            display_name = ?,
                            class_name = ?,
                            enabled = ?,
                            note = ?,
                            updated_at = ?
                        WHERE student_id = ?
                        """,
                        (
                            initial_hash,
                            initial_salt,
                            initial_hash,
                            initial_salt,
                            student["display_name"],
                            student["class_name"],
                            1 if student["enabled"] else 0,
                            student["note"],
                            stamp,
                            student["student_id"],
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE students
                        SET initial_password_hash = ?,
                            initial_password_salt = ?,
                            display_name = ?,
                            class_name = ?,
                            enabled = ?,
                            note = ?,
                            updated_at = ?
                        WHERE student_id = ?
                        """,
                        (
                            initial_hash,
                            initial_salt,
                            student["display_name"],
                            student["class_name"],
                            1 if student["enabled"] else 0,
                            student["note"],
                            stamp,
                            student["student_id"],
                        ),
                    )
                    current_passwords_preserved += 1
                updated += 1
        return {
            "source": str(app.state.students_file),
            "totalInFile": len(students),
            "inserted": inserted,
            "updated": updated,
            "currentPasswordsPreserved": current_passwords_preserved,
            "testAccounts": test_accounts,
        }

    def create_student(payload: StudentCreateIn) -> dict[str, Any]:
        student_id = validate_student_id(payload.studentId)
        password = payload.password or generate_password()
        password_hash, password_salt = hash_password(password)
        stamp = now_iso()
        display_name = (payload.displayName or student_id).strip() or student_id
        class_name = (payload.className or "").strip()
        note = payload.note or ""
        with connect() as conn:
            exists = conn.execute("SELECT 1 FROM students WHERE student_id = ?", (student_id,)).fetchone()
            if exists is not None:
                raise HTTPException(status_code=409, detail="学生已存在，请使用修改资料或重置密码")
            conn.execute(
                """
                INSERT INTO students
                (student_id, password_hash, password_salt, initial_password_hash, initial_password_salt,
                 password_is_initial, password_updated_at, display_name, class_name, enabled, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, '', ?, ?, ?, ?, ?, ?)
                """,
                (
                    student_id,
                    password_hash,
                    password_salt,
                    password_hash,
                    password_salt,
                    display_name,
                    class_name,
                    1 if payload.enabled else 0,
                    note,
                    stamp,
                    stamp,
                ),
            )
        return {"studentId": student_id, "password": password, "mustChangePassword": True}

    def current_student_from_token(token: str) -> dict[str, Any] | None:
        now = time.time()
        with connect() as conn:
            row = conn.execute(
                """
                SELECT students.*
                FROM sessions
                JOIN students ON students.student_id = sessions.student_id
                WHERE sessions.token = ? AND sessions.expires_at > ?
                """,
                (token, now),
            ).fetchone()
        if row is None or not bool(row["enabled"]):
            return None
        return sanitize_student(row)

    def get_bearer_token(request: Request) -> str | None:
        value = request.headers.get("Authorization", "")
        if not value:
            return None
        parts = value.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise HTTPException(status_code=401, detail="Authorization 格式应为 Bearer token")
        return parts[1].strip()

    def require_student(request: Request) -> dict[str, Any]:
        token = get_bearer_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="请先登录")
        student = current_student_from_token(token)
        if student is None:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
        return student

    def optional_student(request: Request) -> dict[str, Any] | None:
        token = get_bearer_token(request)
        if not token:
            return None
        student = current_student_from_token(token)
        if student is None:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
        return student

    def require_space_owner(student_id: str, student: dict[str, Any]) -> None:
        if student.get("studentId") != student_id:
            raise HTTPException(status_code=403, detail="只能管理自己的作品空间")

    def is_teacher_key_valid(value: str) -> bool:
        if not teacher_key_enabled:
            return False
        if not teacher_key:
            return False
        return secrets.compare_digest(str(value or ""), teacher_key)

    def require_admin(request: Request, x_teacher_key: str = "") -> str:
        if is_teacher_key_valid(x_teacher_key):
            return "teacher-key"
        token = request.cookies.get(ADMIN_COOKIE_NAME, "")
        expires_at = app.state.admin_sessions.get(token)
        if token and expires_at and expires_at > time.time():
            return "cookie"
        if token:
            app.state.admin_sessions.pop(token, None)
        raise HTTPException(status_code=401, detail="请先访问 /admin 登录")

    def student_api_docs_html() -> str:
        api_config = public_url("/sites/你的学号/api-config.js")
        student_entry = public_url("/student")
        return f"""
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>期末作品学生接口说明</title>
          <style>
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; background: #f6f7f9; color: #17202a; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif; line-height: 1.7; }}
            main {{ max-width: 980px; margin: 0 auto; padding: 28px 18px 44px; }}
            h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.25; }}
            h2 {{ margin: 22px 0 10px; font-size: 20px; }}
            p {{ margin: 8px 0; }}
            .lead {{ color: #52606d; }}
            .card {{ margin-top: 14px; padding: 16px; background: #fff; border: 1px solid #dde2e8; border-radius: 8px; }}
            .card h2 {{ margin-top: 0; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: #fff; }}
            th, td {{ border: 1px solid #dde2e8; padding: 8px 10px; text-align: left; vertical-align: top; }}
            th {{ color: #52606d; background: #f8fafc; }}
            code {{ background: #f1f5f9; border-radius: 4px; padding: 2px 5px; }}
            pre {{ margin: 10px 0 0; padding: 12px; overflow: auto; border-radius: 6px; background: #111827; color: #f8fafc; line-height: 1.55; }}
            a {{ color: #1f6feb; }}
            .muted {{ color: #667085; }}
          </style>
        </head>
        <body>
          <main>
            <h1>期末作品学生接口说明</h1>
            <p class="lead">这个页面只列学生作品会用到的接口。教师管理、归档、清理等接口不在这里展示。</p>

            <section class="card">
              <h2>1. 先登录学生管理页</h2>
              <p>入口：<a href="{student_entry}">{student_entry}</a></p>
              <p>不需要注册。学生账号由老师创建；如果仍使用初始密码，登录后请先修改密码。</p>
            </section>

            <section class="card">
              <h2>2. 作品里推荐引入配置文件</h2>
              <p><code>api-config.js</code> 是平台自动提供的固定配置文件名，学生不需要自己上传或改名。它会提供 <code>API_ROOT</code> 和 <code>API_BASE</code>。你的业务 JS 文件可以任意命名，例如 <code>xxx.js</code>、<code>main.js</code> 或 <code>app.js</code>。</p>
              <p>例子一：自己的 JS 和 <code>index.html</code> 放在同一层。</p>
              <pre>index.html
xxx.js</pre>
              <pre>&lt;!-- index.html --&gt;
&lt;script src="./api-config.js"&gt;&lt;/script&gt;
&lt;script src="./xxx.js"&gt;&lt;/script&gt;</pre>
              <pre>// xxx.js
fetch(API_BASE + "/comments")
  .then(function (res) {{ return res.json() }})
  .then(function (body) {{ console.log(body) }})</pre>
              <p>例子二：自己的 JS 放在子文件夹中。</p>
              <pre>index.html
js/
  main.js</pre>
              <pre>&lt;!-- index.html --&gt;
&lt;script src="./api-config.js"&gt;&lt;/script&gt;
&lt;script src="./js/main.js"&gt;&lt;/script&gt;</pre>
              <p>例子三：如果当前 HTML 文件本身在子文件夹中，先回到网站根目录再引入平台配置。</p>
              <pre>pages/
  detail.html
  detail.js</pre>
              <pre>&lt;!-- pages/detail.html --&gt;
&lt;script src="../api-config.js"&gt;&lt;/script&gt;
&lt;script src="./detail.js"&gt;&lt;/script&gt;</pre>
              <p class="muted">注意：<code>api-config.js</code> 的路径是相对当前 HTML 文件写的。本地示例路径：<code>{api_config}</code>。实际作品上传后，首页通常使用 <code>./api-config.js</code>。</p>
            </section>

            <section class="card">
              <h2>3. 虚拟 API 数据接口</h2>
              <p>学生在管理页创建接口名后，就可以用下面的接口。把 <code>comments</code> 换成你自己的接口名。</p>
              <table>
                <tr><th>方法</th><th>地址</th><th>用途</th></tr>
                <tr><td>GET</td><td><code>API_BASE + "/comments"</code></td><td>读取当前接口的数据列表，支持分页。</td></tr>
                <tr><td>POST</td><td><code>API_BASE + "/comments"</code></td><td>新增一条 JSON 数据，例如评论、留言、报名信息。</td></tr>
                <tr><td>PUT</td><td><code>API_BASE + "/comments/{'{记录id}'}"</code></td><td>作者登录后修改自己的数据。</td></tr>
                <tr><td>DELETE</td><td><code>API_BASE + "/comments/{'{记录id}'}"</code></td><td>作者登录后删除自己的数据。</td></tr>
              </table>
              <pre>fetch(API_BASE + "/comments", {{
  method: "POST",
  headers: {{ "Content-Type": "application/json" }},
  body: JSON.stringify({{ nickname: "小李", content: "作品很好看" }})
}})</pre>
            </section>

            <section class="card">
              <h2>4. 三种访问规则</h2>
              <table>
                <tr><th>规则</th><th>含义</th><th>适合场景</th></tr>
                <tr><td><code>public_read</code></td><td>访客可以看，作者登录后写入、修改、删除。</td><td>商品、作品、文章列表。</td></tr>
                <tr><td><code>public_submit</code></td><td>访客可以提交，也可以公开查看。</td><td>留言板、公开评论。</td></tr>
                <tr><td><code>private_collect</code></td><td>访客可以提交，只有作者登录后查看。</td><td>报名、订单、联系方式收集。</td></tr>
              </table>
            </section>

            <section class="card">
              <h2>5. 媒体文件</h2>
              <p>静态图片、CSS、JS 可以直接放进网站 zip。运行中需要上传并保存到数据里的图片、PDF、音频、视频，使用学生管理页的“媒体文件”上传，复制返回的 <code>fileUrl</code> 保存进自己的数据。</p>
            </section>

            <section class="card">
              <h2>6. 可选：作品内管理页</h2>
              <p>如果你的作品里做了自己的管理页，可以调用平台登录接口，拿到 token 后再管理自己的接口和数据。这不是强制评分项。</p>
              <p>它主要和接口权限配合使用：<code>public_read</code> 的新增、修改、删除需要作者 token；<code>private_collect</code> 的查看需要作者 token；<code>public_submit</code> 的访客提交和公开查看不需要 token，但作者想清理或修改数据时仍需要 token。</p>
              <table>
                <tr><th>权限</th><th>访客能做什么</th><th>作品内管理页拿到 token 后能做什么</th></tr>
                <tr><td><code>public_read</code></td><td>公开查看。</td><td>新增、修改、删除作者自己的数据。</td></tr>
                <tr><td><code>public_submit</code></td><td>公开提交，也能公开查看。</td><td>修改、删除需要维护的数据。</td></tr>
                <tr><td><code>private_collect</code></td><td>只能提交，不能查看列表。</td><td>查看、修改、删除收集到的数据。</td></tr>
              </table>
              <pre>fetch(API_ROOT + "/api/auth/login", {{
  method: "POST",
  headers: {{ "Content-Type": "application/json" }},
  body: JSON.stringify({{ username: "你的学号", password: "你的密码" }})
}})
  .then(function (res) {{ return res.json() }})
  .then(function (body) {{
    var token = body.data.token
    return fetch(API_BASE + "/comments", {{
      headers: {{ Authorization: "Bearer " + token }}
    }})
  }})</pre>
            </section>
          </main>
        </body>
        </html>
        """

    def get_resource(student_id: str, resource_name: str) -> sqlite3.Row:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM resources
                WHERE student_id = ? AND resource_name = ?
                """,
                (student_id, resource_name),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="资源接口不存在")
        return row

    def list_resource_records(student_id: str, resource_name: str, page: int, page_size: int) -> dict[str, Any]:
        page, page_size, offset = normalize_pagination(page, page_size)
        with connect() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*) FROM records
                WHERE student_id = ? AND resource_name = ?
                """,
                (student_id, resource_name),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM records
                WHERE student_id = ? AND resource_name = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (student_id, resource_name, page_size, offset),
            ).fetchall()
        return paginated_response([decode_record(row) for row in rows], total, page, page_size)

    def get_record(student_id: str, resource_name: str, record_id: str) -> sqlite3.Row:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM records
                WHERE id = ? AND student_id = ? AND resource_name = ?
                """,
                (record_id, student_id, resource_name),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="数据不存在")
        return row

    def get_student_record(student_id: str, record_id: str) -> sqlite3.Row:
        student_id = validate_student_id(student_id)
        record_id = validate_file_id(record_id, "recordId")
        with connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM records
                WHERE id = ? AND student_id = ?
                """,
                (record_id, student_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="数据不存在")
        return row

    def decode_file(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "studentId": row["student_id"],
            "originalName": row["original_name"],
            "fileName": row["stored_name"],
            "contentType": row["content_type"],
            "kind": row["file_kind"],
            "sizeBytes": row["size_bytes"],
            "fileUrl": media_file_url(row["student_id"], row["id"], row["stored_name"]),
            "createdAt": row["created_at"],
        }

    def file_kind_for_suffix(suffix: str) -> str | None:
        suffix = suffix.lower()
        for kind, extensions in FILE_KIND_EXTENSIONS.items():
            if suffix in extensions:
                return kind
        return None

    def files_root_for_student(student_id: str) -> Path:
        valid_id = validate_student_id(student_id)
        path = (files_path / valid_id).resolve()
        try:
            path.relative_to(files_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="文件路径无效") from None
        return path

    def cleanup_path(path: Path | None) -> None:
        if path is None or not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink()

    async def save_upload_to_temp(upload: UploadFile, max_bytes: int, too_large_detail: str) -> tuple[Path, int]:
        temp_path = (tmp_path / f"upload_{uuid4().hex}.tmp").resolve()
        try:
            temp_path.relative_to(tmp_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="临时文件路径无效") from None

        total = 0
        try:
            with temp_path.open("wb") as output:
                while True:
                    chunk = await upload.read(app.state.upload_chunk_bytes)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(status_code=413, detail=too_large_detail)
                    output.write(chunk)
        except Exception:
            cleanup_path(temp_path)
            raise
        return temp_path, total

    def get_student_file(student_id: str, file_id: str) -> sqlite3.Row:
        student_id = validate_student_id(student_id)
        file_id = validate_file_id(file_id)
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE student_id = ? AND id = ?",
                (student_id, file_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="文件不存在")
        return row

    def list_student_files(student_id: str) -> list[dict[str, Any]]:
        student_id = validate_student_id(student_id)
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE student_id = ? ORDER BY created_at DESC",
                (student_id,),
            ).fetchall()
        return [decode_file(row) for row in rows]

    def list_student_files_page(student_id: str, page: int, page_size: int) -> dict[str, Any]:
        student_id = validate_student_id(student_id)
        page, page_size, offset = normalize_pagination(page, page_size)
        with connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM files WHERE student_id = ?",
                (student_id,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM files
                WHERE student_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (student_id, page_size, offset),
            ).fetchall()
        return paginated_response([decode_file(row) for row in rows], total, page, page_size)

    def list_student_records_page(student_id: str, page: int, page_size: int) -> dict[str, Any]:
        student_id = validate_student_id(student_id)
        page, page_size, offset = normalize_pagination(page, page_size)
        with connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM records WHERE student_id = ?",
                (student_id,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM records
                WHERE student_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (student_id, page_size, offset),
            ).fetchall()
        return paginated_response([decode_record(row) for row in rows], total, page, page_size)

    def enforce_student_file_caps(student_id: str, size_bytes: int) -> None:
        with connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(size_bytes), 0) AS total FROM files WHERE student_id = ?",
                (student_id,),
            ).fetchone()
        if row["count"] >= app.state.max_student_file_count:
            raise HTTPException(status_code=429, detail="该学生文件数量已达上限")
        if row["total"] + size_bytes > app.state.max_student_file_total_bytes:
            raise HTTPException(status_code=413, detail="该学生文件空间已达容量上限")

    def uploaded_file_metadata(filename: str) -> tuple[str, str, str, str, int]:
        original_name = Path(filename or "").name.strip()
        if not original_name:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        suffix = Path(original_name).suffix.lower()
        kind = file_kind_for_suffix(suffix)
        if kind is None:
            raise HTTPException(status_code=400, detail="不支持该文件类型")
        limit = app.state.file_kind_max_bytes[kind]
        content_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        return original_name, suffix, kind, content_type, limit

    def resolve_uploaded_file(filename: str, size_bytes: int) -> tuple[str, str, str, str]:
        original_name, suffix, kind, content_type, limit = uploaded_file_metadata(filename)
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail="文件不能为空")
        if size_bytes > limit:
            raise HTTPException(status_code=413, detail=f"{kind} 文件过大")
        return original_name, suffix, kind, content_type

    def enforce_record_caps(student_id: str, resource_name: str) -> None:
        with connect() as conn:
            space_count = conn.execute(
                "SELECT COUNT(*) FROM records WHERE student_id = ?",
                (student_id,),
            ).fetchone()[0]
            resource_count = conn.execute(
                "SELECT COUNT(*) FROM records WHERE student_id = ? AND resource_name = ?",
                (student_id, resource_name),
            ).fetchone()[0]
        if space_count >= app.state.max_records_per_space:
            raise HTTPException(status_code=429, detail="该学生空间数据量已达上限")
        if resource_count >= app.state.max_records_per_resource:
            raise HTTPException(status_code=429, detail="该资源数据量已达上限")

    def enforce_public_post_limits(request: Request, student_id: str) -> None:
        now = time.time()
        window = app.state.public_post_window_seconds
        ip = request_ip(request)
        ip_events = [item for item in app.state.public_post_by_ip.get(ip, []) if now - item < window]
        space_events = [
            item
            for item in app.state.public_post_by_space.get(student_id, [])
            if now - item < window
        ]
        if len(ip_events) >= app.state.public_post_ip_limit:
            raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试")
        if len(space_events) >= app.state.public_post_space_limit:
            raise HTTPException(status_code=429, detail="该作品短时间内提交较多，请稍后再试")
        ip_events.append(now)
        space_events.append(now)
        app.state.public_post_by_ip[ip] = ip_events
        app.state.public_post_by_space[student_id] = space_events

    def site_root_for_student(student_id: str) -> Path:
        valid_id = validate_student_id(student_id)
        path = (sites_path / valid_id).resolve()
        try:
            path.relative_to(sites_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="站点路径无效") from None
        return path

    def resolve_site_file(student_id: str, file_path: str = "") -> Path:
        root = site_root_for_student(student_id)
        requested = (file_path or "index.html").replace("\\", "/").strip("/")
        if not requested:
            requested = "index.html"
        parts = PurePosixPath(requested).parts
        if any(part in {"..", ""} for part in parts):
            raise HTTPException(status_code=400, detail="文件路径无效")
        path = (root / Path(*parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="文件路径无效") from None
        if path.is_dir():
            path = path / "index.html"
        return path

    def validate_zip_member(name: str) -> PurePosixPath:
        normalized = name.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or any(part in {"..", ""} for part in path.parts):
            raise HTTPException(status_code=400, detail="zip 中存在不安全路径")
        suffix = path.suffix.lower()
        if suffix and suffix not in ALLOWED_SITE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不允许上传 {suffix} 文件")
        return path

    def make_site_temp_dir(student_id: str) -> Path:
        valid_id = validate_student_id(student_id)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{valid_id}-upload-", dir=sites_path)).resolve()
        try:
            temp_dir.relative_to(sites_path.resolve())
        except ValueError:
            cleanup_path(temp_dir)
            raise HTTPException(status_code=400, detail="站点临时目录无效") from None
        return temp_dir

    def refresh_latest_site_backup(student_id: str, root: Path) -> Path | None:
        if not root.exists():
            return None
        valid_id = validate_student_id(student_id)
        backup_parent = (backups_path / "sites" / valid_id).resolve()
        try:
            backup_parent.relative_to(backups_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="站点备份目录无效") from None
        backup_parent.mkdir(parents=True, exist_ok=True)
        latest = backup_parent / "latest"
        temp_backup = backup_parent / f".latest-{uuid4().hex}"
        try:
            shutil.copytree(root, temp_backup)
            cleanup_path(latest)
            temp_backup.replace(latest)
        except Exception:
            cleanup_path(temp_backup)
            raise HTTPException(status_code=500, detail="旧站点备份失败，已保留原站点") from None
        return latest

    def replace_site_root(student_id: str, new_root: Path) -> None:
        root = site_root_for_student(student_id)
        rollback_root: Path | None = None
        if root.exists():
            refresh_latest_site_backup(student_id, root)
            rollback_root = (sites_path / f".{validate_student_id(student_id)}-rollback-{uuid4().hex}").resolve()
            try:
                rollback_root.relative_to(sites_path.resolve())
            except ValueError:
                raise HTTPException(status_code=400, detail="站点回滚目录无效") from None
        try:
            if root.exists() and rollback_root is not None:
                root.replace(rollback_root)
            new_root.replace(root)
        except Exception:
            if root.exists():
                failed_root = (sites_path / f".{validate_student_id(student_id)}-failed-{uuid4().hex}").resolve()
                try:
                    root.replace(failed_root)
                    cleanup_path(failed_root)
                except Exception:
                    pass
            if rollback_root is not None and rollback_root.exists():
                try:
                    rollback_root.replace(root)
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail="站点替换失败，旧站点已保留") from None
        finally:
            cleanup_path(rollback_root)

    def write_site_archive(archive: zipfile.ZipFile, safe_members: list[tuple[zipfile.ZipInfo, PurePosixPath]], root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for info, safe_path in safe_members:
            target = (root / Path(*safe_path.parts)).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise HTTPException(status_code=400, detail="zip 中存在不安全路径") from None
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=app.state.upload_chunk_bytes)
            except (OSError, zipfile.BadZipFile):
                raise HTTPException(status_code=400, detail="zip 文件无法读取") from None

    def list_tree_files(root: Path) -> list[dict[str, Any]]:
        if not root.exists():
            return []
        files = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            files.append(
                {
                    "relativePath": path.relative_to(root).as_posix(),
                    "sizeBytes": path.stat().st_size,
                }
            )
        return files

    def admin_backup_root(action: str, student_id: str, backup_id: str, created_at: str) -> Path:
        safe_time = created_at.replace(":", "").replace("-", "").split(".", 1)[0]
        root = (backups_path / "admin-actions" / f"{safe_time}_{action}_{student_id}_{backup_id}").resolve()
        try:
            root.relative_to(backups_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="备份目录无效") from None
        root.mkdir(parents=True, exist_ok=False)
        return root

    def write_admin_audit(
        audit_id: str,
        action: str,
        student_id: str,
        backup_path: Path,
        summary: dict[str, Any],
        request: Request,
        created_at: str,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_audits
                (id, action, student_id, backup_path, summary_json, actor, created_ip, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    action,
                    student_id,
                    str(backup_path),
                    json.dumps(summary, ensure_ascii=False),
                    ADMIN_USERNAME,
                    request_ip(request),
                    created_at,
                ),
            )

    def create_admin_backup(
        action: str,
        student_id: str,
        request: Request,
        summary: dict[str, Any],
        source_dir: Path | None = None,
        source_label: str | None = None,
    ) -> dict[str, Any]:
        student_id = validate_student_id(student_id)
        backup_id = f"backup_{uuid4().hex}"
        created_at = now_iso()
        root = admin_backup_root(action, student_id, backup_id, created_at)
        copied_dir = ""
        try:
            if source_dir is not None and source_dir.exists():
                copied = (root / (source_label or "files")).resolve()
                copied.relative_to(root)
                shutil.copytree(source_dir, copied)
                copied_dir = str(copied)
            manifest = {
                "backupId": backup_id,
                "action": action,
                "studentId": student_id,
                "createdAt": created_at,
                "copiedDir": copied_dir,
                "summary": summary,
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            write_admin_audit(backup_id, action, student_id, root, summary, request, created_at)
        except HTTPException:
            cleanup_path(root)
            raise
        except Exception:
            cleanup_path(root)
            raise HTTPException(status_code=500, detail="清空前自动备份失败，未删除数据") from None
        return {
            "backupId": backup_id,
            "backupPath": str(root),
            "manifestPath": str(root / "manifest.json"),
            "createdAt": created_at,
        }

    def deployment_warnings() -> list[str]:
        warnings = []
        public_like = bool(public_origin or site_origin) or not is_loopback_host(app.state.backend_host)
        if app.state.trust_proxy_headers and not is_loopback_host(app.state.backend_host):
            warnings.append(
                "FINAL_BACKEND_TRUST_PROXY_HEADERS=true 时后端应只监听 127.0.0.1 或 ::1；当前 FINAL_BACKEND_HOST 不是本机回环地址，请确认后端端口不会被公网直连。"
            )
        if public_like and not app.state.require_separate_site_origin:
            warnings.append(
                "FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=false 只适合本地教师自测；真实学生互访必须使用独立作品 origin。"
            )
        if public_origin.startswith("https://") and not cookie_secure:
            warnings.append(
                "FINAL_BACKEND_PUBLIC_BASE_URL 是 HTTPS，但 FINAL_BACKEND_COOKIE_SECURE=false；正式线上教师 Cookie 应启用 Secure。"
            )
        if teacher_key_enabled and teacher_key == DEFAULT_TEACHER_KEY:
            warnings.append(
                "FINAL_BACKEND_ENABLE_TEACHER_KEY=true 且仍使用默认教师密钥；正式线上应关闭教师 key 或设置自定义强密钥。"
            )
        if public_like and app.state.enable_cors and "*" in app.state.cors_allow_origins:
            warnings.append(
                "FINAL_BACKEND_CORS_ORIGINS 未限制导致允许任意 Origin；正式线上建议只允许学生作品域名。"
            )
        return warnings

    def build_export_payload(student_id: str | None = None) -> dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if student_id:
            clauses.append("student_id = ?")
            params.append(validate_student_id(student_id))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with connect() as conn:
            students = [sanitize_student(row) for row in conn.execute("SELECT * FROM students ORDER BY student_id").fetchall()]
            resources = [row_to_dict(row) for row in conn.execute(f"SELECT * FROM resources{where} ORDER BY student_id, resource_name", params).fetchall()]
            records = [decode_record(row) for row in conn.execute(f"SELECT * FROM records{where} ORDER BY created_at DESC", params).fetchall()]
            files = [decode_file(row) for row in conn.execute(f"SELECT * FROM files{where} ORDER BY created_at DESC", params).fetchall()]
        return {
            "exportedAt": now_iso(),
            "studentId": student_id,
            "students": students if student_id is None else [item for item in students if item["studentId"] == student_id],
            "resources": resources,
            "records": records,
            "files": files,
        }

    def build_resource_export_payload(student_id: str, resource_name: str) -> dict[str, Any]:
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        resource = get_resource(student_id, resource_name)
        with connect() as conn:
            student_row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
            rows = conn.execute(
                """
                SELECT * FROM records
                WHERE student_id = ? AND resource_name = ?
                ORDER BY created_at DESC
                """,
                (student_id, resource_name),
            ).fetchall()
        return {
            "exportedAt": now_iso(),
            "student": sanitize_student(student_row) if student_row else None,
            "resource": row_to_dict(resource),
            "records": [decode_record(row) for row in rows],
        }

    def write_json_to_zip(archive: zipfile.ZipFile, name: str, payload: Any) -> None:
        archive.writestr(name, json.dumps(payload, ensure_ascii=False, indent=2))

    def write_dir_to_zip(archive: zipfile.ZipFile, root: Path, prefix: str) -> list[dict[str, Any]]:
        files = []
        if not root.exists():
            return files
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            archive.write(path, f"{prefix.rstrip('/')}/{relative}")
            files.append({"relativePath": relative, "sizeBytes": path.stat().st_size})
        return files

    def build_student_archive(student_id: str) -> Path:
        student_id = validate_student_id(student_id)
        payload = build_export_payload(student_id)
        temp_path = (tmp_path / f"archive_{student_id}_{uuid4().hex}.zip").resolve()
        try:
            temp_path.relative_to(tmp_path.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="归档路径无效") from None
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                site_files = write_dir_to_zip(archive, site_root_for_student(student_id), "site")
                media_files = write_dir_to_zip(archive, files_root_for_student(student_id), "media")
                manifest = {
                    "exportedAt": now_iso(),
                    "studentId": student_id,
                    "recordCount": len(payload["records"]),
                    "resourceCount": len(payload["resources"]),
                    "fileCount": len(payload["files"]),
                    "siteFiles": site_files,
                    "mediaFiles": media_files,
                }
                write_json_to_zip(archive, "manifest.json", manifest)
                write_json_to_zip(archive, "students.json", payload["students"])
                write_json_to_zip(archive, "resources.json", payload["resources"])
                write_json_to_zip(archive, "records.json", payload["records"])
                write_json_to_zip(archive, "files.json", payload["files"])
        except Exception:
            cleanup_path(temp_path)
            raise
        return temp_path

    init_db()
    if app.state.auto_sync_students:
        sync_students_from_file()

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return f"""
        <!doctype html>
        <html lang="zh-CN">
        <head><meta charset="utf-8"><title>期末作品平台后端</title></head>
        <body>
          <h1>期末作品平台后端</h1>
          <p>学生登录后管理自己的虚拟接口、数据和静态网站。</p>
          <ul>
            <li><a href="{public_url('/api-docs')}">学生接口说明</a></li>
            <li><a href="{public_url('/student')}">学生管理入口</a></li>
            <li><a href="{public_url('/admin')}">教师管理入口</a></li>
          </ul>
        </body>
        </html>
        """

    @app.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
    async def student_api_docs():
        return HTMLResponse(student_api_docs_html())

    @app.get("/api-docs/", response_class=HTMLResponse, include_in_schema=False)
    async def student_api_docs_slash():
        return HTMLResponse(student_api_docs_html())

    if teacher_docs_enabled:
        @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
        async def teacher_swagger_docs(request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
            try:
                require_admin(request, x_teacher_key)
            except HTTPException:
                if not x_teacher_key:
                    return RedirectResponse(public_url("/admin"), status_code=303)
                raise
            return get_swagger_ui_html(
                openapi_url=public_url("/openapi.json"),
                title="期末作品平台后端 - 教师调试文档",
            )

        @app.get("/openapi.json", response_class=JSONResponse, include_in_schema=False)
        async def teacher_openapi_json(request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
            require_admin(request, x_teacher_key)
            return JSONResponse(app.openapi())

    @app.get("/student", response_class=HTMLResponse)
    async def student_page():
        return FileResponse(UI_DIR / "student.html", media_type="text/html; charset=utf-8")

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page():
        return FileResponse(UI_DIR / "admin.html", media_type="text/html; charset=utf-8")

    @app.post("/api/admin/login")
    async def admin_login(payload: LoginIn, request: Request):
        ensure_login_allowed("admin", payload.username, request)
        if payload.username != ADMIN_USERNAME or payload.password != admin_password:
            record_login_failure("admin", payload.username, request)
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        clear_login_failures("admin", payload.username, request)
        token = make_token("admin")
        app.state.admin_sessions[token] = time.time() + ADMIN_SESSION_SECONDS
        response = Response(
            content=json.dumps(success_response("登录成功", {"username": ADMIN_USERNAME}), ensure_ascii=False),
            media_type="application/json; charset=utf-8",
        )
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            max_age=ADMIN_SESSION_SECONDS,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
            path=root_path or "/",
        )
        return response

    @app.post("/api/admin/logout")
    async def admin_logout(request: Request):
        token = request.cookies.get(ADMIN_COOKIE_NAME, "")
        app.state.admin_sessions.pop(token, None)
        response = Response(
            content=json.dumps(success_response("已退出登录"), ensure_ascii=False),
            media_type="application/json; charset=utf-8",
        )
        response.delete_cookie(ADMIN_COOKIE_NAME, path=root_path or "/")
        return response

    @app.get("/api/admin/me")
    async def admin_me(request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        method = require_admin(request, x_teacher_key)
        return success_response("当前教师获取成功", {"username": ADMIN_USERNAME, "method": method})

    @app.get("/api/admin/status")
    async def admin_status(request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        with connect() as conn:
            student_count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            resource_count = conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            record_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            file_bytes = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM files").fetchone()[0]
        data_size = sum(path.stat().st_size for path in data_path.rglob("*") if path.is_file())
        return success_response(
            "状态获取成功",
            {
                "version": "final-0.1.0",
                "dataDir": str(data_path),
                "dbPath": str(db_path),
                "students": student_count,
                "resources": resource_count,
                "records": record_count,
                "files": file_count,
                "fileBytes": file_bytes,
                "dataBytes": data_size,
                "teacherKeyEnabled": teacher_key_enabled,
                "teacherKeyIsDefault": teacher_key_enabled and teacher_key == DEFAULT_TEACHER_KEY,
                "cookieSecure": cookie_secure,
                "rootPath": root_path,
                "publicBaseUrl": public_base_url,
                "siteBaseUrl": site_base_url,
                "loginRateLimitEnabled": login_rate_limit_enabled,
                "siteSandboxEnabled": site_sandbox_enabled,
                "trustProxyHeaders": trust_proxy_headers,
                "backendHost": app.state.backend_host,
                "corsEnabled": app.state.enable_cors,
                "corsAllowOrigins": app.state.cors_allow_origins,
                "studentsFile": str(app.state.students_file),
                "autoSyncStudents": app.state.auto_sync_students,
                "studentsFileExists": app.state.students_file.exists(),
                "deploymentWarnings": deployment_warnings(),
                "requireSeparateSiteOrigin": require_separate_site_origin,
                "defaultPageSize": app.state.default_page_size,
                "maxPageSize": app.state.max_page_size,
                "uploadChunkBytes": app.state.upload_chunk_bytes,
            },
        )

    @app.get("/api/admin/students")
    async def admin_students(request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        with connect() as conn:
            rows = conn.execute("SELECT * FROM students ORDER BY student_id").fetchall()
        return success_response("学生列表获取成功", [sanitize_student(row) for row in rows])

    @app.post("/api/admin/students/sync")
    async def admin_sync_students(request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        try:
            data = sync_students_from_file()
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return success_response("学生名单已同步", data)

    @app.post("/api/admin/students", status_code=201)
    async def admin_create_student(payload: StudentCreateIn, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        data = create_student(payload)
        return success_response("学生账号已创建", data)

    @app.put("/api/admin/students/{student_id}")
    async def admin_update_student(student_id: str, payload: StudentUpdateIn, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        updates = []
        params: list[Any] = []
        if payload.displayName is not None:
            updates.append("display_name = ?")
            params.append(payload.displayName.strip() or student_id)
        if payload.className is not None:
            updates.append("class_name = ?")
            params.append(payload.className.strip())
        if payload.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if payload.enabled else 0)
        if payload.note is not None:
            updates.append("note = ?")
            params.append(payload.note)
        if not updates:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        updates.append("updated_at = ?")
        params.append(now_iso())
        params.append(student_id)
        with connect() as conn:
            result = conn.execute(f"UPDATE students SET {', '.join(updates)} WHERE student_id = ?", params)
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="学生不存在")
        return success_response("学生信息已更新", {"studentId": student_id})

    @app.post("/api/admin/students/{student_id}/reset-password")
    async def admin_reset_password(student_id: str, payload: ResetPasswordIn, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        password = payload.password or initial_password_from_file(student_id)
        if not password:
            raise HTTPException(status_code=400, detail="没有可恢复的初始密码，请在请求中提供 password")
        password_hash, password_salt = hash_password(password)
        with connect() as conn:
            result = conn.execute(
                """
                UPDATE students
                SET password_hash = ?,
                    password_salt = ?,
                    initial_password_hash = ?,
                    initial_password_salt = ?,
                    password_is_initial = 1,
                    password_updated_at = '',
                    updated_at = ?
                WHERE student_id = ?
                """,
                (password_hash, password_salt, password_hash, password_salt, now_iso(), student_id),
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="学生不存在")
            conn.execute("DELETE FROM sessions WHERE student_id = ?", (student_id,))
        return success_response("学生密码已重置为初始密码", {"studentId": student_id, "password": password, "mustChangePassword": True})

    @app.get("/api/admin/students/{student_id}/resources")
    async def admin_student_resources(student_id: str, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM resources WHERE student_id = ? ORDER BY resource_name",
                (student_id,),
            ).fetchall()
        return success_response("资源列表获取成功", [row_to_dict(row) for row in rows])

    @app.get("/api/admin/students/{student_id}/records")
    async def admin_student_records(
        student_id: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
        page: int = Query(default=1),
        pageSize: int = Query(default=DEFAULT_PAGE_SIZE),
    ):
        require_admin(request, x_teacher_key)
        return success_response("数据获取成功", list_student_records_page(student_id, page, pageSize))

    @app.get("/api/admin/students/{student_id}/resources/{resource_name}/records")
    async def admin_student_resource_records(
        student_id: str,
        resource_name: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
        page: int = Query(default=1),
        pageSize: int = Query(default=DEFAULT_PAGE_SIZE),
    ):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        get_resource(student_id, resource_name)
        return success_response("资源数据获取成功", list_resource_records(student_id, resource_name, page, pageSize))

    @app.get("/api/admin/students/{student_id}/resources/{resource_name}/export")
    async def admin_student_resource_export(
        student_id: str,
        resource_name: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
    ):
        require_admin(request, x_teacher_key)
        payload = build_resource_export_payload(student_id, resource_name)
        filename = f"final_backend_{validate_student_id(student_id)}_{validate_resource_name(resource_name)}.json"
        return Response(
            content=json_response_bytes(payload),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": content_disposition_header("attachment", filename)},
        )

    @app.get("/api/admin/students/{student_id}/files")
    async def admin_student_files(
        student_id: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
        page: int = Query(default=1),
        pageSize: int = Query(default=DEFAULT_PAGE_SIZE),
    ):
        require_admin(request, x_teacher_key)
        return success_response("文件列表获取成功", list_student_files_page(student_id, page, pageSize))

    @app.delete("/api/admin/students/{student_id}/records")
    async def admin_clear_student_records(student_id: str, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM records WHERE student_id = ? ORDER BY created_at DESC",
                (student_id,),
            ).fetchall()
        backup = create_admin_backup(
            "clear-records",
            student_id,
            request,
            {
                "recordsDeleted": len(rows),
                "records": [decode_record(row) for row in rows],
            },
        )
        with connect() as conn:
            deleted = conn.execute("DELETE FROM records WHERE student_id = ?", (student_id,)).rowcount
        return success_response("学生数据已清空", {"studentId": student_id, "recordsDeleted": deleted, "backup": backup})

    @app.delete("/api/admin/students/{student_id}/records/{record_id}")
    async def admin_delete_student_record(
        student_id: str,
        record_id: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
    ):
        require_admin(request, x_teacher_key)
        row = get_student_record(student_id, record_id)
        record = decode_record(row)
        backup = create_admin_backup(
            "delete-record",
            record["studentId"],
            request,
            {
                "recordId": record["id"],
                "resourceName": record["resourceName"],
                "recordDeleted": 1,
                "record": record,
            },
        )
        with connect() as conn:
            deleted = conn.execute(
                "DELETE FROM records WHERE student_id = ? AND id = ?",
                (record["studentId"], record["id"]),
            ).rowcount
        return success_response(
            "数据记录已删除",
            {"studentId": record["studentId"], "recordId": record["id"], "recordDeleted": deleted, "backup": backup},
        )

    @app.delete("/api/admin/students/{student_id}/resources/{resource_name}/records")
    async def admin_clear_student_resource_records(
        student_id: str,
        resource_name: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
    ):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        get_resource(student_id, resource_name)
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM records
                WHERE student_id = ? AND resource_name = ?
                ORDER BY created_at DESC
                """,
                (student_id, resource_name),
            ).fetchall()
        backup = create_admin_backup(
            "clear-resource-records",
            student_id,
            request,
            {
                "resourceName": resource_name,
                "recordsDeleted": len(rows),
                "records": [decode_record(row) for row in rows],
            },
        )
        with connect() as conn:
            deleted = conn.execute(
                "DELETE FROM records WHERE student_id = ? AND resource_name = ?",
                (student_id, resource_name),
            ).rowcount
        return success_response(
            "资源数据已清空",
            {"studentId": student_id, "resourceName": resource_name, "recordsDeleted": deleted, "backup": backup},
        )

    @app.delete("/api/admin/students/{student_id}/site")
    async def admin_clear_student_site(student_id: str, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        root = site_root_for_student(student_id)
        backup = create_admin_backup(
            "clear-site",
            student_id,
            request,
            {
                "siteExisted": root.exists(),
                "files": list_tree_files(root),
            },
            source_dir=root if root.exists() else None,
            source_label="site",
        )
        if root.exists():
            shutil.rmtree(root)
        return success_response("学生站点已清空", {"studentId": student_id, "backup": backup})

    @app.delete("/api/admin/students/{student_id}/files")
    async def admin_clear_student_files(student_id: str, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        root = files_root_for_student(student_id)
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE student_id = ? ORDER BY created_at DESC",
                (student_id,),
            ).fetchall()
        backup = create_admin_backup(
            "clear-files",
            student_id,
            request,
            {
                "filesDeleted": len(rows),
                "files": [decode_file(row) for row in rows],
                "storedFiles": list_tree_files(root),
            },
            source_dir=root if root.exists() else None,
            source_label="files",
        )
        with connect() as conn:
            deleted = conn.execute("DELETE FROM files WHERE student_id = ?", (student_id,)).rowcount
        if root.exists():
            shutil.rmtree(root)
        return success_response("学生文件已清空", {"studentId": student_id, "filesDeleted": deleted, "backup": backup})

    @app.delete("/api/admin/students/{student_id}/files/{file_id}")
    async def admin_delete_student_file(
        student_id: str,
        file_id: str,
        request: Request,
        x_teacher_key: str = Header(default="", alias="X-Teacher-Key"),
    ):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        file_id = validate_file_id(file_id)
        row = get_student_file(student_id, file_id)
        file_data = decode_file(row)
        folder = files_root_for_student(student_id) / file_id
        backup = create_admin_backup(
            "delete-file",
            student_id,
            request,
            {
                "fileId": file_id,
                "filesDeleted": 1,
                "file": file_data,
                "storedFiles": list_tree_files(folder),
            },
            source_dir=folder if folder.exists() else None,
            source_label=f"file-{file_id}",
        )
        with connect() as conn:
            deleted = conn.execute("DELETE FROM files WHERE student_id = ? AND id = ?", (student_id, file_id)).rowcount
        if folder.exists():
            shutil.rmtree(folder)
        return success_response(
            "学生文件已删除",
            {"studentId": student_id, "fileId": file_id, "filesDeleted": deleted, "file": file_data, "backup": backup},
        )

    @app.post("/api/admin/export-token")
    async def admin_export_token(payload: AdminExportTokenIn, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(payload.studentId) if payload.studentId else None
        token = make_token("export")
        app.state.export_tokens[token] = (time.time() + ADMIN_EXPORT_TOKEN_SECONDS, student_id)
        return success_response(
            "导出链接已生成",
            {"expiresIn": ADMIN_EXPORT_TOKEN_SECONDS, "downloadUrl": public_url(f"/api/admin/export?token={quote(token, safe='')}")},
        )

    @app.get("/api/admin/export")
    async def admin_export(token: str | None = None, student_id: str | None = None, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        if token:
            entry = app.state.export_tokens.pop(token, None)
            if entry is None or entry[0] < time.time():
                raise HTTPException(status_code=401, detail="导出链接已失效")
            student_id = entry[1]
        elif not is_teacher_key_valid(x_teacher_key):
            raise HTTPException(status_code=401, detail="请先在 /admin 页面生成导出链接")
        payload = build_export_payload(student_id)
        filename = f"final_backend_export_{student_id or 'all'}.json"
        return Response(
            content=json_response_bytes(payload),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": content_disposition_header("attachment", filename)},
        )

    @app.get("/api/admin/students/{student_id}/archive")
    async def admin_student_archive(student_id: str, request: Request, x_teacher_key: str = Header(default="", alias="X-Teacher-Key")):
        require_admin(request, x_teacher_key)
        student_id = validate_student_id(student_id)
        archive_path = build_student_archive(student_id)
        filename = f"final_backend_archive_{student_id}.zip"
        return FileResponse(
            path=archive_path,
            media_type="application/zip",
            headers={"Content-Disposition": content_disposition_header("attachment", filename)},
            background=BackgroundTask(lambda: cleanup_path(archive_path)),
        )

    @app.post("/api/auth/login")
    async def student_login(payload: LoginIn, request: Request):
        ensure_login_allowed("student", payload.username, request)
        student_id = validate_student_id(payload.username, "username")
        row = get_student(student_id)
        if row is None or not verify_password(payload.password, row["password_hash"], row["password_salt"]):
            record_login_failure("student", payload.username, request)
            raise HTTPException(status_code=401, detail="学号或密码错误")
        if not bool(row["enabled"]):
            record_login_failure("student", payload.username, request)
            raise HTTPException(status_code=403, detail="账号已停用，请联系教师")
        clear_login_failures("student", payload.username, request)
        token = make_token("stu")
        now = time.time()
        with connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, student_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, student_id, now, now + STUDENT_SESSION_SECONDS),
            )
        return success_response("登录成功", {"token": token, "user": sanitize_student(row)})

    @app.get("/api/auth/me")
    async def student_me(student: dict[str, Any] = Depends(require_student)):
        return success_response("当前用户获取成功", {"user": student})

    @app.post("/api/auth/change-password")
    async def student_change_password(payload: ChangePasswordIn, request: Request, student: dict[str, Any] = Depends(require_student)):
        if payload.oldPassword == payload.newPassword:
            raise HTTPException(status_code=400, detail="新密码不能和旧密码相同")
        token = get_bearer_token(request)
        row = get_student(student["studentId"])
        if row is None or not verify_password(payload.oldPassword, row["password_hash"], row["password_salt"]):
            raise HTTPException(status_code=401, detail="旧密码错误")
        password_hash, password_salt = hash_password(payload.newPassword)
        stamp = now_iso()
        with connect() as conn:
            conn.execute(
                """
                UPDATE students
                SET password_hash = ?,
                    password_salt = ?,
                    password_is_initial = 0,
                    password_updated_at = ?,
                    updated_at = ?
                WHERE student_id = ?
                """,
                (password_hash, password_salt, stamp, stamp, student["studentId"]),
            )
            if token:
                conn.execute("DELETE FROM sessions WHERE student_id = ? AND token <> ?", (student["studentId"], token))
            else:
                conn.execute("DELETE FROM sessions WHERE student_id = ?", (student["studentId"],))
        updated = get_student(student["studentId"])
        return success_response("密码已修改", {"user": sanitize_student(updated) if updated else student})

    @app.post("/api/auth/logout")
    async def student_logout(request: Request):
        token = get_bearer_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="请先登录")
        with connect() as conn:
            deleted = conn.execute("DELETE FROM sessions WHERE token = ?", (token,)).rowcount
        return success_response("退出登录成功" if deleted else "已退出登录")

    @app.post("/api/auth/register")
    async def register_disabled():
        raise HTTPException(status_code=403, detail="学生注册已关闭，请由教师创建账号")

    @app.get("/api/student/resources")
    async def student_resources(student: dict[str, Any] = Depends(require_student)):
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM resources WHERE student_id = ? ORDER BY resource_name",
                (student["studentId"],),
            ).fetchall()
        return success_response("资源列表获取成功", [row_to_dict(row) for row in rows])

    @app.post("/api/student/resources", status_code=201)
    async def student_create_resource(payload: ResourceCreateIn, student: dict[str, Any] = Depends(require_student)):
        resource_name = validate_resource_name(payload.resourceName)
        access_mode = validate_access_mode(payload.accessMode)
        display_name = (payload.displayName or resource_name).strip() or resource_name
        stamp = now_iso()
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO resources
                (student_id, resource_name, display_name, access_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id, resource_name) DO UPDATE SET
                    display_name = excluded.display_name,
                    access_mode = excluded.access_mode,
                    updated_at = excluded.updated_at
                """,
                (student["studentId"], resource_name, display_name, access_mode, stamp, stamp),
            )
        return success_response("资源接口已保存", {"resourceName": resource_name, "displayName": display_name, "accessMode": access_mode})

    @app.put("/api/student/resources/{resource_name}")
    async def student_update_resource(resource_name: str, payload: ResourceUpdateIn, student: dict[str, Any] = Depends(require_student)):
        resource_name = validate_resource_name(resource_name)
        updates = []
        params: list[Any] = []
        if payload.displayName is not None:
            updates.append("display_name = ?")
            params.append(payload.displayName.strip() or resource_name)
        if payload.accessMode is not None:
            updates.append("access_mode = ?")
            params.append(validate_access_mode(payload.accessMode))
        if not updates:
            raise HTTPException(status_code=400, detail="没有需要修改的字段")
        updates.append("updated_at = ?")
        params.append(now_iso())
        params.extend([student["studentId"], resource_name])
        with connect() as conn:
            result = conn.execute(
                f"UPDATE resources SET {', '.join(updates)} WHERE student_id = ? AND resource_name = ?",
                params,
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="资源接口不存在")
        return success_response("资源接口已更新", {"resourceName": resource_name})

    @app.delete("/api/student/resources/{resource_name}")
    async def student_delete_resource(resource_name: str, student: dict[str, Any] = Depends(require_student)):
        resource_name = validate_resource_name(resource_name)
        with connect() as conn:
            deleted = conn.execute(
                "DELETE FROM resources WHERE student_id = ? AND resource_name = ?",
                (student["studentId"], resource_name),
            ).rowcount
        if deleted == 0:
            raise HTTPException(status_code=404, detail="资源接口不存在")
        return success_response("资源接口已删除", {"resourceName": resource_name})

    @app.post("/api/student/site/upload", status_code=201)
    async def student_upload_site(file: UploadFile = File(...), student: dict[str, Any] = Depends(require_student)):
        filename = Path(file.filename or "").name
        if Path(filename).suffix.lower() != ".zip":
            raise HTTPException(status_code=400, detail="请上传 zip 文件")
        temp_zip: Path | None = None
        temp_root: Path | None = None
        try:
            temp_zip, size_bytes = await save_upload_to_temp(file, MAX_SITE_ZIP_SIZE, "站点 zip 文件过大")
            if size_bytes <= 0:
                raise HTTPException(status_code=400, detail="zip 文件不能为空")
            try:
                with zipfile.ZipFile(temp_zip) as archive:
                    members = [item for item in archive.infolist() if not item.is_dir()]
                    if len(members) > MAX_SITE_FILE_COUNT:
                        raise HTTPException(status_code=413, detail="站点文件数量过多")
                    total_size = sum(item.file_size for item in members)
                    if total_size > MAX_SITE_TOTAL_SIZE:
                        raise HTTPException(status_code=413, detail="站点文件总大小过大")
                    safe_members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
                    has_index = False
                    for info in members:
                        safe_path = validate_zip_member(info.filename)
                        if safe_path.as_posix().lower() == "index.html":
                            has_index = True
                        safe_members.append((info, safe_path))
                    if not has_index:
                        raise HTTPException(status_code=400, detail="zip 根目录必须包含 index.html")
                    temp_root = make_site_temp_dir(student["studentId"])
                    write_site_archive(archive, safe_members, temp_root)
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="zip 文件无法读取") from None
            replace_site_root(student["studentId"], temp_root)
            temp_root = None
        finally:
            cleanup_path(temp_zip)
            cleanup_path(temp_root)
        return success_response("站点上传成功", {"studentId": student["studentId"], "siteUrl": student_site_url(student["studentId"])})

    @app.get("/api/student/site/status")
    async def student_site_status(student: dict[str, Any] = Depends(require_student)):
        root = site_root_for_student(student["studentId"])
        files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
        return success_response(
            "站点状态获取成功",
            {
                "studentId": student["studentId"],
                "exists": (root / "index.html").exists(),
                "fileCount": len(files),
                "totalBytes": sum(path.stat().st_size for path in files),
                "siteUrl": student_site_url(student["studentId"]),
            },
        )

    @app.get("/api/student/files")
    async def student_files(
        student: dict[str, Any] = Depends(require_student),
        page: int = Query(default=1),
        pageSize: int = Query(default=DEFAULT_PAGE_SIZE),
    ):
        return success_response("文件列表获取成功", list_student_files_page(student["studentId"], page, pageSize))

    @app.post("/api/student/files", status_code=201)
    async def student_upload_file(file: UploadFile = File(...), student: dict[str, Any] = Depends(require_student)):
        original_name, suffix, kind, content_type, limit = uploaded_file_metadata(file.filename or "")
        temp_file: Path | None = None
        temp_file, size_bytes = await save_upload_to_temp(file, limit, f"{kind} 文件过大")
        try:
            if size_bytes <= 0:
                raise HTTPException(status_code=400, detail="文件不能为空")
            enforce_student_file_caps(student["studentId"], size_bytes)
            file_id = f"file_{uuid4().hex}"
            stored_name = f"{file_id}{suffix}"
            root = files_root_for_student(student["studentId"])
            folder: Path | None = None
            folder = (root / file_id).resolve()
            try:
                folder.relative_to(root)
            except ValueError:
                raise HTTPException(status_code=400, detail="文件路径无效") from None
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / stored_name
            temp_file.replace(target)
            temp_file = None
            stamp = now_iso()
            try:
                with connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO files
                        (id, student_id, original_name, stored_name, content_type, file_kind, size_bytes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (file_id, student["studentId"], original_name, stored_name, content_type, kind, size_bytes, stamp),
                    )
            except Exception:
                cleanup_path(folder)
                raise
        finally:
            cleanup_path(temp_file)
        return success_response("文件上传成功", decode_file(get_student_file(student["studentId"], file_id)))

    @app.delete("/api/student/files/{file_id}")
    async def student_delete_file(file_id: str, student: dict[str, Any] = Depends(require_student)):
        file_id = validate_file_id(file_id)
        row = get_student_file(student["studentId"], file_id)
        with connect() as conn:
            conn.execute("DELETE FROM files WHERE student_id = ? AND id = ?", (student["studentId"], file_id))
        folder = files_root_for_student(student["studentId"]) / file_id
        if folder.exists():
            shutil.rmtree(folder)
        return success_response("文件已删除", decode_file(row))

    @app.get("/api/{student_id}/{resource_name}")
    async def virtual_list(
        student_id: str,
        resource_name: str,
        request: Request,
        page: int = Query(default=1),
        pageSize: int = Query(default=DEFAULT_PAGE_SIZE),
    ):
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        resource = get_resource(student_id, resource_name)
        student = optional_student(request)
        if resource["access_mode"] == "private_collect":
            if student is None:
                raise HTTPException(status_code=401, detail="请先登录")
            require_space_owner(student_id, student)
        return success_response("数据获取成功", list_resource_records(student_id, resource_name, page, pageSize))

    @app.get("/api/{student_id}/{resource_name}/{record_id}")
    async def virtual_get(student_id: str, resource_name: str, record_id: str, request: Request):
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        resource = get_resource(student_id, resource_name)
        student = optional_student(request)
        if resource["access_mode"] == "private_collect":
            if student is None:
                raise HTTPException(status_code=401, detail="请先登录")
            require_space_owner(student_id, student)
        return success_response("数据获取成功", decode_record(get_record(student_id, resource_name, record_id)))

    @app.post("/api/{student_id}/{resource_name}", status_code=201)
    async def virtual_create(student_id: str, resource_name: str, request: Request):
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        resource = get_resource(student_id, resource_name)
        student = optional_student(request)
        created_by_role = "visitor"
        if resource["access_mode"] == "public_read":
            if student is None:
                raise HTTPException(status_code=401, detail="请先登录")
            require_space_owner(student_id, student)
            created_by_role = "author"
        elif student is not None and student.get("studentId") == student_id:
            created_by_role = "author"
        else:
            enforce_public_post_limits(request, student_id)
        payload = await read_json_object(request)
        enforce_record_caps(student_id, resource_name)
        record_id = f"rec_{uuid4().hex}"
        stamp = now_iso()
        ip = request_ip(request)
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO records
                (id, student_id, resource_name, payload_json, created_by_role, created_ip, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record_id, student_id, resource_name, json.dumps(payload, ensure_ascii=False), created_by_role, ip, stamp, stamp),
            )
        return success_response("数据新增成功", decode_record(get_record(student_id, resource_name, record_id)))

    @app.put("/api/{student_id}/{resource_name}/{record_id}")
    async def virtual_update(student_id: str, resource_name: str, record_id: str, request: Request, student: dict[str, Any] = Depends(require_student)):
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        require_space_owner(student_id, student)
        get_resource(student_id, resource_name)
        get_record(student_id, resource_name, record_id)
        payload = await read_json_object(request)
        stamp = now_iso()
        with connect() as conn:
            conn.execute(
                """
                UPDATE records
                SET payload_json = ?, updated_at = ?
                WHERE id = ? AND student_id = ? AND resource_name = ?
                """,
                (json.dumps(payload, ensure_ascii=False), stamp, record_id, student_id, resource_name),
            )
        return success_response("数据已更新", decode_record(get_record(student_id, resource_name, record_id)))

    @app.delete("/api/{student_id}/{resource_name}/{record_id}")
    async def virtual_delete(student_id: str, resource_name: str, record_id: str, student: dict[str, Any] = Depends(require_student)):
        student_id = validate_student_id(student_id)
        resource_name = validate_resource_name(resource_name)
        require_space_owner(student_id, student)
        row = get_record(student_id, resource_name, record_id)
        with connect() as conn:
            conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        return success_response("数据已删除", decode_record(row))

    @app.get("/sites/{student_id}/api-config.js")
    async def site_api_config(student_id: str, request: Request):
        student_id = validate_student_id(student_id)
        redirect = site_origin_redirect(request, student_id, "api-config.js")
        if redirect:
            return redirect
        return Response(
            content=(
                f"window.API_ROOT = {json.dumps(public_base_url, ensure_ascii=False)};\n"
                f"window.API_BASE = {json.dumps(student_api_base_url(student_id), ensure_ascii=False)};\n"
            ),
            media_type="application/javascript; charset=utf-8",
        )

    @app.get("/sites/{student_id}")
    async def site_index_no_slash(student_id: str):
        return RedirectResponse(student_site_path_url(student_id), status_code=308)

    @app.get("/sites/{student_id}/")
    async def site_index(student_id: str, request: Request):
        redirect = site_origin_redirect(request, student_id)
        if redirect:
            return redirect
        return serve_site_file(student_id, "index.html")

    @app.get("/sites/{student_id}/{file_path:path}")
    async def site_file(student_id: str, file_path: str, request: Request):
        redirect = site_origin_redirect(request, student_id, file_path)
        if redirect:
            return redirect
        return serve_site_file(student_id, file_path)

    def serve_site_file(student_id: str, file_path: str):
        path = resolve_site_file(student_id, file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="站点文件不存在，请先上传网站")
        content_type = site_content_type(path)
        headers = {"X-Content-Type-Options": "nosniff"}
        if app.state.site_sandbox_enabled and content_type.startswith("text/html"):
            headers["Content-Security-Policy"] = "sandbox allow-forms allow-modals allow-popups allow-scripts"
        return FileResponse(path=path, media_type=content_type, headers=headers)

    @app.get("/media/{student_id}/{file_id}/{filename}")
    async def media_file(student_id: str, file_id: str, filename: str, request: Request):
        student_id = validate_student_id(student_id)
        file_id = validate_file_id(file_id)
        redirect = media_origin_redirect(request, student_id, file_id, filename)
        if redirect:
            return redirect
        row = get_student_file(student_id, file_id)
        if filename != row["stored_name"]:
            raise HTTPException(status_code=404, detail="文件不存在")
        path = (files_root_for_student(student_id) / file_id / row["stored_name"]).resolve()
        try:
            path.relative_to(files_root_for_student(student_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="文件路径无效") from None
        if not path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(
            path=path,
            media_type=row["content_type"],
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        if exc.status_code == 404 and message == "Not Found":
            message = "接口不存在"
        return Response(
            content=json.dumps(error_payload(message), ensure_ascii=False),
            status_code=exc.status_code,
            media_type="application/json; charset=utf-8",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return Response(
            content=json.dumps(error_payload("参数错误"), ensure_ascii=False),
            status_code=400,
            media_type="application/json; charset=utf-8",
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return Response(
            content=json.dumps(error_payload("服务器内部错误"), ensure_ascii=False),
            status_code=500,
            media_type="application/json; charset=utf-8",
        )

    return app


app = create_app()

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ["FINAL_BACKEND_DATA_DIR"] = str(Path(tempfile.gettempdir()) / "final_backend_import_app")
os.environ["FINAL_BACKEND_ENABLE_TEACHER_KEY"] = "true"
os.environ["FINAL_BACKEND_TEACHER_KEY"] = "123456"
os.environ["FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY"] = "false"
os.environ["FINAL_BACKEND_ADMIN_PASSWORD"] = "admin-test-pass"
os.environ["FINAL_BACKEND_COOKIE_SECURE"] = "false"
os.environ["FINAL_BACKEND_ROOT_PATH"] = ""
os.environ["FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED"] = "true"

from main import create_app  # noqa: E402


TEACHER_HEADERS = {"X-Teacher-Key": "123456"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_ADMIN_PASSWORD", "admin-test-pass")
    monkeypatch.setenv("FINAL_BACKEND_COOKIE_SECURE", "false")
    monkeypatch.setenv("FINAL_BACKEND_ROOT_PATH", "")
    monkeypatch.delenv("FINAL_BACKEND_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FINAL_BACKEND_SITE_BASE_URL", raising=False)
    monkeypatch.delenv("FINAL_BACKEND_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("FINAL_BACKEND_HOST", raising=False)
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_FAILURE_LIMIT", "5")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_FAILURE_WINDOW_SECONDS", "300")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_LOCK_SECONDS", "300")
    app = create_app(data_dir=tmp_path / "data")
    return TestClient(app)


def assert_success(response, status_code: int = 200):
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body["success"] is True
    return body["data"]


def assert_error(response, status_code: int):
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body["success"] is False
    return body


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_student(client: TestClient, student_id: str, password: str = "pass12345") -> str:
    data = assert_success(
        client.post(
            "/api/admin/students",
            headers=TEACHER_HEADERS,
            json={
                "studentId": student_id,
                "password": password,
                "displayName": student_id,
                "className": "final-test",
                "enabled": True,
            },
        ),
        201,
    )
    return data["password"]


def login_student(client: TestClient, student_id: str, password: str = "pass12345") -> str:
    data = assert_success(
        client.post("/api/auth/login", json={"username": student_id, "password": password})
    )
    return data["token"]


def create_resource(
    client: TestClient,
    token: str,
    name: str,
    access_mode: str,
    display_name: str | None = None,
):
    return assert_success(
        client.post(
            "/api/student/resources",
            headers=auth_header(token),
            json={
                "resourceName": name,
                "displayName": display_name or name,
                "accessMode": access_mode,
            },
        ),
        201,
    )


def build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_student_and_admin_pages_are_operational_shells(client: TestClient):
    root = client.get("/")
    assert root.status_code == 200
    assert "/api-docs" in root.text
    assert "/docs" not in root.text

    student = client.get("/student")
    assert student.status_code == 200
    assert "期末作品学生管理" in student.text
    assert 'id="loginPanel"' in student.text
    assert 'id="workspace"' in student.text
    assert 'id="resourceFormMode"' in student.text
    assert 'id="cancelResourceEdit"' in student.text
    assert 'id="siteStatusBtn"' not in student.text
    assert "接口功能" in student.text
    assert "接口列表" in student.text
    assert "接口数据" in student.text
    assert "新增接口数据" in student.text
    assert 'id="recordFormModeBtn"' in student.text
    assert 'id="recordJsonModeBtn"' in student.text
    assert 'id="addRecordField"' in student.text
    assert 'id="formatRecordJson"' in student.text
    assert 'id="recordHelpBtn"' in student.text
    assert 'id="recordHelpDialog"' in student.text
    assert "批量新增" in student.text
    assert "对象数组" in student.text
    assert "新增数据 JSON" not in student.text
    assert "startResourceEdit" in student.text

    admin = client.get("/admin")
    assert admin.status_code == 200
    assert "期末后端教师管理" in admin.text
    assert 'id="loginPanel"' in admin.text
    assert 'id="studentRows"' in admin.text
    assert 'id="docsLink"' in admin.text
    assert 'href="./docs"' in admin.text
    assert "openNoOpener" in admin.text
    assert "noopener,noreferrer" in admin.text
    assert "sessionStorage.getItem" in student.text
    assert "sessionStorage.setItem" in student.text


def test_student_api_docs_are_public_and_fastapi_docs_are_teacher_only(client: TestClient):
    api_docs = client.get("/api-docs")
    assert api_docs.status_code == 200
    assert "期末作品学生接口说明" in api_docs.text
    assert "API_BASE" in api_docs.text
    assert "接口权限" in api_docs.text
    assert "Authorization" in api_docs.text
    assert "/api/admin" not in api_docs.text
    assert "X-Teacher-Key" not in api_docs.text

    api_docs_slash = client.get("/api-docs/")
    assert api_docs_slash.status_code == 200
    assert "期末作品学生接口说明" in api_docs_slash.text

    docs_without_login = client.get("/docs", follow_redirects=False)
    assert docs_without_login.status_code == 303
    assert docs_without_login.headers["location"].endswith("/admin")
    assert_error(client.get("/openapi.json"), 401)

    login = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin-test-pass"},
    )
    assert_success(login)

    teacher_docs = client.get("/docs")
    assert teacher_docs.status_code == 200
    assert "SwaggerUIBundle" in teacher_docs.text
    assert "期末作品平台后端 - 教师调试文档" in teacher_docs.text

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "期末作品平台后端"


def test_teacher_creates_student_and_student_login(client: TestClient):
    status = assert_success(client.get("/api/admin/status", headers=TEACHER_HEADERS))
    assert status["students"] == 0

    password = create_student(client, "stu_login_001")
    assert password == "pass12345"

    token = login_student(client, "stu_login_001")
    me = assert_success(client.get("/api/auth/me", headers=auth_header(token)))
    assert me["user"]["studentId"] == "stu_login_001"

    assert_error(
        client.post("/api/auth/register", json={"username": "x", "password": "x"}),
        403,
    )

    assert_success(client.post("/api/auth/logout", headers=auth_header(token)))
    assert_error(client.get("/api/auth/me", headers=auth_header(token)), 401)


def test_existing_student_create_does_not_reset_password_or_enable(client: TestClient):
    sid = "stu_account_safe_001"
    create_student(client, sid, "original-pass")
    assert login_student(client, sid, "original-pass")

    assert_success(
        client.put(
            f"/api/admin/students/{sid}",
            headers=TEACHER_HEADERS,
            json={"enabled": False},
        )
    )

    duplicate = client.post(
        "/api/admin/students",
        headers=TEACHER_HEADERS,
        json={
            "studentId": sid,
            "displayName": "New Name",
            "className": "new-class",
            "enabled": True,
        },
    )
    assert_error(duplicate, 409)

    students = assert_success(client.get("/api/admin/students", headers=TEACHER_HEADERS))
    current = [item for item in students if item["studentId"] == sid][0]
    assert current["enabled"] is False

    assert_success(
        client.put(
            f"/api/admin/students/{sid}",
            headers=TEACHER_HEADERS,
            json={"displayName": "New Name"},
        )
    )
    students = assert_success(client.get("/api/admin/students", headers=TEACHER_HEADERS))
    current = [item for item in students if item["studentId"] == sid][0]
    assert current["displayName"] == "New Name"
    assert current["enabled"] is False

    assert_success(
        client.put(
            f"/api/admin/students/{sid}",
            headers=TEACHER_HEADERS,
            json={"enabled": True},
        )
    )
    assert login_student(client, sid, "original-pass")
    assert_error(client.post("/api/auth/login", json={"username": sid, "password": "changed-by-accident"}), 401)


def test_admin_can_reset_student_to_specific_password(client: TestClient):
    sid = "stu_specific_reset_001"
    create_student(client, sid, "old-pass-001")
    assert login_student(client, sid, "old-pass-001")

    reset = assert_success(
        client.post(
            f"/api/admin/students/{sid}/reset-password",
            headers=TEACHER_HEADERS,
            json={"password": "teacher-set-001"},
        )
    )
    assert reset["password"] == "teacher-set-001"
    assert reset["mustChangePassword"] is True

    assert_error(client.post("/api/auth/login", json={"username": sid, "password": "old-pass-001"}), 401)
    assert login_student(client, sid, "teacher-set-001")


def test_students_sync_imports_roster_test_accounts_and_password_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    roster = tmp_path / "students.json"
    roster.write_text(
        json.dumps(
            [
                {
                    "student_id": "20260001",
                    "code": "initial001",
                    "display_name": "正式学生",
                    "class_name": "测试班",
                    "enabled": True,
                    "note": "",
                },
                {
                    "student_id": "test_ass45_001",
                    "code": "testcode001",
                    "display_name": "接口测试学生001",
                    "class_name": "接口测试班",
                    "enabled": True,
                    "note": "长期测试账号",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_STUDENTS_FILE", str(roster))
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        status = assert_success(local.get("/api/admin/status", headers=TEACHER_HEADERS))
        assert status["studentsFile"] == str(roster.resolve())
        sync = assert_success(local.post("/api/admin/students/sync", headers=TEACHER_HEADERS))
        assert sync["totalInFile"] == 2
        assert sync["inserted"] == 2
        assert sync["testAccounts"] == 1

        login = assert_success(local.post("/api/auth/login", json={"username": "20260001", "password": "initial001"}))
        assert login["user"]["mustChangePassword"] is True
        token = login["token"]
        changed = assert_success(
            local.post(
                "/api/auth/change-password",
                headers=auth_header(token),
                json={"oldPassword": "initial001", "newPassword": "changed001"},
            )
        )
        assert changed["user"]["mustChangePassword"] is False
        assert_success(local.post("/api/auth/login", json={"username": "20260001", "password": "changed001"}))

        roster.write_text(
            json.dumps(
                [
                    {
                        "student_id": "20260001",
                        "code": "initial002",
                        "display_name": "正式学生",
                        "class_name": "测试班",
                        "enabled": True,
                        "note": "",
                    },
                    {
                        "student_id": "test_ass45_001",
                        "code": "testcode001",
                        "display_name": "接口测试学生001",
                        "class_name": "接口测试班",
                        "enabled": True,
                        "note": "长期测试账号",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        resync = assert_success(local.post("/api/admin/students/sync", headers=TEACHER_HEADERS))
        assert resync["currentPasswordsPreserved"] == 1
        assert_success(local.post("/api/auth/login", json={"username": "20260001", "password": "changed001"}))
        assert_error(local.post("/api/auth/login", json={"username": "20260001", "password": "initial002"}), 401)

        reset = assert_success(local.post("/api/admin/students/20260001/reset-password", headers=TEACHER_HEADERS, json={}))
        assert reset["password"] == "initial002"
        after_reset = assert_success(local.post("/api/auth/login", json={"username": "20260001", "password": "initial002"}))
        assert after_reset["user"]["mustChangePassword"] is True
        assert_success(local.post("/api/auth/login", json={"username": "test_ass45_001", "password": "testcode001"}))


def test_virtual_resources_enforce_access_modes(client: TestClient):
    sid = "stu_resource_001"
    create_student(client, sid)
    token = login_student(client, sid)

    create_resource(client, token, "products", "public_read")
    create_resource(client, token, "comments", "public_submit")
    create_resource(client, token, "orders", "private_collect")

    products = assert_success(client.get(f"/api/{sid}/products"))
    assert products["items"] == []
    assert products["total"] == 0
    assert_error(client.post(f"/api/{sid}/products", json={"title": "Book"}), 401)

    product = assert_success(
        client.post(
            f"/api/{sid}/products",
            headers=auth_header(token),
            json={"title": "Book", "price": 12},
        ),
        201,
    )
    assert product["createdByRole"] == "author"

    comment = assert_success(
        client.post(f"/api/{sid}/comments", json={"name": "visitor", "text": "good"}),
        201,
    )
    assert comment["createdByRole"] == "visitor"
    comments = assert_success(client.get(f"/api/{sid}/comments"))
    assert comments["items"][0]["data"]["text"] == "good"

    assert_error(client.delete(f"/api/{sid}/comments/{comment['id']}"), 401)
    updated = assert_success(
        client.put(
            f"/api/{sid}/comments/{comment['id']}",
            headers=auth_header(token),
            json={"name": "visitor", "text": "kept"},
        )
    )
    assert updated["data"]["text"] == "kept"
    assert_success(client.delete(f"/api/{sid}/comments/{comment['id']}", headers=auth_header(token)))

    order = assert_success(
        client.post(f"/api/{sid}/orders", json={"email": "visitor@example.com"}),
        201,
    )
    assert order["createdByRole"] == "visitor"
    assert_error(client.get(f"/api/{sid}/orders"), 401)
    orders = assert_success(client.get(f"/api/{sid}/orders", headers=auth_header(token)))
    assert orders["items"][0]["data"]["email"] == "visitor@example.com"


def test_student_spaces_are_isolated(client: TestClient):
    create_student(client, "stu_owner_001")
    owner_token = login_student(client, "stu_owner_001")
    create_student(client, "stu_other_001")
    other_token = login_student(client, "stu_other_001")

    create_resource(client, owner_token, "posts", "public_read")
    post = assert_success(
        client.post(
            "/api/stu_owner_001/posts",
            headers=auth_header(owner_token),
            json={"title": "Mine"},
        ),
        201,
    )

    assert_error(
        client.post(
            "/api/stu_owner_001/posts",
            headers=auth_header(other_token),
            json={"title": "Wrong owner"},
        ),
        403,
    )
    assert_error(
        client.put(
            f"/api/stu_owner_001/posts/{post['id']}",
            headers=auth_header(other_token),
            json={"title": "Changed"},
        ),
        403,
    )
    assert_error(
        client.delete(f"/api/stu_owner_001/posts/{post['id']}", headers=auth_header(other_token)),
        403,
    )


def test_public_write_limits_and_record_caps(client: TestClient):
    sid = "stu_limits_001"
    create_student(client, sid)
    token = login_student(client, sid)
    create_resource(client, token, "comments", "public_submit")

    client.app.state.public_post_ip_limit = 1
    assert_success(client.post(f"/api/{sid}/comments", json={"text": "first"}), 201)
    assert_error(client.post(f"/api/{sid}/comments", json={"text": "second"}), 429)

    create_resource(client, token, "orders", "private_collect")
    client.app.state.max_records_per_resource = 1
    assert_success(
        client.post(f"/api/{sid}/orders", headers=auth_header(token), json={"name": "first"}),
        201,
    )
    assert_error(
        client.post(f"/api/{sid}/orders", headers=auth_header(token), json={"name": "second"}),
        429,
    )

    create_resource(client, token, "messages", "public_submit")
    client.app.state.public_post_ip_limit = 100
    client.app.state.max_json_body_bytes = 5
    assert_error(client.post(f"/api/{sid}/messages", json={"text": "too long"}), 413)


def test_non_multipart_body_limit_rejects_before_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINAL_BACKEND_MAX_JSON_BODY_BYTES", "32")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        response = local.post(
            "/api/not-a-route",
            content=b"x" * 64,
            headers={"content-type": "application/json"},
        )
        assert_error(response, 413)


def test_body_limit_does_not_block_multipart_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINAL_BACKEND_MAX_JSON_BODY_BYTES", "512")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        create_student(local, "stu_multipart_limit")
        token = login_student(local, "stu_multipart_limit")
        content = b"\x89PNG\r\n" + (b"x" * 1024)
        uploaded = assert_success(
            local.post(
                "/api/student/files",
                headers=auth_header(token),
                files={"file": ("cover.png", content, "image/png")},
            ),
            201,
        )
        assert uploaded["sizeBytes"] == len(content)


def test_student_site_upload_and_static_files(client: TestClient):
    sid = "stu_site_001"
    create_student(client, sid)
    token = login_student(client, sid)

    site_zip = build_zip(
        {
            "index.html": "<!doctype html><title>Final Site</title><h1>Hello</h1>",
            "style.css": "body { color: #222; }",
            "app.js": "window.rootLoaded = true;",
            "js/app.js": "window.loaded = true;",
        }
    )
    data = assert_success(
        client.post(
            "/api/student/site/upload",
            headers=auth_header(token),
            files={"file": ("site.zip", site_zip, "application/zip")},
        ),
        201,
    )
    assert data["siteUrl"] == f"/sites/{sid}/"

    index = client.get(f"/sites/{sid}/")
    assert index.status_code == 200
    assert "Final Site" in index.text

    no_slash = client.get(f"/sites/{sid}", follow_redirects=False)
    assert no_slash.status_code == 308
    assert no_slash.headers["location"].endswith(f"/sites/{sid}/")

    config = client.get(f"/sites/{sid}/api-config.js")
    assert config.status_code == 200
    assert 'window.API_ROOT = "";' in config.text
    assert f'window.API_BASE = "/api/{sid}"' in config.text

    script = client.get(f"/sites/{sid}/js/app.js")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("application/javascript")

    root_script = client.get(f"/sites/{sid}/app.js")
    assert root_script.status_code == 200
    assert root_script.headers["content-type"].startswith("application/javascript")
    assert root_script.headers["x-content-type-options"] == "nosniff"

    style = client.get(f"/sites/{sid}/style.css")
    assert style.status_code == 200
    assert style.headers["content-type"].startswith("text/css")

    bad_zip = build_zip({"index.html": "ok", "../evil.html": "bad"})
    assert_error(
        client.post(
            "/api/student/site/upload",
            headers=auth_header(token),
            files={"file": ("bad.zip", bad_zip, "application/zip")},
        ),
        400,
    )
    assert "Final Site" in client.get(f"/sites/{sid}/").text


def test_student_site_upload_replace_failure_keeps_old_site(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    sid = "stu_site_safe_001"
    create_student(client, sid)
    token = login_student(client, sid)

    old_zip = build_zip({"index.html": "<!doctype html><title>Old Site</title>"})
    assert_success(
        client.post(
            "/api/student/site/upload",
            headers=auth_header(token),
            files={"file": ("site.zip", old_zip, "application/zip")},
        ),
        201,
    )

    original_replace = Path.replace

    def fail_new_site_replace(self: Path, target) -> Path:
        target_path = Path(target)
        if self.name.startswith(f".{sid}-upload-") and target_path.name == sid:
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_new_site_replace)
    new_zip = build_zip({"index.html": "<!doctype html><title>New Site</title>"})
    assert_error(
        client.post(
            "/api/student/site/upload",
            headers=auth_header(token),
            files={"file": ("site.zip", new_zip, "application/zip")},
        ),
        500,
    )

    index = client.get(f"/sites/{sid}/")
    assert index.status_code == 200
    assert "Old Site" in index.text
    backup_index = client.app.state.backups_dir / "sites" / sid / "latest" / "index.html"
    assert "Old Site" in backup_index.read_text(encoding="utf-8")


def test_student_file_upload_list_media_and_delete(client: TestClient):
    sid = "stu_file_001"
    create_student(client, sid)
    token = login_student(client, sid)
    content = b"fake image bytes"

    uploaded = assert_success(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("cover.png", content, "image/png")},
        ),
        201,
    )
    assert uploaded["studentId"] == sid
    assert uploaded["originalName"] == "cover.png"
    assert uploaded["kind"] == "image"
    assert uploaded["sizeBytes"] == len(content)
    assert uploaded["fileUrl"].startswith(f"/media/{sid}/{uploaded['id']}/")

    media = client.get(uploaded["fileUrl"])
    assert media.status_code == 200
    assert media.content == content
    assert media.headers["content-type"].startswith("image/png")

    files = assert_success(client.get("/api/student/files", headers=auth_header(token)))
    assert files["total"] == 1
    assert len(files["items"]) == 1
    assert files["items"][0]["fileUrl"] == uploaded["fileUrl"]

    deleted = assert_success(client.delete(f"/api/student/files/{uploaded['id']}", headers=auth_header(token)))
    assert deleted["id"] == uploaded["id"]
    assert_error(client.get(uploaded["fileUrl"]), 404)
    assert_success(client.get("/api/student/files", headers=auth_header(token)))["items"] == []


def test_student_file_type_size_and_count_limits(client: TestClient):
    sid = "stu_file_limits_001"
    create_student(client, sid)
    token = login_student(client, sid)

    assert_error(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("bad.exe", b"bad", "application/octet-stream")},
        ),
        400,
    )

    client.app.state.file_kind_max_bytes["image"] = 4
    assert_error(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("big.jpg", b"12345", "image/jpeg")},
        ),
        413,
    )
    assert list(client.app.state.tmp_dir.glob("*")) == []

    client.app.state.file_kind_max_bytes["image"] = 100
    client.app.state.max_student_file_count = 1
    assert_success(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("one.jpg", b"one", "image/jpeg")},
        ),
        201,
    )
    assert_error(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("two.jpg", b"two", "image/jpeg")},
        ),
        429,
    )


def test_admin_cookie_login_when_teacher_key_is_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("FINAL_BACKEND_COOKIE_SECURE", "true")
    monkeypatch.setenv("FINAL_BACKEND_ROOT_PATH", "")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app, base_url="https://testserver") as local:
        assert_error(local.get("/api/admin/status", headers=TEACHER_HEADERS), 401)

        login = local.post(
            "/api/admin/login",
            json={"username": "admin", "password": "admin-secret"},
        )
        assert_success(login)
        assert "Secure" in login.headers["set-cookie"]

        status = assert_success(local.get("/api/admin/status"))
        assert status["teacherKeyEnabled"] is False


def test_root_path_public_urls_and_site_base_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sid = "stu_url_001"
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_ADMIN_PASSWORD", "admin-test-pass")
    monkeypatch.setenv("FINAL_BACKEND_ROOT_PATH", "/2025-2026-2/final")
    monkeypatch.setenv("FINAL_BACKEND_PUBLIC_BASE_URL", "https://course.example.com/2025-2026-2/final")
    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://sites.example.com")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        status = assert_success(local.get("/api/admin/status", headers=TEACHER_HEADERS))
        assert status["rootPath"] == "/2025-2026-2/final"
        assert status["publicBaseUrl"] == "https://course.example.com/2025-2026-2/final"
        assert status["siteBaseUrl"] == "https://sites.example.com"

        create_student(local, sid)
        token = login_student(local, sid)
        site_zip = build_zip({"index.html": "<!doctype html><title>URL Site</title>"})
        upload = assert_success(
            local.post(
                "/api/student/site/upload",
                headers=auth_header(token),
                files={"file": ("site.zip", site_zip, "application/zip")},
            ),
            201,
        )
        assert upload["siteUrl"] == f"https://sites.example.com/{sid}/"

        site_status = assert_success(local.get("/api/student/site/status", headers=auth_header(token)))
        assert site_status["siteUrl"] == f"https://sites.example.com/{sid}/"

        config = local.get(f"/sites/{sid}/api-config.js")
        assert config.status_code == 200
        assert 'window.API_ROOT = "https://course.example.com/2025-2026-2/final"' in config.text
        assert (
            f'window.API_BASE = "https://course.example.com/2025-2026-2/final/api/{sid}"'
            in config.text
        )

        export_token = assert_success(local.post("/api/admin/export-token", headers=TEACHER_HEADERS, json={}))
        assert export_token["downloadUrl"].startswith(
            "https://course.example.com/2025-2026-2/final/api/admin/export?token="
        )

        file_upload = assert_success(
            local.post(
                "/api/student/files",
                headers=auth_header(token),
                files={"file": ("poster.jpg", b"poster", "image/jpeg")},
            ),
            201,
        )
        assert file_upload["fileUrl"].startswith(f"https://sites.example.com/media/{sid}/")
        media_path = file_upload["fileUrl"].replace("https://sites.example.com", "")
        assert local.get(media_path).content == b"poster"


def test_separate_site_origin_is_enforced_for_uploaded_sites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sid = "stu_origin_001"
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN", "true")
    monkeypatch.setenv("FINAL_BACKEND_PUBLIC_BASE_URL", "https://course.example.com/2025-2026-2/final")
    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://sites.example.com")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app, base_url="https://course.example.com") as local:
        create_student(local, sid)
        token = login_student(local, sid)
        site_zip = build_zip({"index.html": "<!doctype html><title>Origin Site</title>"})
        assert_success(
            local.post(
                "/api/student/site/upload",
                headers=auth_header(token),
                files={"file": ("site.zip", site_zip, "application/zip")},
            ),
            201,
        )

        course_site = local.get(
            f"/sites/{sid}/",
            headers={"X-Forwarded-Host": "course.example.com"},
            follow_redirects=False,
        )
        assert course_site.status_code == 308
        assert course_site.headers["location"] == f"https://sites.example.com/{sid}/"

        course_config = local.get(
            f"/sites/{sid}/api-config.js",
            headers={"X-Forwarded-Host": "course.example.com"},
            follow_redirects=False,
        )
        assert course_config.status_code == 308
        assert course_config.headers["location"] == f"https://sites.example.com/{sid}/api-config.js"

        site_index = local.get(f"/sites/{sid}/", headers={"X-Forwarded-Host": "sites.example.com"})
        assert site_index.status_code == 200
        assert "Origin Site" in site_index.text

        media_upload = assert_success(
            local.post(
                "/api/student/files",
                headers=auth_header(token),
                files={"file": ("origin.jpg", b"origin-media", "image/jpeg")},
            ),
            201,
        )
        media_path = media_upload["fileUrl"].replace("https://sites.example.com", "")
        course_media = local.get(
            media_path,
            headers={"X-Forwarded-Host": "course.example.com"},
            follow_redirects=False,
        )
        assert course_media.status_code == 308
        assert course_media.headers["location"] == media_upload["fileUrl"]

        site_media = local.get(media_path, headers={"X-Forwarded-Host": "sites.example.com"})
        assert site_media.status_code == 200
        assert site_media.content == b"origin-media"


def test_online_cors_allows_only_configured_site_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_CORS", "true")
    monkeypatch.setenv("FINAL_BACKEND_CORS_ORIGINS", "https://sites.example.com")
    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://sites.example.com")
    monkeypatch.setenv("FINAL_BACKEND_PUBLIC_BASE_URL", "https://course.example.com/2025-2026-2/final")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        allowed = local.options(
            "/api/auth/login",
            headers={
                "Origin": "https://sites.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://sites.example.com"

        denied = local.options(
            "/api/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers


def test_teacher_key_default_is_disabled_and_default_key_can_be_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", raising=False)
    monkeypatch.delenv("FINAL_BACKEND_TEACHER_KEY", raising=False)
    monkeypatch.setenv("FINAL_BACKEND_ADMIN_PASSWORD", "admin-secret")
    app = create_app(data_dir=tmp_path / "default-disabled")

    with TestClient(app) as local:
        assert_error(local.get("/api/admin/status", headers=TEACHER_HEADERS), 401)

    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "true")
    monkeypatch.delenv("FINAL_BACKEND_TEACHER_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app(data_dir=tmp_path / "blocked-default")


def test_login_failure_rate_limit_for_student_and_admin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_FAILURE_LIMIT", "2")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_FAILURE_WINDOW_SECONDS", "300")
    monkeypatch.setenv("FINAL_BACKEND_LOGIN_LOCK_SECONDS", "300")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        create_student(local, "stu_rate_001")
        assert_error(local.post("/api/auth/login", json={"username": "stu_rate_001", "password": "bad"}), 401)
        assert_error(local.post("/api/auth/login", json={"username": "stu_rate_001", "password": "bad"}), 401)
        assert_error(
            local.post("/api/auth/login", json={"username": "stu_rate_001", "password": "pass12345"}),
            429,
        )

        assert_error(local.post("/api/admin/login", json={"username": "admin", "password": "bad"}), 401)
        assert_error(local.post("/api/admin/login", json={"username": "admin", "password": "bad"}), 401)
        assert_error(
            local.post("/api/admin/login", json={"username": "admin", "password": "admin-secret"}),
            429,
        )


def test_virtual_records_and_admin_lists_are_paginated(client: TestClient):
    sid = "stu_page_001"
    create_student(client, sid)
    token = login_student(client, sid)
    create_resource(client, token, "posts", "public_read")

    for index in range(3):
        assert_success(
            client.post(
                f"/api/{sid}/posts",
                headers=auth_header(token),
                json={"title": f"post-{index}"},
            ),
            201,
        )

    page_1 = assert_success(client.get(f"/api/{sid}/posts?page=1&pageSize=2"))
    assert page_1["total"] == 3
    assert page_1["page"] == 1
    assert page_1["pageSize"] == 2
    assert len(page_1["items"]) == 2

    page_2 = assert_success(client.get(f"/api/{sid}/posts?page=2&pageSize=2"))
    assert page_2["total"] == 3
    assert len(page_2["items"]) == 1

    assert_error(client.get(f"/api/{sid}/posts?page=0&pageSize=2"), 400)
    assert_error(client.get(f"/api/{sid}/posts?page=1&pageSize=999"), 400)

    admin_records = assert_success(
        client.get(f"/api/admin/students/{sid}/records?page=1&pageSize=2", headers=TEACHER_HEADERS)
    )
    assert admin_records["total"] == 3
    assert len(admin_records["items"]) == 2

    for name in ["one.jpg", "two.jpg"]:
        assert_success(
            client.post(
                "/api/student/files",
                headers=auth_header(token),
                files={"file": (name, b"image", "image/jpeg")},
            ),
            201,
        )
    admin_files = assert_success(
        client.get(f"/api/admin/students/{sid}/files?page=1&pageSize=1", headers=TEACHER_HEADERS)
    )
    assert admin_files["total"] == 2
    assert len(admin_files["items"]) == 1


def test_admin_clear_actions_create_backups_and_audits(client: TestClient):
    sid = "stu_backup_001"
    create_student(client, sid)
    token = login_student(client, sid)
    create_resource(client, token, "posts", "public_read")
    assert_success(
        client.post(f"/api/{sid}/posts", headers=auth_header(token), json={"title": "keep me"}),
        201,
    )
    site_zip = build_zip({"index.html": "<!doctype html><title>Backup Site</title>"})
    assert_success(
        client.post(
            "/api/student/site/upload",
            headers=auth_header(token),
            files={"file": ("site.zip", site_zip, "application/zip")},
        ),
        201,
    )
    uploaded = assert_success(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("cover.png", b"cover", "image/png")},
        ),
        201,
    )

    records_clear = assert_success(
        client.delete(f"/api/admin/students/{sid}/records", headers=TEACHER_HEADERS)
    )
    assert records_clear["recordsDeleted"] == 1
    records_manifest = json.loads(Path(records_clear["backup"]["manifestPath"]).read_text(encoding="utf-8"))
    assert records_manifest["summary"]["records"][0]["data"]["title"] == "keep me"
    assert assert_success(client.get(f"/api/{sid}/posts"))["total"] == 0

    site_clear = assert_success(
        client.delete(f"/api/admin/students/{sid}/site", headers=TEACHER_HEADERS)
    )
    site_manifest = json.loads(Path(site_clear["backup"]["manifestPath"]).read_text(encoding="utf-8"))
    assert site_manifest["summary"]["siteExisted"] is True
    assert "Backup Site" in (Path(site_clear["backup"]["backupPath"]) / "site" / "index.html").read_text(encoding="utf-8")
    assert client.get(f"/sites/{sid}/").status_code == 404

    files_clear = assert_success(
        client.delete(f"/api/admin/students/{sid}/files", headers=TEACHER_HEADERS)
    )
    assert files_clear["filesDeleted"] == 1
    files_manifest = json.loads(Path(files_clear["backup"]["manifestPath"]).read_text(encoding="utf-8"))
    assert files_manifest["summary"]["files"][0]["id"] == uploaded["id"]
    assert (Path(files_clear["backup"]["backupPath"]) / "files" / uploaded["id"]).exists()
    assert_error(client.get(uploaded["fileUrl"]), 404)

    with sqlite3.connect(client.app.state.db_path) as conn:
        rows = conn.execute(
            "SELECT action, student_id FROM admin_audits WHERE student_id = ? ORDER BY created_at",
            (sid,),
        ).fetchall()
    assert [row[0] for row in rows] == ["clear-records", "clear-site", "clear-files"]
    assert all(row[1] == sid for row in rows)


def test_admin_can_export_and_clear_records_by_resource(client: TestClient):
    sid = "stu_resource_admin_001"
    create_student(client, sid)
    token = login_student(client, sid)
    create_resource(client, token, "posts", "public_read")
    create_resource(client, token, "comments", "public_submit")

    assert_success(client.post(f"/api/{sid}/posts", headers=auth_header(token), json={"title": "post"}), 201)
    assert_success(client.post(f"/api/{sid}/comments", json={"text": "comment"}), 201)

    posts = assert_success(
        client.get(f"/api/admin/students/{sid}/resources/posts/records?page=1&pageSize=10", headers=TEACHER_HEADERS)
    )
    assert posts["total"] == 1
    assert posts["items"][0]["resourceName"] == "posts"
    assert posts["items"][0]["data"]["title"] == "post"

    export = client.get(f"/api/admin/students/{sid}/resources/posts/export", headers=TEACHER_HEADERS)
    assert export.status_code == 200
    assert "final_backend_stu_resource_admin_001_posts.json" in export.headers["content-disposition"]
    exported = json.loads(export.content.decode("utf-8"))
    assert exported["resource"]["resource_name"] == "posts"
    assert exported["records"][0]["data"]["title"] == "post"

    cleared = assert_success(
        client.delete(f"/api/admin/students/{sid}/resources/posts/records", headers=TEACHER_HEADERS)
    )
    assert cleared["recordsDeleted"] == 1
    manifest = json.loads(Path(cleared["backup"]["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["action"] == "clear-resource-records"
    assert manifest["summary"]["resourceName"] == "posts"

    assert assert_success(client.get(f"/api/{sid}/posts"))["total"] == 0
    comments = assert_success(client.get(f"/api/{sid}/comments"))
    assert comments["total"] == 1
    assert comments["items"][0]["data"]["text"] == "comment"


def test_admin_can_delete_single_record_and_file_with_backup(client: TestClient):
    sid = "stu_admin_single_delete_001"
    create_student(client, sid)
    token = login_student(client, sid)
    create_resource(client, token, "comments", "public_submit")

    first = assert_success(client.post(f"/api/{sid}/comments", json={"text": "remove"}), 201)
    kept = assert_success(client.post(f"/api/{sid}/comments", json={"text": "keep"}), 201)
    record_deleted = assert_success(
        client.delete(f"/api/admin/students/{sid}/records/{first['id']}", headers=TEACHER_HEADERS)
    )
    assert record_deleted["recordDeleted"] == 1
    record_manifest = json.loads(Path(record_deleted["backup"]["manifestPath"]).read_text(encoding="utf-8"))
    assert record_manifest["action"] == "delete-record"
    assert record_manifest["summary"]["record"]["data"]["text"] == "remove"
    records = assert_success(client.get(f"/api/{sid}/comments"))
    assert records["total"] == 1
    assert records["items"][0]["id"] == kept["id"]

    one = assert_success(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("one.png", b"one", "image/png")},
        ),
        201,
    )
    two = assert_success(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("two.png", b"two", "image/png")},
        ),
        201,
    )
    file_deleted = assert_success(
        client.delete(f"/api/admin/students/{sid}/files/{one['id']}", headers=TEACHER_HEADERS)
    )
    assert file_deleted["filesDeleted"] == 1
    file_manifest = json.loads(Path(file_deleted["backup"]["manifestPath"]).read_text(encoding="utf-8"))
    assert file_manifest["action"] == "delete-file"
    assert file_manifest["summary"]["file"]["id"] == one["id"]
    assert (Path(file_deleted["backup"]["backupPath"]) / f"file-{one['id']}").exists()
    assert_error(client.get(one["fileUrl"]), 404)
    assert client.get(two["fileUrl"]).status_code == 200
    files = assert_success(client.get(f"/api/admin/students/{sid}/files", headers=TEACHER_HEADERS))
    assert files["total"] == 1
    assert files["items"][0]["id"] == two["id"]


def test_admin_student_archive_contains_data_site_and_media(client: TestClient):
    sid = "stu_archive_001"
    create_student(client, sid)
    token = login_student(client, sid)
    create_resource(client, token, "posts", "public_read")
    assert_success(client.post(f"/api/{sid}/posts", headers=auth_header(token), json={"title": "archived"}), 201)

    assert_success(
        client.post(
            "/api/student/site/upload",
            headers=auth_header(token),
            files={"file": ("site.zip", build_zip({"index.html": "<!doctype html><title>Archive Site</title>" }), "application/zip")},
        ),
        201,
    )
    uploaded = assert_success(
        client.post(
            "/api/student/files",
            headers=auth_header(token),
            files={"file": ("cover.png", b"cover-bytes", "image/png")},
        ),
        201,
    )

    response = client.get(f"/api/admin/students/{sid}/archive", headers=TEACHER_HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "final_backend_archive_stu_archive_001.zip" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "students.json", "resources.json", "records.json", "files.json", "site/index.html"}.issubset(names)
        assert any(name.startswith(f"media/{uploaded['id']}/") for name in names)
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["studentId"] == sid
        assert manifest["recordCount"] == 1
        records = json.loads(archive.read("records.json").decode("utf-8"))
        assert records[0]["data"]["title"] == "archived"
        assert "Archive Site" in archive.read("site/index.html").decode("utf-8")


def test_public_post_rate_limit_uses_trusted_proxy_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sid = "stu_proxy_001"
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_TRUST_PROXY_HEADERS", "true")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        create_student(local, sid)
        token = login_student(local, sid)
        create_resource(local, token, "comments", "public_submit")
        local.app.state.public_post_ip_limit = 1

        assert_success(
            local.post(f"/api/{sid}/comments", headers={"X-Forwarded-For": "10.0.0.1"}, json={"text": "one"}),
            201,
        )
        assert_success(
            local.post(f"/api/{sid}/comments", headers={"X-Forwarded-For": "10.0.0.2"}, json={"text": "two"}),
            201,
        )
        assert_error(
            local.post(f"/api/{sid}/comments", headers={"X-Forwarded-For": "10.0.0.1"}, json={"text": "again"}),
            429,
        )


def test_trust_proxy_headers_status_warns_when_host_is_public(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("FINAL_BACKEND_HOST", "0.0.0.0")
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        status = assert_success(local.get("/api/admin/status", headers=TEACHER_HEADERS))
        assert status["backendHost"] == "0.0.0.0"
        assert status["deploymentWarnings"]
        assert "FINAL_BACKEND_TRUST_PROXY_HEADERS=true" in status["deploymentWarnings"][0]


def test_status_warns_for_unsafe_online_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_TEACHER_KEY", "true")
    monkeypatch.setenv("FINAL_BACKEND_TEACHER_KEY", "123456")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY", "false")
    monkeypatch.setenv("FINAL_BACKEND_PUBLIC_BASE_URL", "https://course.example.com/final")
    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://sites.example.com")
    monkeypatch.setenv("FINAL_BACKEND_COOKIE_SECURE", "false")
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN", "false")
    monkeypatch.setenv("FINAL_BACKEND_ENABLE_CORS", "true")
    monkeypatch.delenv("FINAL_BACKEND_CORS_ORIGINS", raising=False)
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as local:
        status = assert_success(local.get("/api/admin/status", headers=TEACHER_HEADERS))
        warnings = "\n".join(status["deploymentWarnings"])
        assert status["corsAllowOrigins"] == ["*"]
        assert "FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=false" in warnings
        assert "FINAL_BACKEND_COOKIE_SECURE=false" in warnings
        assert "默认教师密钥" in warnings
        assert "FINAL_BACKEND_CORS_ORIGINS" in warnings


def test_separate_site_origin_can_be_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN", "true")
    monkeypatch.setenv("FINAL_BACKEND_PUBLIC_BASE_URL", "https://course.example.com/final")
    monkeypatch.delenv("FINAL_BACKEND_SITE_BASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        create_app(data_dir=tmp_path / "missing-site")

    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://course.example.com/sites")
    with pytest.raises(RuntimeError):
        create_app(data_dir=tmp_path / "same-origin")

    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://course.example.com:9443")
    with pytest.raises(RuntimeError):
        create_app(data_dir=tmp_path / "same-host-different-port")

    monkeypatch.setenv("FINAL_BACKEND_SITE_BASE_URL", "https://sites.example.com")
    app = create_app(data_dir=tmp_path / "different-origin")
    with TestClient(app) as local:
        login = local.post("/api/admin/login", json={"username": "admin", "password": app.state.admin_password})
        assert_success(login)
        status = assert_success(local.get("/api/admin/status"))
        assert status["requireSeparateSiteOrigin"] is True


def test_gitignore_excludes_runtime_upload_dirs():
    text = (BACKEND_DIR / ".gitignore").read_text(encoding="utf-8")
    assert "data/files/" in text
    assert "data/backups/" in text
    assert "data/tmp/" in text

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from prepare_demo_sites import demo_config_v2, make_zip, ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload final demo sites by student accounts only.")
    parser.add_argument("--base-url", required=True, help="Backend public base URL, for example https://host/final")
    parser.add_argument("--student-password", default="123456")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--out-dir", default=r"C:\tmp")
    parser.add_argument("--keep-records", action="store_true", help="Do not clear demo resource records before seeding")
    return parser.parse_args()


def login_student(client: httpx.Client, student_id: str, password: str) -> str:
    data = ok(client.post("/api/auth/login", json={"username": student_id, "password": password}), f"login {student_id}")
    return data["token"]


def resource_name(resource: dict[str, Any]) -> str:
    return resource.get("resource_name") or resource.get("resourceName") or ""


def ensure_resource(client: httpx.Client, headers: dict[str, str], resource: dict[str, Any]) -> None:
    existing = ok(client.get("/api/student/resources", headers=headers), "list resources") or []
    names = {resource_name(item) for item in existing}
    name = resource["resourceName"]
    if name in names:
        update_payload = {
            "displayName": resource.get("displayName", ""),
            "accessMode": resource.get("accessMode", "public_read"),
        }
        ok(
            client.put(f"/api/student/resources/{quote(name, safe='')}", headers=headers, json=update_payload),
            f"update resource {name}",
        )
        return
    ok(client.post("/api/student/resources", headers=headers, json=resource), f"create resource {name}")


def clear_resource_records(client: httpx.Client, headers: dict[str, str], student_id: str, resource_name_value: str) -> int:
    deleted = 0
    while True:
        page = ok(
            client.get(
                f"/api/{quote(student_id, safe='')}/{quote(resource_name_value, safe='')}?page=1&pageSize=50",
                headers=headers,
            ),
            f"list {student_id}/{resource_name_value}",
        )
        items = page.get("items", []) if isinstance(page, dict) else []
        if not items:
            return deleted
        for item in items:
            record_id = item.get("id")
            if not record_id:
                continue
            ok(
                client.delete(
                    f"/api/{quote(student_id, safe='')}/{quote(resource_name_value, safe='')}/{quote(record_id, safe='')}",
                    headers=headers,
                ),
                f"delete {student_id}/{resource_name_value}/{record_id}",
            )
            deleted += 1


def seed_records(client: httpx.Client, headers: dict[str, str], student_id: str, seed: list[tuple[str, dict[str, Any]]]) -> int:
    created = 0
    created_posts: dict[str, str] = {}
    for resource_name_value, payload_in in seed:
        payload = dict(payload_in)
        post_slug = payload.pop("postSlug", "")
        if post_slug:
            payload["postId"] = created_posts.get(post_slug, post_slug)
        result = ok(
            client.post(
                f"/api/{quote(student_id, safe='')}/{quote(resource_name_value, safe='')}",
                headers=headers,
                json=payload,
            ),
            f"seed {student_id} {resource_name_value}",
        )
        if resource_name_value == "posts":
            created_posts[payload.get("slug", "")] = result["id"]
        created += 1
    return created


def upload_site(client: httpx.Client, headers: dict[str, str], site_dir: Path, zip_path: Path) -> dict[str, Any]:
    zip_file = make_zip(site_dir, zip_path)
    with zip_file.open("rb") as file_obj:
        ok(
            client.post(
                "/api/student/site/upload",
                headers=headers,
                files={"file": (zip_file.name, file_obj, "application/zip")},
            ),
            f"upload site {site_dir.name}",
        )
    return ok(client.get("/api/student/site/status", headers=headers), f"site status {site_dir.name}")


def main() -> None:
    args = parse_args()
    workspace = Path(args.workspace)
    out_dir = Path(args.out_dir)
    configs = demo_config_v2(workspace, out_dir, args.student_password)
    prepared: list[dict[str, Any]] = []

    for student_id, config in configs.items():
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60.0, trust_env=False) as client:
            token = login_student(client, student_id, config["password"])
            headers = {"Authorization": "Bearer " + token}
            json_headers = {**headers, "Content-Type": "application/json"}
            for resource in config["resources"]:
                ensure_resource(client, json_headers, resource)
            deleted_total = 0
            if not args.keep_records:
                for resource in config["resources"]:
                    deleted_total += clear_resource_records(client, headers, student_id, resource["resourceName"])
            created_total = seed_records(client, json_headers, student_id, config["seed"])
            status = upload_site(client, headers, config["site_dir"], config["zip"])
            prepared.append({
                "student": student_id,
                "siteUrl": status.get("siteUrl"),
                "zip": str(config["zip"]),
                "resources": [item["resourceName"] for item in config["resources"]],
                "deletedRecords": deleted_total,
                "createdRecords": created_total,
            })

    print(json.dumps(prepared, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

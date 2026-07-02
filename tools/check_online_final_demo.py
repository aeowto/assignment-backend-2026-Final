from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check online final backend demo and student UI state.")
    parser.add_argument("--course-url", default="https://hw.codedock.top/2025-2026-2/final")
    parser.add_argument("--site-url", default="https://sites.hw.codedock.top")
    return parser.parse_args()


def get_text(client: httpx.Client, url: str) -> tuple[httpx.Response, str]:
    response = client.get(url)
    return response, response.text


def page_summary(response: httpx.Response, text: str) -> dict[str, Any]:
    return {
        "status": response.status_code,
        "contentType": response.headers.get("content-type", ""),
        "sample": text[:160],
    }


def api_total(client: httpx.Client, course_url: str, student_id: str, resource: str) -> dict[str, Any]:
    url = f"{course_url}/api/{student_id}/{resource}?page=1&pageSize=50"
    response = client.get(url)
    body = response.json()
    data = body.get("data", {})
    return {
        "url": url,
        "status": response.status_code,
        "success": body.get("success"),
        "total": data.get("total"),
        "items": len(data.get("items", [])),
    }


def main() -> None:
    args = parse_args()
    course_url = args.course_url.rstrip("/")
    site_url = args.site_url.rstrip("/")
    result: dict[str, Any] = {"checks": {}, "ok": True}

    with httpx.Client(timeout=25.0, follow_redirects=False, trust_env=False) as client:
        student_response, student_html = get_text(client, f"{course_url}/student")
        student_ui = {
            **page_summary(student_response, student_html),
            "helpKeyCount": student_html.count("data-help-key"),
            "hasHelpDialog": "helpDialog" in student_html,
            "hasOldRecordHelp": "recordHelpBtn" in student_html,
            "hasSmallModuleTitleCss": "h2 { margin: 0 0 10px; font-size: 14px" in student_html,
        }
        result["checks"]["studentUi"] = student_ui

        for student_id in ["codex_live_001", "codex_live_002"]:
            page_response, page_html = get_text(client, f"{site_url}/{student_id}/")
            config_response, config_js = get_text(client, f"{site_url}/{student_id}/api-config.js")
            result["checks"][student_id] = {
                "site": page_summary(page_response, page_html),
                "apiConfig": {
                    **page_summary(config_response, config_js),
                    "hasApiRoot": f'window.API_ROOT = "{course_url}"' in config_js,
                    "hasApiBase": f'window.API_BASE = "{course_url}/api/{student_id}"' in config_js,
                },
            }

        result["checks"]["codex_live_002_records"] = {
            resource: api_total(client, course_url, "codex_live_002", resource)
            for resource in ["posts", "comments", "likes"]
        }

    expected = [
        result["checks"]["studentUi"]["status"] == 200,
        result["checks"]["studentUi"]["helpKeyCount"] == 7,
        result["checks"]["studentUi"]["hasHelpDialog"],
        not result["checks"]["studentUi"]["hasOldRecordHelp"],
        result["checks"]["studentUi"]["hasSmallModuleTitleCss"],
        result["checks"]["codex_live_001"]["site"]["status"] == 200,
        result["checks"]["codex_live_001"]["apiConfig"]["hasApiBase"],
        result["checks"]["codex_live_002"]["site"]["status"] == 200,
        result["checks"]["codex_live_002"]["apiConfig"]["hasApiBase"],
        result["checks"]["codex_live_002_records"]["posts"]["total"] == 50,
        result["checks"]["codex_live_002_records"]["comments"]["total"] == 30,
        result["checks"]["codex_live_002_records"]["likes"]["total"] == 50,
    ]
    result["ok"] = all(expected)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

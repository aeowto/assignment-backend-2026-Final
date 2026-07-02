from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare final exam demo sites on a running backend.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--student-password", default="123456")
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--out-dir", default=r"C:\tmp")
    return parser.parse_args()


def ok(response: httpx.Response, label: str) -> Any:
    if response.status_code >= 400:
        raise RuntimeError(f"{label} failed {response.status_code}: {response.text[:500]}")
    body = response.json()
    if body.get("success") is False:
        raise RuntimeError(f"{label} failed body: {body}")
    return body.get("data")


def make_zip(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.name.lower() != "readme.md":
                archive.write(path, path.relative_to(source).as_posix())
    return target


def travel_feed_seed() -> list[tuple[str, dict[str, Any]]]:
    photos = [
        "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1493558103817-58b2924bce98?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1526772662000-3f88f10405ff?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=1200&q=80",
        "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=1200&q=80",
    ]
    places = [
        ("大理洱海", "环湖骑行", ["云南", "湖边", "骑行"]),
        ("厦门鼓浪屿", "海风和老别墅", ["海岛", "散步", "建筑"]),
        ("成都人民公园", "茶馆慢下午", ["成都", "茶馆", "城市观察"]),
        ("杭州西湖", "雨后湖边路线", ["杭州", "湖景", "路线"]),
        ("苏州平江路", "小巷里的夜色", ["苏州", "古城", "夜游"]),
        ("桂林漓江", "山水之间的清晨", ["桂林", "山水", "清晨"]),
        ("敦煌鸣沙山", "沙丘上的日落", ["敦煌", "沙漠", "日落"]),
        ("青岛八大关", "转角遇到海", ["青岛", "海边", "街区"]),
        ("重庆山城步道", "台阶和江景", ["重庆", "山城", "步道"]),
        ("上海武康路", "梧桐树下的城市漫游", ["上海", "街拍", "城市"]),
    ]
    authors = ["阿岚", "木木", "南风", "小满", "橙子", "远山"]
    details = [
        "这条路线适合上午出发，避开正午人流后，拍照和休息都会从容很多。",
        "临时改变计划反而遇到很舒服的街角，旅行里这种偶然感很值得记录。",
        "建议带一双好走的鞋，路上有不少坡和台阶，但视野打开以后很值。",
        "如果只停留半天，可以把路线压缩成两个点，留出时间坐下来观察。",
        "照片里看起来安静，现场其实很热闹，适合做成旅行记录站里的对比内容。",
    ]
    comments = [
        "这个地点看起来很适合做一日路线。",
        "图片和文字搭在一起很有画面感。",
        "如果加上交通方式会更完整。",
        "这个时间段去人会不会很多？",
        "我想收藏这条路线，之后可以照着走。",
    ]
    seed: list[tuple[str, dict[str, Any]]] = []
    slugs: list[str] = []
    for index in range(50):
        place, theme, tags = places[index % len(places)]
        slug = f"travel-{index + 1:02d}"
        slugs.append(slug)
        images = [photos[index % len(photos)]]
        if index % 3 == 0:
            images.append(photos[(index + 3) % len(photos)])
        seed.append((
            "posts",
            {
                "slug": slug,
                "title": f"{place}｜{theme}",
                "place": place,
                "date": f"2026-07-{(index % 18) + 1:02d}",
                "author": authors[index % len(authors)],
                "content": details[index % len(details)],
                "tags": tags,
                "images": images,
                "imageSource": "Unsplash",
            },
        ))
    for index, slug in enumerate(slugs[:30]):
        seed.append((
            "comments",
            {
                "postSlug": slug,
                "nickname": ["路过同学", "小李", "晴天", "背包客", "地图收藏家"][index % 5],
                "content": comments[index % len(comments)],
                "createdAt": f"2026-07-02T{8 + (index % 10):02d}:{index % 60:02d}:00+08:00",
            },
        ))
    for index, slug in enumerate(slugs):
        seed.append((
            "likes",
            {
                "postSlug": slug,
                "nickname": ["访客A", "访客B", "访客C", "访客D"][index % 4],
                "createdAt": f"2026-07-02T{9 + (index % 8):02d}:{index % 60:02d}:30+08:00",
            },
        ))
    return seed


def demo_config_v2(workspace: Path, out_dir: Path, student_password: str) -> dict[str, dict[str, Any]]:
    demo_root = workspace / "final_exam_materials" / "demo_sites"
    return {
        "codex_live_001": {
            "password": student_password,
            "site_dir": demo_root / "flight_chess_extreme",
            "zip": out_dir / "final_demo_flight_chess_extreme.zip",
            "resources": [
                {"resourceName": "rooms", "displayName": "飞行棋房间状态", "accessMode": "public_collaborate"},
                {"resourceName": "moves", "displayName": "飞行棋操作记录", "accessMode": "public_submit"},
            ],
            "seed": [],
        },
        "codex_live_002": {
            "password": student_password,
            "site_dir": demo_root / "info_cross_showcase",
            "zip": out_dir / "final_demo_info_cross_showcase.zip",
            "resources": [
                {"resourceName": "posts", "displayName": "旅行记录", "accessMode": "public_read"},
                {"resourceName": "comments", "displayName": "旅行评论", "accessMode": "public_submit"},
                {"resourceName": "likes", "displayName": "旅行点赞", "accessMode": "public_submit"},
            ],
            "seed": travel_feed_seed(),
        },
    }


def admin_login(client: httpx.Client, password: str) -> None:
    ok(client.post("/api/admin/login", json={"username": "admin", "password": password}), "admin login")


def ensure_student_login(base_url: str, student_id: str, password: str, admin_password: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=base_url, timeout=30.0, trust_env=False)
    login = client.post("/api/auth/login", json={"username": student_id, "password": password})
    if login.status_code >= 400:
        with httpx.Client(base_url=base_url, timeout=30.0, trust_env=False) as admin:
            admin_login(admin, admin_password)
            ok(admin.post(f"/api/admin/students/{student_id}/reset-password", json={"password": password}), f"reset {student_id}")
        login = client.post("/api/auth/login", json={"username": student_id, "password": password})
    data = ok(login, f"login {student_id}")
    return client, data["token"]


def main() -> None:
    args = parse_args()
    workspace = Path(args.workspace)
    out_dir = Path(args.out_dir)
    configs = demo_config_v2(workspace, out_dir, args.student_password)
    prepared = []

    with httpx.Client(base_url=args.base_url, timeout=30.0, trust_env=False) as admin:
        admin_login(admin, args.admin_password)
        for student_id in configs:
            for part in ["records", "site", "files"]:
                ok(admin.delete(f"/api/admin/students/{student_id}/{part}"), f"clear {student_id} {part}")

    for student_id, config in configs.items():
        client, token = ensure_student_login(args.base_url, student_id, config["password"], args.admin_password)
        try:
            auth_headers = {"Authorization": "Bearer " + token}
            json_headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
            desired_resources = {item["resourceName"] for item in config["resources"]}
            existing_resources = ok(client.get("/api/student/resources", headers=auth_headers), f"list resources {student_id}") or []
            for resource in existing_resources:
                resource_name = resource.get("resource_name") or resource.get("resourceName")
                if resource_name and resource_name not in desired_resources:
                    ok(
                        client.delete(f"/api/student/resources/{quote(resource_name, safe='')}", headers=auth_headers),
                        f"delete stale resource {student_id} {resource_name}",
                    )
            for resource in config["resources"]:
                ok(client.post("/api/student/resources", headers=json_headers, json=resource), f"resource {student_id} {resource['resourceName']}")

            created_posts: dict[str, str] = {}
            for resource_name, payload in config["seed"]:
                payload = dict(payload)
                post_slug = payload.pop("postSlug", "")
                if post_slug:
                    payload["postId"] = created_posts.get(post_slug, post_slug)
                result = ok(client.post(f"/api/{student_id}/{resource_name}", headers=json_headers, json=payload), f"seed {student_id} {resource_name}")
                if resource_name == "posts":
                    created_posts[payload.get("slug", "")] = result["id"]

            zip_path = make_zip(config["site_dir"], config["zip"])
            with zip_path.open("rb") as file_obj:
                ok(
                    client.post(
                        "/api/student/site/upload",
                        headers=auth_headers,
                        files={"file": (zip_path.name, file_obj, "application/zip")},
                    ),
                    f"upload site {student_id}",
                )
            status = ok(client.get("/api/student/site/status", headers=auth_headers), f"site status {student_id}")
            prepared.append({
                "student": student_id,
                "siteUrl": status.get("siteUrl"),
                "zip": str(zip_path),
                "resources": [item["resourceName"] for item in config["resources"]],
            })
        finally:
            client.close()

    print(json.dumps(prepared, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

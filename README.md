# 期末作品平台后端

本目录是 Web 前端课程期末大作业专用后端，独立于 `teaching_fastapi_server/` 和 `backend_ass4_ass5/`。

它的作用：

```text
教师管理学生账号
学生登录课程平台账号
学生创建自己的虚拟资源接口
学生管理自己的数据
访客浏览学生作品并提交评论、留言、报名等数据
学生上传静态网站文件
学生上传作品运行中需要引用的图片、PDF、音频、视频文件
本地用 /sites/{学号}/ 访问学生作品
线上推荐用独立站点域名访问学生作品
```

它不做：

```text
学生自行注册
学生作品内部真实用户系统
真实动态创建 Python 路由
自动评分
内置互评系统
每次浏览逐条写入日志
要求学生在上传作品里登录平台账号管理数据
```

## 启动

```bash
cd backend_final_exam
pip install -r requirements.txt
python run.py
```

常用地址：

```text
http://127.0.0.1:8000/          简要说明
http://127.0.0.1:8000/api-docs  学生接口说明
http://127.0.0.1:8000/admin     教师管理入口
http://127.0.0.1:8000/student   学生管理入口
http://127.0.0.1:8000/docs      教师登录后可看的 FastAPI 调试文档
```

云端长期运行建议用非交互命令：

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## 线上环境变量

```bash
export FINAL_BACKEND_ADMIN_PASSWORD="强密码"
export FINAL_BACKEND_COOKIE_SECURE="true"
export FINAL_BACKEND_HOST="127.0.0.1"
export FINAL_BACKEND_ROOT_PATH="/2025-2026-2/final"
export FINAL_BACKEND_PUBLIC_BASE_URL="https://hw.codedock.top/2025-2026-2/final"
export FINAL_BACKEND_SITE_BASE_URL="https://sites.hw.codedock.top"
export FINAL_BACKEND_DATA_DIR="/srv/final_backend_data"
export FINAL_BACKEND_STUDENTS_FILE="/home/ubuntu/2025-2-Web/final/assignment-backend-2026-Final/final_students.json"
export FINAL_BACKEND_AUTO_SYNC_STUDENTS="false"
export FINAL_BACKEND_ENABLE_CORS="true"
export FINAL_BACKEND_CORS_ORIGINS="https://sites.hw.codedock.top,http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:3000,http://localhost:3000"
export FINAL_BACKEND_ENABLE_TEACHER_DOCS="true"
export FINAL_BACKEND_ENABLE_TEACHER_KEY="false"
export FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY="true"
export FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED="true"
export FINAL_BACKEND_TRUST_PROXY_HEADERS="true"
export FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN="true"
export FINAL_BACKEND_DEFAULT_PAGE_SIZE="20"
export FINAL_BACKEND_MAX_PAGE_SIZE="50"
export FINAL_BACKEND_MAX_JSON_BODY_BYTES="32768"
export FINAL_BACKEND_MAX_STUDENT_FILE_COUNT="100"
export FINAL_BACKEND_MAX_STUDENT_FILE_TOTAL_BYTES="52428800"
export FINAL_BACKEND_MAX_IMAGE_FILE_BYTES="2097152"
export FINAL_BACKEND_MAX_PDF_FILE_BYTES="5242880"
export FINAL_BACKEND_MAX_AUDIO_FILE_BYTES="5242880"
export FINAL_BACKEND_MAX_VIDEO_FILE_BYTES="20971520"
export FINAL_BACKEND_UPLOAD_CHUNK_BYTES="1048576"
export FINAL_BACKEND_PORT="8010"
```

第一版线上建议把后台/API 和学生作品分成两个 origin。同机同时部署 Ass4&5 时，Ass4&5 保持 `127.0.0.1:8000`，Final 使用 `127.0.0.1:8010`：

```text
hw.codedock.top
  /admin
  /student
  /api

sites.hw.codedock.top
  /{学号}/
```

正式线上 `FINAL_BACKEND_CORS_ORIGINS` 建议写学生作品域名和常见本地开发 origin，不要使用 `*`。学生作品从 `sites.hw.codedock.top` 调用 `hw.codedock.top` 下的 API；学生线下开发时，VS Code Live Server 等本地页面也可以调用云端 API。教师后台仍然走同源 Cookie，跨域请求不开放 credentials。

常见本地开发 origin：

```text
http://127.0.0.1:5500
http://localhost:5500
http://127.0.0.1:5173
http://localhost:5173
http://127.0.0.1:3000
http://localhost:3000
```

`FINAL_BACKEND_CORS_ORIGINS` 是精确列表，不支持端口通配。如果学生使用 `5501` 或其它端口，需要把完整 origin 加进去。

开启 `FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=true` 后，后端会检查 `/sites/...` 和 `/media/...` 请求的 Host。只有 `FINAL_BACKEND_SITE_BASE_URL` 对应的 Host 可以直接访问学生站点和媒体文件；如果从课程后台域名访问这些地址，后端会 308 跳转到学生作品域名。

学生上传作品主要用于展示和公开互动。学生本人管理资源、数据和站点时，回到 `hw.codedock.top/student`。

本地单域名模式只适合教师自测，不适合组织真实学生互访。真实学生互访前必须开启 `FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=true`，让上传作品与 `/student`、`/admin`、`/api/admin` 分属不同浏览器 origin。正式云端必须使用不同 hostname，例如 `hw.codedock.top` 和 `sites.hw.codedock.top`；不要用同一个 hostname 的不同端口或不同协议来替代双域名。

`/student` 和 `/admin` 已提供最小可用管理页。学生可以在 `/student` 管理自己的资源、数据、站点 zip 和媒体文件；教师可以在 `/admin` 管理学生账号、查看学生空间、按资源查看或清空数据、导出 JSON、下载完整归档 zip。

`/api-docs` 是学生可读接口说明页，只展示学生作品会用到的接口。FastAPI 自动调试文档不公开展示：内置 `/docs`、`/redoc`、`/openapi.json` 已关闭，后端改为提供教师权限保护的 `/docs` 和 `/openapi.json`。老师先登录 `/admin` 后可以访问 `/docs`；如完全不想提供教师调试文档，可设置 `FINAL_BACKEND_ENABLE_TEACHER_DOCS=false`。

## 学生名单和初始密码

期末后端随代码提供独立名单种子文件：

```text
backend_final_exam/final_students.json
```

该文件由 Ass4/5 名单生成，但已按期末要求统一初始密码为 `123456`，并补入期末本地模拟测试账号。默认路径已指向该文件，也可以用 `FINAL_BACKEND_STUDENTS_FILE` 指定其它位置。教师在 `/admin` 点击“同步名单”或请求：

```text
POST /api/admin/students/sync
```

即可导入名单。当前名单口径为：

```text
正式学生 111 个
长期测试账号 10 个：test_ass45_001 到 test_ass45_010
期末模拟测试账号 2 个：codex_live_001、codex_live_002
总账号 123 个
```

名单中的 `code` 会作为期末平台初始密码，当前全部为 `123456`。学生第一次登录后，`/student` 会提示仍在使用初始密码，学生可在页面中修改密码。如果学生忘记密码，教师在 `/admin` 点击“重置密码”，后端会把密码重置回名单中的初始密码，并清除该学生旧 session。

手动新建账号只用于临时补充。`POST /api/admin/students` 只创建新账号；已有学生请用 `PUT /api/admin/students/{student_id}` 修改资料，或用 `POST /api/admin/students/{student_id}/reset-password` 重置密码，避免保存资料时误改密码。

## 学生接口

学生不注册。教师先创建账号，学生登录：

```text
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/change-password
POST /api/auth/logout
```

学生创建资源：

```text
POST /api/student/resources
Authorization: Bearer token
```

示例：

```json
{
  "resourceName": "comments",
  "displayName": "评论",
  "accessMode": "public_submit"
}
```

学生作品调用虚拟接口：

```text
GET    /api/{学号}/{资源名}?page=1&pageSize=20
POST   /api/{学号}/{资源名}
PUT    /api/{学号}/{资源名}/{id}
DELETE /api/{学号}/{资源名}/{id}
```

列表接口返回分页结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "pageSize": 20
}
```

学生文件接口：

```text
GET    /api/student/files
POST   /api/student/files
DELETE /api/student/files/{file_id}

GET    /media/{学号}/{file_id}/{filename}
```

文件接口需要学生登录后上传。上传成功后会返回 `fileUrl`，学生可以把 `fileUrl` 保存进自己的业务数据里，例如商品图片、活动海报、作品截图或演示视频地址。

四类权限：

| accessMode | GET | POST | PUT / DELETE | 场景 |
| --- | --- | --- | --- | --- |
| `public_read` | 访客可看 | 作者登录后可发 | 作者登录后可改删 | 商品、文章、活动 |
| `public_submit` | 访客可看 | 访客可提交 | 作者登录后可改删 | 评论、留言 |
| `private_collect` | 作者登录后可看 | 访客可提交 | 作者登录后可改删 | 报名、订单、联系表单 |
| `public_collaborate` | 访客可看 | 访客可提交 | 访客可改，删除需作者登录 | 飞行棋、五子棋、共享房间状态 |

`public_collaborate` 只建议用于教师案例或挑战型公开协作数据。它会让知道接口地址的人都能修改数据，不要用于报名、订单、联系方式等私密数据。

## 静态网站

学生登录后上传 zip：

```text
POST /api/student/site/upload
Authorization: Bearer token
```

zip 中应包含：

```text
index.html
css/
js/
images/
```

上传后访问：

```text
本地：/sites/{学号}/
线上：https://sites.hw.codedock.top/{学号}/
```

建议学生在 `index.html` 中引入后端生成的配置：

```html
<script src="./api-config.js"></script>
```

然后在自己的 JS 中使用：

```js
const API_ROOT = window.API_ROOT;
const API_BASE = window.API_BASE;

fetch(API_BASE + "/comments")
```

`API_ROOT` 指向课程平台根地址，适合调用 `/api/auth/login`、`/api/student/files` 等平台接口。`API_BASE` 指向当前学生自己的数据接口，适合调用 `/api/{学号}/{资源名}`。这样部署在 `/2025-2026-2/final` 这类子路径时，学生作品不会误请求到域名根路径。

第一版不建议学生在上传作品中保存平台 token 或制作作者管理页；作者管理回到 `/student` 页面完成。学生管理页只把 token 保存在 `sessionStorage`，关闭浏览器标签后需要重新登录；这只能降低持久泄露窗口，不能替代正式线上双 origin 隔离。

## 多媒体文件

如果图片、音频、视频是网站固定素材，可以直接放进 zip：

```text
images/cover.jpg
media/demo.mp4
```

如果图片或视频需要在作品运行过程中作为数据内容上传，使用学生文件接口：

```text
POST /api/student/files
Authorization: Bearer token
```

支持类型：

```text
图片：png / jpg / jpeg / gif / webp，默认单文件 2MB
PDF：pdf，默认单文件 5MB
音频：mp3，默认单文件 5MB
视频：mp4 / webm，默认单文件 20MB
单学生文件总量：默认 50MB
单学生文件数量：默认 100 个
```

视频文件容易占用空间。课程第一版建议优先使用图片和 PDF；较大的视频可以使用外链或提前压缩后再上传。

云端使用 Nginx 反代时，`client_max_body_size` 应略高于应用允许的单文件上限。例如应用允许 20MiB 视频时，Nginx 建议设置为 `30m`，避免 multipart/form-data 的边界和头部开销导致临界文件被反代层提前拒绝。这个限制也是超大 JSON 请求的第一道防线；应用层仍会返回 413，但不应让后端端口绕过 Nginx 直接暴露公网。

## 写入控制

为了避免公开评论、留言、报名接口造成 SQLite 高频写入，本后端默认限制：

```text
单 IP 每分钟公开 POST 次数
单学生空间每分钟公开 POST 次数
单资源记录数
单学生空间记录数
单条 JSON 请求体大小
字符串字段长度
登录失败次数临时锁定
单学生文件数量和总容量
单文件大小
```

云端反代时，公开提交和登录限流需要识别真实客户端 IP。只有确认后端只监听 `127.0.0.1` 且请求必经 Nginx 时，才设置：

```bash
export FINAL_BACKEND_TRUST_PROXY_HEADERS="true"
```

如果 `FINAL_BACKEND_TRUST_PROXY_HEADERS=true` 但 `FINAL_BACKEND_HOST` 不是 `127.0.0.1`、`::1` 或 `localhost`，`/api/admin/status` 会返回 `deploymentWarnings`，提示后端端口可能被公网直连。

正式线上建议同时开启：

```bash
export FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN="true"
```

开启后，`FINAL_BACKEND_PUBLIC_BASE_URL` 和 `FINAL_BACKEND_SITE_BASE_URL` 必须存在且 hostname 不同，避免学生作品和后台/API 回到同源。后端会拒绝同 hostname 不同端口的配置。

Nginx 应转发原始 Host 信息：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

第一版不记录每次浏览、点击和页面打开日志。

教师清空某个学生的 records、site 或 files 前，后端会自动在 `data/backups/admin-actions/` 下生成 manifest 备份，并在 SQLite 的 `admin_audits` 表中记录操作时间、操作类型、目标学生、备份路径和操作 IP。该备份用于误操作后的人工恢复，不是面向学生开放的下载接口。

教师管理接口补充：

```text
GET    /api/admin/students/{学号}/resources/{资源名}/records
GET    /api/admin/students/{学号}/resources/{资源名}/export
DELETE /api/admin/students/{学号}/resources/{资源名}/records
GET    /api/admin/students/{学号}/archive
```

其中 `/archive` 会打包该学生的账号信息、资源定义、数据记录、媒体文件清单、静态站点文件和媒体文件，便于期末归档。

## 相关计划和检查文档

```text
PROJECT_PLAN.md
TRIAL_GUIDE.md
LOCAL_TEST_LIMITATIONS.md
```

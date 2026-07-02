# TRIAL_GUIDE.md — 期末后端试跑与人工检查文档

最后更新日期：2026-06-27

------

## 1. 文档用途

本文档用于 `backend_final_exam/` 第一版完成后进行本地试跑和云端试部署检查。

目标不是替代自动测试，而是把 Ass4/5 后端上线时遇到过的问题提前变成检查项，避免期末后端再次踩同类坑。

对应计划文档：

```text
PROJECT_PLAN.md
LOCAL_TEST_LIMITATIONS.md
```

------

## 2. 试跑目标

本地和云端都应确认：

```text
教师能登录后台
教师能创建学生账号
学生能登录
学生能创建资源接口
四类资源权限生效，基础作品主要使用前三类
访客能浏览和提交允许公开提交的数据
学生带 token 能管理自己的数据
学生不能管理他人数据
本地学生网站能通过 /sites/{学号}/ 打开
线上学生网站能通过独立站点域名打开
学生网站能 fetch 后端生成的 API_ROOT 和 API_BASE
教师能导出和清空数据
公开提交接口有频率和容量限制
子路径反代下所有链接和接口仍然正确
```

------

## 3. 本地自动检查

进入后端目录：

```bash
cd backend_final_exam
```

语法检查：

```bash
python -m py_compile main.py run.py
```

运行测试：

```bash
python -m pytest -q
```

如有前端管理页 JS，再检查：

```bash
node --check static/admin.js
node --check static/student.js
```

第一版自动测试至少覆盖：

```text
登录成功和失败
学生不能注册
学生 token 只能管理自己的空间
教师 Cookie 登录
教师 Header 调试入口可关闭
资源名格式校验
四类 access_mode 权限
GET / POST / PUT / DELETE 基础流程
普通访客默认不能 PUT / DELETE
public_collaborate 允许访客 PUT
所有模式下匿名 DELETE 必须失败
登录的非空间拥有者 DELETE 必须失败
私密收集型 GET 需要作者 token
学生 A 看不到或改不了学生 B 的私密数据
公开 POST 的限流和容量限制
zip 上传路径穿越被拒绝
/sites/{学号}/ 能返回 index.html
root_path 下 /api-docs、教师 /docs 和内置页面不跳到域名根路径
SQLite 并发基础写入
```

------

## 4. 本地启动检查

推荐本地临时环境变量：

```bash
export FINAL_BACKEND_ADMIN_PASSWORD="dev-admin-pass"
export FINAL_BACKEND_COOKIE_SECURE="false"
export FINAL_BACKEND_ROOT_PATH=""
export FINAL_BACKEND_DATA_DIR="./data"
export FINAL_BACKEND_ENABLE_CORS="true"
export FINAL_BACKEND_ENABLE_TEACHER_KEY="true"
export FINAL_BACKEND_PORT="8000"
```

本地单域名模式只用于教师自测和功能演示。不要在该模式下组织真实学生互访，因为 `/student` 和 `/sites/{学号}/` 同 origin，上传作品有机会共享浏览器存储。真实学生试跑必须走后面的双域名配置。

启动：

```bash
python run.py
```

或非交互方式：

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

本地打开：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api-docs
http://127.0.0.1:8000/admin
http://127.0.0.1:8000/docs
```

检查：

```text
页面无乱码
/api-docs 能打开学生接口说明，且不展示教师管理接口
/docs 未登录会跳到 /admin；教师登录后能加载 openapi.json
/admin 能登录
退出登录后教师接口失败
Cookie Secure 在本地 HTTP 模式下没有开启
```

------

## 5. 基础账号试跑

建议准备两个测试学生：

```text
test_final_001
test_final_002
```

教师后台操作：

```text
创建 test_final_001
创建 test_final_002
重置 test_final_001 密码
停用和重新启用 test_final_002
```

学生登录：

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "test_final_001",
  "password": "测试密码"
}
```

检查返回：

```text
success = true
data.token 存在
data.user.studentId = test_final_001
```

获取当前用户：

```http
GET /api/auth/me
Authorization: Bearer token
```

退出：

```http
POST /api/auth/logout
Authorization: Bearer token
```

退出后再次访问 `/api/auth/me` 应失败。

------

## 6. 资源权限试跑

用 `test_final_001` 创建 3 个资源：

```text
products  公开展示 public_read
comments  公开互动 public_submit
orders    私密收集 private_collect
```

### 6.1 公开展示型

访客读取：

```text
GET /api/test_final_001/products
```

预期：成功。

访客新增：

```text
POST /api/test_final_001/products
```

预期：失败，提示需要作者登录。

学生带 token 新增：

```text
POST /api/test_final_001/products
Authorization: Bearer token
```

预期：成功。

### 6.2 公开互动型

访客读取：

```text
GET /api/test_final_001/comments
```

预期：成功。

访客提交：

```text
POST /api/test_final_001/comments
```

body 示例：

```json
{
  "nickname": "访客A",
  "content": "这个作品页面很好看"
}
```

预期：成功。

访客删除：

```text
DELETE /api/test_final_001/comments/{id}
```

预期：失败。

学生带 token 删除：

```text
DELETE /api/test_final_001/comments/{id}
Authorization: Bearer token
```

预期：成功。

### 6.3 私密收集型

访客提交：

```text
POST /api/test_final_001/orders
```

body 示例：

```json
{
  "name": "李同学",
  "contact": "13800000000",
  "content": "想了解这个商品"
}
```

预期：成功。

访客读取：

```text
GET /api/test_final_001/orders
```

预期：失败。

学生带 token 读取：

```text
GET /api/test_final_001/orders
Authorization: Bearer token
```

预期：成功。

### 6.4 学生隔离

用 `test_final_002` 的 token 请求：

```text
PUT /api/test_final_001/products/{id}
DELETE /api/test_final_001/products/{id}
```

预期：403，不能管理其他学生空间。

------

## 7. 写入压力与磁盘检查

这个检查专门针对公开评论、留言、报名等接口，避免 SQLite 高频写入导致数据库膨胀和磁盘损耗。

### 7.1 限流检查

对公开互动资源连续提交：

```text
POST /api/test_final_001/comments
```

检查：

```text
同一 IP 超过每分钟限制后返回 429
返回信息能说明提交太频繁
没有生成超过限制数量的数据
```

对同一学生空间集中提交：

```text
POST /api/test_final_001/comments
POST /api/test_final_001/orders
```

检查：

```text
超过单学生空间每分钟公开 POST 限制后返回 429
不同学生空间互不影响
```

### 7.2 容量检查

检查：

```text
单条 JSON body 超过上限会被拒绝
单资源记录数超过上限会被拒绝
单学生空间记录数超过上限会被拒绝
超长字符串字段会被拒绝或截断前返回错误
```

建议错误状态码：

```text
413 请求体过大
429 请求过于频繁
400 字段内容不符合要求
```

### 7.3 不写高频日志检查

确认第一版没有默认写入：

```text
每次 GET 浏览日志
每次页面打开日志
每次点击日志
轮询心跳日志
```

如实现浏览量，应确认：

```text
写的是聚合计数
短时间内去重
定时低频落库
不保存每次访问明细
```

### 7.4 SQLite 文件检查

在压测或批量提交后查看：

```text
SQLite 主文件大小
-wal 文件大小
-shm 文件是否正常
data 目录总大小
磁盘剩余空间
```

如 WAL 文件持续变大，安排低峰期做 checkpoint，不要在学生集中使用时频繁做重操作。

------

## 8. 静态网站试跑

准备一个最小网站 zip：

```text
index.html
style.css
app.js
```

`app.js` 示例使用：

```js
const API_ROOT = window.API_ROOT;
const API_BASE = window.API_BASE;

fetch(API_BASE + "/products")
  .then(function (res) {
    return res.json()
  })
  .then(function (body) {
    console.log(body)
})
```

`index.html` 中先引入平台生成的配置：

```html
<script src="./api-config.js"></script>
<script src="./app.js"></script>
```

学生登录后上传 zip。

检查：

```text
本地：GET /sites/test_final_001/
线上：GET https://sites.hw.codedock.top/test_final_001/
```

预期：

```text
返回 index.html
页面可以加载 style.css 和 app.js
api-config.js 中的 API_ROOT 指向课程平台根地址
api-config.js 中的 API_BASE 指向课程平台 API
页面可以 fetch API_BASE + "/products"
```

安全检查：

```text
zip 中包含 ../evil.html 应被拒绝
zip 中包含绝对路径应被拒绝
zip 中没有 index.html 应给出清楚提示
超过大小限制应返回中文提示
超过文件数量限制应返回中文提示
```

------

## 9. 学生文件接口试跑

学生文件接口用于运行过程中上传图片、PDF、音频和视频。固定素材仍建议直接放进网站 zip。

上传检查：

```text
POST /api/student/files
Authorization: Bearer token
form-data: file=cover.jpg
```

预期：

```text
返回 fileUrl
GET fileUrl 可以访问文件
GET /api/student/files 可以看到文件列表
DELETE /api/student/files/{file_id} 后 fileUrl 访问失败
```

业务数据使用方式：

```json
{
  "title": "活动海报",
  "imageUrl": "返回的 fileUrl"
}
```

限制检查：

```text
exe 等不允许类型应被拒绝
超过图片 / PDF / 音频 / 视频单文件大小应返回 413
超过单学生文件数量应返回 429
超过单学生总容量应返回 413
```

线上双域名检查：

```text
fileUrl 应指向 https://sites.hw.codedock.top/media/{学号}/{file_id}/{filename}
该地址不应和 /admin、/student、/api/admin 共用同一个浏览器 origin
hw.codedock.top 下访问 /media/... 应 308 跳转到 sites.hw.codedock.top/media/...
sites.hw.codedock.top 下访问 /media/... 应正常返回文件
```

------

## 10. 云端环境变量检查

线上推荐：

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

检查点：

```text
FINAL_BACKEND_ADMIN_PASSWORD 已设置，不使用随机不可见密码
FINAL_BACKEND_COOKIE_SECURE 只在 HTTPS 正式访问时为 true
FINAL_BACKEND_HOST 为 127.0.0.1
FINAL_BACKEND_ROOT_PATH 和 Nginx 挂载路径一致
FINAL_BACKEND_PUBLIC_BASE_URL 包含正式课程平台公开地址和子路径
FINAL_BACKEND_SITE_BASE_URL 指向学生作品独立域名
FINAL_BACKEND_DATA_DIR 在代码目录外
FINAL_BACKEND_STUDENTS_FILE 指向 backend_final_exam/final_students.json 或正式期末名单
FINAL_BACKEND_ENABLE_TEACHER_KEY 线上为 false
FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY 线上为 true
FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED 线上为 true
FINAL_BACKEND_TRUST_PROXY_HEADERS 只在后端不直接暴露公网且请求必经 Nginx 时为 true
FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN 线上为 true
FINAL_BACKEND_DEFAULT_PAGE_SIZE 为 20
FINAL_BACKEND_MAX_PAGE_SIZE 不超过 50 或 100
FINAL_BACKEND_MAX_JSON_BODY_BYTES 保持较小值，避免非上传接口被大 JSON 请求撑爆
/api/admin/status 中 teacherKeyEnabled 为 false
/api/admin/status 中 teacherKeyIsDefault 为 false
/api/admin/status 中 deploymentWarnings 为空
学生站点 api-config.js 中有 API_ROOT 和 API_BASE
```

名单同步检查：

```text
/admin 点击“同步名单”成功
或 POST /api/admin/students/sync 成功
正式学生为 111 个
长期测试账号为 10 个：test_ass45_001 到 test_ass45_010
测试账号可登录，测试结束后只清理测试数据，不删除测试账号
学生首次使用初始密码登录时会看到改密提醒
教师重置密码会重置回名单初始密码
```

登录限流检查：

```text
连续输错学生密码达到 FINAL_BACKEND_LOGIN_FAILURE_LIMIT 后返回 429
连续输错教师密码达到 FINAL_BACKEND_LOGIN_FAILURE_LIMIT 后返回 429
限流计数保存在内存，不写入 SQLite
```

------

## 11. systemd 检查

长期云端部署不要使用等待输入的交互式启动脚本。

Final 推荐使用项目目录内的独立虚拟环境：

```bash
cd /home/ubuntu/2025-2-Web/final/assignment-backend-2026-Final
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

systemd 示例：

```ini
[Unit]
Description=2025-2 Web Final Backend
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/2025-2-Web/final/assignment-backend-2026-Final
EnvironmentFile=/etc/2025-2-web-final.env
ExecStart=/home/ubuntu/2025-2-Web/final/assignment-backend-2026-Final/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8010
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

检查：

```bash
sudo systemctl daemon-reload
sudo systemctl restart 2025-2-web-final
sudo systemctl status 2025-2-web-final
journalctl -u 2025-2-web-final -f
```

不要用 root 跑后端。确认：

```text
User=ubuntu
Group=ubuntu
```

------

## 12. SQLite 权限检查

数据目录：

```text
/srv/final_backend_data
```

检查权限：

```bash
sudo chown -R ubuntu:ubuntu /srv/final_backend_data
sudo chmod -R u+rwX,go-rwx /srv/final_backend_data
```

注意：

```text
SQLite 不只写 .sqlite3 文件
WAL 模式还会写 -wal 和 -shm
因此目录本身也必须可写
```

如果出现：

```text
sqlite3.OperationalError: attempt to write a readonly database
```

优先检查：

```text
systemd User 是否正确
数据目录 owner 是否正确
数据库文件 owner 是否正确
数据目录是否允许创建 -wal / -shm
```

不要用 `chmod 777` 作为长期解决方式。

------

## 13. Nginx 子路径和双域名反代检查

目标示例：

```text
https://hw.codedock.top/2025-2026-2/final/
https://sites.hw.codedock.top/test_final_001/
```

Nginx 需要包含：

```nginx
client_max_body_size 30m;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Prefix /2025-2026-2/final;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-Host $host;
```

反代层请求体上限应略高于应用允许的单文件上限。当前应用默认允许 20MiB 视频，`30m` 可以给 multipart/form-data 的边界和头部开销留出空间；它同时也是超大 JSON 请求进入应用前的第一道保护。

建议 Nginx 分成两个 server_name：

```text
hw.codedock.top 只开放 /2025-2026-2/final/ 下的后台、学生管理和 API
sites.hw.codedock.top 只开放学生上传作品
```

两个 server_name 必须是不同 hostname。不要用 `hw.codedock.top` 和 `hw.codedock.top:9443` 这种同 hostname 不同端口配置替代双域名；后端在线上隔离模式下会拒绝启动。

`sites.hw.codedock.top/test_final_001/` 可以在 Nginx 中转到后端的 `/sites/test_final_001/`。不要让学生作品和 `/admin`、`/student`、`/api/admin` 共用同一个浏览器 origin。

后端也会在 `FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=true` 时检查 `/sites/...` 请求 Host：`sites.hw.codedock.top` 可以直接访问学生站点；`hw.codedock.top` 下的 `/sites/...` 会被 308 跳转到 `sites.hw.codedock.top`。

检查：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

浏览器检查：

```text
https://hw.codedock.top/2025-2026-2/final/
https://hw.codedock.top/2025-2026-2/final/api-docs
https://hw.codedock.top/2025-2026-2/final/admin
https://hw.codedock.top/2025-2026-2/final/docs
https://hw.codedock.top/2025-2026-2/final/sites/test_final_001/
https://sites.hw.codedock.top/test_final_001/
```

确认：

```text
/api-docs 是学生接口说明
/docs 未登录不公开，教师登录后请求的是带前缀的 openapi.json
/admin 登录后接口请求带前缀
学生站点 URL 不跳到 hw.codedock.top 的域名根路径
hw.codedock.top 下的 /sites/test_final_001/ 不直接返回学生 HTML，而是跳转到 sites.hw.codedock.top/test_final_001/
学生站点 api-config.js 中的 API_ROOT 指向 hw.codedock.top/2025-2026-2/final
学生站点 api-config.js 中的 API_BASE 指向 hw.codedock.top/2025-2026-2/final/api/test_final_001
静态文件 CSS / JS 路径正确
```

------

## 14. HTTPS 和 Cookie 检查

正式线上：

```text
FINAL_BACKEND_COOKIE_SECURE=true
浏览器访问必须是 https://
```

检查：

```text
教师 /admin 登录成功
刷新页面后仍保持登录
浏览器开发者工具中 Cookie 带 Secure
教师接口不再返回 401
```

如果临时用 HTTP 测试：

```text
FINAL_BACKEND_COOKIE_SECURE=false
```

否则浏览器不会在 HTTP 请求中发送 Secure Cookie。

------

## 15. Live Server 跨域检查

学生本地可能使用：

```text
http://127.0.0.1:5500/
```

本地页面请求云端：

```js
fetch("https://hw.codedock.top/2025-2026-2/final/api/test_final_001/products")
```

检查：

```text
GET 公开资源没有 CORS 报错
POST 公开互动资源没有 CORS 报错
带 Authorization 的管理请求没有 CORS 报错
OPTIONS 预检请求通过
```

如果失败，优先检查：

```text
FINAL_BACKEND_ENABLE_CORS=true
FINAL_BACKEND_CORS_ORIGINS 包含 https://sites.hw.codedock.top 和当前本地开发 origin
allow_headers 包含 Authorization 和 Content-Type
allow_methods 包含 GET / POST / PUT / DELETE / OPTIONS
```

------

## 16. 教师导出检查

教师页面导出建议使用一次性短时 token。

检查：

```text
教师登录后可以生成导出链接
导出链接短时间内有效
下载一次后 token 失效
退出登录后不能生成新导出链接
导出文件名支持中文或至少不乱码
```

线上关闭 Header 教师密钥后，直接请求导出接口应失败。

------

## 17. 上线前收尾

上线给学生前确认：

```text
自动测试通过
本地人工试跑通过
云端 /admin 可登录
云端 /api-docs 正常
云端 /docs 教师登录后正常
云端 /sites/test_final_001/ 正常
公开 POST 限流生效
测试学生数据已清理
测试学生账号保留
正式学生名单已同步
数据目录已备份
记录总数和 SQLite 文件大小正常
Nginx 已 reload
systemd 服务已重启
线上 Header 教师密钥已关闭
默认密码和默认密钥没有在线上使用
FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=true
FINAL_BACKEND_CORS_ORIGINS 允许学生作品域名和常见本地开发 origin，不使用 *
/api/admin/status 的部署检查没有线上硬化警告
```

如有任何一项不能验证，应在上线说明中明确标注原因和风险。

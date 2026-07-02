# PROJECT_PLAN.md — 期末作品平台后端计划

最后更新日期：2026-06-27

------

## 1. 项目定位

本子项目用于支撑 Web 前端课程期末大作业。它不是通用多课程平台，也不是完整生产级 CMS，而是一个面向本课程期末作品的轻量平台：

```text
教师管理学生账号
学生登录后管理自己的接口、数据和静态网站
访客打开学生作品后可以浏览、评论、留言或提交表单
```

建议新建独立目录：

```text
backend_final_exam/
```

不要继续在 `teaching_fastapi_server/` 中叠加功能。`teaching_fastapi_server/` 功能完整但耦合较高，已经包含通用 CRUD、作品空间、上传、互评、教师工具、JSON / SQLite 双模式等多条线。期末后端应吸收其中有效经验，但独立实现更清晰。

本项目可以参考 `backend_ass4_ass5/` 的独立后端经验，但不能机械复制其接口。Ass4/5 以学号和对接码调用接口；期末后端需要学生登录课程平台账号，并管理自己的作品空间。

------

## 2. 正式任务依据

期末任务以正式提交版为准：

```text
final_exam_materials/Web 前端课程期末大作业说明-最后提交.md
```

评分重点是：

```text
HTML / CSS / JavaScript
fetch 数据交互
数据展示、新增、修改、删除
动态渲染和操作反馈
页面设计与交互体验
代码结构
云端部署和演示
```

正式评分说明中已经写明：

```text
本次作业不考核登录、注册、退出登录、token、当前用户信息等功能。
```

因此，平台登录不是学生作品的评分核心，而是用于给学生本人提供“作者管理权限”。学生作品给普通访客使用时，不要求访客登录。

------

## 3. 角色定义

### 3.1 教师

教师负责：

```text
创建学生账号
重置学生密码
停用或启用学生
查看学生资源和数据
查看学生上传的网站文件
导出数据
清空测试数据或某个学生空间
必要时重置学生网站文件
```

教师入口应使用 `/admin` 页面和 Cookie 会话。Header 密钥最多作为本地调试兼容入口，线上应能关闭。

### 3.2 学生作者

学生作者使用课程平台账号登录。课程平台账号相当于该学生作品的后台管理员账号。

学生登录后可以：

```text
创建资源接口
设置资源权限模式
查看自己的 API 地址和 fetch 示例
查看、新增、修改、删除自己的数据
上传静态网站文件
打开自己的线上作品地址
在自己作品里制作 admin.html 管理页
```

### 3.3 普通访客

普通访客包括同学互评时访问作品的人。访客不需要课程账号。

访客可以：

```text
打开 /sites/{学号}/
浏览公开数据
提交评论、留言、报名、反馈等允许公开提交的数据
```

访客不能：

```text
修改或删除学生已有数据
管理资源接口
查看私密收集型数据列表
访问教师后台
```

------

## 4. 核心设计

### 4.1 每个学生一个作品空间

每个学生使用学号作为空间标识：

```text
学生账号：20240101
接口空间：/api/20240101/
网站空间：/sites/20240101/
```

后端要校验：

```text
token 属于 20240101，才可以管理 /api/20240101/ 下的数据和资源
```

### 4.2 虚拟接口，不动态创建 Python 路由

学生可以创建自己的资源接口，例如：

```text
products
posts
comments
orders
signups
```

学生前端看到的接口是真实 URL：

```text
GET    /api/20240101/products
POST   /api/20240101/products
PUT    /api/20240101/products/{id}
DELETE /api/20240101/products/{id}
```

但后端代码不需要为每个资源动态新增 Python 路由，而是用统一路由接住：

```text
/api/{student_id}/{resource_name}
```

数据库记录：

```text
student_id
resource_name
access_mode
record data
```

这种方式让学生感觉是在管理自己的真实接口，同时避免运行时动态注册路由带来的复杂度。

### 4.3 资源名规则

资源名只允许：

```text
英文字母
数字
下划线
中划线
```

建议长度：

```text
1-40
```

中文只作为显示名，例如：

```text
resource_name = products
display_name = 商品
```

不要把中文直接放进 URL，减少学生调试和部署时的编码问题。

------

## 5. 权限模式

学生创建资源时需要选择权限模式。基础作品主要使用前三类；第四类用于教师案例或挑战型公开协作作品。

| 中文名称 | 底层值 | GET | POST | PUT / DELETE | 适合场景 |
| ---- | ---- | ---- | ---- | ---- | ---- |
| 公开展示 | `public_read` | 访客可看 | 学生登录后可发 | 学生登录后可改删 | 商品、文章、活动、作品 |
| 公开互动 | `public_submit` | 访客可看 | 访客可提交 | 学生登录后可改删 | 评论、留言、反馈 |
| 私密收集 | `private_collect` | 学生登录后可看 | 访客可提交 | 学生登录后可改删 | 报名、订单、联系表单 |
| 公开协作 | `public_collaborate` | 访客可看 | 访客可提交 | 访客可改，删除需作者登录 | 飞行棋、五子棋、共享房间状态 |

判断规则：

```text
GET:
  public_read / public_submit / public_collaborate 不需要 token
  private_collect 需要作者 token

POST:
  public_submit / private_collect / public_collaborate 不需要 token
  public_read 需要作者 token

PUT / DELETE:
  public_collaborate 的 PUT 不需要 token
  其它 PUT 和全部 DELETE 需要作者 token
```

这样可以覆盖大多数期末作品：

```text
商品展示站：products = 公开展示，comments = 公开互动
博客站：posts = 公开展示，comments = 公开互动
活动站：events = 公开展示，signups = 私密收集
作品集：works = 公开展示，messages = 公开互动
飞行棋案例：rooms = 公开协作，moves = 公开互动
```

------

## 6. 高频写入与硬盘损耗控制

期末后端会允许访客提交评论、留言、报名和反馈。公开提交接口如果不加限制，可能产生大量 SQLite 写入，带来数据库膨胀、磁盘 I/O 压力和云服务器硬盘损耗风险。因此第一版必须把“写入控制”作为核心设计，而不是上线后再补。

### 6.1 不做高频逐条写入

第一版不建议实现或默认开启：

```text
每次浏览都写一条 view 记录
每次页面打开都写访问日志到 SQLite
每次点击都写行为日志
自动保存输入框草稿到后端
轮询接口里顺便写心跳记录
```

如后续需要浏览量，可优先使用：

```text
内存计数 + 定时低频落库
按 IP / 访客标识短时间去重
只保存聚合数字，不保存每次访问明细
```

### 6.2 公开提交必须有限额

所有不需要 token 的 POST 都必须有基础限制：

```text
单 IP 每分钟写入次数限制
单资源每分钟写入次数限制
单学生空间每日新增记录上限
单资源记录总数上限
单条 JSON body 大小上限
字段字符串长度上限
```

建议第一版默认值：

```text
单 IP 每分钟最多 20 次公开 POST
单学生空间每分钟最多 120 次公开 POST
单学生空间总 records 最多 5000 条
单资源总 records 最多 1000 条
单条请求体最大 32KB
单个字符串字段最大 2000 字符
```

这些默认值可通过环境变量调整，但不应默认无限制。

### 6.3 写入策略

SQLite 写入建议：

```text
启用 WAL
设置 busy_timeout
写入事务尽量短
不要每次请求都 VACUUM
不要每条数据写多个冗余表
列表读取分页，默认 pageSize 不超过 20 或 50
管理端导出走只读查询，避免导出过程修改状态
```

对公开提交型和私密收集型资源，后端只保存业务数据本身，不额外写访问日志。

### 6.4 清理和归档

教师后台需要支持：

```text
查看每个学生空间记录数
查看每个资源记录数
清空某个资源
清空某个学生的测试数据
导出后清理
```

上线前和互评前应清理测试账号产生的数据，避免测试垃圾占用空间。

### 6.5 监控检查

上线检查应包含：

```text
SQLite 文件大小
-wal 文件大小
data 目录总大小
记录总数
单学生最大记录数
最近公开 POST 频率
磁盘剩余空间
```

如果 SQLite WAL 文件持续变大，应安排低峰期 checkpoint，而不是频繁对线上库做重操作。

------

## 7. 主要接口草案

### 7.1 认证接口

学生不开放注册，账号由教师创建。

```text
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/change-password
POST /api/auth/logout
```

后续管理请求携带：

```text
Authorization: Bearer token_xxx
```

学生第一次使用名单初始密码登录时，`GET /api/auth/me` 和登录返回的 `user.mustChangePassword` 为 `true`。学生可在 `/student` 页面修改密码。教师重置密码时默认重置回名单中的初始密码。

### 7.1.1 教师账号和名单接口

期末后端可以读取 `backend_ass4_ass5/data/students.json`，复用同一门课的 111 名正式学生和 10 个长期测试账号：

```text
POST /api/admin/students/sync
POST /api/admin/students
PUT  /api/admin/students/{student_id}
POST /api/admin/students/{student_id}/reset-password
```

`POST /api/admin/students` 只用于新建账号；如果学号已存在，应返回冲突提示，不静默重置密码。已有学生资料修改走 `PUT`，密码重置走 `reset-password`。同步名单时，如果学生已经修改过密码，后端保留当前密码，只更新可重置的初始密码。

### 7.2 学生资源管理接口

这些接口需要学生本人 token。

```text
GET    /api/student/resources
POST   /api/student/resources
PUT    /api/student/resources/{resource_name}
DELETE /api/student/resources/{resource_name}
```

新增资源示例：

```json
{
  "resourceName": "comments",
  "displayName": "评论",
  "accessMode": "public_submit"
}
```

### 7.3 虚拟数据接口

学生作品和访客主要调用这些接口。

```text
GET    /api/{student_id}/{resource_name}
POST   /api/{student_id}/{resource_name}
GET    /api/{student_id}/{resource_name}/{record_id}
PUT    /api/{student_id}/{resource_name}/{record_id}
DELETE /api/{student_id}/{resource_name}/{record_id}
```

列表接口使用分页：

```text
GET /api/{student_id}/{resource_name}?page=1&pageSize=20
```

返回：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "pageSize": 20
}
```

新增数据时，body 可以是任意 JSON 对象：

```json
{
  "title": "商品 A",
  "price": 99,
  "imageUrl": "images/a.jpg"
}
```

后端自动补充：

```text
id
student_id
resource_name
created_at
updated_at
created_by_role
```

### 7.4 静态网站托管

访问：

```text
GET /sites/{student_id}/
GET /sites/{student_id}/{file_path}
```

学生上传后保存到：

```text
data/sites/{student_id}/
```

上传入口可以第一版只在学生管理页中提供，不必让学生用代码直接调。

------

### 7.5 学生文件接口

学生作品中的固定图片、音频、视频可以直接放进网站 zip。运行过程中需要上传并保存到业务数据里的文件，使用独立文件接口：

```text
GET    /api/student/files
POST   /api/student/files
DELETE /api/student/files/{file_id}

GET    /media/{student_id}/{file_id}/{filename}
```

文件接口需要学生本人 token。上传成功后返回：

```json
{
  "id": "file_xxx",
  "originalName": "cover.jpg",
  "kind": "image",
  "sizeBytes": 12345,
  "fileUrl": "https://sites.example.com/media/20240101/file_xxx/file_xxx.jpg"
}
```

学生可以把 `fileUrl` 存进自己的资源数据里，例如：

```json
{
  "title": "活动海报",
  "imageUrl": "https://sites.example.com/media/20240101/file_xxx/file_xxx.jpg"
}
```

默认限制：

```text
图片 2MB
PDF 5MB
音频 5MB
视频 20MB
单学生 100 个文件
单学生总量 50MB
```

文件接口不记录每次访问日志。删除业务数据时不自动删除文件，避免误删；学生或教师可以单独清理文件。

开启 `FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN=true` 后，`/media/...` 与 `/sites/...` 一样检查 Host。课程后台域名访问媒体文件会 308 跳转到 `FINAL_BACKEND_SITE_BASE_URL`，避免学生上传媒体从后台/API origin 直接打开。

------

### 7.6 教师资源级运维和归档接口

教师可以通过 `/admin` 页面或接口查看、导出和清理单个学生的资源数据，并下载完整归档：

```text
GET    /api/admin/students/{student_id}/resources/{resource_name}/records
GET    /api/admin/students/{student_id}/resources/{resource_name}/export
DELETE /api/admin/students/{student_id}/resources/{resource_name}/records
GET    /api/admin/students/{student_id}/archive
```

资源级清理会先写入 `data/backups/admin-actions/` 备份和 `admin_audits` 审计记录。完整归档 zip 包含账号信息、资源定义、records、文件清单、静态站点文件和媒体文件。

------

## 8. 静态网站上传与上线

第一版建议支持 zip 上传。

学生本地项目结构建议：

```text
index.html
css/
js/
images/
```

上传后访问：

```text
本地：/sites/20240101/
线上：https://sites.example.com/20240101/
```

实现要求：

```text
必须限制解压路径在 data/sites/{student_id}/ 下
必须拒绝路径穿越，例如 ../
必须限制单个 zip 大小
必须限制单个学生站点总大小
必须限制文件数量
默认不执行任何学生上传的服务端脚本
index.html 不存在时给出清楚提示
```

不建议后端自动批量修改学生 HTML / JS 中的接口地址，容易改坏。推荐学生引入平台生成的配置文件：

```html
<script src="./api-config.js"></script>
```

然后使用：

```js
const API_ROOT = window.API_ROOT;
const API_BASE = window.API_BASE;

fetch(API_BASE + "/comments")
```

`api-config.js` 由后端根据 `FINAL_BACKEND_PUBLIC_BASE_URL` 和 `FINAL_BACKEND_ROOT_PATH` 生成。`API_ROOT` 指向课程平台根地址，`API_BASE` 指向当前学生自己的 `/api/{student_id}`，避免子路径部署时请求到域名根路径。

第一版线上安全边界：

```text
后台和 API：course.example.com
学生作品：sites.example.com
```

学生作品主要用于展示、评论、留言、报名等公开交互。学生本人管理资源和数据回到平台 `/student` 页面，不把平台 token 长期放在上传作品里。

------

## 9. 数据存储建议

第一版只做 SQLite，不做 JSON / SQLite 双模式。

建议表：

```text
students
sessions
resources
records
files
admin_sessions
rate_limits
```

SQLite 要求：

```text
启用 WAL
设置 busy_timeout
所有写入使用短事务
运行数据默认不进入 Git
线上数据目录放到代码目录外
```

线上建议数据目录：

```text
/srv/final_backend_data
```

不要把 SQLite 文件、上传网站文件、导出文件提交到 Git。

------

## 10. 云端部署要求

需要从第一版就考虑云端，不要等功能完成后补。

建议环境变量：

```bash
export FINAL_BACKEND_ADMIN_PASSWORD="强密码"
export FINAL_BACKEND_COOKIE_SECURE="true"
export FINAL_BACKEND_HOST="127.0.0.1"
export FINAL_BACKEND_ROOT_PATH="/2025-2026-2/final"
export FINAL_BACKEND_PUBLIC_BASE_URL="https://course.example.com/2025-2026-2/final"
export FINAL_BACKEND_SITE_BASE_URL="https://sites.example.com"
export FINAL_BACKEND_DATA_DIR="/srv/final_backend_data"
export FINAL_BACKEND_ENABLE_CORS="true"
export FINAL_BACKEND_CORS_ORIGINS="https://sites.example.com"
export FINAL_BACKEND_ENABLE_TEACHER_KEY="false"
export FINAL_BACKEND_REQUIRE_CUSTOM_TEACHER_KEY="true"
export FINAL_BACKEND_LOGIN_RATE_LIMIT_ENABLED="true"
export FINAL_BACKEND_TRUST_PROXY_HEADERS="true"
export FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN="true"
export FINAL_BACKEND_DEFAULT_PAGE_SIZE="20"
export FINAL_BACKEND_MAX_PAGE_SIZE="50"
export FINAL_BACKEND_MAX_STUDENT_FILE_COUNT="100"
export FINAL_BACKEND_MAX_STUDENT_FILE_TOTAL_BYTES="52428800"
export FINAL_BACKEND_MAX_IMAGE_FILE_BYTES="2097152"
export FINAL_BACKEND_MAX_PDF_FILE_BYTES="5242880"
export FINAL_BACKEND_MAX_AUDIO_FILE_BYTES="5242880"
export FINAL_BACKEND_MAX_VIDEO_FILE_BYTES="20971520"
export FINAL_BACKEND_UPLOAD_CHUNK_BYTES="1048576"
export FINAL_BACKEND_PORT="8000"
```

必须提前处理：

```text
子路径部署 root_path
HTTPS 下 Secure Cookie
HTTP 临时测试时不要开启 Secure Cookie
systemd 非交互启动
FINAL_BACKEND_HOST 固定为 127.0.0.1
SQLite data/ 目录写权限
SQLite -wal / -shm 文件写权限
Nginx client_max_body_size
Nginx 请求体上限略高于应用单文件上限
X-Forwarded-Prefix / Proto / Host
课程域名下 /sites/... 不直接服务学生 HTML
上传 zip 路径穿越
静态文件响应 Content-Type
教师导出使用一次性短时 token
线上关闭默认 Header 教师密钥
后台/API 与学生作品使用不同 origin
后端返回给浏览器的链接使用 PUBLIC_BASE_URL / SITE_BASE_URL
登录失败限流
公开提交接口限流和容量限制
学生文件上传类型、数量和容量限制
列表接口分页
反代环境可信 IP 头配置
正式环境强制后台/API 和学生作品不同 origin
教师清空 records/site/files 前自动备份和审计
```

------

## 11. 第一版不做

第一版先不要做：

```text
学生作品内部真实注册登录系统
自动评分
内置互评系统
真实动态创建 Python 路由
复杂字段建模和字段校验器
每次浏览逐条写入日志
高频行为追踪
多教师协作后台
WebSocket
对象存储
生产级防刷和风控
```

这些可以后续扩展，但不进入最小可用期末平台。

------

## 12. 第一版验收标准

最小可用版本应满足：

```text
教师可以创建学生账号
学生可以登录
学生可以创建 products / comments / signups 等资源
资源有四类权限模式，基础作品主要使用前三类
访客可以 GET 公开展示资源
访客可以 POST 公开互动和私密收集资源
访客公开 POST 受到频率和容量限制
学生带 token 可以 POST / PUT / DELETE 自己资源的数据
学生不能管理其他学生空间
学生可以上传静态网站
/sites/{学号}/ 可以打开学生网站
学生网站可以 fetch /api/{学号}/{资源名}
教师可以查看、导出、清空某个学生的数据
教师可以查看记录数量和数据目录大小
子路径反代下页面、接口、OpenAPI、静态网站都不跳到域名根路径
SQLite 在 systemd 用户下可写
自动测试覆盖权限、隔离、限流、静态站点路径和 root_path
```

------

## 13. 建议实施阶段

```text
阶段 1：实现账号、登录、资源、records CRUD、权限模式和写入限制。
阶段 2：实现教师后台、导出、清空、学生资源管理页和数据量统计。
阶段 3：实现静态网站 zip 上传和 /sites/{学号}/ 托管。
阶段 4：做本地自动测试和试跑文档中的人工检查。
阶段 5：云端子路径部署，处理 HTTPS、Cookie、SQLite 权限和 CORS。
阶段 6：写学生最小对接说明和教师管理说明。
```

接口冻结后，再写学生分发文档。学生文档只推荐一种最稳写法，优先使用：

```text
querySelector
onclick
onsubmit
event.preventDefault()
fetch().then()
JSON.stringify()
FormData
localStorage
```

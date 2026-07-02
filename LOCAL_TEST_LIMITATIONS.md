# LOCAL_TEST_LIMITATIONS.md - 期末后端本地测试边界说明

最后更新日期：2026-06-30

------

## 1. 文档用途

本文档用于约束“模拟学生本地测试”对话的反馈范围。

建议分工：

```text
当前主对话：判断后端设计、修改代码、维护文档、决定哪些问题需要上线验证。
独立测试对话：模拟学生使用平台，只反馈本地能够验证或复现的问题。
```

独立测试对话可以发现学生视角的问题，但不要把所有反馈都当成本地缺陷。遇到域名、HTTPS、Nginx、systemd、云服务器权限等内容时，应标记为“上线验证项”。

------

## 2. 本地测试推荐环境

本地测试默认使用：

```bash
cd backend_final_exam
python run.py
```

推荐本地环境变量：

```bash
export FINAL_BACKEND_COOKIE_SECURE="false"
export FINAL_BACKEND_ROOT_PATH=""
export FINAL_BACKEND_PUBLIC_BASE_URL=""
export FINAL_BACKEND_SITE_BASE_URL=""
export FINAL_BACKEND_DATA_DIR="./data"
export FINAL_BACKEND_ENABLE_CORS="true"
export FINAL_BACKEND_ENABLE_TEACHER_KEY="true"
export FINAL_BACKEND_REQUIRE_SEPARATE_SITE_ORIGIN="false"
export FINAL_BACKEND_TRUST_PROXY_HEADERS="false"
export FINAL_BACKEND_PORT="8000"
```

本地访问地址：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api-docs
http://127.0.0.1:8000/admin
http://127.0.0.1:8000/student
http://127.0.0.1:8000/docs  # 教师登录 /admin 后可看
http://127.0.0.1:8000/sites/{studentId}/
```

------

## 3. 本地可以可靠验证的内容

本地测试可以重点检查：

```text
教师能登录 /admin。
教师能创建、停用、启用、重置学生账号。
教师能同步 Ass4/5 学生名单。
学生能登录 /student。
学生使用初始密码登录后能看到改密提醒。
学生能修改密码。
学生能创建 resources。
四类 accessMode 的 GET / POST / PUT / DELETE 权限符合预期。
学生 A 不能管理学生 B 的数据。
访客能读取 public_read / public_submit 允许公开读取的数据。
访客能向 public_submit / private_collect 提交数据。
public_collaborate 资源允许访客提交和修改公开协作数据。
普通访客默认不能修改或删除数据；public_collaborate 只例外放开 PUT。
所有模式下匿名 DELETE 必须失败，登录的非空间拥有者 DELETE 也必须失败。
公开提交接口有限流和容量限制。
学生能上传静态网站 zip。
/sites/{studentId}/ 能返回 index.html。
静态站点能加载 CSS、JS、图片等文件。
.js 文件返回 application/javascript，不应返回 text/plain。
api-config.js 能生成 API_ROOT 和 API_BASE。
学生作品能 fetch API_BASE + "/资源名"。
学生能上传、查看、删除媒体文件。
媒体文件大小、类型、数量限制生效。
教师能导出数据和完整归档。
教师清空数据前会生成备份。
本地 SQLite 能正常写入，不写每次浏览日志。
```

------

## 4. 本地不能直接下结论的内容

下面这些问题在本地可以记录，但不能直接判定为后端缺陷：

```text
真实 HTTPS 是否正常。
Secure Cookie 在线上浏览器中是否发送。
course.example.com 和 sites.example.com 双 origin 是否完全隔离。
Nginx 子路径反代是否正确。
Nginx 是否正确转发 Host、X-Forwarded-Proto、X-Forwarded-Host、X-Forwarded-Prefix。
线上 /2025-2026-2/final 这类 root_path 是否完全正确。
DNS、域名解析、证书签发、服务器防火墙是否正确。
公网用户是否能访问服务器。
systemd 是否能长期守护后端进程。
Ubuntu 上数据目录、SQLite、-wal、-shm 文件权限是否正确。
Nginx client_max_body_size 是否匹配后端上传限制。
反代后的真实客户端 IP 是否能用于限流。
111 名正式学生同时使用时的真实性能。
云服务器磁盘空间、备份、日志轮转是否充足。
```

这些内容应写成：

```text
上线验证项：需要部署到 Ubuntu + Nginx + HTTPS + 正式域名后验证。
```

------

## 5. 本地测试常见误判

### 5.1 Chrome DevTools 的 well-known 404

如果后端日志出现：

```text
GET /.well-known/appspecific/com.chrome.devtools.json 404 Not Found
```

这是 Chrome / DevTools 自动探测请求，不是学生作品请求的资源，也不是后端缺陷。可以忽略。

### 5.2 页面太简单不等于后端失败

如果模拟作品只显示：

```text
Codex Live Final Site
items=1
```

需要先检查作品源码。若 `index.html` 只写了标题和一个容器，`app.js` 只把接口数量写到页面上，那么这正是预期结果。

### 5.3 MIME 报错要看当前响应头

如果浏览器曾经报：

```text
Refused to execute script because its MIME type ('text/plain') is not executable
```

先直接检查当前响应头：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/sites/{studentId}/app.js" -UseBasicParsing
```

重点看：

```text
Content-Type: application/javascript
X-Content-Type-Options: nosniff
```

如果当前响应头已经正确，但浏览器还报旧错误，优先尝试：

```text
Ctrl + F5 强制刷新。
开发者工具 Network 勾选 Disable cache 后刷新。
确认 8000 端口运行的是当前 backend_final_exam 目录里的代码。
```

### 5.4 本地不要强行测试线上安全 Cookie

本地 HTTP 环境应使用：

```text
FINAL_BACKEND_COOKIE_SECURE=false
```

线上 HTTPS 环境才使用：

```text
FINAL_BACKEND_COOKIE_SECURE=true
```

如果本地 HTTP 开启 Secure Cookie，浏览器不会发送 Cookie，这不是登录接口本身失败。

------

## 6. 独立测试对话的反馈格式

建议让独立测试对话按下面格式反馈：

```text
问题标题：
本地地址：
测试账号：
操作步骤：
预期结果：
实际结果：
浏览器控制台错误：
Network 关键请求和状态码：
是否属于本地可验证：是 / 否
如果否，归类为：上线验证项 / 测试作品过于简陋 / 浏览器缓存 / 使用方式不明确
建议处理：修复后端 / 修改文档 / 上线后验证 / 忽略
```

如果没有 Network 信息，不建议直接判断为后端缺陷。

------

## 7. 可直接给独立测试对话的提示词

```text
你现在扮演 Web 前端课程期末作业的学生测试员。
请只测试本地能够验证的问题，不要把 HTTPS、正式域名、Nginx、systemd、Ubuntu 文件权限、真实公网访问这类问题当成本地后端缺陷。
如果遇到这些内容，请标记为“上线验证项”。

本地后端地址：http://127.0.0.1:8000
学生管理页：http://127.0.0.1:8000/student
教师管理页：http://127.0.0.1:8000/admin
学生作品地址：http://127.0.0.1:8000/sites/{studentId}/

请模拟学生完成：登录、创建资源、添加数据、上传静态网站 zip、让作品 fetch 自己的 API、上传图片或媒体文件。
反馈时必须包含：操作步骤、预期结果、实际结果、浏览器控制台错误、Network 关键请求和状态码，并说明该问题是否属于本地可验证。
```

------

## 8. 何时回到主对话处理

独立测试对话发现下面问题时，回到主对话处理：

```text
接口状态码明显错误。
返回 JSON 结构和文档不一致。
权限控制和 accessMode 规则不一致。
学生 A 可以操作学生 B 数据。
访客可以修改或删除数据。
上传 zip 后 /sites/{studentId}/ 无法打开。
CSS / JS / 图片 MIME 或路径错误。
api-config.js 生成的 API_ROOT / API_BASE 错误。
媒体文件上传、访问、删除流程错误。
/admin 或 /student 页面操作链路断掉。
测试文档表达让学生无法照着做。
```

发现下面问题时，先记录到上线检查，不急着改后端：

```text
正式域名访问失败。
HTTPS 证书问题。
Nginx 反代路径问题。
跨域只在正式双域名下出现。
systemd 重启失败。
Ubuntu 数据目录权限问题。
线上上传大文件被 Nginx 拦截。
公网访问、DNS、防火墙问题。
```

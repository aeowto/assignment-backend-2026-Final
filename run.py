"""Local runner for the final exam backend."""

import os

import uvicorn

from main import app


def main() -> None:
    host = os.getenv("FINAL_BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("FINAL_BACKEND_PORT", "8000"))
    print("期末作品平台后端已准备启动")
    print(f"教师账号：admin")
    print(f"教师密码：{app.state.admin_password}")
    print(f"地址：http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()


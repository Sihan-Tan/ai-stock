#!/usr/bin/env python3
"""根目录一键启动：FastAPI (uvicorn) + Vite 前端；Ctrl+C 同时结束两者。"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"
DEFAULT_SQLITE = "sqlite:///./data/desk.db"
API_HOST = "127.0.0.1"
API_PORT = 8000
WEB_PORT = 5173

_procs: list[subprocess.Popen[bytes]] = []


def _repo_python() -> str:
    """优先使用仓库 .venv 中的解释器。"""
    if sys.platform == "win32":
        candidates = [ROOT / ".venv" / "Scripts" / "python.exe"]
    else:
        candidates = [ROOT / ".venv" / "bin" / "python"]
    for path in candidates:
        if path.is_file():
            return str(path)
    return sys.executable


def _ensure_env() -> None:
    """若无 .env 则从 .env.example 复制，并默认写入 SQLite 便于本地一键跑。"""
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if env_path.is_file():
        print("[dev] 已存在 .env，将尊重其中配置。")
        return

    if not example.is_file():
        print("[dev] 未找到 .env / .env.example，将仅用进程环境变量。")
        os.environ.setdefault("DATABASE_URL", DEFAULT_SQLITE)
        return

    print("[dev] 未找到 .env，正在从 .env.example 复制…")
    lines: list[str] = []
    replaced = False
    for line in example.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            lines.append(f"DATABASE_URL={DEFAULT_SQLITE}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.insert(0, f"DATABASE_URL={DEFAULT_SQLITE}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[dev] 已创建 .env（默认 DATABASE_URL={DEFAULT_SQLITE}）。")


def _check_deps(python_exe: str) -> bool:
    """最小依赖检查；缺依赖时打印提示并返回 False。"""
    ok = True
    try:
        subprocess.run(
            [python_exe, "-c", "import fastapi, uvicorn"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        ok = False
        print(
            "[dev] 缺少 Python 依赖（fastapi / uvicorn）。\n"
            "      请先：python -m venv .venv && .\\.venv\\Scripts\\activate && "
            'pip install -e ".[dev]"'
        )

    if not (WEB_DIR / "package.json").is_file():
        ok = False
        print(f"[dev] 未找到前端工程：{WEB_DIR}")
    elif not (WEB_DIR / "node_modules").is_dir():
        ok = False
        print(
            "[dev] 前端依赖未安装（缺少 apps/web/node_modules）。\n"
            "      请先：cd apps/web && npm install"
        )

    if shutil.which("npm") is None:
        ok = False
        print("[dev] 未找到 npm，请先安装 Node.js。")

    return ok


def _stop_all() -> None:
    """终止所有子进程（Windows 下含进程树）。"""
    for proc in list(_procs):
        if proc.poll() is not None:
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                proc.send_signal(signal.SIGTERM)
        except OSError:
            pass

    deadline = time.time() + 5
    for proc in list(_procs):
        remaining = max(0.0, deadline - time.time())
        try:
            proc.wait(timeout=remaining if remaining > 0 else 0.1)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
    _procs.clear()


def _on_signal(_signum: int, _frame: object) -> None:
    """Ctrl+C / SIGTERM：结束前后端子进程。"""
    print("\n[dev] 正在停止 API 与前端…")
    _stop_all()
    sys.exit(0)


def main() -> int:
    """启动 API + Web，前台等待任一退出或用户中断。"""
    os.chdir(ROOT)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    _ensure_env()
    python_exe = _repo_python()
    if not _check_deps(python_exe):
        return 1

    # 若仓库根尚无 .env 以外的覆盖，且用户未显式设置，则保证 SQLite 一键可用
    if "DATABASE_URL" not in os.environ and not (ROOT / ".env").is_file():
        os.environ["DATABASE_URL"] = DEFAULT_SQLITE

    signal.signal(signal.SIGINT, _on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_signal)

    env = os.environ.copy()
    # 保证可从仓库根导入 app（uvicorn --app-dir）
    api_cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        API_HOST,
        "--port",
        str(API_PORT),
        "--app-dir",
        str(API_DIR),
    ]
    web_cmd = ["npm", "run", "dev"]
    if sys.platform == "win32":
        # npm 在 Windows 上常为 npm.cmd
        web_cmd = ["npm.cmd", "run", "dev"]

    print(f"[dev] API  → http://{API_HOST}:{API_PORT}/health  (docs: /docs)")
    print(f"[dev] Web → http://{API_HOST}:{WEB_PORT}/")
    print("[dev] Ctrl+C 同时停止两者\n")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    try:
        api_proc = subprocess.Popen(
            api_cmd,
            cwd=ROOT,
            env=env,
            creationflags=creationflags,
        )
        _procs.append(api_proc)

        web_proc = subprocess.Popen(
            web_cmd,
            cwd=WEB_DIR,
            env=env,
            creationflags=creationflags,
        )
        _procs.append(web_proc)
    except OSError as exc:
        print(f"[dev] 启动失败：{exc}")
        _stop_all()
        return 1

    # 等待任一子进程退出
    while True:
        for proc in _procs:
            code = proc.poll()
            if code is not None:
                print(f"[dev] 子进程已退出 (pid={proc.pid}, code={code})，正在清理…")
                _stop_all()
                return code if isinstance(code, int) else 1
        time.sleep(0.4)


if __name__ == "__main__":
    raise SystemExit(main())

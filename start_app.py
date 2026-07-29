#!/usr/bin/env python3
"""Utility launcher for the Upbit trading app.

Running this script performs the following steps without relying on a
virtual environment:

1. Installs/updates the backend Python dependencies globally for the
   current interpreter.
2. Installs/updates the frontend Node dependencies via npm.
3. Boots both the FastAPI backend (uvicorn) and the React frontend (Vite)
   so they run concurrently.

It is designed to simplify first-run setup on Windows, macOS, and Linux.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"


def run_step(command: Iterable[str], *, cwd: Path, description: str) -> None:
    """Execute a command synchronously, surfacing its output live."""
    cmd_list: list[str] = list(command)
    print(f"\n[setup] {description}\n        $ {' '.join(cmd_list)}\n")
    subprocess.run(cmd_list, cwd=str(cwd), check=True)


def spawn_process(command: Iterable[str], *, cwd: Path, name: str) -> subprocess.Popen:
    cmd_list: list[str] = list(command)
    print(f"[launch] starting {name}: {' '.join(cmd_list)}")
    return subprocess.Popen(cmd_list, cwd=str(cwd))


def terminate_process(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return
    print(f"[shutdown] stopping {name} (pid={proc.pid})")
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        print(f"[shutdown] force killing {name} (pid={proc.pid})")
        proc.kill()


def ensure_dependencies(skip_install: bool) -> None:
    if skip_install:
        return

    run_step(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=BACKEND_DIR,
        description="Installing backend Python dependencies",
    )
    run_step(
        ["npm", "install"],
        cwd=FRONTEND_DIR,
        description="Installing frontend Node dependencies",
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the trading dashboard stack")
    parser.add_argument("--skip-install", action="store_true", help="Skip dependency installation steps")
    parser.add_argument("--backend-host", default="0.0.0.0", help="Host interface for the FastAPI server")
    parser.add_argument("--backend-port", default="8000", help="Port for the FastAPI server")
    parser.add_argument("--frontend-host", default="0.0.0.0", help="Host interface for the Vite dev server")
    parser.add_argument("--frontend-port", default="5173", help="Port for the Vite dev server")
    parser.add_argument("--no-frontend", action="store_true", help="Do not start the frontend dev server")
    parser.add_argument("--no-backend", action="store_true", help="Do not start the backend API server")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.no_backend and args.no_frontend:
        parser.error("Both --no-backend and --no-frontend are set; nothing to run.")

    ensure_dependencies(args.skip_install)

    processes: list[tuple[subprocess.Popen, str]] = []
    try:
        if not args.no_backend:
            backend_cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                args.backend_host,
                "--port",
                str(args.backend_port),
                "--reload",
            ]
            processes.append((spawn_process(backend_cmd, cwd=BACKEND_DIR, name="backend"), "backend"))

        if not args.no_frontend:
            frontend_cmd = [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                args.frontend_host,
                "--port",
                str(args.frontend_port),
            ]
            processes.append((spawn_process(frontend_cmd, cwd=FRONTEND_DIR, name="frontend"), "frontend"))

        if not processes:
            print("No processes started. Exiting.")
            return 0

        print("\nServers are running. Press Ctrl+C to stop.\n")
        while True:
            for proc, name in list(processes):
                return_code = proc.poll()
                if return_code is not None:
                    print(f"[exit] {name} exited with code {return_code}")
                    processes.remove((proc, name))
                    if return_code != 0:
                        return return_code
                    if not processes:
                        return 0
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[signal] Keyboard interrupt received. Shutting down...")
        return 0
    finally:
        for proc, name in processes:
            terminate_process(proc, name)


if __name__ == "__main__":
    sys.exit(main())

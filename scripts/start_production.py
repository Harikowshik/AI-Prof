"""Production entrypoint for Render (migrate, seed demo data, serve API)."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def run(args: list[str]) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.check_call(args)


def main() -> None:
    run([sys.executable, "-m", "alembic", "upgrade", "head"])
    run([sys.executable, "scripts/seed.py"])
    run([sys.executable, "scripts/generate_data.py"])
    port = os.environ.get("PORT", "10000")
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()

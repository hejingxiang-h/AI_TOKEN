"""Start isolated fixture and native LiteLLM processes, run probes, then clean up."""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
OPENER = build_opener(ProxyHandler({}))


@contextmanager
def child(command: list[str], output: Path, env: dict[str, str],
          cwd: Path) -> Iterator[subprocess.Popen[Any]]:
    with output.open("wb") as stream:
        process = subprocess.Popen(command, env=env, cwd=cwd, stdout=stream,
                                   stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=8)


def ready(url: str, process: subprocess.Popen[Any], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited ({process.returncode}) while waiting for {url}")
        try:
            with OPENER.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, OSError):
            pass
        time.sleep(0.5)
    raise TimeoutError(f"No readiness response from {url}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--protocol-only", action="store_true")
    parser.add_argument("--fixture-port", type=int, default=18089)
    parser.add_argument("--proxy-port", type=int, default=18401)
    parser.add_argument("--startup-timeout", type=int, default=45)
    args = parser.parse_args()
    logs = args.logs.resolve()
    logs.mkdir(parents=True, exist_ok=True)
    root = f"http://127.0.0.1:{args.fixture_port}"
    proxy = f"http://127.0.0.1:{args.proxy_port}"
    env = {
        **os.environ,
        "POC_MASTER_KEY": f"sk-{secrets.token_hex(24)}",
        "POC_FAKE_PROVIDER_KEY": f"sk-{secrets.token_hex(24)}",
        "LITELLM_SALT_KEY": f"sk-{secrets.token_hex(24)}",
        "POC_UPSTREAM_ROOT": root,
        "POC_OPENAI_BASE": f"{root}/v1",
        "POC_PROXY_ROOT": proxy,
        "POC_FIXTURE_PORT": str(args.fixture_port),
        "POC_FIXTURE_BIND": "127.0.0.1",
        "LITELLM_TELEMETRY": "False",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.pop("LITELLM_LICENSE", None)
    if args.protocol_only:
        env.pop("DATABASE_URL", None)
    elif not env.get("DATABASE_URL"):
        parser.error("Set DATABASE_URL for the dedicated PoC database or use --protocol-only.")
    launcher = Path(sys.executable).with_name("litellm.exe" if os.name == "nt" else "litellm")
    probe = [sys.executable, str(HERE / "probe.py")]
    if args.protocol_only:
        probe.append("--protocol-only")
    proxy_command = [
        str(launcher), "--config", str(HERE / "config.yaml"),
        "--host", "127.0.0.1", "--port", str(args.proxy_port),
    ]
    with child([sys.executable, str(HERE / "fixture.py")], logs / "fixture.log", env, logs) as fixture:
        ready(f"{root}/_health", fixture, 10)
        with child(proxy_command, logs / "proxy.log", env, logs) as server:
            ready(f"{proxy}/health/liveliness", server, args.startup_timeout)
            return subprocess.run(probe, cwd=logs, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

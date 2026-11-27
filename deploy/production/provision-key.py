"""Provision a restricted proxy credential to stdout for redirection into a secret file."""
import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


def main() -> int:
    master = Path("/run/secrets/proxy_master_key").read_text().strip()
    request = Request(
        "http://127.0.0.1:4000/key/generate",
        data=json.dumps(
            {"models": ["deepseek-flash"], "key_type": "llm_api", "duration": "90d"}
        ).encode(),
        headers={"Authorization": f"Bearer {master}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=20) as response:
            key = json.load(response)["key"]
        if not isinstance(key, str) or not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,}", key):
            raise ValueError("Unrecognized credential format")
    except (URLError, ValueError, KeyError, TypeError):
        print("LiteLLM service Key provisioning failed.", file=sys.stderr)
        return 1
    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

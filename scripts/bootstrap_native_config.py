#!/usr/bin/env python3
"""Create or minimally complete the native macOS config without losing user data."""

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    data_root = Path(os.environ.get("COW_DATA_DIR", "~/.cow")).expanduser()
    data_root.mkdir(parents=True, exist_ok=True)
    config_path = data_root / "config.json"
    created = not config_path.exists()

    if created:
        config = json.loads((project_root / "config-template.json").read_text(encoding="utf-8"))
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            print(f"existing config is unreadable: {exc}", file=sys.stderr)
            return 1

    if not isinstance(config, dict):
        print("existing config must contain a JSON object", file=sys.stderr)
        return 1

    defaults = {
        "agent": True,
        "agent_workspace": "~/cow",
        "agent_permission_mode": "full-access",
        "web_console": True,
        "web_host": "127.0.0.1",
        "web_port": 9899,
    }
    for key, value in defaults.items():
        if created or config.get(key) in (None, ""):
            config[key] = value
    if created:
        config["channel_type"] = "web,weixin"

    generated_password = False
    if not str(config.get("web_password") or ""):
        config["web_password"] = secrets.token_urlsafe(24)
        generated_password = True

    data_root.chmod(0o700)
    fd, temp_name = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=str(data_root))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path.chmod(0o600)
        os.replace(temp_path, config_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    config_path.chmod(0o600)
    print(f"config_path={config_path}")
    if generated_password:
        print(f"web_password={config['web_password']}")
    else:
        print("web_password=existing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

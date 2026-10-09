"""Create a local workspace token without modifying or displaying existing secrets."""
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
path = root / "backend/private/control_token.txt"
if dotenv_values(root / "backend/.env").get("CONTROL_TOKEN"):
    print("Existing CONTROL_TOKEN will be used.")
else:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass
    print(f"Local access token available at {path}. Value not printed.")

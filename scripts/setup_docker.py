"""Create local Docker settings without overwriting existing credentials."""

import secrets
from pathlib import Path

target = Path(__file__).resolve().parents[1] / ".env.docker"
try:
    with target.open("x", encoding="utf-8") as output:
        output.write(f"APP_PORT=8014\nPOSTGRES_PASSWORD={secrets.token_hex(24)}\n")
except FileExistsError:
    print("Existing .env.docker preserved.")
else:
    print("Created .env.docker with a private local password. Do not commit this file.")

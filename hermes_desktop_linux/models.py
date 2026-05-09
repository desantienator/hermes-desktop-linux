from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import json, os, time

APP_ID = "hermes-desktop-linux"


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    p = base / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p

@dataclass
class ConnectionProfile:
    name: str = "local"
    host: str = "localhost"
    user: str = os.environ.get("USER", "")
    port: int = 22
    hermes_home: str = "~/.hermes"
    ssh_alias: str = ""

    @property
    def target(self) -> str:
        if self.ssh_alias.strip():
            return self.ssh_alias.strip()
        return f"{self.user}@{self.host}" if self.user else self.host

class ProfileStore:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "connections.json"

    def load(self) -> list[ConnectionProfile]:
        if not self.path.exists():
            return [ConnectionProfile()]
        data = json.loads(self.path.read_text())
        return [ConnectionProfile(**item) for item in data]

    def save(self, profiles: list[ConnectionProfile]) -> None:
        self.path.write_text(json.dumps([asdict(p) for p in profiles], indent=2))

@dataclass
class RemoteResult:
    ok: bool
    data: Any = None
    error: str = ""
    elapsed_ms: int = 0


def now_ms() -> int:
    return int(time.time() * 1000)

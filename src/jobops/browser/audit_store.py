import re
from pathlib import Path
from typing import Protocol

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class BrowserAuditArtifactStore(Protocol):
    def write_bytes(self, run_id: str, file_name: str, payload: bytes) -> str: ...


class LocalBrowserAuditArtifactStore:
    """Persist private browser audit artifacts under a configured local root."""

    def __init__(self, root: str | Path = "artifacts/browser-audit") -> None:
        self.root = Path(root)

    def write_bytes(self, run_id: str, file_name: str, payload: bytes) -> str:
        if _RUN_ID.fullmatch(run_id) is None:
            raise ValueError("audit run_id contains unsupported characters")
        if _FILE_NAME.fullmatch(file_name) is None:
            raise ValueError("audit file_name contains unsupported characters")

        run_directory = self.root / run_id
        run_directory.mkdir(parents=True, exist_ok=True)
        target = run_directory / file_name
        target.write_bytes(payload)
        return f"{run_id}/{file_name}"

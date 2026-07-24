import uuid
from pathlib import Path

from src.data.local_history import _local_appdata_dir


def client_id_path() -> Path:
    return _local_appdata_dir() / "client_id"


def get_or_create_client_id() -> str:
    """Return a stable anonymous ID for fair proxy rate limiting."""

    path = client_id_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
        return str(uuid.UUID(existing))
    except (FileNotFoundError, OSError, ValueError):
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    client_id = str(uuid.uuid4())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(client_id, encoding="utf-8")
    temporary.replace(path)
    return client_id

"""Local files use opaque keys. A request only removes files it created."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from bill_lens.db.repository import new_storage_key


def write_pdf(root: Path, data: bytes) -> tuple[str, Path]:
    key = new_storage_key()
    target = root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Same filesystem. UUID key is never derived from the client's filename.
        temporary.rename(target)
        return key, target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

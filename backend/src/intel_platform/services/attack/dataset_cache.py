"""On-disk cache for the downloaded MITRE datasets (ATT&CK, CWE, CAPEC).

Callers parse a download *before* handing it here, and it is written through a
temp file and an atomic rename. A truncated body or an HTML error page can
therefore never become the cached copy that every later ingest trusts, and a
reader never sees a half-written file.
"""
from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# The ATT&CK bundle is ~53 MB and the CWE zip and CAPEC XML are tens of MB,
# above ProxiedClient's default body cap (settings.max_fetch_bytes).
MAX_DATASET_BYTES = 200_000_000


def is_fresh(path: Path, max_age: timedelta | None) -> bool:
    """Whether ``path`` exists and (when ``max_age`` is set) is younger than it."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    return max_age is None or (time.time() - mtime) < max_age.total_seconds()


def write_atomically(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` via a same-directory temp file + rename.

    A failure to cache is logged, not raised: the parsed dataset is still good
    and the caller goes on to use it.
    """
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        tmp = None
    except OSError:
        logger.warning("Could not cache %s", path, exc_info=True)
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)

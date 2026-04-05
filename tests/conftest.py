from __future__ import annotations

import os
import tempfile
from pathlib import Path


# Force a hermetic test environment before test modules import app.py. This
# avoids accidental dependence on a developer's local MongoDB/Auth setup.
os.environ["ANON_STORE_BACKEND"] = "memory"
os.environ["MONGODB_URI"] = ""

# tldextract writes a lock file during email-domain validation. In sandboxed
# test runs, ~/.cache may be unwritable, so redirect it to a temp directory.
_TLDEXTRACT_CACHE = Path(tempfile.gettempdir()) / "anon_studio_tldextract_cache"
_TLDEXTRACT_CACHE.mkdir(parents=True, exist_ok=True)
os.environ["TLDEXTRACT_CACHE"] = str(_TLDEXTRACT_CACHE)

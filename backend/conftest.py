import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "SCENEFORGE_DATA_DIR", tempfile.mkdtemp(prefix="sceneforge-test-")
)

from app.config import get_settings  # noqa: E402
from app.database.db import Base, engine  # noqa: E402

get_settings().ensure_data_dirs()
from app import models  # noqa: E402,F401

Base.metadata.create_all(engine)

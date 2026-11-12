"""AppSail entry point: puts the bundled libraries on the path and starts the API."""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)

# The knowledge base ships with the app. Copy it somewhere writable in case the
# app folder is read-only.
src = os.path.join(HERE, "knowledge.db")
if os.path.exists(src) and not os.getenv("CARECHAT_KNOWLEDGE_PATH"):
    dst = "/tmp/carechat-knowledge.db"
    if not os.path.exists(dst):
        shutil.copy(src, dst)
    os.environ["CARECHAT_KNOWLEDGE_PATH"] = dst
os.environ.setdefault("CARECHAT_STORE", "catalyst")
# Catalyst's own cron calls /api/internal/hourly; this in-server timer is a backup.
os.environ.setdefault("CARECHAT_INPROCESS_JOBS", "true")

from carechat.main import run  # noqa: E402

run()

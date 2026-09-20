"""Runtime settings, read from environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("ARGUS_DB", str(ROOT / "data" / "argus.db"))
SECRET = os.environ.get("ARGUS_SECRET", "dev-secret-change-me")
# Pause between agent steps so the interface can show the investigation as it happens.
STEP_DELAY = float(os.environ.get("ARGUS_STEP_DELAY", "0.8"))
# Evidence sufficiency threshold (percent). Below this the agent asks for more evidence.
THRESHOLD = int(os.environ.get("ARGUS_THRESHOLD", "85"))
TOKEN_HOURS = int(os.environ.get("ARGUS_TOKEN_HOURS", "8"))
FRONTEND_DIR = ROOT / "frontend"

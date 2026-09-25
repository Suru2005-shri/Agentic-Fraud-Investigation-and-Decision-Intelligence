"""Runtime settings."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
DB_PATH=os.environ.get("ARGUS_DB",str(ROOT/"data"/"argus.db"))
DATA_DIR=Path(os.environ.get("ARGUS_DATA_DIR",str(ROOT/"data"/"fraud_dataset")))
DATA_ZIP=Path(os.environ.get("ARGUS_DATA_ZIP",str(ROOT/"data"/"fraud.zip")))
SECRET=os.environ.get("ARGUS_SECRET","dev-secret-change-me")
STEP_DELAY=float(os.environ.get("ARGUS_STEP_DELAY","0.35"))
THRESHOLD=int(os.environ.get("ARGUS_THRESHOLD","85"))
TOKEN_HOURS=int(os.environ.get("ARGUS_TOKEN_HOURS","8"))
FRONTEND_DIR=ROOT/"frontend"

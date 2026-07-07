from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TRIAS_API_KEY = (PROJECT_ROOT / "triasApi.key").open().read()


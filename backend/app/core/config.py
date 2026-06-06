import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EXPORTS_DIR = DATA_DIR / "exports"
STORE_FILE = DATA_DIR / "store.json"

APP_TITLE = "AI Adaptation Studio API"
APP_VERSION = "0.1.0"
API_PREFIX = "/api/v1"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "rule")

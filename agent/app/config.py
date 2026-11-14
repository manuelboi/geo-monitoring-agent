import os
from pathlib import Path

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("POSTGRES_DB", "geo")
DB_OWNER_USER = os.environ.get("POSTGRES_USER", "geo_owner")
DB_OWNER_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
DB_READONLY_USER = os.environ.get("DB_READONLY_USER", "geo_reader")
DB_READONLY_PASSWORD = os.environ.get("DB_READONLY_PASSWORD", "")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

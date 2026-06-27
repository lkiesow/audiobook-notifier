import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "data.db")
SCRAPE_INTERVAL_HOURS: int = int(os.environ.get("SCRAPE_INTERVAL_HOURS", "24"))
SCRAPE_DELAY_SECONDS: int = int(os.environ.get("SCRAPE_DELAY_SECONDS", "60"))
HOST: str = os.environ.get("HOST", "127.0.0.1")
PORT: int = int(os.environ.get("PORT", "5000"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

MATRIX_HOMESERVER: str = os.environ.get("MATRIX_HOMESERVER", "")
MATRIX_ACCESS_TOKEN: str = os.environ.get("MATRIX_ACCESS_TOKEN", "")
MATRIX_ROOM_ID: str = os.environ.get("MATRIX_ROOM_ID", "")

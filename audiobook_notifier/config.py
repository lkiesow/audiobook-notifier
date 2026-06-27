import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "./audiobook_notifier.db")
SCRAPE_INTERVAL_HOURS: int = int(os.environ.get("SCRAPE_INTERVAL_HOURS", "24"))
SCRAPE_DELAY_SECONDS: int = int(os.environ.get("SCRAPE_DELAY_SECONDS", "60"))
HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = int(os.environ.get("PORT", "5000"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

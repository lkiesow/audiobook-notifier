import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "data.db")
SCRAPE_INTERVAL_HOURS: int = int(os.environ.get("SCRAPE_INTERVAL_HOURS", "24"))
SCRAPE_DELAY_SECONDS: int = int(os.environ.get("SCRAPE_DELAY_SECONDS", "5"))
SCRAPE_TIMEOUT_SECONDS: int = int(os.environ.get("SCRAPE_TIMEOUT_SECONDS", "30"))
SCRAPE_RETRY_ATTEMPTS: int = int(os.environ.get("SCRAPE_RETRY_ATTEMPTS", "6"))
SCRAPE_RETRY_BACKOFF_SECONDS: float = float(os.environ.get("SCRAPE_RETRY_BACKOFF_SECONDS", "5"))
SCRAPE_RETRY_MAX_BACKOFF_SECONDS: float = float(os.environ.get("SCRAPE_RETRY_MAX_BACKOFF_SECONDS", "30"))
RELEASE_CHECK_HOUR: int = int(os.environ.get("RELEASE_CHECK_HOUR", "9"))
RELEASE_CHECK_MINUTE: int = int(os.environ.get("RELEASE_CHECK_MINUTE", "0"))
HOST: str = os.environ.get("HOST", "127.0.0.1")
PORT: int = int(os.environ.get("PORT", "5000"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

MATRIX_HOMESERVER: str = os.environ.get("MATRIX_HOMESERVER", "")
MATRIX_ACCESS_TOKEN: str = os.environ.get("MATRIX_ACCESS_TOKEN", "")
MATRIX_ROOM_ID: str = os.environ.get("MATRIX_ROOM_ID", "")
NOTIFY_SCRAPE_ERRORS: bool = os.environ.get("NOTIFY_SCRAPE_ERRORS", "").lower() == "true"

MATRIX_MSGTYPE_NEW_BOOK: str = os.environ.get("MATRIX_MSGTYPE_NEW_BOOK", "m.notice")
MATRIX_MSGTYPE_RELEASING_TODAY: str = os.environ.get("MATRIX_MSGTYPE_RELEASING_TODAY", "m.notice")
MATRIX_MSGTYPE_SCRAPE_ERROR: str = os.environ.get("MATRIX_MSGTYPE_SCRAPE_ERROR", "m.notice")
MATRIX_MSGTYPE_POSTPONED: str = os.environ.get("MATRIX_MSGTYPE_POSTPONED", "m.notice")

MATRIX_TIMEOUT_SECONDS: int = int(os.environ.get("MATRIX_TIMEOUT_SECONDS", "10"))
MATRIX_RETRY_ATTEMPTS: int = int(os.environ.get("MATRIX_RETRY_ATTEMPTS", "3"))
MATRIX_RETRY_BACKOFF_SECONDS: float = float(os.environ.get("MATRIX_RETRY_BACKOFF_SECONDS", "2"))
MATRIX_RETRY_MAX_BACKOFF_SECONDS: float = float(os.environ.get("MATRIX_RETRY_MAX_BACKOFF_SECONDS", "60"))

AUTH_USERNAME: str = os.environ.get("AUTH_USERNAME", "")
AUTH_PASSWORD: str = os.environ.get("AUTH_PASSWORD", "")
SECRET_KEY: str = os.environ.get("SECRET_KEY", "")

OIDC_CLIENT_ID: str = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET: str = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_ISSUER_URL: str = os.environ.get("OIDC_ISSUER_URL", "")
OIDC_REDIRECT_URI: str = os.environ.get("OIDC_REDIRECT_URI", "")

METRICS_BASIC_AUTH_USER: str = os.environ.get("METRICS_BASIC_AUTH_USER", "")
METRICS_BASIC_AUTH_PASS: str = os.environ.get("METRICS_BASIC_AUTH_PASS", "")

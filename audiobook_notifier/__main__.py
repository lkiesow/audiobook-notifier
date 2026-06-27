import atexit
import logging

from audiobook_notifier import config  # load_dotenv() fires on import

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from audiobook_notifier import database, scheduler
from audiobook_notifier.app import app

database.init_db()
scheduler.start_scheduler()
atexit.register(scheduler.shutdown_scheduler)

app.run(host=config.HOST, port=config.PORT, use_reloader=False)

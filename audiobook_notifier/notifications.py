import logging

logger = logging.getLogger(__name__)


def notify_new_book(book_title: str, series_title: str) -> None:
    logger.info("New book: %s in %s", book_title, series_title)


def notify_releasing_today(book_title: str, series_title: str) -> None:
    logger.info("Releasing today: %s in %s", book_title, series_title)

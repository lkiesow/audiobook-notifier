from prometheus_client import Counter, Gauge, REGISTRY
from prometheus_client.core import GaugeMetricFamily

scrapes_total = Counter(
    "audiobook_notifier_scrapes_total",
    "Total scrape attempts by outcome",
    ["result"],
)

new_books_discovered_total = Counter(
    "audiobook_notifier_new_books_discovered_total",
    "Total new books discovered across all scrapes",
)

notifications_sent_total = Counter(
    "audiobook_notifier_notifications_sent_total",
    "Total Matrix notifications sent by type",
    ["type"],
)

last_scrape_timestamp_seconds = Gauge(
    "audiobook_notifier_last_scrape_timestamp_seconds",
    "Unix timestamp of the most recent completed scheduled scrape run",
)


class _DatabaseStatsCollector:
    def collect(self):
        from audiobook_notifier import database  # deferred to avoid circular import

        series = database.get_all_series()
        s = GaugeMetricFamily(
            "audiobook_notifier_tracked_series",
            "Number of series currently tracked",
        )
        s.add_metric([], len(series))
        yield s

        b = GaugeMetricFamily(
            "audiobook_notifier_tracked_books",
            "Total books in the database",
        )
        b.add_metric([], sum(row.get("book_count", 0) for row in series))
        yield b

        upcoming = database.get_upcoming_books(limit=9999)
        u = GaugeMetricFamily(
            "audiobook_notifier_upcoming_books",
            "Books with a future release date",
        )
        u.add_metric([], len(upcoming))
        yield u


REGISTRY.register(_DatabaseStatsCollector())

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

notifications_failed_total = Counter(
    "audiobook_notifier_notifications_failed_total",
    "Total Matrix notifications that could not be delivered, by type",
    ["type"],
)

last_scrape_timestamp_seconds = Gauge(
    "audiobook_notifier_last_scrape_timestamp_seconds",
    "Unix timestamp of the most recent completed scheduled scrape run",
)


class _DatabaseStatsCollector:
    def describe(self):
        yield GaugeMetricFamily(
            "audiobook_notifier_tracked_series",
            "Number of series currently tracked",
        )
        yield GaugeMetricFamily(
            "audiobook_notifier_tracked_books",
            "Total books in the database",
        )
        yield GaugeMetricFamily(
            "audiobook_notifier_upcoming_books",
            "Books with a future release date",
        )

    def collect(self):
        from audiobook_notifier import database  # deferred to avoid circular import

        counts = database.get_counts()
        s = GaugeMetricFamily(
            "audiobook_notifier_tracked_series",
            "Number of series currently tracked",
        )
        s.add_metric([], counts["series"])
        yield s

        b = GaugeMetricFamily(
            "audiobook_notifier_tracked_books",
            "Total books in the database",
        )
        b.add_metric([], counts["books"])
        yield b

        u = GaugeMetricFamily(
            "audiobook_notifier_upcoming_books",
            "Books with a future release date",
        )
        u.add_metric([], counts["upcoming"])
        yield u


REGISTRY.register(_DatabaseStatsCollector())

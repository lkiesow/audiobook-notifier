FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY audiobook_notifier ./audiobook_notifier
RUN pip install --no-cache-dir '.[server]'

EXPOSE 5000

# Single worker to avoid running the APScheduler background jobs more than once.
# Four threads handle concurrent requests within that worker.
#
# --timeout 0 disables the arbiter's worker timeout. It is meant to catch a
# wedged request handler, but the scrape run lives in a background thread in
# this same worker and takes far longer than the 30s default, so the arbiter
# was SIGKILLing healthy workers mid-scrape. With -w 1 there is no fleet to
# protect, and a killed worker loses the whole run.
CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "0", "-b", "0.0.0.0:5000", "audiobook_notifier.__main__:app"]

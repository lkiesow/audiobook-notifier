FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY audiobook_notifier ./audiobook_notifier
RUN pip install --no-cache-dir '.[server]'

EXPOSE 5000

# waitress is a single-process, threaded server, so the scheduler started on
# import runs exactly once. Four threads handle concurrent requests, and there
# is no request timeout that could kill the scrape thread. Crash recovery is up
# to the container restart policy.
CMD ["waitress-serve", "--threads", "4", "--listen", "0.0.0.0:5000", "audiobook_notifier.__main__:app"]

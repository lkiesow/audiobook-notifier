FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

# Single worker to avoid running the APScheduler background jobs more than once.
# Four threads handle concurrent requests within that worker.
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:5000", "audiobook_notifier.__main__:app"]

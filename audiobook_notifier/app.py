import os
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory

from audiobook_notifier import database, scheduler

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="",
)


def _normalize_url(url: str) -> str:
    """Strip query string and fragment from a URL."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/series")
def list_series():
    return jsonify(database.get_all_series())


@app.post("/api/series")
def add_series():
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    url = _normalize_url(url)
    parsed = urlparse(url)
    if "audible." not in parsed.netloc or "/series/" not in parsed.path:
        return jsonify({"error": "URL must be an Audible series page"}), 400

    if database.get_series_by_url(url):
        return jsonify({"error": "Series already tracked"}), 409

    series_id = database.add_series(url)
    scheduler.scrape_series_now(series_id)
    return jsonify(database.get_series(series_id)), 201


@app.delete("/api/series/<int:series_id>")
def delete_series(series_id):
    if not database.get_series(series_id):
        return jsonify({"error": "Not found"}), 404
    database.delete_series(series_id)
    return "", 204


@app.get("/api/upcoming")
def upcoming_books():
    return jsonify(database.get_upcoming_books())


@app.get("/api/series/<int:series_id>/books")
def get_books(series_id):
    if not database.get_series(series_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(database.get_books(series_id))


@app.post("/api/series/<int:series_id>/refresh")
def refresh_series(series_id):
    if not database.get_series(series_id):
        return jsonify({"error": "Not found"}), 404
    scheduler.scrape_series_now(series_id)
    return jsonify({"status": "refresh started"}), 202

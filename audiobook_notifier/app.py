import hmac
import logging
import os
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session

from audiobook_notifier import config, database, scheduler

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="",
)

_auth_enabled = bool(config.AUTH_USERNAME and config.AUTH_PASSWORD)

if config.SECRET_KEY:
    app.secret_key = config.SECRET_KEY
elif _auth_enabled:
    app.secret_key = secrets.token_hex(32)
    logging.getLogger(__name__).warning(
        "SECRET_KEY not set — using ephemeral key, sessions reset on restart."
    )
else:
    app.secret_key = secrets.token_hex(32)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _auth_enabled:
            return f(*args, **kwargs)
        if not session.get("authenticated"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def _normalize_url(url: str) -> str:
    """Strip query string and fragment from a URL."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


@app.get("/")
def index():
    if _auth_enabled and not session.get("authenticated"):
        return redirect("/login")
    return render_template("index.html", auth_enabled=_auth_enabled)


@app.get("/login")
def login_page():
    if not _auth_enabled or session.get("authenticated"):
        return redirect("/")
    return render_template("login.html")


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").encode()
    password = (body.get("password") or "").encode()
    ok = (
        hmac.compare_digest(username, config.AUTH_USERNAME.encode())
        and hmac.compare_digest(password, config.AUTH_PASSWORD.encode())
    )
    if not ok:
        return jsonify({"error": "Invalid credentials"}), 401
    session["authenticated"] = True
    return jsonify({"authenticated": True})


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login" if _auth_enabled else "/")


@app.get("/api/series")
@login_required
def list_series():
    return jsonify(database.get_all_series())


@app.post("/api/series")
@login_required
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
@login_required
def delete_series(series_id):
    if not database.get_series(series_id):
        return jsonify({"error": "Not found"}), 404
    database.delete_series(series_id)
    return "", 204


@app.get("/api/upcoming")
@login_required
def upcoming_books():
    return jsonify(database.get_upcoming_books())


@app.get("/api/series/<int:series_id>/books")
@login_required
def get_books(series_id):
    if not database.get_series(series_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(database.get_books(series_id))


@app.post("/api/series/<int:series_id>/refresh")
@login_required
def refresh_series(series_id):
    if not database.get_series(series_id):
        return jsonify({"error": "Not found"}), 404
    scheduler.scrape_series_now(series_id)
    return jsonify({"status": "refresh started"}), 202

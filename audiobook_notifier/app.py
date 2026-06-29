import hmac
import logging
import os
import secrets
from functools import wraps
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from prometheus_client import REGISTRY
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST, generate_latest

from audiobook_notifier import config, database, metrics, scheduler

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="",
)

_local_auth_enabled = bool(config.AUTH_USERNAME and config.AUTH_PASSWORD)
_oidc_enabled = bool(
    not _local_auth_enabled
    and config.OIDC_CLIENT_ID
    and config.OIDC_CLIENT_SECRET
    and config.OIDC_ISSUER_URL
)
_auth_enabled = _local_auth_enabled or _oidc_enabled

if config.SECRET_KEY:
    app.secret_key = config.SECRET_KEY
elif _auth_enabled:
    app.secret_key = secrets.token_hex(32)
    logging.getLogger(__name__).warning(
        "SECRET_KEY not set — using ephemeral key, sessions reset on restart."
    )
else:
    app.secret_key = secrets.token_hex(32)

oauth = OAuth(app)
if _oidc_enabled:
    oauth.register(
        name="oidc",
        client_id=config.OIDC_CLIENT_ID,
        client_secret=config.OIDC_CLIENT_SECRET,
        server_metadata_url=config.OIDC_ISSUER_URL.rstrip("/") + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


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
    error = request.args.get("error")
    if _oidc_enabled and not error:
        return redirect(url_for("oidc_login"))
    return render_template(
        "login.html",
        local_auth_enabled=_local_auth_enabled,
        oidc_enabled=_oidc_enabled,
        error=error,
    )


@app.get("/auth/oidc/login")
def oidc_login():
    if not _oidc_enabled:
        return redirect("/login")
    try:
        redirect_uri = url_for("oidc_callback", _external=True)
        return oauth.oidc.authorize_redirect(redirect_uri)
    except Exception:
        logging.getLogger(__name__).warning("OIDC provider unavailable", exc_info=True)
        return redirect("/login?error=provider_unavailable")


@app.get("/auth/oidc/callback")
def oidc_callback():
    if not _oidc_enabled:
        return redirect("/")
    try:
        oauth.oidc.authorize_access_token()
    except Exception:
        logging.getLogger(__name__).warning("OIDC callback failed", exc_info=True)
        return redirect("/login?error=oidc_failed")
    session["authenticated"] = True
    return redirect("/")


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


@app.get("/metrics")
def metrics_endpoint():
    if config.METRICS_BASIC_AUTH_USER and config.METRICS_BASIC_AUTH_PASS:
        auth = request.authorization
        if (
            not auth
            or not hmac.compare_digest(auth.username, config.METRICS_BASIC_AUTH_USER)
            or not hmac.compare_digest(auth.password, config.METRICS_BASIC_AUTH_PASS)
        ):
            return "Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="metrics"'}
    return generate_latest(REGISTRY), 200, {"Content-Type": CONTENT_TYPE_LATEST}

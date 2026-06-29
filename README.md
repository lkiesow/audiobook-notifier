# Audiobook Notifier

A self-hosted web app that tracks Audible audiobook series and notifies you when new books are added or released. Paste an Audible series URL, and the app scrapes it periodically, stores the books in a local SQLite database, and sends [Matrix](https://matrix.org/) notifications on new discoveries and release days.

![](.github/screenshot.png)

## Features

- Track any number of Audible series (audible.com and audible.de supported)
- Background scraping on a configurable interval (default: every 24 hours)
- Daily release-day notifications at 09:00
- Upcoming releases panel in the web UI
- Matrix notifications (optional) — with a setup wizard to create a bot room
- Light/dark mode web UI
- No external runtime dependencies beyond Python

## Installation

```bash
git clone <repo-url>
cd audiobook-notifier
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to adjust settings (see [Configuration](#configuration) below), then start the server:

```bash
python -m audiobook_notifier
```

The web UI is available at `http://localhost:5000` by default.

## Configuration

All configuration is done via environment variables or a `.env` file in the project root.

| Variable                   | Default     | Description
|----------------------------|-------------|------------------
| `DATABASE_PATH`            | `data.db`   | Path to the SQLite database file
| `SCRAPE_INTERVAL_HOURS`    | `24`        | How often (in hours) to re-scrape all tracked series
| `SCRAPE_DELAY_SECONDS`     | `60`        | Delay between scraping consecutive series (rate limiting)
| `HOST`                     | `127.0.0.1` | Host for the Flask web server
| `PORT`                     | `5000`      | Port for the Flask web server
| `LOG_LEVEL`                | `INFO`      | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
| `MATRIX_HOMESERVER`        |             | Matrix homeserver URL — leave blank to disable notifications
| `MATRIX_ACCESS_TOKEN`      |             | Matrix bot access token
| `MATRIX_ROOM_ID`           |             | Room ID (`!abc:example.org`) or alias (`#name:example.org`)
| `SECRET_KEY`               |             | Secret key for signing session cookies — required when using any form of authentication; an ephemeral key is used if not set (sessions reset on restart)
| `AUTH_USERNAME`            |             | Username for local authentication — leave blank to disable
| `AUTH_PASSWORD`            |             | Password for local authentication
| `OIDC_CLIENT_ID`           |             | OIDC client ID — leave blank to disable OIDC login
| `OIDC_CLIENT_SECRET`       |             | OIDC client secret
| `OIDC_ISSUER_URL`          |             | OIDC provider base URL
| `OIDC_REDIRECT_URI`        |             | Override the OIDC callback URL
| `METRICS_BASIC_AUTH_USER`  |             | Username for Basic Auth on `/metrics` — leave blank to keep endpoint open
| `METRICS_BASIC_AUTH_PASS`  |             | Password for Basic Auth on `/metrics`

## Authentication

The app supports two optional authentication methods. If neither is configured, the UI is accessible without login.

### Local authentication

Set `AUTH_USERNAME` and `AUTH_PASSWORD` to enable a username/password login screen. If both are set, OIDC is ignored.

### OpenID Connect (OIDC)

Set `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URL` to enable OIDC login. The provider's discovery document is fetched automatically from `{OIDC_ISSUER_URL}/.well-known/openid-configuration`. Examples:

```env
# Authentik
OIDC_ISSUER_URL=https://auth.example.com/application/o/myapp

# Keycloak
OIDC_ISSUER_URL=https://auth.example.com/realms/myrealm

# Google
OIDC_ISSUER_URL=https://accounts.google.com
```

Register `http(s)://your-host/auth/oidc/callback` as the redirect URI with your provider. If the app runs behind a reverse proxy, set `OIDC_REDIRECT_URI` to the public-facing callback URL explicitly.

### SECRET_KEY

Both authentication methods use Flask session cookies. Set `SECRET_KEY` to a stable random value so sessions survive restarts:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Matrix Notifications

Matrix notifications are optional. All three `MATRIX_*` variables must be set to enable them.

The easiest way to set up a bot account and notification room is the built-in wizard:

```bash
python -m audiobook_notifier setup-matrix
```

The wizard logs in with a bot account, creates a private room, invites you, promotes your account to admin, and prints the three environment variables to add to your `.env` file.

For an existing bot account, set the variables manually:

```env
MATRIX_HOMESERVER=https://matrix.example.org
MATRIX_ACCESS_TOKEN=your_access_token_here
MATRIX_ROOM_ID=!yourRoomId:example.org
```

Two types of notifications are sent:
- **New book discovered** — when a scrape finds a book that wasn't in the database before
- **Releasing today** — sent at 09:00 on the day a tracked book is released

## Production

Instead of using the internal web server, which is meant for debugging only, in production, you can run the app using a WSGI server like gunicorn:

```bash
gunicorn -w 1 --threads 4 -b 127.0.0.1:5000 audiobook_notifier.__main__:app
```

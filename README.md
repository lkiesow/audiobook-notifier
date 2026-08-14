# Audiobook Notifier

A self-hosted web app that tracks Audible audiobook series and notifies you when new books are added or released. Paste an Audible series URL, and the app scrapes it periodically, stores the books in a local SQLite database, and sends [Matrix](https://matrix.org/) notifications on new discoveries and release days.

![](.github/screenshot.png)

## Features

- Track any number of Audible series (audible.com and audible.de supported)
- Background scraping on a configurable interval (default: every 24 hours)
- Daily release-day notifications (09:00 local time by default, configurable)
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

`RELEASE_CHECK_HOUR`/`RELEASE_CHECK_MINUTE` are interpreted in the container's local timezone. Set the standard `TZ` environment variable (e.g. `TZ=Europe/Berlin`) to control what "local time" means; without it, the check runs in the container's default timezone (UTC).

| Variable                   | Default     | Description
|----------------------------|-------------|------------------
| `DATABASE_PATH`            | `data.db`   | Path to the SQLite database file
| `SCRAPE_INTERVAL_HOURS`    | `24`        | How often (in hours) to re-scrape all tracked series
| `SCRAPE_DELAY_SECONDS`     | `60`        | Delay between scraping consecutive series (rate limiting)
| `SCRAPE_TIMEOUT_SECONDS`   | `30`        | HTTP timeout for a single page request
| `SCRAPE_RETRY_ATTEMPTS`    | `6`         | How often to re-fetch a series page before giving up — see [Scrape retries](#scrape-retries)
| `SCRAPE_RETRY_BACKOFF_SECONDS`     | `5`  | Initial delay between scrape attempts, doubling each time
| `SCRAPE_RETRY_MAX_BACKOFF_SECONDS` | `30` | Upper bound on that delay
| `RELEASE_CHECK_HOUR`       | `9`         | Hour (0-23, in the container's local time) to run the daily release check
| `RELEASE_CHECK_MINUTE`     | `0`         | Minute (0-59) to run the daily release check
| `HOST`                     | `127.0.0.1` | Host for the Flask web server
| `PORT`                     | `5000`      | Port for the Flask web server
| `LOG_LEVEL`                | `INFO`      | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
| `MATRIX_HOMESERVER`        |             | Matrix homeserver URL — leave blank to disable notifications
| `MATRIX_ACCESS_TOKEN`      |             | Matrix bot access token
| `MATRIX_ROOM_ID`           |             | Room ID (`!abc:example.org`) or alias (`#name:example.org`)
| `MATRIX_TIMEOUT_SECONDS`   | `10`        | HTTP timeout for a single Matrix request
| `MATRIX_RETRY_ATTEMPTS`    | `3`         | How often to retry a send that failed on a connection error, 5xx or 429
| `MATRIX_RETRY_BACKOFF_SECONDS`     | `2`  | Initial delay between send attempts, doubling each time
| `MATRIX_RETRY_MAX_BACKOFF_SECONDS` | `60` | Upper bound on that delay
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

The notifications sent are:

- **New book discovered** — when a scrape finds a book that wasn't in the database before
- **Releasing today** — sent at `RELEASE_CHECK_HOUR` on the day a tracked book is released
- **Postponed** — when Audible moves a release we already announced to a later date. The book is then announced again on its real release date
- **Scrape failed** — only when `NOTIFY_SCRAPE_ERRORS=true`

## Scrape retries

Audible serves two different series pages for the same URL, and which one you
get varies per request. The classic page lists titles as
`<li class="productListItem">` and is the one this scraper understands. The
other is built from `<adbl-product-row>` web components; it lists the same
titles but carries no release dates at all, so there is nothing to parse.

Both come back as a healthy HTTP 200, which is why a scrape retries the whole
fetch and parse rather than just the HTTP request. Attempts are independent —
each one takes a fresh `User-Agent` and no shared cookie jar. The backoff is
capped because this is a coin flip over which page you get, not a rate limit,
so waiting longer buys nothing.

A series that exhausts its attempts is skipped entirely for that run rather
than written to the database, so a page we cannot read can never overwrite
good data. `Got Audible's unsupported new layout` in the logs tells the two
failure modes apart.

Note this only works while the classic page is still being served. If Audible
completes the rollout, the scraper will need a different source for release
dates.

## Production

Instead of using the internal web server, which is meant for debugging only, in production, you can run the app using a WSGI server like gunicorn:

```bash
gunicorn -w 1 --threads 4 --timeout 0 -b 127.0.0.1:5000 audiobook_notifier.__main__:app
```

`-w 1` is required: the scheduler starts on import, so every additional worker
would scrape and notify a second time.

`--timeout 0` matters just as much. Gunicorn's 30-second default is there to
kill a wedged request handler, but the scrape run lives in a background thread
inside that same worker and takes far longer, so the arbiter ends up SIGKILLing
a perfectly healthy worker in the middle of a run — losing it entirely and
resetting the interval timer.

A full run takes roughly `series × SCRAPE_DELAY_SECONDS`, plus up to ~95s for
each series that has to exhaust its retries. For 25 series that is around 25
minutes normally and just over an hour if every single series fails.

# TradeEye

TradeEye is a market trend detection platform built around an agentic OHLCV scanner. It identifies sustained **up** and **down** trends using five statistical signals plus optional veto gates, then delivers alerts via Discord, Telegram, or a multi-user SaaS API.

The repo has two main parts:


| Component         | Path             | Purpose                                                                              |
| ----------------- | ---------------- | ------------------------------------------------------------------------------------ |
| **Trend Scanner** | `trend_scanner/` | CLI engine — fetch data, analyse trends, generate charts, send alerts                |
| **SaaS Backend**  | `backend/`       | FastAPI API — auth, subscriptions, scheduled scans, per-user notifications, admin UI |


---

## Prerequisites

- **Python 3.12+**
- **MySQL 8** (local install or Docker)
- **Git**

Optional:

- Docker & Docker Compose (for containerised DB + API)
- SMTP credentials (for email verification / password reset)
- Telegram bot token, Discord webhooks (for alerts)
- Gemini API key (for optional VLM chart verification in the CLI scanner)

---

## Project structure

```
TradeEye/
├── trend_scanner/          # Core trend detection engine (CLI)
│   ├── main.py             # CLI entry point
│   ├── config/             # Tickers, signals, vetoes, notifications
│   ├── engine/             # TrendEngine, signals, pivots
│   ├── data/               # yfinance / CCXT fetcher
│   ├── charts/             # Matplotlib chart generator
│   └── alerts/             # Discord / Telegram dispatcher
├── backend/                # FastAPI SaaS backend
│   ├── app/
│   │   ├── api/v1/         # REST endpoints
│   │   ├── admin/          # Jinja2 + HTMX admin UI
│   │   ├── services/       # Scan scheduler, coordinator, notifications
│   │   └── indicators/     # Pluggable indicator registry
│   ├── alembic/            # Database migrations
│   └── scripts/seed.py     # Seed tickers, timeframes, plans
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Quick start (local development)

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/Abdulwadood39/TradeEye
git checkout saas
cd TradeEye

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

> The backend requirements file also installs all `trend_scanner` dependencies. The first install can take several minutes (scipy, matplotlib, ccxt, etc.).

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:


| Variable              | Description                                          |
| --------------------- | ---------------------------------------------------- |
| `JWT_SECRET_KEY`      | Long random string for API tokens                    |
| `SESSION_SECRET_KEY`  | Random string for admin session cookies              |
| `ENCRYPTION_KEY`      | Fernet key for encrypting user webhook/token secrets |
| `ADMIN_PASSWORD_HASH` | bcrypt hash of your admin password (see below)       |


Generate secrets:

```bash
# JWT / session secrets
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Fernet encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Admin password hash (example password: admin123)
python3 -c "import bcrypt; print(bcrypt.hashpw(b'admin123', bcrypt.gensalt(12)).decode())"
```

**Docker Compose note:** bcrypt hashes contain `$` characters. In `.env`, escape each `$` as `$$` so Compose does not treat them as variables:

```env
ADMIN_PASSWORD_HASH=$$2b$$12$$...your-hash-here...
```

The backend automatically unescapes `$$` → `$` at startup.

### 3. Start MySQL

**Option A — Docker (if port 3306 is free)**

```bash
docker compose up -d db
```

**Option B — Local MySQL**

```bash
mysql -u root -p <<'SQL'
CREATE DATABASE tradeeye CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tradeeye'@'localhost' IDENTIFIED BY 'tradeeye';
GRANT ALL PRIVILEGES ON tradeeye.* TO 'tradeeye'@'localhost';
FLUSH PRIVILEGES;
SQL
```

Set `DATABASE_URL` in `.env`:

```env
DATABASE_URL=mysql+aiomysql://tradeeye:tradeeye@localhost:3306/tradeeye?charset=utf8mb4
```

### 4. Run database migrations and seed

```bash
# Option A — helper script (from repo root)
./scripts/migrate.sh upgrade head
PYTHONPATH=. python backend/scripts/seed.py

# Option B — from backend/ (no PYTHONPATH needed after env.py fix)
cd backend
alembic upgrade head
PYTHONPATH=.. python scripts/seed.py
cd ..
```

The seed script loads:

- Tickers from `trend_scanner/config/tickers.py` (with display aliases, e.g. `GC=F` → Gold)
- Default timeframes (`1m`, `5m`, `15m`, `1h`, `1d`, `1w`, …)
- Scan schedules (e.g. `1m` every 180 min, `1h` every 1440 min)
- `continuous_trend` indicator type
- Free billing plan

### 5. Start the API server

```bash
PYTHONPATH=. uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```


| URL                                                                    | Description      |
| ---------------------------------------------------------------------- | ---------------- |
| [http://localhost:8000/docs](http://localhost:8000/docs)               | Swagger API docs |
| [http://localhost:8000/health](http://localhost:8000/health)           | Health check     |
| [http://localhost:8000/admin/login](http://localhost:8000/admin/login) | Admin panel      |


Default admin credentials (if you used the hash example above):

- **Username:** `admin`
- **Password:** `admin123`

Change these before any production deployment.

---

## Docker (full stack)

Run MySQL and the API together:

```bash
cp .env.example .env
# Edit .env — set secrets and ADMIN_PASSWORD_HASH (use $$ for $ in bcrypt hash)

docker compose up --build
```

The API container uses `DATABASE_URL=mysql+aiomysql://tradeeye:tradeeye@db:3306/tradeeye?charset=utf8mb4` (set in `docker-compose.yml`).

After the containers are up, run migrations and seed inside the API container:

```bash
docker compose exec api alembic -c backend/alembic.ini upgrade head
docker compose exec api python backend/scripts/seed.py
```

> If port `3306` is already in use on your machine, either stop the local MySQL service or change the host port mapping in `docker-compose.yml`.

---

## Trend Scanner CLI

The CLI runs independently of the SaaS backend. Configuration lives in Python files under `trend_scanner/config/` (not `.env`, except for alert tokens).

### Run a scan

From the project root:

```bash
source .venv/bin/activate
PYTHONPATH=.

# Scan default watchlist (~170 tickers) in continuous mode
python -m trend_scanner.main

# Scan specific tickers once
python -m trend_scanner.main --tickers AAPL MSFT GC=F EURUSD=X
```

### CLI configuration


| File                      | What it controls                                      |
| ------------------------- | ----------------------------------------------------- |
| `config/tickers.py`       | Watchlists (stocks, forex, crypto, commodities)       |
| `config/run.py`           | Mode (`continuous` / `once`), scan intervals, workers |
| `config/signals.py`       | Signal thresholds (slope, ADX, Mann-Kendall, etc.)    |
| `config/vetoes.py`        | Veto gate thresholds                                  |
| `config/notifications.py` | Enable/disable Discord and Telegram channels          |
| `config/misc.py`          | Charts, VLM (Gemini), logging                         |


### CLI alerts (optional)

Add to `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DISCORD_WEBHOOK_URL=...
GEMINI_API_KEY=...          # optional VLM chart verification
```

Enable channels in `trend_scanner/config/notifications.py`.

### CLI output

- Terminal summaries for trending tickers
- CSV log: `trend_scanner/output/logs/trend_log.csv`
- Charts: `trend_scanner/output/charts/{timeframe}/{UP|DOWN|NONE}/`

---

## SaaS API overview

### Authentication


| Method | Endpoint                              | Description                               |
| ------ | ------------------------------------- | ----------------------------------------- |
| POST   | `/api/v1/auth/signup`                 | Create account (sends verification email) |
| GET    | `/api/v1/auth/verify-email?token=...` | Verify email                              |
| POST   | `/api/v1/auth/resend-verification`    | Resend verification link                  |
| POST   | `/api/v1/auth/login`                  | Login (requires verified email)           |
| POST   | `/api/v1/auth/refresh`                | Refresh JWT tokens                        |
| POST   | `/api/v1/auth/forgot-password`        | Request password reset                    |
| POST   | `/api/v1/auth/reset-password`         | Reset password with token                 |
| GET    | `/api/v1/me`                          | Current user profile                      |


Without SMTP configured, verification/reset emails are logged to the console instead of sent.

### Catalog & subscriptions


| Method | Endpoint                   | Description                                           |
| ------ | -------------------------- | ----------------------------------------------------- |
| GET    | `/api/v1/tickers`          | Available tickers with display names                  |
| GET    | `/api/v1/timeframes`       | Supported timeframes                                  |
| GET    | `/api/v1/indicators`       | Indicator types                                       |
| CRUD   | `/api/v1/subscriptions`    | User ticker/timeframe/bars subscriptions              |
| PUT    | `/api/v1/me/notifications` | Discord webhook, Telegram creds, delete-previous flag |
| GET    | `/api/v1/trends`           | Historical trend events for subscribed tickers        |


### Example: sign up and subscribe

```bash
# Sign up
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpassword123"}'

# Verify email (use token from email or server logs)
curl "http://localhost:8000/api/v1/auth/verify-email?token=YOUR_TOKEN"

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpassword123"}'

# List tickers (use access_token from login response)
curl http://localhost:8000/api/v1/tickers \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## How scheduled scans work

The SaaS backend runs scans on a **fixed interval from scan start** (not from when the pipeline finishes):

1. Admin configures `interval_minutes` per timeframe in `/admin/schedules`
2. Scheduler fires at `T`, records `next_run_at = T + interval`
3. Coordinator groups active user subscriptions by ticker + timeframe
4. Fetches OHLCV once per group using **MAX(bars)** across subscribers
5. Analyses once per **unique bars** value (e.g. 1500 and 2500 separately)
6. Notifies only users whose `subscription.bars` exactly matches the result
7. Generates ephemeral chart PNGs, sends alerts, then deletes the temp files

---

## Admin panel

Password-protected UI at `/admin/`:


| Page       | Purpose                                        |
| ---------- | ---------------------------------------------- |
| Dashboard  | User counts, recent scan runs                  |
| Tickers    | CRUD ticker catalog and aliases                |
| Timeframes | View supported timeframes                      |
| Schedules  | Set rerun interval per timeframe               |
| Plans      | Billing plans (billing provider not wired yet) |
| Settings   | Default subscription bars                      |


---

## Running tests

```bash
source .venv/bin/activate
PYTHONPATH=. pytest backend/tests -q
```

Tests cover password hashing, coordinator bars-matching logic, scheduler job registration, and temp chart cleanup.

---

## Common issues


| Problem                                                   | Fix                                                                                    |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: backend`                            | Run `cd backend && alembic upgrade head`, or `./scripts/migrate.sh upgrade head` from repo root |
| `No 'script_location' key found`                          | No `alembic.ini` at repo root — run from `backend/` or use `./scripts/migrate.sh`              |
| Port 3306 already in use                                  | Stop local MySQL or change Docker port mapping                                         |
| Docker Compose warns about unset variables in bcrypt hash | Escape `$` as `$$` in `ADMIN_PASSWORD_HASH`                                            |
| `greenlet` required error                                 | `pip install greenlet`                                                                 |
| `python-multipart` required                               | `pip install python-multipart`                                                         |
| Email not received in dev                                 | Expected — check server logs; configure SMTP in `.env` for real delivery               |
| `docker-credential-desktop` not found                     | Run `echo '{}' > ~/.docker/config.json` or fix Docker Desktop credentials              |
| yfinance 1m data limited to ~7 days                       | Validate `bars` against timeframe limits when creating subscriptions                   |


---

## Production deployment (Ubuntu)

CI/CD and server configs live in [`deploy/`](deploy/README.md):

- **GitHub Actions** — `.github/workflows/ci-cd.yml` (test on PR, deploy on push to `main`/`saas`)
- **systemd** — `deploy/systemd/tradeeye-api.service`
- **nginx** — `deploy/nginx/tradeeye.conf`
- **Scripts** — `deploy/scripts/bootstrap-server.sh` (first-time setup), `deploy/scripts/deploy.sh` (pull + migrate + restart)

Quick start on a VPS:

```bash
git clone <repo> /opt/tradeeye && cd /opt/tradeeye
sudo bash deploy/scripts/bootstrap-server.sh
# edit /opt/tradeeye/.env, run migrations, start tradeeye-api
```

See [deploy/README.md](deploy/README.md) for GitHub secrets, TLS, and troubleshooting.

---

## License

Private / personal project — add your license here if open-sourcing.
# Module 4: Docker & Containerization

A complete Docker exercise using the Feedback Board web application: **Source Code → Dockerfile → Image → Container → Docker Compose → Running Application**.

Repository: https://github.com/Gauravwakle96/module-4-

The application uses Python/FastAPI and plain HTML/CSS/JavaScript. Docker Compose runs it alongside PostgreSQL with health checks, private database networking, and a persistent volume. The app runs as a non-root user with a read-only root filesystem.

## Run the Docker application

Install Docker Desktop with Linux containers (or Docker Engine and Compose) and Python 3.11 or newer.

```powershell
git clone https://github.com/Gauravwakle96/module-4-.git
cd module-4-
python scripts/setup_docker.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
```

Open **http://localhost:8014**. `setup_docker.py` creates an ignored `.env.docker` with a random local database password and preserves an existing file. No cloud credentials or paid services are needed.

```powershell
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 20 app
docker compose --env-file .env.docker down
```

`down` stops the containers while keeping the database volume. Restart with `up -d --wait`. Feedback survives container replacement. Avoid `down --volumes` when you need the saved feedback.

## Tests and submission

```powershell
docker build --target test -t module4-feedback-tests:1.0 .
docker run --rm module4-feedback-tests:1.0
```

**28 tests passed** on Windows and inside a Linux container. Actual Compose startup, save/reload, data persistence across replacing both containers, database outage recovery, image scanning, and browser checks are documented in [module-4-submission/README.md](module-4-submission/README.md).

- [Dockerfile](Dockerfile), [Compose configuration](compose.yaml), and [local database schema](docker/init.sql).
- [Module 4 guide and architecture diagram](MODULE_4.md).
- [One LinkedIn image](module-4-submission/02-module4-summary.png) and [caption](module-4-submission/post.txt).

The runtime image excludes local secret files, development tools, tests, and Git history. Version/digest-pinned base images receive available OS security updates during the build. The scan found zero fixable HIGH/CRITICAL vulnerabilities at the time of verification; the exact scope is recorded in the evidence.

The existing cloud version of this application is at https://module3-feedback-board.onrender.com. It is the Module 3 native Python deployment. This Module 4 repository demonstrates local containerization; CI/CD and cloud container deployment are later modules.

## Configuration

Local Docker configuration is in `.env.docker`; `.env.docker.example` documents the variables. `APP_PORT` defaults to 8014. Keep the generated hexadecimal `POSTGRES_PASSWORD` private. The database is not published to the host, and HTTP is bound to loopback.

The application settings are documented in `.env.example`. `DATABASE_SSLMODE=disable` is used only for the isolated local PostgreSQL network. The application's `cloud` environment still requires TLS and a PostgreSQL URL.

Code is MIT licensed; dependencies retain their own licenses. System fonts and no external image assets are used. `.python-version` pins the tested Python runtime.

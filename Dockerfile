# syntax=docker/dockerfile:1
FROM python:3.13.15-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26 AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN python -m venv /opt/venv
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Optional test image; the final application image contains no test dependencies.
FROM dependencies AS test
RUN pip install --no-cache-dir pytest==9.2.0 httpx==0.28.1
COPY feedback_board ./feedback_board
COPY tests ./tests
COPY pyproject.toml ./
CMD ["pytest", "-q", "--strict-markers"]

FROM python:3.13.15-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    LOCAL_DB_PATH="/data/feedback.sqlite3" \
    PORT=8000
WORKDIR /app
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 feedback \
    && useradd --uid 10001 --gid feedback --no-create-home --shell /usr/sbin/nologin feedback \
    && mkdir /data \
    && chown feedback:feedback /data
COPY --from=dependencies /opt/venv /opt/venv
RUN /usr/local/bin/python -m pip uninstall --yes pip setuptools \
    && /opt/venv/bin/python -m pip uninstall --yes pip setuptools
COPY --chown=feedback:feedback feedback_board ./feedback_board
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=8s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=6).read()" || exit 1
CMD ["sh", "-c", "exec uvicorn feedback_board.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --no-access-log"]

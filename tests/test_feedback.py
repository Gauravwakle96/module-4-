import logging
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from feedback_board.config import Settings
from feedback_board.database import Database, FeedbackQuotaReached
from feedback_board.main import WriteLimiter, create_app


def local_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        local_db_path=tmp_path / "feedback.sqlite3",
        allowed_hosts="testserver",
        **overrides,
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(local_settings(tmp_path))) as test_client:
        yield test_client


def test_empty_board_and_health(client: TestClient) -> None:
    assert client.get("/api/feedback").json() == {"total": 0, "items": []}
    assert client.get("/health").json() == {"status": "ok", "database": "sqlite-local"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Feedback Board" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/app.js").status_code == 200


def test_saves_trimmed_feedback_and_survives_restart(tmp_path: Path) -> None:
    settings = local_settings(tmp_path)
    with TestClient(create_app(settings)) as first:
        saved = first.post("/api/feedback", json={"name": " Gaurav ", "message": " Hello! "})
        assert saved.status_code == 201
        assert saved.json()["name"] == "Gaurav"
        assert saved.json()["message"] == "Hello!"
        assert saved.json()["created_at"].endswith("Z")
    with TestClient(create_app(settings)) as restarted:
        listing = restarted.get("/api/feedback").json()
        assert listing["total"] == 1
        assert listing["items"] == [saved.json()]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "  ", "message": "Hello"},
        {"name": "Gaurav", "message": "\n\t "},
        {"name": "a" * 61, "message": "Hello"},
        {"name": "Gaurav", "message": "a" * 501},
        {"name": 123, "message": "Hello"},
        {"name": "Gaurav"},
        {"name": "Gaurav", "message": "Hello", "admin": True},
    ],
)
def test_invalid_input_does_not_write(client: TestClient, payload: object) -> None:
    assert client.post("/api/feedback", json=payload).status_code == 422
    assert client.get("/api/feedback").json()["total"] == 0


def test_maximum_lengths_are_accepted(client: TestClient) -> None:
    response = client.post("/api/feedback", json={"name": "a" * 60, "message": "b" * 500})
    assert response.status_code == 201


def test_sql_and_html_are_stored_as_plain_text(client: TestClient) -> None:
    payload = {
        "name": "Robert'); DROP TABLE module3_feedback;--",
        "message": "<script>x()</script>",
    }
    assert client.post("/api/feedback", json=payload).status_code == 201
    stored = client.get("/api/feedback").json()["items"][0]
    assert stored["name"] == payload["name"]
    assert stored["message"] == payload["message"]
    assert client.get("/health").status_code == 200


def test_latest_ten_and_total_are_distinct(tmp_path: Path) -> None:
    with TestClient(create_app(local_settings(tmp_path, write_limit=30))) as client:
        for index in range(12):
            assert (
                client.post(
                    "/api/feedback", json={"name": "Visitor", "message": str(index)}
                ).status_code
                == 201
            )
        listing = client.get("/api/feedback").json()
        assert listing["total"] == 12
        assert [item["message"] for item in listing["items"]] == [
            str(index) for index in range(11, 1, -1)
        ]


def test_quota_returns_clear_error(tmp_path: Path) -> None:
    with TestClient(create_app(local_settings(tmp_path, feedback_limit=1))) as client:
        payload = {"name": "Visitor", "message": "Hello"}
        assert client.post("/api/feedback", json=payload).status_code == 201
        assert client.post("/api/feedback", json=payload).status_code == 409
        assert client.get("/api/feedback").json()["total"] == 1


def test_concurrent_writes_cannot_exceed_quota(tmp_path: Path) -> None:
    database = Database(local_settings(tmp_path, feedback_limit=2))
    database.initialize()

    def submit(index: int) -> bool:
        try:
            database.add("Visitor", str(index))
            return True
        except FeedbackQuotaReached:
            return False

    with ThreadPoolExecutor(max_workers=6) as executor:
        assert sum(executor.map(submit, range(6))) == 2
    assert database.recent()["total"] == 2


def test_rate_limit_and_retry_header(tmp_path: Path) -> None:
    with TestClient(create_app(local_settings(tmp_path, write_limit=1))) as client:
        payload = {"name": "Visitor", "message": "Hello"}
        assert client.post("/api/feedback", json=payload).status_code == 201
        blocked = client.post("/api/feedback", json=payload)
        assert blocked.status_code == 429
        assert 1 <= int(blocked.headers["retry-after"]) <= 60


def test_rate_limit_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr("feedback_board.main.time.monotonic", lambda: now[0])
    limiter = WriteLimiter(1)
    assert limiter.retry_after() == 0
    assert limiter.retry_after() == 60
    now[0] = 160.0
    assert limiter.retry_after() == 0


@pytest.mark.parametrize("endpoint", ["/health", "/api/feedback"])
def test_database_failure_is_retriable_and_redacted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("private database details")

    method = "check" if endpoint == "/health" else "recent"
    monkeypatch.setattr(client.app.state.database, method, fail)
    response = client.get(endpoint)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "10"
    assert "private" not in response.text


def test_save_failure_preserves_generic_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("private password")

    monkeypatch.setattr(client.app.state.database, "add", fail)
    response = client.post("/api/feedback", json={"name": "Visitor", "message": "Hello"})
    assert response.status_code == 503
    assert "password" not in response.text


def test_rejects_cross_site_non_json_and_oversized_bodies(client: TestClient) -> None:
    payload = {"name": "Visitor", "message": "Hello"}
    assert (
        client.post(
            "/api/feedback", json=payload, headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/feedback", data=payload).status_code == 415
    assert (
        client.post(
            "/api/feedback", content="x" * 8193, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/feedback", content="{invalid", headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )
    assert client.get("/api/feedback").json()["total"] == 0


def test_untrusted_host_is_rejected(client: TestClient) -> None:
    assert client.get("/", headers={"Host": "untrusted.example"}).status_code == 400


def test_logs_do_not_contain_feedback_or_query_strings(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="feedback_board")
    client.post("/api/feedback", json={"name": "PrivateName", "message": "PrivateMessage"})
    client.get("/missing?private=query")
    output = " ".join(
        record.message for record in caplog.records if record.name == "feedback_board"
    )
    assert "route=/api/feedback status=201" in output
    assert "route=other status=404" in output
    assert "PrivateName" not in output
    assert "PrivateMessage" not in output
    assert "private=query" not in output


def test_cloud_cannot_silently_use_sqlite() -> None:
    with pytest.raises(ValidationError, match="Cloud deployment requires DATABASE_URL"):
        Settings(_env_file=None, environment="cloud", database_url="")


def test_bad_configuration_does_not_print_database_secret() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, database_url="bad-url-with-private-password")
    assert "private-password" not in str(caught.value)


def test_render_hostname_is_accepted(tmp_path: Path) -> None:
    settings = local_settings(tmp_path, render_external_hostname="feedback.onrender.com")
    with TestClient(create_app(settings)) as client:
        assert client.get("/", headers={"Host": "feedback.onrender.com"}).status_code == 200


def test_cloud_database_cannot_disable_tls() -> None:
    with pytest.raises(ValidationError, match="Cloud database connections require TLS"):
        Settings(
            _env_file=None,
            environment="cloud",
            database_url="postgresql://db.example/feedback",
            database_sslmode="disable",
        )


@pytest.mark.parametrize("sslmode", ["require", "disable"])
def test_postgres_connection_uses_configured_tls(sslmode: str) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://db.example/feedback",
        database_sslmode=sslmode,
    )
    with patch("feedback_board.database.psycopg.connect") as connect:
        Database(settings).check()
        assert connect.call_args.kwargs["sslmode"] == sslmode
        assert connect.call_args.kwargs["connect_timeout"] == 5

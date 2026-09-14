from fastapi.testclient import TestClient


def test_health(monkeypatch) -> None:
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    from app.main import app

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

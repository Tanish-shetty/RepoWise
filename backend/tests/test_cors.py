import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:5174"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_frontend_preflight(origin, method):
    response = TestClient(app).options(
        "/api/repositories",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert method in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_unlisted_origin_is_rejected():
    response = TestClient(app).options(
        "/api/repositories",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

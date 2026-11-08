import pytest


@pytest.mark.asyncio
async def test_validation_error_has_reference_without_echoing_private_input(client):
    response = await client.post("/auth/refresh", json={"refresh_token": {"private": "must-not-appear"}})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["fields"][0]["loc"] == ["body", "refresh_token"]
    assert "must-not-appear" not in response.text


@pytest.mark.asyncio
async def test_browser_can_read_export_metadata_headers(client):
    response = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-export-total" in exposed and "content-disposition" in exposed

import httpx
import pytest

from app.main import app


@pytest.fixture
def asgi_transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=app)


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_database(
    asgi_transport: httpx.ASGITransport,
) -> None:
    async with httpx.AsyncClient(
        transport=asgi_transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_index_redirects_anonymous_user_to_login(
    asgi_transport: httpx.ASGITransport,
) -> None:
    async with httpx.AsyncClient(
        transport=asgi_transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"

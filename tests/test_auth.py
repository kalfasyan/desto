"""Tests for dashboard login, post-login redirects and network binding settings."""

import asyncio

import httpx
import pytest
from nicegui import app as nicegui_app
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from desto.app.auth import AuthMiddleware, check_password, get_auth_config, is_loopback, safe_redirect_target, setup_auth

AUTH_ENV_VARS = ("DESTO_HOST", "DESTO_PORT", "DESTO_PASSWORD", "DESTO_STORAGE_SECRET")


@pytest.fixture
def clean_env(monkeypatch):
    for name in AUTH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _protected_app(authenticated: bool) -> Starlette:
    async def ok(request):
        return PlainTextResponse("dashboard")

    routes = [
        Route("/", ok),
        Route("/login", ok),
        Route("/logout", ok),
        Route("/_nicegui/3.0.0/static/app.js", ok),
        Route("/_nicegui_ws/socket.io/", ok),
        Route("/_nicegui_lookalike", ok),
    ]
    starlette_app = Starlette(routes=routes)
    starlette_app.add_middleware(AuthMiddleware, is_authenticated=lambda: authenticated)
    return starlette_app


def _get(starlette_app: Starlette, path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=starlette_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path, follow_redirects=False)

    return asyncio.run(send())


@pytest.mark.parametrize("path", ["/", "/scripts", "/_nicegui_lookalike"])
def test_pages_redirect_to_login_when_logged_out(path):
    response = _get(_protected_app(authenticated=False), path)
    assert response.status_code == 307
    assert response.headers["location"] == f"/login?redirect_to={path}"


@pytest.mark.parametrize("path", ["/login", "/logout", "/_nicegui/3.0.0/static/app.js", "/_nicegui_ws/socket.io/"])
def test_login_and_nicegui_assets_are_public(path):
    assert _get(_protected_app(authenticated=False), path).status_code == 200


def test_pages_are_served_when_logged_in():
    response = _get(_protected_app(authenticated=True), "/")
    assert response.status_code == 200
    assert response.text == "dashboard"


@pytest.mark.parametrize("host", ["127.0.0.1", "127.5.5.5", "localhost", "LOCALHOST", "::1", "[::1]", "::ffff:127.0.0.1"])
def test_is_loopback_accepts_local_addresses(host):
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "example.com", ""])
def test_is_loopback_rejects_network_addresses(host):
    assert not is_loopback(host)


def test_check_password_requires_exact_match():
    assert check_password("s3cret", "s3cret")
    assert not check_password("s3cre", "s3cret")
    assert not check_password("S3CRET", "s3cret")
    assert not check_password("", "s3cret")


def test_check_password_never_matches_when_no_password_is_configured():
    assert not check_password("", "")
    assert not check_password("anything", "")


@pytest.mark.parametrize("target", ["/", "/scripts", "/scripts?tab=new"])
def test_safe_redirect_target_keeps_same_site_paths(target):
    assert safe_redirect_target(target) == target


@pytest.mark.parametrize("target", [None, "", "scripts", "//evil.com", "http://evil.com", "https://evil.com/x", "/\\evil.com"])
def test_safe_redirect_target_falls_back_to_root(target):
    assert safe_redirect_target(target) == "/"


def test_auth_config_defaults_to_loopback_without_password(clean_env):
    cfg = get_auth_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8809
    assert cfg.password == ""
    assert cfg.storage_secret


def test_auth_config_reads_environment_overrides(clean_env):
    clean_env.setenv("DESTO_HOST", "0.0.0.0")
    clean_env.setenv("DESTO_PORT", "8899")
    clean_env.setenv("DESTO_PASSWORD", "s3cret")
    clean_env.setenv("DESTO_STORAGE_SECRET", "fixed-secret")
    cfg = get_auth_config()
    assert (cfg.host, cfg.port, cfg.password, cfg.storage_secret) == ("0.0.0.0", 8899, "s3cret", "fixed-secret")


def test_empty_host_and_port_fall_back_to_defaults(clean_env):
    clean_env.setenv("DESTO_HOST", "")
    clean_env.setenv("DESTO_PORT", "")
    cfg = get_auth_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8809


def test_generated_storage_secret_differs_between_calls(clean_env):
    assert get_auth_config().storage_secret != get_auth_config().storage_secret


def test_setup_auth_without_password_adds_no_middleware():
    before = len(nicegui_app.user_middleware)
    setup_auth("")
    assert len(nicegui_app.user_middleware) == before

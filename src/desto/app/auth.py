"""Optional password login for the web dashboard and network binding settings."""

import asyncio
import hmac
import ipaddress
import os
import secrets
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote

from nicegui import app, ui
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp

LOGIN_PATH = "/login"
LOGOUT_PATH = "/logout"
# Pages that stay reachable without logging in. NiceGUI serves its JavaScript, CSS and websocket
# under the prefixes, which must stay reachable too, otherwise the login page itself cannot load.
PUBLIC_PAGES = (LOGIN_PATH, LOGOUT_PATH)
PUBLIC_PREFIXES = ("/_nicegui/", "/_nicegui_ws/")
FAILED_LOGIN_DELAY_SECONDS = 1.0


@dataclass(frozen=True)
class AuthConfig:
    """Network and login settings for the dashboard."""

    host: str
    port: int
    password: str
    storage_secret: str


def get_auth_config() -> AuthConfig:
    """Read the dashboard settings from environment variables."""
    return AuthConfig(
        # An empty host would make NiceGUI listen on all interfaces, so it falls back to loopback instead.
        host=os.getenv("DESTO_HOST", "").strip() or "127.0.0.1",
        port=int(os.getenv("DESTO_PORT", "").strip() or "8809"),
        password=os.getenv("DESTO_PASSWORD", ""),
        # Without a fixed secret a random one is generated, so browser sessions end when the process restarts.
        storage_secret=os.getenv("DESTO_STORAGE_SECRET", "") or secrets.token_urlsafe(32),
    )


def is_loopback(host: str) -> bool:
    """Return True if the host only accepts connections from this machine."""
    host = host.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Other hostnames and empty values are treated as reachable from the network.
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def check_password(candidate: str, expected: str) -> bool:
    """Compare two passwords in constant time. An empty expected password never matches."""
    if not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def safe_redirect_target(target: Optional[str]) -> str:
    """Return a same-site path to redirect to after login, or "/" for anything else."""
    # Protocol-relative ("//host") and backslash forms are treated as other hosts by browsers.
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def _is_authenticated() -> bool:
    return bool(app.storage.user.get("authenticated", False))


class AuthMiddleware(BaseHTTPMiddleware):
    """Send requests to the login page until the browser session has logged in."""

    def __init__(self, asgi_app: ASGIApp, is_authenticated: Callable[[], bool] = _is_authenticated) -> None:
        super().__init__(asgi_app)
        self.is_authenticated = is_authenticated

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in PUBLIC_PAGES or path.startswith(PUBLIC_PREFIXES) or self.is_authenticated():
            return await call_next(request)
        return RedirectResponse(f"{LOGIN_PATH}?redirect_to={quote(path, safe='/')}")


def setup_auth(password: str) -> None:
    """Require the password for every dashboard page. Does nothing when the password is empty."""
    if not password:
        return
    app.add_middleware(AuthMiddleware)

    @ui.page(LOGOUT_PATH)
    def logout_page() -> RedirectResponse:
        # Page builders run inside the request, which app.storage.user needs. Click handlers on the dashboard do not.
        app.storage.user.clear()
        return RedirectResponse(LOGIN_PATH)

    @ui.page(LOGIN_PATH, title="desto login")
    def login(request: Request) -> Optional[Response]:
        if _is_authenticated():
            return RedirectResponse("/")
        redirect_to = safe_redirect_target(request.query_params.get("redirect_to"))

        async def try_login() -> None:
            if check_password(password_input.value, password):
                app.storage.user.update({"authenticated": True})
                ui.navigate.to(redirect_to)
            else:
                ui.notify("Wrong password", color="negative")
                await asyncio.sleep(FAILED_LOGIN_DELAY_SECONDS)  # Slows down password guessing.

        with ui.card().classes("absolute-center w-80 gap-4"):
            ui.label("desto").classes("text-2xl font-black tracking-tighter text-primary italic uppercase")
            password_input = ui.input("Password", password=True, password_toggle_button=True).props("autofocus").classes("w-full").on("keydown.enter", try_login)
            ui.button("Log in", on_click=try_login).classes("w-full")
        return None


def logout() -> None:
    """Send the browser to the logout page, which forgets its login and returns to the login page."""
    ui.navigate.to(LOGOUT_PATH)

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx
import msal

# Owner read/write only (0o600); the file holds a bearer token.
_OWNER_RW = stat.S_IRUSR | stat.S_IWUSR


def load_msal_cache(token_cache_file: Path) -> msal.SerializableTokenCache:
    """Load MSAL token cache from disk if it exists."""
    cache = msal.SerializableTokenCache()
    try:
        cache.deserialize(token_cache_file.read_text())
    except (json.JSONDecodeError, TypeError, OSError):
        pass
    return cache


def save_msal_cache(cache: msal.SerializableTokenCache, token_cache_file: Path) -> None:
    """Persist MSAL token cache to disk if it has changed."""
    if cache.has_state_changed:
        token_cache_dir = token_cache_file.parent
        token_cache_dir.mkdir(parents=True, exist_ok=True)
        # Create the file atomically with restrictive permissions so the
        # bearer token is never world-readable, even briefly.
        fd = os.open(token_cache_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _OWNER_RW)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(cache.serialize())
        finally:
            # If the file pre-existed, O_CREAT won't reset its mode; enforce it.
            try:
                token_cache_file.chmod(_OWNER_RW)
            except (OSError, NotImplementedError):
                # chmod may fail on non-POSIX filesystems
                pass


def acquire_msal_token(
    token_cache_file: Path,
    scopes: list[str],
    client_id: str,
    tenant_id: str | None = None,
    callback_port: int = 8080,
) -> str:
    """Acquire an MSAL token using the device code flow, with caching to avoid unnecessary re-authentication."""
    cache = load_msal_cache(token_cache_file)
    authority = f"https://login.microsoftonline.com/{tenant_id}" if tenant_id else None
    # MSAL will use https://login.microsoftonline.com/common if authority is None,
    # which supports multi-tenant apps but may require interactive login on every
    # run if the tenant can't be inferred from the cache
    app = msal.PublicClientApplication(
        client_id, authority=authority, token_cache=cache
    )

    accounts = app.get_accounts()
    account = accounts[0] if accounts else None

    result = app.acquire_token_silent(scopes, account=account)
    if not result:
        result = app.acquire_token_interactive(scopes, port=callback_port)

    if "access_token" not in result:
        raise SystemExit(
            f"MSAL authentication failed: {result.get('error_description', result)}"
        )

    save_msal_cache(cache, token_cache_file)
    return result["access_token"]


class MSALBearerAuth(httpx.Auth):
    """httpx.Auth that injects a fresh MSAL Bearer token on every request."""

    requires_request_body = False

    def __init__(
        self,
        token_cache_file: Path,
        scopes: list[str],
        client_id: str,
        tenant_id: str,
        callback_port: int,
    ):
        self._token = acquire_msal_token(
            token_cache_file=token_cache_file,
            scopes=scopes,
            client_id=client_id,
            tenant_id=tenant_id,
            callback_port=callback_port,
        )

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request

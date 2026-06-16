"""
Fides Gateway command-line entry point.

Parses CLI arguments, constructs a :class:`fastmcp_proxy.MCPGateway` from the
given configuration file, and serves its ASGI app with ``uvicorn``. All proxy
behaviour — per-upstream FastMCP proxies, middleware composition, the
``initialize``/``tools`` hook surface — lives in :mod:`fastmcp_proxy`.
"""

from __future__ import annotations

import argparse
import logging
import uvicorn

from pathlib import Path

from fastmcp.server.middleware.logging import LoggingMiddleware

from fastmcp_proxy import MCPGateway

_DEFAULT_HTTP_HOST = "127.0.0.1"
_DEFAULT_HTTP_PORT = 9090
_DEFAULT_CONFIG = "config.json"
_DEFAULT_TOKEN_CACHE_FILE = Path.home() / ".cache" / "fides-gateway" / "msal_cache.json"
_LOG_LEVELS = ["critical", "error", "warning", "info", "debug"]
_DEFAULT_LOG_LEVEL = "info"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fides Gateway - multi-server MCP proxy"
    )
    parser.add_argument(
        "--config",
        help=f"Path to the proxy configuration JSON file (default: {_DEFAULT_CONFIG}). "
        "See config.workiq.example.json",
        default=_DEFAULT_CONFIG,
    )
    parser.add_argument(
        "--token_cache",
        help=f"Path to the MSAL token cache file (default: {_DEFAULT_TOKEN_CACHE_FILE})",
        default=_DEFAULT_TOKEN_CACHE_FILE,
    )
    parser.add_argument(
        "--host",
        help=f"HTTP host to listen on (default: {_DEFAULT_HTTP_HOST})",
        default=_DEFAULT_HTTP_HOST,
    )
    parser.add_argument(
        "--port",
        help=f"HTTP port to listen on (default: {_DEFAULT_HTTP_PORT})",
        type=int,
        default=_DEFAULT_HTTP_PORT,
    )
    parser.add_argument(
        "--log-level",
        help=f"Logging level (default: {_DEFAULT_LOG_LEVEL})",
        choices=_LOG_LEVELS,
        default=_DEFAULT_LOG_LEVEL,
    )

    args = parser.parse_args()

    log_level = args.log_level.upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    gateway = MCPGateway(
        config_path=Path(args.config), token_cache_path=Path(args.token_cache)
    )

    if log_level == "DEBUG":
        debug_logger = logging.getLogger("fides_gateway.debug")
        for server_id in gateway.config.keys():
            gateway.add_middleware(
                server_id,
                LoggingMiddleware(
                    logger=debug_logger,
                    include_payloads=True,
                ),
            )

    app = gateway.asgi_app()

    print(f"[gateway] FastMCP Gateway listening on http://{args.host}:{args.port}")
    print(f"[gateway] Configured servers: {list(gateway.config.keys())}")
    print(f"[gateway] Proxy endpoints: http://{args.host}:{args.port}/mcp/<server_id>/")

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()

"""Textual TUI playground for fides-gateway Regorus policies.

Three-panel layout, inspired by https://anakrish.github.io/regorus-playground/
(minus the Data panel):

  +-----------------------------------------------+
  | Query: data.example.allow                     |
  +-----------------------+-----------------------+
  | Policy (.rego)        | Input (JSON)          |
  |                       |                       |
  +-----------------------+-----------------------+
  | Output                                        |
  +-----------------------------------------------+

The Input pane holds the JSON representation of a
:class:`policy_engine.LabeledToolCallParams` (i.e. ``name``,
``arguments``, ``_meta``). The Output pane shows the result of
:func:`policy_engine.eval_policy` evaluated on the given Rego *query*
(e.g. ``data.example.allow``).

The playground wires the gateway's full set of Rego extensions:

* ``ifc.label("<jsonpath>")`` — resolves the effective IFC label of
  any sub-object of the Input.
* ``upstream.serverInfo()`` — returns the hardcoded
  :data:`SERVER_INFO` snapshot of the upstream's ``Implementation``
  block (see ``--server`` / ``--config`` flags below).
* ``upstream.<ToolName>(args)`` — invokes the corresponding tool on
  the upstream MCP server configured in ``../config.json``. Built
  from the same MSAL / OAuth machinery as :class:`MCPGateway`, so
  on first use the upstream's auth flow (e.g. MSAL device or browser
  login) will fire interactively. Pass ``--no-upstream`` to skip this
  and run the playground in a fully-offline mode (only ``ifc.label``
  and ``upstream.serverInfo`` are then available).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from pathlib import Path
from typing import Any, Callable

from fastmcp import Client
from fastmcp.client.auth import OAuth
from fastmcp.client.transports import StreamableHttpTransport
from msal_auth import MSALBearerAuth
from fastmcp_proxy import load_config
from policy_engine import LabeledToolCallParams, eval_policy
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import MouseDown, MouseMove, MouseUp
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, Static, TextArea
from rich.text import Text

SAMPLES_DIR = Path(__file__).parent / "samples"
DEFAULT_POLICY = (SAMPLES_DIR / "example.rego").read_text()
DEFAULT_INPUT = (SAMPLES_DIR / "example.json").read_text()
DEFAULT_QUERY = "data.example.decision"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config.json"
DEFAULT_TOKEN_CACHE = Path.home() / ".cache" / "fides-gateway" / "msal_cache.json"

# Hardcoded snapshot of the upstream's ``Implementation`` block as
# captured by ``gateway.py`` against ``config.json`` (the WorkIQ
# TeamsServer). Exposed to policies as ``upstream.serverInfo()``.
SERVER_INFO: dict[str, Any] = {
    "name": "mcp_TeamsServer",
    "version": "3.3.1",
}


UpstreamClientFactory = Callable[[], Client]


class Splitter(Widget):
    """A draggable bar between two siblings that resizes them on drag.

    Place between two widgets identified by ``prev_id`` and
    ``next_id``. On ``mouse_down`` the splitter captures the mouse;
    while held, each ``mouse_move`` adjusts the prev/next widgets'
    width (``orientation="vertical"``) or height
    (``orientation="horizontal"``) so their combined size is preserved
    and the split tracks the cursor. ``mouse_up`` releases the
    capture.

    The two siblings must start with a sizable ``width``/``height``
    style (``1fr`` works); on first drag those are converted to
    integer cell counts so subsequent layout passes respect the user's
    chosen split.
    """

    DEFAULT_CSS = """
    Splitter {
        background: transparent;
    }
    Splitter:hover {
        background: $accent 40%;
    }
    Splitter.-dragging {
        background: $accent;
    }
    Splitter.-vertical {
        width: 1;
        height: 1fr;
    }
    Splitter.-horizontal {
        width: 1fr;
        height: 1;
    }
    """

    # Minimum size in cells we'll leave on either side of the handle so
    # a frantic drag can't completely collapse a pane.
    MIN_CELLS = 5

    def __init__(
        self,
        prev_id: str,
        next_id: str,
        orientation: str = "vertical",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if orientation not in ("vertical", "horizontal"):
            raise ValueError(
                f"Splitter orientation must be 'vertical' or 'horizontal', "
                f"got {orientation!r}"
            )
        self._orientation = orientation
        self._prev_id = prev_id
        self._next_id = next_id
        self._dragging = False
        self.add_class(f"-{orientation}")
        self.can_focus = False

    def render(self) -> Text:
        # Render as a blank cell — the splitter's visual is purely the
        # styled background; any default placeholder text (e.g. the
        # widget class name) would clash with that.
        return Text("")

    def on_mouse_down(self, event: MouseDown) -> None:
        self._dragging = True
        self.add_class("-dragging")
        self.capture_mouse(True)
        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.remove_class("-dragging")
            self.capture_mouse(False)
            event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        if not self._dragging:
            return
        try:
            prev = self.screen.query_one(f"#{self._prev_id}")
            next_ = self.screen.query_one(f"#{self._next_id}")
        except Exception:
            return
        if self._orientation == "vertical":
            total = prev.region.width + next_.region.width
            new_prev = event.screen_x - prev.region.x
            new_prev = max(self.MIN_CELLS, min(total - self.MIN_CELLS, new_prev))
            prev.styles.width = new_prev
            next_.styles.width = total - new_prev
        else:
            total = prev.region.height + next_.region.height
            new_prev = event.screen_y - prev.region.y
            new_prev = max(self.MIN_CELLS, min(total - self.MIN_CELLS, new_prev))
            prev.styles.height = new_prev
            next_.styles.height = total - new_prev
        event.stop()


def build_upstream_client_factory(
    config_path: Path,
    token_cache_path: Path,
    server_id: str | None = None,
) -> tuple[str, UpstreamClientFactory]:
    """Build a factory that returns a fresh :class:`fastmcp.Client` per call.

    Mirrors :meth:`MCPGateway._build_proxy`'s transport setup (MSAL,
    OAuth, or plain HTTP) for the upstream identified by *server_id*
    in *config_path*. If *server_id* is ``None``, the first entry in
    ``mcpServers`` is used. Returns the resolved ``server_id`` and a
    zero-arg factory that produces a fresh ``Client`` bound to the
    configured ``StreamableHttpTransport`` — each call to
    :func:`policy_engine.eval_policy` instantiates one (the gateway
    follows the same pattern).
    """
    config = load_config(config_path)
    if not config:
        raise ValueError(f"{config_path} has no upstream servers")
    if server_id is None:
        server_id = next(iter(config))
    if server_id not in config:
        raise ValueError(
            f"server_id {server_id!r} not in {config_path}; " f"have: {list(config)}"
        )
    cfg = config[server_id]
    headers = cfg.get("headers")
    if "msal" in cfg:
        msal_cfg = cfg["msal"]
        transport = StreamableHttpTransport(
            url=cfg["url"],
            headers=headers,
            auth=MSALBearerAuth(
                token_cache_file=token_cache_path,
                scopes=msal_cfg["scopes"],
                client_id=msal_cfg["client_id"],
                tenant_id=msal_cfg["tenant_id"],
                callback_port=msal_cfg["callback_port"],
            ),
        )
    elif "oauth" in cfg:
        oauth_cfg = cfg["oauth"]
        auth = OAuth(
            mcp_url=cfg["url"],
            scopes=oauth_cfg["scopes"],
            callback_port=oauth_cfg["callback_port"],
            client_id=oauth_cfg["client_id"],
            client_secret=oauth_cfg["client_secret"],
        )
        transport = StreamableHttpTransport(url=cfg["url"], headers=headers, auth=auth)
    else:
        transport = StreamableHttpTransport(url=cfg["url"], headers=headers)

    def factory() -> Client:
        return Client(transport)

    return server_id, factory


class PlaygroundApp(App[None]):
    """Three-pane Regorus playground."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #query-row {
        height: 3;
        padding: 0 1;
    }
    #query-row > Static {
        width: auto;
        padding: 1 1 0 0;
        color: $text-muted;
    }
    #query-input {
        width: 1fr;
    }
    #body {
        height: 1fr;
    }
    #editors {
        height: 2fr;
    }
    #output-pane {
        height: 1fr;
    }
    #policy-pane, #input-pane {
        width: 1fr;
    }
    .pane {
        border: round $accent;
        padding: 0;
    }
    .pane-title {
        background: $accent 30%;
        color: $text;
        padding: 0 1;
        height: 1;
    }
    .pane TextArea {
        height: 1fr;
    }
    #output-scroll {
        height: 1fr;
        scrollbar-gutter: stable;
    }
    #output {
        color: $text;
        padding: 0 1;
        height: auto;
    }
    .error {
        color: $error;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "evaluate", "Evaluate", show=True),
        Binding("f5", "evaluate", "Evaluate", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        upstream_client_factory: UpstreamClientFactory | None = None,
        upstream_server_id: str | None = None,
    ) -> None:
        """Build the playground app.

        *upstream_client_factory* is a zero-arg callable returning a
        fresh :class:`fastmcp.Client` bound to the upstream MCP server.
        When provided, every evaluation calls it and forwards the
        client to :func:`policy_engine.eval_policy`, which then exposes
        each upstream tool to Rego as ``upstream.<ToolName>(args)``.
        When ``None``, only the ``ifc.label`` and ``upstream.serverInfo``
        extensions are available.
        """
        super().__init__()
        self._upstream_client_factory = upstream_client_factory
        self._upstream_server_id = upstream_server_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="query-row"):
            yield Static("Query:")
            yield Input(value=DEFAULT_QUERY, id="query-input")
        with Vertical(id="body"):
            with Horizontal(id="editors"):
                with Vertical(classes="pane", id="policy-pane"):
                    yield Static("Policy (.rego)", classes="pane-title")
                    yield TextArea.code_editor(
                        DEFAULT_POLICY,
                        language=None,
                        id="policy-editor",
                    )
                yield Splitter(
                    prev_id="policy-pane",
                    next_id="input-pane",
                    orientation="vertical",
                    id="editors-splitter",
                )
                with Vertical(classes="pane", id="input-pane"):
                    yield Static(
                        "Input (JSON — LabeledToolCallParams)",
                        classes="pane-title",
                    )
                    yield TextArea.code_editor(
                        DEFAULT_INPUT,
                        language="json",
                        id="input-editor",
                    )
            yield Splitter(
                prev_id="editors",
                next_id="output-pane",
                orientation="horizontal",
                id="body-splitter",
            )
            with Vertical(classes="pane", id="output-pane"):
                yield Static("Output", classes="pane-title")
                with VerticalScroll(id="output-scroll"):
                    yield Static("", id="output", expand=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "fides-gateway Regorus Playground"
        upstream_status = (
            f"upstream={self._upstream_server_id}"
            if self._upstream_client_factory is not None
            else "upstream=disabled"
        )
        self.sub_title = f"Ctrl+S to evaluate · Ctrl+Q to quit · {upstream_status}"
        self.call_after_refresh(self.action_evaluate)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "query-input":
            self.action_evaluate()

    async def action_evaluate(self) -> None:
        policy = self.query_one("#policy-editor", TextArea).text
        input_text = self.query_one("#input-editor", TextArea).text
        query = self.query_one("#query-input", Input).value.strip()
        output = self.query_one("#output", Static)

        try:
            await self._evaluate(policy, input_text, query, output)
        except Exception:
            # Catch-all so an unexpected exception in the evaluation
            # path (or in our error-rendering itself) never tears down
            # the app — surface it in the Output pane instead.
            output.update(_error(traceback.format_exc()))

    async def _evaluate(
        self, policy: str, input_text: str, query: str, output: Static
    ) -> None:
        try:
            raw = json.loads(input_text)
        except json.JSONDecodeError as e:
            output.update(_error(f"Input JSON parse error:\n{e}"))
            return

        try:
            # Validate the input matches LabeledToolCallParams. We then
            # pass the *raw dict* through to eval_policy so that the
            # wire-form labels (under _meta[IFC_LABELS_META_PREFIX])
            # are visible to ifc.label(...) unmodified.
            LabeledToolCallParams.model_validate(raw)
        except Exception as e:  # pydantic ValidationError, etc.
            output.update(_error(f"Input does not match LabeledToolCallParams:\n{e}"))
            return

        if not query:
            output.update(_error("Query is empty. Try e.g. data.example.allow"))
            return

        try:
            upstream_client = (
                self._upstream_client_factory()
                if self._upstream_client_factory is not None
                else None
            )
            result = await eval_policy(
                raw,
                policy,
                upstream_client=upstream_client,
                server_info=SERVER_INFO,
                query=query,
            )
        except Exception:
            output.update(_error(traceback.format_exc()))
            return

        try:
            pretty = json.dumps(result, indent=2, default=str)
        except (TypeError, ValueError):
            pretty = repr(result)
        # Plain ``Text`` (no markup parsing) so output that happens to
        # contain ``[...]`` substrings isn't mis-interpreted by Rich.
        output.update(Text(pretty))


def _error(msg: str) -> Text:
    """Render *msg* as red text without Rich markup parsing.

    Pydantic and traceback messages routinely contain ``[type=...]``
    substrings that Rich's markup parser would otherwise try to
    interpret as a style tag and choke on, so we build a ``Text``
    object directly.
    """
    return Text(msg, style="red")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Textual TUI playground for editing and evaluating Regorus "
            "policies against fides-gateway LabeledToolCallParams."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=(
            "Path to the gateway config JSON file used to build the "
            f"upstream client (default: {DEFAULT_CONFIG})."
        ),
    )
    parser.add_argument(
        "--token-cache",
        type=Path,
        default=DEFAULT_TOKEN_CACHE,
        help=(
            "Path to the MSAL token cache used when the upstream is "
            f"MSAL-authed (default: {DEFAULT_TOKEN_CACHE})."
        ),
    )
    parser.add_argument(
        "--server",
        default=None,
        help=(
            "Which upstream server_id from the config to wire as "
            "``upstream.<Tool>()``. Defaults to the first entry under "
            "``mcpServers``."
        ),
    )
    parser.add_argument(
        "--no-upstream",
        action="store_true",
        help=(
            "Skip building an upstream client. ``upstream.<Tool>()`` "
            "extensions are not registered; ``ifc.label`` and "
            "``upstream.serverInfo`` still work."
        ),
    )
    args = parser.parse_args()

    factory: UpstreamClientFactory | None = None
    server_id: str | None = None
    if not args.no_upstream:
        try:
            server_id, factory = build_upstream_client_factory(
                args.config, args.token_cache, args.server
            )
        except Exception as exc:
            print(
                f"warning: failed to build upstream client from {args.config}: "
                f"{exc}. Continuing with upstream extensions disabled."
            )

    PlaygroundApp(
        upstream_client_factory=factory,
        upstream_server_id=server_id,
    ).run()


if __name__ == "__main__":
    main()

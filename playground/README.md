# fides-gateway Regorus playground

A three-panel Textual TUI for editing and evaluating Regorus policies
against the JSON shape of
`policy_engine.LabeledToolCallParams`.

```
+---------------------------------+
| Query: data.example.allow       |
+----------------+----------------+
| Policy (.rego) | Input (JSON)   |
+----------------+----------------+
+ Output (query)                  |
+---------------------------------+
```

## Run

```
cd playground
uv sync
uv run fides-playground       # or: uv run python playground.py
```

Keybindings:

- `Ctrl+S` (or `F5`) — evaluate
- `Enter` in the query field — evaluate
- `Ctrl+Q` — quit

## What it does

The Input pane must contain JSON that matches
`policy_engine.LabeledToolCallParams` — i.e. `name`, `arguments` and
`_meta` (with `"com.github.ifc/labels"` keyed by RFC 9535 JSONPath
strings). The playground hands the raw dict to
`policy_engine.eval_policy(...)` with:

- `upstream_client=<factory()>` — by default the playground builds a
  fresh `fastmcp.Client` per evaluation against the first server in
  `../config.json` (reusing the same MSAL / OAuth machinery as
  `MCPGateway`), so policies can call `upstream.<ToolName>(args)`.
  On first use the upstream's auth flow (MSAL device / browser
  login) will fire interactively. Pick a different server with
  `--server`, point at a different config with `--config`, or disable
  upstream extensions entirely with `--no-upstream`.
- `server_info=SERVER_INFO` — a hardcoded snapshot of the upstream's
  `Implementation` block from a real run of `gateway.py` with
  `../config.json` (currently `{"name": "mcp_TeamsServer", "version":
  "3.3.1"}`). Replace `SERVER_INFO` in `playground.py` to experiment
  with other upstreams.
- `query=<query string>` — the Rego expression typed into the Query
  field (e.g. `data.example.allow`, `data.example.tool_label`,
  `data.example.teams`).

The raw value of the query is shown in the Output pane, pretty-printed
as JSON.

## CLI flags

- `--config PATH` — gateway config JSON (default: `../config.json`).
- `--server SERVER_ID` — which upstream from the config to wire
  (default: the first entry under `mcpServers`).
- `--token-cache PATH` — MSAL token cache (default:
  `~/.cache/fides-gateway/msal_cache.json`).
- `--no-upstream` — skip the upstream client. `upstream.<Tool>()`
  is then unavailable; `ifc.label` and `upstream.serverInfo` still work.

## Files

- `playground.py` — the Textual app.
- `samples/example.rego` — initial policy. Exercises `ifc.label(...)`
  and `upstream.serverInfo()`.
- `samples/example.json` — initial input, a labelled `ListTeams` call.

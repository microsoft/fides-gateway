from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

server = FastMCP("stdio-test-server")


@server.tool
def inspect_runtime(value: str) -> dict[str, str]:
    return {
        "cwd": os.getcwd(),
        "marker": os.environ["FIDES_STDIO_MARKER"],
        "value": value,
    }


Path(os.environ["FIDES_STDIO_PID_PATH"]).write_text(str(os.getpid()))
server.run(transport="stdio", show_banner=False)

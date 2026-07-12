#!/usr/bin/env python3
"""Tiny deterministic MCP stdio server used by the live verifier."""

from __future__ import annotations

import json
import sys


def result(request_id, value):
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": value}), flush=True)


def main() -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        request_id = request.get("id")
        if request_id is None:
            continue
        method = request.get("method")
        if method == "initialize":
            result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "cody-live", "version": "1"},
                },
            )
        elif method == "tools/list":
            result(
                request_id,
                {
                    "tools": [
                        {
                            "name": "echo_marker",
                            "description": "Return a deterministic marker for a value",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"value": {"type": "string"}},
                                "required": ["value"],
                            },
                        }
                    ]
                },
            )
        elif method == "tools/call":
            params = request.get("params") or {}
            value = (params.get("arguments") or {}).get("value", "")
            result(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": f"MCP_LIVE_OK::{str(value).upper()}"}
                    ],
                    "isError": False,
                },
            )
        else:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": f"Unknown method: {method}"},
                    }
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

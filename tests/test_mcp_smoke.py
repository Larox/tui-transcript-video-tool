"""Smoke test the stdio MCP server boots and answers `list_tools`."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest


@pytest.mark.asyncio
async def test_mcp_server_lists_tools() -> None:
    """Spawn the server as a subprocess and verify the MCP handshake + tools list."""
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tui_transcript_mcp.server"],
        env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "fake")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=10)
            tools = await asyncio.wait_for(session.list_tools(), timeout=10)
            names = {t.name for t in tools.tools}
            assert names == {"list_materias", "search_knowledge"}

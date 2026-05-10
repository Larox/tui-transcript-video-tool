"""Stdio MCP server. Console script: `tui-transcript-mcp`.

Two read-only tools:
- list_materias()
- search_knowledge(query, materia_name=None, k=8)
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tui_transcript_mcp.tools import (
    AmbiguousMateria,
    MateriaNotFound,
    list_materias,
    search_knowledge,
)

logger = logging.getLogger(__name__)


def _build_server() -> Server:
    server = Server("tui-transcript")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name="list_materias",
                description=(
                    "List all materias (courses) in the user's knowledge base, "
                    "with file/transcript/chunk counts. Call this first to know "
                    "what materias exist."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="search_knowledge",
                description=(
                    "Semantic search over the user's materias (PDFs + class transcripts). "
                    "Pass `materia_name` to scope the search to one materia (use list_materias "
                    "to discover names). Omit `materia_name` to search across all materias."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "materia_name": {"type": "string"},
                        "k": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "list_materias":
            materias = await asyncio.to_thread(list_materias)
            payload = "\n".join(
                f"- {m.name} (id={m.id}): {m.file_count} files, "
                f"{m.transcript_count} transcripts, {m.indexed_chunk_count} chunks"
                + (f". {m.description}" if m.description else "")
                for m in materias
            )
            return [TextContent(type="text", text=payload or "(no materias)")]

        if name == "search_knowledge":
            try:
                hits = await asyncio.to_thread(
                    search_knowledge,
                    arguments["query"],
                    materia_name=arguments.get("materia_name"),
                    k=int(arguments.get("k", 8)),
                )
            except (MateriaNotFound, AmbiguousMateria) as exc:
                return [TextContent(type="text", text=f"Error: {exc}")]
            if not hits:
                return [TextContent(type="text", text="(no results)")]
            blocks = [
                f"[{h.score:.2f}] {h.source} — {h.materia}\n{h.text}"
                for h in hits
            ]
            return [TextContent(type="text", text="\n\n---\n\n".join(blocks))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _serve() -> None:
    server = _build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Console script entry point."""
    asyncio.run(_serve())


if __name__ == "__main__":
    main()

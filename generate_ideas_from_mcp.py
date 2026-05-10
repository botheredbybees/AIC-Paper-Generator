#!/usr/bin/env python3
"""
generate_ideas_from_mcp.py

Query the a1c-knowledge MCP server for topics with open research questions,
check each question against Semantic Scholar for novelty, translate to AI
Scientist idea JSON via a local Ollama LLM, and write the enriched ideas JSON.

Usage:
    python generate_ideas_from_mcp.py --query "elder clowning wellbeing" \
        --confidence high --limit 10 --output ai_scientist/ideas/elder_clowning.json
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from mcp import ClientSession
from mcp.client.sse import sse_client

from ai_scientist.llm import create_client, extract_json_between_markers, get_response_from_llm
from ai_scientist.tools.semantic_scholar import search_for_papers


# ---------------------------------------------------------------------------
# BibTeX utilities
# ---------------------------------------------------------------------------

def bibtex_from_s2_paper(paper: dict) -> str:
    """Return a BibTeX string for a Semantic Scholar paper dict."""
    styles = paper.get("citationStyles") or {}
    if styles.get("bibtex"):
        return styles["bibtex"]

    authors = paper.get("authors") or []
    year = str(paper.get("year") or "0000")
    title = paper.get("title") or "Unknown Title"
    venue = paper.get("venue") or ""

    first_last = ""
    if authors:
        name_parts = (authors[0].get("name") or "").split()
        first_last = name_parts[-1] if name_parts else "unknown"

    key = re.sub(r"[^a-z0-9]", "", f"{first_last.lower()}{year}")
    author_str = " and ".join(a.get("name", "") for a in authors) or "Unknown"

    entry_type = "@inproceedings" if venue else "@article"
    venue_line = f"  booktitle = {{{venue}}},\n" if venue else ""

    return (
        f"{entry_type}{{{key},\n"
        f"  title = {{{title}}},\n"
        f"  author = {{{author_str}}},\n"
        f"  year = {{{year}}},\n"
        f"{venue_line}}}"
    )


# ---------------------------------------------------------------------------
# MCP client
# ---------------------------------------------------------------------------

def filter_topics_with_questions(topics: list[dict]) -> list[dict]:
    """Keep only topics that have at least one open question."""
    return [t for t in topics if t.get("open_questions")]


async def fetch_mcp_topics(
    query: str,
    domain: str | None,
    confidence: str | None,
    limit: int,
    mcp_url: str,
) -> list[dict]:
    """Query the MCP server and return full topic records for topics with open questions."""
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            args: dict = {"query": query, "limit": limit}
            if domain:
                args["domain"] = domain
            if confidence:
                args["confidence"] = confidence

            search_result = await session.call_tool("search_topics", arguments=args)
            if not search_result.content:
                return []
            topics_raw = json.loads(search_result.content[0].text)
            topics = filter_topics_with_questions(topics_raw)

            full_topics = []
            for topic in topics:
                get_result = await session.call_tool(
                    "get_topic", arguments={"slug": topic["slug"]}
                )
                if not get_result.content:
                    print(f"WARNING: get_topic returned empty content for slug={topic['slug']!r}")
                    continue
                try:
                    full_topics.append(json.loads(get_result.content[0].text))
                except json.JSONDecodeError as exc:
                    print(f"WARNING: invalid JSON from get_topic for slug={topic['slug']!r}: {exc}")
                    continue

            return full_topics

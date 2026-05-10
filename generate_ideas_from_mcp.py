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


# ---------------------------------------------------------------------------
# LLM idea translation
# ---------------------------------------------------------------------------

_TRANSLATION_SYSTEM = "You are a research idea generator for arts and health research."

_TRANSLATION_PROMPT = """\
Given a topic from a personal knowledge base, an open research question,
and a Semantic Scholar literature search on that question, your job is to:

1. Assess whether the open question is already well-answered in the broader
   literature. The personal knowledge base may have gaps that do not reflect
   real-world research gaps.
2. If the question is already comprehensively addressed: identify the genuine
   remaining gap — a specific population (e.g. older adults), setting
   (e.g. residential aged care), method, or outcome not yet studied.
3. Produce a structured research idea grounded in what actually exists.

Topic title: {title}
Domain: {domain}
Confidence level of existing evidence in personal knowledge base: {confidence}

Key findings from personal knowledge base:
{findings}

Open research question from personal knowledge base:
{open_question}

Semantic Scholar search results for this question:
{s2_text}

Instructions:
- If Semantic Scholar returns papers that already answer the question, acknowledge
  this explicitly in Related Work and refine the hypothesis to address the true gap.
- If no relevant papers are found, state this and proceed with the original question.
- Do not fabricate citations. Only reference papers present in the Semantic Scholar
  results above or in the personal knowledge base sources listed below.

Grounding sources from personal knowledge base: {sources}

Return a single JSON object wrapped in ```json ... ``` with these exact fields:
- "Name": short identifier, lowercase, underscores only (e.g. "elder_clowning_mechanisms")
- "Title": informative 8-12 word title
- "Short Hypothesis": 2-3 sentences stating a testable hypothesis for the genuine gap
- "Related Work": synthesis of what Semantic Scholar AND personal notes show; explicitly name the gap
- "Abstract": ~250-word conference-style abstract framing this as a proposal
- "Experiments": list of 3-5 proposed studies appropriate for arts and health research
  (interviews, observational studies, small-N designs, systematic reviews — NOT Python ML code)
- "Risk Factors and Limitations": list of 3-5 practical or methodological risks

Return only the JSON object, no other text.\
"""


def translate_to_idea(
    topic: dict,
    open_question: str,
    s2_papers: list[dict],
    model: str,
) -> dict | None:
    """Call an LLM to translate an open research question into an AI Scientist idea dict."""
    client, client_model = create_client(model)

    findings = "\n".join(
        f"{i + 1}. {f}"
        for i, f in enumerate(topic.get("key_findings") or [])
    ) or "No key findings recorded."

    s2_text = "\n".join(
        f"- {p.get('title', 'Unknown')} "
        f"({p.get('year', '?')}, {p.get('venue', 'unknown venue')}, "
        f"{p.get('citationCount', 0)} citations): "
        f"{(p.get('abstract') or '')[:300]}"
        for p in (s2_papers or [])
    ) or "No papers found for this query."

    def _esc(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    prompt = _TRANSLATION_PROMPT.format(
        title=_esc(topic.get("title", "")),
        domain=_esc(topic.get("domain", "")),
        confidence=_esc(topic.get("confidence", "")),
        findings=_esc(findings),
        open_question=_esc(open_question),
        s2_text=_esc(s2_text),
        sources=_esc(", ".join(topic.get("sources") or [])),
    )

    content, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=client_model,
        system_message=_TRANSLATION_SYSTEM,
        temperature=0.7,
    )
    result = extract_json_between_markers(content)
    return result if isinstance(result, dict) else None


def attach_private_keys(idea: dict, topic: dict, s2_papers: list[dict]) -> dict:
    """Attach private metadata keys to an idea dict for downstream use."""
    result = dict(idea)
    result["_mcp_topic"] = topic
    result["_s2_bibtex"] = [bibtex_from_s2_paper(p) for p in (s2_papers or [])]
    return result

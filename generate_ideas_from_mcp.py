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
from ai_scientist.tools.semantic_scholar import fetch_paper_citations, fetch_paper_references, search_for_papers, utas_library_url


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
    print(f"[MCP] Connecting to {mcp_url}")
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            print("[MCP] Session initialising...")
            await session.initialize()
            print("[MCP] Session ready")

            args: dict = {"query": query, "limit": limit}
            if domain:
                args["domain"] = domain
            if confidence:
                args["confidence"] = confidence

            print(f"[MCP] Calling search_topics: {args}")
            search_result = await session.call_tool("search_topics", arguments=args)
            print(f"[MCP] search_topics returned {len(search_result.content)} content item(s)")

            if not search_result.content:
                print("[MCP] WARNING: empty content from search_topics — 0 topics found")
                return []

            # FastMCP may return one TextContent per item OR a single item containing a JSON array.
            topics_raw = []
            for i, item in enumerate(search_result.content):
                if not hasattr(item, "text"):
                    print(f"[MCP] Skipping content[{i}]: no .text attribute (type={type(item).__name__})")
                    continue
                try:
                    parsed = json.loads(item.text)
                except json.JSONDecodeError as exc:
                    print(f"[MCP] WARNING: content[{i}] is not valid JSON: {exc}")
                    continue
                if isinstance(parsed, list):
                    print(f"[MCP] content[{i}] is a JSON array ({len(parsed)} items) — flattening")
                    topics_raw.extend(parsed)
                elif isinstance(parsed, dict):
                    topics_raw.append(parsed)
                else:
                    print(f"[MCP] WARNING: content[{i}] is {type(parsed).__name__}, skipping")

            print(f"[MCP] Parsed {len(topics_raw)} raw topic(s)")
            topics = filter_topics_with_questions(topics_raw)
            print(f"[MCP] {len(topics)} topic(s) have open questions")

            full_topics = []
            for topic in topics:
                slug = topic["slug"]
                print(f"[MCP] Fetching full record for slug={slug!r}")
                get_result = await session.call_tool(
                    "get_topic", arguments={"slug": slug}
                )
                if not get_result.content:
                    print(f"[MCP] WARNING: get_topic returned empty content for slug={slug!r}")
                    continue
                try:
                    full_topics.append(json.loads(get_result.content[0].text))
                    print(f"[MCP]   OK: got full topic for {slug!r}")
                except json.JSONDecodeError as exc:
                    print(f"[MCP] WARNING: invalid JSON from get_topic for slug={slug!r}: {exc}")
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
    print(f"[LLM] Calling {model} to translate question into idea JSON...")
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
    print(f"[LLM] Response received ({len(content)} chars), extracting JSON...")
    result = extract_json_between_markers(content)
    if not isinstance(result, dict):
        print(f"[LLM] WARNING: expected dict, got {type(result).__name__} — raw response head: {content[:200]!r}")
        return None
    print(f"[LLM] Idea extracted: Name={result.get('Name')!r}")
    return result


# ---------------------------------------------------------------------------
# Recursive S2 expansion
# ---------------------------------------------------------------------------

def expand_papers_recursively(
    seed_papers: list[dict],
    max_papers: int = 100,
) -> list[dict]:
    """
    Given seed papers from the initial S2 search, fetch their forward citations
    and backward references, deduplicate by paperId, and return up to max_papers
    sorted by citationCount descending. Seeds are always included.
    """
    seen: dict[str, dict] = {}

    # Seed papers go in first
    for p in seed_papers:
        pid = p.get("paperId")
        if pid and pid not in seen:
            seen[pid] = p

    # Traverse citations + references for each seed
    for p in seed_papers:
        pid = p.get("paperId")
        if not pid:
            continue
        print(f"    [S2] Fetching citations for {pid!r}")
        for related in fetch_paper_citations(pid, limit=50):
            rpid = related.get("paperId")
            if rpid and rpid not in seen:
                seen[rpid] = related
        print(f"    [S2] Fetching references for {pid!r}")
        for related in fetch_paper_references(pid, limit=50):
            rpid = related.get("paperId")
            if rpid and rpid not in seen:
                seen[rpid] = related

    # Sort by citationCount descending, cap at max_papers
    all_papers = sorted(seen.values(), key=lambda p: p.get("citationCount") or 0, reverse=True)
    return all_papers[:max_papers]


def classify_papers(papers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split papers into (open_access, paywalled) buckets."""
    oa = [p for p in papers if p.get("isOpenAccess")]
    paywalled = [p for p in papers if not p.get("isOpenAccess")]
    return oa, paywalled


def write_library_list(paywalled: list[dict], output_path: str) -> None:
    """Write a Markdown shopping list of paywalled papers with UTAS library links."""
    lines = [
        "# Papers Requiring Manual Library Download\n",
        "These papers were identified as highly relevant but are not open access.\n"
        "Retrieve them via UTAS Library using the links below, then save PDFs to the\n"
        "`pdfs/` folder alongside your ideas JSON file.\n",
        "## Paywalled Papers\n",
    ]

    for p in paywalled:
        title = p.get("title") or "Unknown Title"
        authors = p.get("authors") or []
        year = p.get("year") or "unknown"
        doi = (p.get("externalIds") or {}).get("DOI")

        first_author = ""
        if authors:
            name = authors[0].get("name") or ""
            parts = name.replace(",", " ").split()
            first_author = parts[0] if parts else "Unknown"

        safe_title = re.sub(r"[^\w\s]", "", title)[:40].strip().replace(" ", "_")
        suggested = f"{first_author}_{year}_{safe_title}.pdf"

        author_str = " & ".join(a.get("name", "") for a in authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        library_url = utas_library_url(doi=doi, title=title if not doi else None)
        link_label = "Library link" if doi else "Library search"

        lines.extend([
            f"- **Title:** {title}",
            f"  - Authors: {author_str} ({year})",
            f"  - Reason: paywalled (isOpenAccess=False)",
            f"  - {link_label}: {library_url}",
            f"  - Suggested filename: `{suggested}`",
            "",
        ])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"[Library] Wrote {len(paywalled)} paywalled paper(s) to {output_path}")


def attach_private_keys(
    idea: dict,
    topic: dict,
    s2_papers: list[dict],
    paywalled: list[dict] | None = None,
    oa_fulltext: dict | None = None,
) -> dict:
    """Attach private metadata keys to an idea dict for downstream use."""
    result = dict(idea)
    result["_mcp_topic"] = topic
    result["_s2_bibtex"] = [bibtex_from_s2_paper(p) for p in (s2_papers or [])]
    result["_s2_papers"] = s2_papers or []
    result["_paywalled"] = paywalled or []
    result["_oa_fulltext"] = oa_fulltext or {}
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate AI Scientist ideas from the a1c-knowledge MCP server"
    )
    parser.add_argument("--query", required=True,
                        help="Semantic search query, e.g. 'elder clowning wellbeing'")
    parser.add_argument("--confidence", default=None,
                        choices=["low", "medium", "high"])
    parser.add_argument("--domain", default=None,
                        choices=["intervention", "theory", "method"])
    parser.add_argument("--limit", type=int, default=10,
                        help="Max topics to retrieve from MCP")
    parser.add_argument("--max-questions", type=int, default=3,
                        help="Max open questions per topic to translate")
    parser.add_argument("--model", default="ollama/qwen2.5-coder:14b",
                        help="Ollama model for idea translation")
    parser.add_argument("--output",
                        default="ai_scientist/ideas/mcp_generated.json",
                        help="Output ideas JSON path")
    parser.add_argument("--s2-papers", type=int, default=10,
                        help="Semantic Scholar results to fetch per question")
    parser.add_argument("--no-novelty-check", action="store_true",
                        help="Skip Semantic Scholar novelty check")
    parser.add_argument("--append", action="store_true",
                        help="Append to existing ideas JSON instead of overwriting")
    parser.add_argument("--mcp-url",
                        default=os.environ.get("MCP_URL", "http://192.168.1.20:8765/sse"),
                        help="MCP server SSE endpoint URL")
    parser.add_argument("--recursive", action="store_true", default=False,
                        help="Expand seed papers via S2 citation/reference traversal")
    parser.add_argument("--max-papers", type=int, default=100, dest="max_papers",
                        help="Max total papers after recursive expansion (default: 100)")
    parser.add_argument("--fetch-fulltext", action="store_true", default=False,
                        dest="fetch_fulltext",
                        help="Download and extract Discussion/Results from OA PDFs (requires --recursive)")
    parser.add_argument("--library-list", default=None, dest="library_list",
                        help="Path to write to_fetch_from_library.md (default: alongside --output)")
    return parser.parse_args()


async def _main(args: argparse.Namespace) -> None:
    print(f"[STAGE 1/4] MCP topic search")
    print(f"  query={args.query!r} confidence={args.confidence} "
          f"domain={args.domain} limit={args.limit} mcp_url={args.mcp_url}")
    topics = await fetch_mcp_topics(
        args.query, args.domain, args.confidence, args.limit, args.mcp_url
    )
    print(f"[STAGE 1/4] Done — {len(topics)} topic(s) with open questions")

    if not topics:
        print("No topics found. Try broadening --query, removing --confidence, or increasing --limit.")
        return

    print(f"\n[STAGE 2/4] Novelty check via Semantic Scholar")
    if args.no_novelty_check:
        print("  Skipping (--no-novelty-check set)")

    ideas: list[dict] = []
    for topic in topics:
        questions = (topic.get("open_questions") or [])[:args.max_questions]
        print(f"\n  Topic: {topic['title']!r} — {len(questions)} question(s) to process")
        for qi, question in enumerate(questions, 1):
            print(f"  [{qi}/{len(questions)}] {question[:100]}")

            s2_papers: list[dict] = []
            oa_fulltext: dict[str, dict] = {}
            if not args.no_novelty_check:
                print(f"    [S2] Searching Semantic Scholar...")
                seed_papers = search_for_papers(question, result_limit=args.s2_papers) or []
                print(f"    [S2] {len(seed_papers)} seed paper(s) found")

                if args.recursive and seed_papers:
                    print(f"    [S2] Recursive expansion (cap={args.max_papers})...")
                    s2_papers = expand_papers_recursively(seed_papers, max_papers=args.max_papers)
                    print(f"    [S2] {len(s2_papers)} paper(s) after expansion")
                else:
                    s2_papers = seed_papers

            oa_papers, paywalled_papers = classify_papers(s2_papers)

            if args.fetch_fulltext and oa_papers:
                from ai_scientist.tools.pdf_reader import extract_sections
                print(f"    [PDF] Fetching full text from {len(oa_papers)} OA paper(s)...")
                for p in oa_papers:
                    oa_url = (p.get("openAccessPdf") or {}).get("url")
                    if not oa_url:
                        continue
                    pid = p.get("paperId", "unknown")
                    authors = p.get("authors") or []
                    first = (authors[0].get("name") or "").split()[-1] if authors else "Unknown"
                    year = str(p.get("year") or "0000")
                    ck = f"{first}{year}"
                    sections = extract_sections(oa_url, citation_key=ck)
                    if sections:
                        oa_fulltext[pid] = sections
                        print(f"      [PDF] {ck}: {list(sections.keys())}")

            print(f"\n[STAGE 3/4] LLM idea translation (model={args.model})")
            idea = translate_to_idea(topic, question, s2_papers, args.model)
            if idea is None:
                print("    WARNING: LLM returned invalid JSON — skipping this question")
                continue

            ideas.append(attach_private_keys(idea, topic, s2_papers, paywalled_papers, oa_fulltext))
            print(f"    Generated idea: {idea.get('Name', 'unknown')!r}")

    print(f"\n[STAGE 4/4] Writing output — {len(ideas)} idea(s) generated")

    if any(idea.get("_paywalled") for idea in ideas):
        library_list_path = args.library_list or str(Path(args.output).parent / "to_fetch_from_library.md")
        all_paywalled = []
        seen_ids: set[str] = set()
        for idea in ideas:
            for p in (idea.get("_paywalled") or []):
                pid = p.get("paperId")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_paywalled.append(p)
        if all_paywalled:
            write_library_list(all_paywalled, library_list_path)

    if args.append and os.path.exists(args.output):
        try:
            with open(args.output, encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, list):
                ideas = existing + ideas
            else:
                print(f"WARNING: {args.output} is not a JSON list — ignoring existing content")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: could not read existing ideas from {args.output}: {exc}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ideas, f, indent=2)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(_main(parse_args()))

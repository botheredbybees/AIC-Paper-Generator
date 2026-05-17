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
from ai_scientist.tools.semantic_scholar import fetch_paper_by_doi, fetch_paper_citations, fetch_paper_references, search_for_papers, utas_library_url


# ---------------------------------------------------------------------------
# BibTeX utilities
# ---------------------------------------------------------------------------

def bibtex_from_s2_paper(paper: dict) -> str:
    """Return a BibTeX string for a Semantic Scholar paper dict."""
    doi = (paper.get("externalIds") or {}).get("DOI") or ""
    doi_line = f"  doi = {{{doi}}},\n" if doi else ""
    note_line = f"  note = {{\\url{{https://doi.org/{doi}}}}},\n" if doi else ""

    styles = paper.get("citationStyles") or {}
    if styles.get("bibtex"):
        bib = styles["bibtex"].rstrip()
        if doi and not re.search(r'\bdoi\s*=', bib, re.IGNORECASE) and "note =" not in bib.lower():
            bib = bib.rstrip("}") + f"\n{doi_line}{note_line}}}"
        return bib

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
        f"{venue_line}"
        f"{doi_line}"
        f"{note_line}}}"
    )


# ---------------------------------------------------------------------------
# MCP client
# ---------------------------------------------------------------------------

def filter_topics_with_questions(topics: list[dict]) -> list[dict]:
    """Keep only topics that have at least one open question."""
    return [t for t in topics if t.get("open_questions")]


async def fetch_source_key_concepts(source_slugs: list[str], session) -> list[str]:
    """Call get_source for each slug and return aggregated unique key_concepts in order."""
    concepts: list[str] = []
    seen: set[str] = set()
    for slug in source_slugs:
        result = await session.call_tool("get_source", arguments={"slug": slug})
        if not result.content:
            continue
        try:
            source = json.loads(result.content[0].text)
        except (json.JSONDecodeError, IndexError):
            continue
        for c in (source.get("key_concepts") or []):
            if c not in seen:
                seen.add(c)
                concepts.append(c)
    return concepts


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
                    full_topic = json.loads(get_result.content[0].text)
                    print(f"[MCP]   OK: got full topic for {slug!r}")
                except json.JSONDecodeError as exc:
                    print(f"[MCP] WARNING: invalid JSON from get_topic for slug={slug!r}: {exc}")
                    continue

                source_slugs = full_topic.get("sources") or []
                if source_slugs:
                    print(f"[MCP]   Fetching key_concepts from {len(source_slugs)} source(s)")
                    full_topic["_key_concepts"] = await fetch_source_key_concepts(
                        source_slugs, session
                    )
                else:
                    full_topic["_key_concepts"] = []

                full_topics.append(full_topic)

            return full_topics


async def fetch_topic_by_slug(slug: str, mcp_url: str) -> list[dict]:
    """Fetch a single wiki topic by slug directly from the MCP server.

    Returns a one-element list in the same format as fetch_mcp_topics, or []
    if the slug is not found or returns invalid JSON.
    """
    print(f"[MCP] Connecting to {mcp_url}")
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            print("[MCP] Session initialising...")
            await session.initialize()
            print("[MCP] Session ready")

            print(f"[MCP] Calling get_topic: slug={slug!r}")
            get_result = await session.call_tool("get_topic", arguments={"slug": slug})

            if not get_result.content:
                print(f"[MCP] WARNING: get_topic returned empty content for slug={slug!r}")
                return []

            try:
                full_topic = json.loads(get_result.content[0].text)
            except json.JSONDecodeError as exc:
                print(f"[MCP] WARNING: invalid JSON from get_topic for slug={slug!r}: {exc}")
                return []

            source_slugs = full_topic.get("sources") or []
            if source_slugs:
                print(f"[MCP]   Fetching key_concepts from {len(source_slugs)} source(s)")
                full_topic["_key_concepts"] = await fetch_source_key_concepts(
                    source_slugs, session
                )
            else:
                full_topic["_key_concepts"] = []

            print(f"[MCP] Got topic {slug!r}: {full_topic.get('title')!r}")
            return [full_topic]


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
        try:
            for related in fetch_paper_citations(pid, limit=50):
                rpid = related.get("paperId")
                if rpid and rpid not in seen:
                    seen[rpid] = related
        except Exception as exc:
            print(f"    [S2] Skipping citations for {pid!r}: {exc}")
        print(f"    [S2] Fetching references for {pid!r}")
        try:
            for related in fetch_paper_references(pid, limit=50):
                rpid = related.get("paperId")
                if rpid and rpid not in seen:
                    seen[rpid] = related
        except Exception as exc:
            print(f"    [S2] Skipping references for {pid!r}: {exc}")

    # Sort by citationCount descending, cap at max_papers
    all_papers = sorted(seen.values(), key=lambda p: p.get("citationCount") or 0, reverse=True)
    return all_papers[:max_papers]


_S2_STOP_WORDS = {
    "the", "a", "an", "of", "in", "for", "and", "to", "with",
    "on", "is", "are", "by", "from", "that", "this", "at", "or",
}


def distil_s2_query(topic: dict, client, client_model: str) -> str:
    """Ask the LLM to distil a focused 4-7 word S2 search phrase from topic metadata."""
    title = topic.get("title", "")
    domain = topic.get("domain", "")
    findings = (topic.get("key_findings") or [])[:2]
    concepts = (topic.get("_key_concepts") or [])[:6]
    fallback = " ".join((topic.get("_key_concepts") or [])[:4])

    prompt = (
        "You are helping a researcher find relevant papers on Semantic Scholar. "
        "Given a research topic, return ONE focused academic search phrase of 4-7 words "
        "that would retrieve relevant arts and health research. "
        "Return only the search phrase with no quotes, punctuation, or explanation.\n\n"
        f"Topic title: {title}\n"
        f"Domain: {domain}\n"
        f"Key findings: {'; '.join(findings)}\n"
        f"Key concepts: {', '.join(concepts)}"
    )
    try:
        content, _ = get_response_from_llm(
            prompt=prompt,
            client=client,
            model=client_model,
            system_message="You are a research librarian specialising in arts and health.",
            temperature=0.1,
        )
        query = content.strip().strip('"').strip("'").replace("\n", " ").strip()
        query = query[:120]
        print(f"    [S2] Distilled query: {query!r}")
        return query
    except Exception as exc:
        print(f"    [S2] WARNING: distil_s2_query failed ({exc}), falling back to key_concepts")
        return fallback


def filter_relevant_seeds(
    papers: list[dict],
    topic_title: str,
    key_concepts: list[str],
    min_overlap: int = 2,
    title_only: bool = False,
) -> list[dict]:
    """Keep papers whose title overlaps >= min_overlap meaningful words with the topic.

    title_only=True restricts the word set to the topic title (skipping key_concepts),
    which avoids false positives from generic methodology terms in concepts.
    """
    topic_words: set[str] = set()
    for word in topic_title.lower().split():
        w = re.sub(r"[^a-z]", "", word)
        if w and w not in _S2_STOP_WORDS:
            topic_words.add(w)
    if not title_only:
        for concept in key_concepts:
            for part in re.split(r"[-\s]+", concept.lower()):
                w = re.sub(r"[^a-z]", "", part)
                if w and w not in _S2_STOP_WORDS:
                    topic_words.add(w)

    accepted = []
    for paper in papers:
        title = (paper.get("title") or "").lower()
        title_words = {re.sub(r"[^a-z]", "", w) for w in title.split()}
        title_words.discard("")
        overlap = len(topic_words & title_words)
        status = "ACCEPT" if overlap >= min_overlap else "REJECT"
        print(f"    [S2] {status} (overlap={overlap}): {paper.get('title', '')[:80]!r}")
        if overlap >= min_overlap:
            accepted.append(paper)
    return accepted


def classify_papers(papers: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split papers into (open_access, paywalled) buckets."""
    oa = [p for p in papers if p.get("isOpenAccess")]
    paywalled = [p for p in papers if not p.get("isOpenAccess")]
    return oa, paywalled


def _library_entry(p: dict, *, reason: str, pdf_url: str | None = None) -> list[str]:
    """Format one paper as a library-list Markdown entry."""
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

    entry = [
        f"- **Title:** {title}",
        f"  - Authors: {author_str} ({year})",
        f"  - Reason: {reason}",
    ]
    if pdf_url:
        entry.append(f"  - Direct URL (try in browser): {pdf_url}")
    entry.extend([
        f"  - {link_label}: {library_url}",
        f"  - Suggested filename: `{suggested}`",
        "",
    ])
    return entry


def write_library_list(
    paywalled: list[dict],
    output_path: str,
    blocked_oa: list[dict] | None = None,
) -> None:
    """Write a Markdown shopping list of paywalled and download-blocked papers."""
    lines = [
        "# Papers Requiring Manual Library Download\n",
        "Save downloaded PDFs to the `pdfs/` folder alongside your ideas JSON file.\n",
    ]

    if paywalled:
        lines.append("## Paywalled Papers\n")
        for p in paywalled:
            lines.extend(_library_entry(p, reason="paywalled (isOpenAccess=False)"))

    if blocked_oa:
        lines.append("## Publisher-Blocked Downloads\n")
        lines.append(
            "These papers are open access but the publisher blocked automated download.\n"
            "The direct URL usually works in a browser — save to the `pdfs/` folder.\n"
        )
        for p in blocked_oa:
            pdf_url = (p.get("openAccessPdf") or {}).get("url")
            lines.extend(_library_entry(p, reason="download blocked (403)", pdf_url=pdf_url))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    total = len(paywalled) + len(blocked_oa or [])
    print(f"[Library] Wrote {total} paper(s) to {output_path} "
          f"({len(paywalled)} paywalled, {len(blocked_oa or [])} blocked)")


_LIBRARY_HTML_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:17px;max-width:860px;margin:0 auto;padding:24px 28px 60px;background:#fafafa;color:#1a1a1a}
h1{font-size:24px;margin-bottom:4px}
.meta{color:#666;font-size:14px;margin-bottom:32px}
h2{font-size:20px;border-bottom:2px solid #e0e0e0;padding-bottom:8px;margin-top:36px}
h3{font-size:15px;color:#555;font-weight:500;margin:24px 0 12px;text-transform:uppercase;letter-spacing:.05em}
.badge{display:inline-block;background:#e8f0fe;color:#1a73e8;font-size:12px;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle;font-weight:500}
.badge.blocked{background:#fff3e0;color:#e65100}
.badge.dl{background:#e8f5e9;color:#2e7d32}
.intro{color:#555;font-size:15px;margin-top:-4px}
.paper{border-bottom:1px solid #efefef;padding:18px 0}
.paper:last-child{border-bottom:none}
.paper-title{font-size:17px;font-weight:600;margin-bottom:5px;line-height:1.4}
.paper-year{color:#888;font-weight:400}
.paper-meta{color:#666;font-size:14px;margin-bottom:12px}
.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
a.btn-lib{color:#1a73e8;font-size:14px;text-decoration:none;border:1px solid #1a73e8;padding:5px 14px;border-radius:5px}
a.btn-lib:hover{background:#e8f0fe}
button.btn-copy{font-size:14px;padding:5px 14px;border:1px solid #bbb;border-radius:5px;cursor:pointer;background:#f5f5f5;color:#333}
button.btn-copy:hover{background:#e8e8e8}
button.btn-copy.copied{background:#e8f5e9;border-color:#2e7d32;color:#2e7d32}
.dl-paper{display:flex;align-items:flex-start;gap:14px;padding:14px 0;border-bottom:1px solid #efefef;cursor:pointer}
.dl-paper:last-child{border-bottom:none}
.dl-paper input[type=checkbox]{width:20px;height:20px;flex-shrink:0;margin-top:3px;cursor:pointer;accent-color:#d32f2f}
.dl-paper-text{flex:1}
.dl-paper-title{font-size:16px;font-weight:500;line-height:1.4}
.dl-paper-meta{color:#888;font-size:13px;margin-top:3px}
.dl-paper.selected .dl-paper-title{color:#b71c1c;text-decoration:line-through}
.tab-bar{display:flex;border-bottom:2px solid #e0e0e0;margin-bottom:28px}
.tab-btn{padding:10px 20px;border:none;background:none;cursor:pointer;font-size:15px;color:#555;border-bottom:3px solid transparent;margin-bottom:-2px}
.tab-btn.active{color:#1a73e8;border-bottom-color:#1a73e8;font-weight:600}
.tab-panel{display:none}
.tab-panel.active{display:block}
"""
_LIBRARY_HTML_CSS_LAUNCH = (
    ".idea-row{display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-bottom:1px solid #efefef;cursor:pointer}"
    ".idea-row:last-child{border-bottom:none}"
    ".idea-title{font-size:17px;font-weight:600;line-height:1.4}"
    ".idea-slug{font-size:13px;color:#888;margin-top:3px}"
    ".form-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}"
    ".field{display:flex;flex-direction:column;gap:6px}"
    ".field label{font-size:14px;color:#555;font-weight:500}"
    ".field select,.field input[type=number]{font-size:15px;padding:6px 10px;border:1px solid #ccc;border-radius:5px;min-width:180px}"
    ".field-help{font-weight:400;color:#888}"
    'textarea.launch-cmd{width:100%;font-family:"SFMono-Regular",Consolas,monospace;font-size:13px;color:#ce9178;background:#1e1e1e;border:1px solid #444;border-radius:5px;padding:10px;resize:vertical;box-sizing:border-box}'
)
_LIBRARY_HTML_CSS_BLOCKED = (
    "a.btn-direct{color:#2e7d32;font-size:14px;text-decoration:none;"
    "border:1px solid #2e7d32;padding:5px 14px;border-radius:5px}"
    "a.btn-direct:hover{background:#e8f5e9}"
)
_LIBRARY_HTML_CSS_DL = (
    ".rm-box{margin-top:24px}"
    ".rm-label{display:flex;justify-content:space-between;color:#555;font-size:13px;margin-bottom:6px}"
    ".rm-empty{color:#999;font-size:14px;font-style:italic;padding:8px 0}"
    "textarea.rm-cmd{width:100%;font-family:\"SFMono-Regular\",Consolas,monospace;"
    "font-size:13px;color:#ce9178;background:#1e1e1e;border:1px solid #444;"
    "border-radius:5px;padding:10px;resize:vertical;min-height:56px;box-sizing:border-box}"
)


def write_library_html(
    paywalled: list[dict],
    output_path: str,
    *,
    blocked_oa: list[dict] | None = None,
    downloaded: list[tuple[dict, str]] | None = None,
    pdfs_dir: "Path | None" = None,
    ideas: list[dict] | None = None,
    ideas_path: str | None = None,
    ollama_base_url: str | None = None,
    supabase_url: str | None = None,
    supabase_anon_key: str | None = None,
) -> None:
    """Write a standalone interactive HTML library download page."""
    import json as _json
    from datetime import date as _date

    def _esc(s: str) -> str:
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;"))

    def _authors_str(p: dict, n: int = 3) -> str:
        authors = p.get("authors") or []
        names = [a.get("name", "") for a in authors[:n]]
        result = ", ".join(names)
        if len(authors) > n:
            result += " et al."
        return result

    def _suggested(p: dict) -> str:
        authors = p.get("authors") or []
        first = ""
        if authors:
            parts = (authors[0].get("name") or "").replace(",", " ").split()
            first = parts[0] if parts else "Unknown"
        year = p.get("year") or "0000"
        title = p.get("title") or ""
        safe = re.sub(r"[^\w\s]", "", title)[:40].strip().replace(" ", "_")
        return f"{first}_{year}_{safe}.pdf"

    def _fetch_entry(p: dict, *, is_blocked: bool = False) -> str:
        title = _esc(p.get("title") or "Unknown Title")
        year = p.get("year") or ""
        authors = _esc(_authors_str(p))
        venue = _esc(p.get("venue") or "")
        doi = (p.get("externalIds") or {}).get("DOI")
        lib_url = _esc(utas_library_url(doi=doi, title=(p.get("title") or "") if not doi else None))
        fname = _esc(_suggested(p))
        meta = authors + (" · " + venue if venue else "")
        direct = ""
        if is_blocked:
            pdf_url = ((p.get("openAccessPdf") or {}).get("url") or "")
            if pdf_url:
                direct = f'<a class="btn-direct" href="{_esc(pdf_url)}" target="_blank">↗ Try direct URL</a>\n    '
        return (
            f'<div class="paper">'
            f'<div class="paper-title">{title} <span class="paper-year">({year})</span></div>'
            f'<div class="paper-meta">{meta}</div>'
            f'<div class="actions">'
            f'<a class="btn-lib" href="{lib_url}" target="_blank">🔗 Open in Library</a>'
            f'{direct}'
            f'<button class="btn-copy" data-filename="{fname}" onclick="copyFilename(this)">📋 {fname}</button>'
            f'</div></div>'
        )

    def _dl_entry(p: dict, idx: int) -> str:
        title = _esc(p.get("title") or "Unknown Title")
        year = p.get("year") or ""
        authors = _esc(_authors_str(p))
        return (
            f'<div class="dl-paper" onclick="togglePaper(this)">'
            f'<input type="checkbox" id="dl-{idx}">'
            f'<div class="dl-paper-text">'
            f'<div class="dl-paper-title">{title} <span class="paper-year">({year})</span></div>'
            f'<div class="dl-paper-meta">{authors}</div>'
            f'</div></div>'
        )

    def _idea_row(idea: dict, idx: int) -> str:
        title = _esc(idea.get("Title") or "Untitled")
        name = _esc(idea.get("Name") or "")
        checked = " checked" if idx == 0 else ""
        return (
            f'<label class="idea-row">'
            f'<input type="radio" name="idea" value="{idx}"{checked} onchange="updateCmd()">'
            f'<div class="idea-text">'
            f'<div class="idea-title">{title}</div>'
            f'<div class="idea-slug">{name} &middot; idx {idx}</div>'
            f'</div></label>'
        )

    n_pw = len(paywalled)
    n_bl = len(blocked_oa or [])
    n_dl = len(downloaded or [])
    today = _date.today().isoformat()
    stem = Path(output_path).stem

    extra_css = _LIBRARY_HTML_CSS_LAUNCH   # always needed — Tab 1 always active
    safe_ollama = (ollama_base_url or "http://localhost:11434").replace("\\", "/")
    js_constants = f'const OLLAMA_BASE_URL = "{_esc(safe_ollama)}";\n'
    tab1_panel = ""
    tab3_btn = ""
    tab3_panel = ""
    localstorage_lastpath = ""
    tab_restore_js = """  var lastTab = _lsGet('activeTab') || 'tab2';
  var panelEl = document.getElementById(lastTab + '-panel');
  var btnEl = document.getElementById(lastTab + '-btn');
  if (panelEl && btnEl) {
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
    panelEl.classList.add('active');
    btnEl.classList.add('active');
  }"""
    tab3_init_js = ""
    tab3_update_js = ""
    tab1_update_js = ""
    tab1_doi_lookup_js = ""
    if ideas:
        idea_items = [
            {"idx": i, "name": idea.get("Name", ""), "title": idea.get("Title", "")}
            for i, idea in enumerate(ideas)
        ]
        safe_path = (ideas_path or "").replace("\\", "/")
        js_constants += (
            f'const LOAD_IDEAS_PATH = "{_esc(safe_path)}";\n'
            f'const IDEA_LIST = {_json.dumps(idea_items)};'
        )
        idea_rows = "\n".join(_idea_row(idea, i) for i, idea in enumerate(ideas))
        tab3_btn = (
            '<button class="tab-btn" id="tab3-btn"'
            " onclick=\"showTab('tab3', this)\">&#x1F680; Launch writer</button>"
        )
        tab3_panel = f"""<div id="tab3-panel" class="tab-panel">
<h2>&#x1F680; Launch Proposal Writer</h2>
<p class="intro">Select an idea and configure the run, then copy the command to your terminal.</p>
<div id="idea-list">
{idea_rows}
</div>
<div class="form-row" style="margin-top:20px">
  <div class="field">
    <label>Writeup type</label>
    <select id="writeup-type" onchange="updateCmd()">
      <option value="icbinb" selected>icbinb &mdash; 4-page proposal</option>
      <option value="review">review &mdash; APA 7 lit review</option>
      <option value="normal">normal &mdash; 8-page ICML</option>
    </select>
  </div>
  <div class="field">
    <label>Model <span class="field-help">Sets --model_writeup and --model_citation</span></label>
    <select id="model-select" onchange="updateCmd()"></select>
  </div>
  <div class="field">
    <label>Cite rounds <span class="field-help">(optional)</span></label>
    <input type="number" id="cite-rounds" value="10" min="1" oninput="updateCmd()">
  </div>
</div>
<div class="field" style="margin-top:4px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <label>Generated command</label>
    <button class="btn-copy" onclick="copyCmd(this)">&#x1F4CB; Copy command</button>
  </div>
  <textarea id="launch-cmd" class="launch-cmd" readonly rows="7"></textarea>
</div>
</div>"""
        localstorage_lastpath = "_lsSet('lastIdeasPath', LOAD_IDEAS_PATH);"
        tab3_init_js = """  var lastModel = _lsGet('lastModel');
  fetch(OLLAMA_BASE_URL + '/api/tags')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var sel = document.getElementById('model-select');
      (data.models || []).forEach(function(m) {
        var opt = document.createElement('option');
        opt.value = 'ollama/' + m.name; opt.textContent = 'ollama/' + m.name;
        sel.appendChild(opt);
      });
      if (lastModel && sel.querySelector('option[value="' + lastModel + '"]')) sel.value = lastModel;
      updateCmd();
    })
    .catch(function() {
      var sel = document.getElementById('model-select');
      var inp = document.createElement('input');
      inp.type = 'text'; inp.id = 'model-select';
      inp.value = _lsGet('lastModel') || 'ollama/qwen2.5:14b';
      inp.addEventListener('input', updateCmd);
      sel.parentNode.replaceChild(inp, sel);
      updateCmd();
    });"""
        tab3_update_js = r"""
function updateCmd() {
  var radios = document.getElementsByName('idea');
  var idx = '0';
  for (var i = 0; i < radios.length; i++) { if (radios[i].checked) { idx = radios[i].value; break; } }
  var writeupType = document.getElementById('writeup-type').value;
  var modelEl = document.getElementById('model-select');
  var model = modelEl.value || 'ollama/qwen2.5:14b';
  var citeRounds = document.getElementById('cite-rounds').value || '10';
  var path = _lsGet('lastIdeasPath') || LOAD_IDEAS_PATH;
  document.getElementById('launch-cmd').value =
    'python launch_proposal_writer.py \\\n' +
    '  --load_ideas ' + path + ' \\\n' +
    '  --idea_idx ' + idx + ' \\\n' +
    '  --writeup-type ' + writeupType + ' \\\n' +
    '  --model_writeup ' + model + ' \\\n' +
    '  --model_citation ' + model + ' \\\n' +
    '  --num_cite_rounds ' + citeRounds;
  _lsSet('lastModel', model);
}
function copyCmd(btn) {
  navigator.clipboard.writeText(document.getElementById('launch-cmd').value).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✓ Copied'; btn.classList.add('copied');
    setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
  });
}"""

    if supabase_url and supabase_anon_key:
        safe_sb_url = supabase_url.replace("\\", "/")
        js_constants += (
            f'\nconst SUPABASE_URL = "{_esc(safe_sb_url)}";\n'
            f'const SUPABASE_ANON_KEY = "{_esc(supabase_anon_key)}";'
        )

    tab1_model_fetch_js = ""
    tab1_tag_fetch_js = ""
    if supabase_url and supabase_anon_key:
        tab1_tag_fetch_js = f"""  fetch(SUPABASE_URL + '/rest/v1/tags?select=slug&order=slug', {{
    headers: {{
      'apikey': SUPABASE_ANON_KEY,
      'Authorization': 'Bearer ' + SUPABASE_ANON_KEY,
      'Content-Profile': 'a1c-wiki-db'
    }}
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(rows) {{
    var dl = document.getElementById('gen-tag-list');
    rows.forEach(function(row) {{
      var opt = document.createElement('option');
      opt.value = row.slug;
      dl.appendChild(opt);
    }});
  }})
  .catch(function() {{
    var inp = document.getElementById('gen-tag');
    inp.placeholder = 'tags unavailable';
    inp.disabled = true;
  }});"""
        tab1_doi_lookup_js = """
function lookupSeedDoi() {
  var doi = (document.getElementById('gen-seed-doi') || {}).value || '';
  if (!doi) return;
  fetch(SUPABASE_URL + '/rest/v1/sources?doi=eq.' + encodeURIComponent(doi)
        + '&select=key_concepts,tags', {
    headers: {
      'apikey': SUPABASE_ANON_KEY,
      'Authorization': 'Bearer ' + SUPABASE_ANON_KEY,
      'Content-Profile': 'a1c-wiki-db'
    }
  })
  .then(function(r) { return r.json(); })
  .then(function(rows) {
    if (!rows || !rows.length) return;
    var src = rows[0];
    var queryEl = document.getElementById('gen-query');
    var concepts = (src.key_concepts || []).slice(0, 8).join(' ');
    if (concepts && queryEl && !queryEl.value) {
      queryEl.value = concepts;
      updateGenCmd();
    }
    var firstTag = (src.tags || [])[0];
    var tagEl = document.getElementById('gen-tag');
    if (firstTag && tagEl && !tagEl.value) tagEl.value = firstTag;
  })
  .catch(function() {});
}"""

    tag_datalist_html = (
        '<input type="text" id="gen-tag" list="gen-tag-list"'
        ' placeholder="type to search tags…" oninput="updateGenCmd()">\n'
        '<datalist id="gen-tag-list"></datalist>'
        if (supabase_url and supabase_anon_key) else
        '<input type="text" id="gen-tag" placeholder="(Supabase not configured)"'
        ' disabled>'
    )

    seed_doi_onblur = ' onblur="lookupSeedDoi()"' if (supabase_url and supabase_anon_key) else ''

    tab1_section1 = f"""<h3>&#x1F50D; What to search for</h3>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Query text</label>
    <input type="text" id="gen-query" placeholder="music therapy dementia wellbeing"
           oninput="updateGenCmd()" style="min-width:260px">
  </div>
  <div class="field">
    <label>Domain</label>
    <select id="gen-domain" onchange="updateGenCmd()">
      <option value="">&mdash; any &mdash;</option>
      <option value="intervention">intervention</option>
      <option value="theory">theory</option>
      <option value="method">method</option>
    </select>
  </div>
  <div class="field">
    <label>Confidence</label>
    <select id="gen-confidence" onchange="updateGenCmd()">
      <option value="">&mdash; any &mdash;</option>
      <option value="low">low</option>
      <option value="medium">medium</option>
      <option value="high">high</option>
    </select>
  </div>
</div>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Topic slug (--topic)</label>
    <input type="text" id="gen-topic" placeholder="therapeutic-clowning"
           oninput="updateGenCmd()" style="min-width:260px"
           title="Wiki topic slug — fetches the topic directly and seeds from its linked DOIs">
  </div>
</div>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Tag <span class="field-help">(discovery aid &mdash; type to search)</span></label>
    {tag_datalist_html}
  </div>
  <div class="field" style="flex:2">
    <label>Seed DOI <span class="field-help">(optional)</span></label>
    <input type="text" id="gen-seed-doi" placeholder="10.1002/14651858.CD011022.pub2"
           oninput="updateGenCmd()"{seed_doi_onblur}>
  </div>
</div>"""

    tab1_section2 = """<h3>&#x2699;&#xFE0F; Run settings</h3>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Model <span class="field-help">sets --model</span></label>
    <select id="model-select-gen" onchange="updateGenCmd()"></select>
  </div>
  <div class="field">
    <label>Limit</label>
    <input type="number" id="gen-limit" value="10" min="1" oninput="updateGenCmd()">
  </div>
  <div class="field">
    <label>Max questions</label>
    <input type="number" id="gen-max-q" value="3" min="1" oninput="updateGenCmd()">
  </div>
</div>
<div class="form-row">
  <div class="field">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input type="checkbox" id="gen-recursive" checked onchange="updateGenCmd()">
      --recursive
    </label>
  </div>
  <div class="field">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input type="checkbox" id="gen-fetch-fulltext" onchange="updateGenCmd()">
      --fetch-fulltext
    </label>
  </div>
</div>
<div class="form-row">
  <div class="field" style="flex:1">
    <label>Seed PDF path <span class="field-help">(optional &mdash; full path)</span></label>
    <input type="text" id="gen-seed-pdf"
           placeholder="/home/…/ai_scientist/ideas/pdfs/Smith2023.pdf"
           oninput="updateGenCmd()" style="min-width:340px">
  </div>
</div>"""

    tab1_section3 = """<h3>&#x1F4C1; Output</h3>
<div class="form-row">
  <div class="field" style="flex:1">
    <label>Output path</label>
    <input type="text" id="gen-output"
           value="ai_scientist/ideas/mcp_generated.json"
           oninput="updateGenCmd(); _lsSet('lastIdeasPath', this.value);"
           style="min-width:340px">
  </div>
</div>"""

    tab1_model_fetch_js = """  var lastModelGen = _lsGet('lastModel');
  fetch(OLLAMA_BASE_URL + '/api/tags')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var sel = document.getElementById('model-select-gen');
      (data.models || []).forEach(function(m) {
        var opt = document.createElement('option');
        opt.value = 'ollama/' + m.name; opt.textContent = 'ollama/' + m.name;
        sel.appendChild(opt);
      });
      if (lastModelGen && sel.querySelector('option[value="' + lastModelGen + '"]')) {
        sel.value = lastModelGen;
      }
      updateGenCmd();
    })
    .catch(function() {
      var sel = document.getElementById('model-select-gen');
      var inp = document.createElement('input');
      inp.type = 'text'; inp.id = 'model-select-gen';
      inp.value = _lsGet('lastModel') || 'ollama/qwen2.5:14b';
      inp.addEventListener('input', updateGenCmd);
      sel.parentNode.replaceChild(inp, sel);
      updateGenCmd();
    });"""

    tab1_cmd_html = """<div class="field" style="margin-top:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <label>Generated command</label>
    <button class="btn-copy" onclick="copyGenCmd(this)">&#x1F4CB; Copy command</button>
  </div>
  <textarea id="generate-cmd" class="launch-cmd" readonly rows="8"></textarea>
</div>"""

    tab1_panel = f"""<h2>&#9881;&#65039; Generate Ideas</h2>
<p class="intro">Configure the run, then copy the command to your terminal.</p>
{tab1_section1}
{tab1_section2}
{tab1_section3}
{tab1_cmd_html}"""

    tab1_update_js = r"""
function updateGenCmd() {
  var query = (document.getElementById('gen-query') || {}).value || '';
  var topic = (document.getElementById('gen-topic') || {}).value || '';
  var domain = (document.getElementById('gen-domain') || {}).value || '';
  var confidence = (document.getElementById('gen-confidence') || {}).value || '';
  var modelEl = document.getElementById('model-select-gen');
  var model = modelEl ? (modelEl.value || 'ollama/qwen2.5:14b') : 'ollama/qwen2.5:14b';
  var limit = (document.getElementById('gen-limit') || {}).value || '10';
  var maxQ = (document.getElementById('gen-max-q') || {}).value || '3';
  var recursive = document.getElementById('gen-recursive') && document.getElementById('gen-recursive').checked;
  var fetchFull = document.getElementById('gen-fetch-fulltext') && document.getElementById('gen-fetch-fulltext').checked;
  var seedDoi = (document.getElementById('gen-seed-doi') || {}).value || '';
  var seedPdf = (document.getElementById('gen-seed-pdf') || {}).value || '';
  var output = (document.getElementById('gen-output') || {}).value || 'ai_scientist/ideas/mcp_generated.json';

  var cmd = 'python generate_ideas_from_mcp.py';
  if (!query && !topic && !seedDoi && !seedPdf) {
    cmd = '# WARNING: provide --query, --topic, --seed-doi, or --seed-pdf\n' + cmd;
  }
  if (query) cmd += ' \\\n  --query "' + query.replace(/"/g, '\\"') + '"';
  if (topic) cmd += ' \\\n  --topic ' + topic;
  if (domain) cmd += ' \\\n  --domain ' + domain;
  if (confidence) cmd += ' \\\n  --confidence ' + confidence;
  cmd += ' \\\n  --model ' + model;
  cmd += ' \\\n  --limit ' + limit;
  cmd += ' \\\n  --max-questions ' + maxQ;
  if (recursive) cmd += ' \\\n  --recursive';
  if (fetchFull) cmd += ' \\\n  --fetch-fulltext';
  if (seedDoi) cmd += ' \\\n  --seed-doi ' + seedDoi;
  if (seedPdf) cmd += ' \\\n  --seed-pdf ' + seedPdf;
  cmd += ' \\\n  --output ' + output;

  var ta = document.getElementById('generate-cmd');
  if (ta) ta.value = cmd;
  _lsSet('lastModel', model);
}
function copyGenCmd(btn) {
  var ta = document.getElementById('generate-cmd');
  if (!ta) return;
  navigator.clipboard.writeText(ta.value).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✓ Copied'; btn.classList.add('copied');
    setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
  });
}"""

    if blocked_oa:
        extra_css += _LIBRARY_HTML_CSS_BLOCKED
    if downloaded:
        extra_css += _LIBRARY_HTML_CSS_DL

    fetch_html = ""
    if paywalled:
        entries = "\n".join(_fetch_entry(p) for p in paywalled)
        fetch_html += f'<h3>Paywalled <span class="badge">{n_pw} papers</span></h3>\n{entries}\n'
    if blocked_oa:
        entries = "\n".join(_fetch_entry(p, is_blocked=True) for p in blocked_oa)
        fetch_html += (
            f'<h3>Publisher-Blocked (open access but 403)'
            f' <span class="badge blocked">{n_bl} papers</span></h3>\n{entries}\n'
        )

    dl_html = ""
    if downloaded:
        prefix = (str(pdfs_dir) + "/") if pdfs_dir else "pdfs/"
        rm_paths = _json.dumps([prefix + fname for _, fname in downloaded])
        items = "\n".join(_dl_entry(p, i) for i, (p, _) in enumerate(downloaded))
        dl_html = f"""
<h2>&#x2705; Auto-Downloaded Papers <span class="badge dl">{n_dl} papers</span></h2>
<p class="intro">Check papers to remove from the PDF pool. The shell command updates below.</p>
<div id="dl-list">
{items}
</div>
<div class="rm-box">
  <div class="rm-label">
    <span>Shell command &mdash; copy and paste to remove selected papers from the pool</span>
    <span id="sel-count">0 selected</span>
  </div>
  <div id="rm-empty" class="rm-empty">Select papers above to generate the rm command.</div>
  <textarea id="rm-cmd" class="rm-cmd" style="display:none" readonly></textarea>
</div>
<script>
const DL_FILES = {rm_paths};
function togglePaper(el) {{
  const cb = el.querySelector('input[type=checkbox]');
  cb.checked = !cb.checked;
  el.classList.toggle('selected', cb.checked);
  updateRm();
}}
function updateRm() {{
  const sel = [];
  document.querySelectorAll('.dl-paper').forEach(function(el, i) {{
    if (el.querySelector('input').checked) sel.push(DL_FILES[i]);
  }});
  document.getElementById('sel-count').textContent = sel.length + ' selected';
  const ta = document.getElementById('rm-cmd');
  const empty = document.getElementById('rm-empty');
  if (sel.length === 0) {{
    ta.style.display = 'none'; empty.style.display = 'block';
  }} else {{
    empty.style.display = 'none'; ta.style.display = 'block';
    ta.value = 'rm ' + sel.join(' ');
  }}
}}
</script>"""

    tab2_content = (
        f'<h2>&#x1F4E5; Papers to Fetch Manually</h2>\n'
        f'{fetch_html}'
        f'{dl_html}'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Library downloads &mdash; {stem}</title>
<style>{_LIBRARY_HTML_CSS}{extra_css}</style>
</head>
<body>
<h1>&#x1F4DA; Library download list</h1>
<div class="meta">Generated {today} &middot; {stem} &middot; {n_pw + n_bl} to fetch, {n_dl} auto-downloaded</div>
<div class="tab-bar">
  <button class="tab-btn" id="tab1-btn" onclick="showTab('tab1', this)">&#9881;&#65039; Generate ideas</button>
  <button class="tab-btn active" id="tab2-btn" onclick="showTab('tab2', this)">&#x1F4E5; Papers</button>
  {tab3_btn}
</div>
<div id="tab1-panel" class="tab-panel">
{tab1_panel}
</div>
<div id="tab2-panel" class="tab-panel active">
{tab2_content}
</div>
{tab3_panel}
<script>
var _lsGet = function(k) {{ try {{ return window.localStorage.getItem(k); }} catch(e) {{ return null; }} }};
var _lsSet = function(k, v) {{ try {{ window.localStorage.setItem(k, v); }} catch(e) {{}} }};
{js_constants}
function showTab(tab, btn) {{
  document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
  document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  document.getElementById(tab + '-panel').classList.add('active');
  btn.classList.add('active');
  _lsSet('activeTab', tab);
}}
document.addEventListener('DOMContentLoaded', function() {{
  {localstorage_lastpath}
{tab_restore_js}
{tab1_tag_fetch_js}
{tab1_model_fetch_js}
{tab3_init_js}
  updateGenCmd();
}});
function copyFilename(btn) {{
  navigator.clipboard.writeText(btn.dataset.filename).then(function() {{
    var orig = btn.textContent;
    btn.textContent = '&#x2713; Copied';
    btn.classList.add('copied');
    setTimeout(function() {{ btn.textContent = orig; btn.classList.remove('copied'); }}, 2000);
  }});
}}
{tab3_update_js}
{tab1_update_js}
{tab1_doi_lookup_js}
</script>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    print(
        f"[Library] Wrote interactive HTML to {output_path} "
        f"({n_pw} paywalled, {n_bl} blocked, {n_dl} downloaded)"
    )


def attach_private_keys(
    idea: dict,
    topic: dict,
    s2_papers: list[dict],
    paywalled: list[dict] | None = None,
    oa_fulltext: dict | None = None,
    blocked_oa: list[dict] | None = None,
    downloaded: list[tuple[dict, str]] | None = None,
) -> dict:
    """Attach private metadata keys to an idea dict for downstream use."""
    result = dict(idea)
    result["_mcp_topic"] = topic
    result["_s2_bibtex"] = [bibtex_from_s2_paper(p) for p in (s2_papers or [])]
    result["_s2_papers"] = s2_papers or []
    result["_paywalled"] = paywalled or []
    result["_blocked_oa"] = blocked_oa or []
    result["_oa_fulltext"] = oa_fulltext or {}
    result["_downloaded"] = downloaded or []
    return result


# ---------------------------------------------------------------------------
# Seed PDF section extraction
# ---------------------------------------------------------------------------

from ai_scientist.tools.pdf_reader import extract_sections


def extract_seed_pdf_sections(pdf_path: str, paper: dict) -> dict[str, dict]:
    """
    Extract named sections from a local seed PDF and return {paperId: {section: text}}.
    Always runs regardless of --fetch-fulltext — the file is already local.
    Returns {} if nothing is extracted or on any error.
    """
    pid = paper.get("paperId") or "seed"
    authors = paper.get("authors") or []
    first = (authors[0].get("name") or "").split()[-1] if authors else "Unknown"
    year = str(paper.get("year") or "0000")
    ck = f"{first}{year}"
    sections = extract_sections(pdf_path, citation_key=ck)
    if sections:
        print(f"[SEED-PDF] Extracted {list(sections.keys())} from local file "
              f"(citation_key={ck!r})")
        return {pid: sections}
    return {}


# ---------------------------------------------------------------------------
# DB DOI seeding
# ---------------------------------------------------------------------------

def fetch_db_dois_for_topics(topics: list[dict]) -> list[dict]:
    """Query the wiki pgvector DB for source DOIs linked to each topic slug."""
    import psycopg2
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)

    host = os.environ.get("POSTGRES_HOST", "192.168.1.20")
    port = int(os.environ.get("POSTGRES_PORT", "5433"))
    dbname = os.environ.get("POSTGRES_DB", "postgres")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")

    if not password:
        print("[DB-SEEDS] WARNING: POSTGRES_PASSWORD not set — skipping DB DOI seeding")
        return []

    slug_set = {t["slug"] for t in topics if t.get("slug")}
    if not slug_set:
        return []

    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname, user=user, password=password
        )
    except Exception as exc:
        print(f"[DB-SEEDS] WARNING: cannot connect to DB ({exc}) — skipping")
        return []

    papers: list[dict] = []
    try:
        with conn.cursor() as cur:
            for slug in sorted(slug_set):
                cur.execute(
                    'SELECT s.doi FROM "a1c-wiki-db".topic_sources ts '
                    'JOIN "a1c-wiki-db".sources s ON ts.source_slug = s.slug '
                    'WHERE ts.topic_slug = %s AND s.doi IS NOT NULL AND s.doi != %s',
                    (slug, ''),
                )
                for (doi,) in cur.fetchall():
                    paper = fetch_paper_by_doi(doi)
                    if paper and paper.get("paperId"):
                        papers.append(paper)
                        print(f"[DB-SEEDS]  DOI {doi!r} → {paper.get('title')!r}")
    finally:
        conn.close()

    seen: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        pid = p.get("paperId")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
    print(f"[DB-SEEDS] {len(unique)} unique paper(s) fetched from wiki DB DOIs")
    return unique


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add all CLI arguments to parser and return it."""
    parser.add_argument("--query", default=None,
                        help="Semantic search query, e.g. 'elder clowning wellbeing'. "
                             "Optional when --seed-doi or --seed-pdf is provided.")
    parser.add_argument(
        "--topic",
        default=None,
        metavar="SLUG",
        help="Fetch a specific wiki topic by slug and seed from its linked DOIs. "
             "Can be combined with --query; topics from both are merged.",
    )
    parser.add_argument("--seed-doi", default=None, dest="seed_doi",
                        help="DOI to seed S2 traversal from (e.g. '10.1002/14651858.CD011022.pub2')")
    parser.add_argument("--seed-pdf", default=None, dest="seed_pdf",
                        help="Path to a local PDF; DOI is extracted and used as seed")
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
                        help="Path to write a Markdown paper shopping list (paywalled + blocked)")
    parser.add_argument("--no-db-seeds", action="store_true", default=False,
                        help="Skip automatic DOI seeding from the wiki pgvector DB.")
    return parser


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate AI Scientist ideas from the a1c-knowledge MCP server"
    )
    build_arg_parser(parser)
    return parser.parse_args(args)


async def _main(args: argparse.Namespace) -> None:
    # Validate: need at least one of --query, --seed-doi, --seed-pdf
    if not args.query and not args.seed_doi and not args.seed_pdf and not args.topic:
        print("ERROR: provide at least one of --query, --topic, --seed-doi, or --seed-pdf")
        return

    # Resolve DOI seed papers early (before MCP, so they can be unioned)
    doi_seed_papers: list[dict] = []
    seed_pdf_fulltext: dict[str, dict] = {}

    if args.seed_doi:
        print(f"[SEED-DOI] Fetching S2 paper for DOI={args.seed_doi!r}")
        paper = fetch_paper_by_doi(args.seed_doi)
        if paper:
            doi_seed_papers.append(paper)
            print(f"[SEED-DOI] Found: {paper.get('title')!r}")
        else:
            print(f"[SEED-DOI] WARNING: DOI not found in S2 — {args.seed_doi!r}")

    if args.seed_pdf:
        print(f"[SEED-PDF] Extracting DOI from {args.seed_pdf!r}")
        from ai_scientist.tools.pdf_reader import extract_doi_from_pdf
        doi = extract_doi_from_pdf(args.seed_pdf)
        if doi:
            print(f"[SEED-PDF] Found DOI={doi!r}, fetching from S2...")
            paper = fetch_paper_by_doi(doi)
            if paper:
                doi_seed_papers.append(paper)
                print(f"[SEED-PDF] Found: {paper.get('title')!r}")
                seed_pdf_fulltext.update(extract_seed_pdf_sections(args.seed_pdf, paper))
            else:
                print(f"[SEED-PDF] WARNING: DOI {doi!r} not found in S2")
        else:
            print(f"[SEED-PDF] WARNING: no DOI found in {args.seed_pdf!r}")

    print(f"\n[STAGE 1/4] MCP topic fetch")
    topics: list[dict] = []

    if args.topic:
        print(f"  --topic={args.topic!r} (direct slug lookup)")
        slug_topics = await fetch_topic_by_slug(args.topic, args.mcp_url)
        topics.extend(slug_topics)
        print(f"[STAGE 1/4] --topic: {len(slug_topics)} topic(s) fetched")

    if args.query:
        print(f"  --query={args.query!r} confidence={args.confidence} "
              f"domain={args.domain} limit={args.limit}")
        query_topics = await fetch_mcp_topics(
            args.query, args.domain, args.confidence, args.limit, args.mcp_url
        )
        # Merge, deduplicating by slug (--topic takes precedence if same slug)
        existing_slugs = {t["slug"] for t in topics}
        new_from_query = [t for t in query_topics if t["slug"] not in existing_slugs]
        topics.extend(new_from_query)
        print(f"[STAGE 1/4] --query: {len(new_from_query)} additional topic(s)")

    if not args.topic and not args.query:
        # No MCP source: synthesise topic from seed paper if available
        if doi_seed_papers:
            seed = doi_seed_papers[0]
            synthetic_topic = {
                "slug": "_seed",
                "title": seed.get("title", "Seeded Paper"),
                "domain": "intervention",
                "confidence": "medium",
                "tags": [],
                "key_findings": [(seed.get("abstract") or "")[:500]],
                "open_questions": [
                    f"What are the implications of '{seed.get('title', 'this paper')}' "
                    f"for arts and health research?"
                ],
                "sources": [],
                "_key_concepts": [],
            }
            topics = [synthetic_topic]
            print(f"[STAGE 1/4] No --query/--topic; synthesised topic from seed paper: "
                  f"{seed.get('title')!r}")

    print(f"[STAGE 1/4] Done — {len(topics)} topic(s) total")

    if not topics:
        print("No topics found. Try --topic <slug>, --query <text>, or --seed-doi <doi>.")
        return

    # Augment seed pool with DOIs from the wiki DB for each fetched topic
    if topics and not args.no_db_seeds and (args.query or args.topic):
        db_papers = fetch_db_dois_for_topics(topics)
        existing_pids = {p.get("paperId") for p in doi_seed_papers}
        new_from_db = [p for p in db_papers if p.get("paperId") not in existing_pids]
        doi_seed_papers.extend(new_from_db)
        if new_from_db:
            print(f"[STAGE 1/4] Added {len(new_from_db)} DB-seeded paper(s); "
                  f"doi_seed_papers total: {len(doi_seed_papers)}")

    print(f"\n[STAGE 2/4] Novelty check via Semantic Scholar")
    if args.no_novelty_check:
        print("  Skipping (--no-novelty-check set)")

    client, client_model = create_client(args.model)
    ideas: list[dict] = []
    for topic in topics:
        questions = (topic.get("open_questions") or [])[:args.max_questions]
        print(f"\n  Topic: {topic['title']!r} — {len(questions)} question(s) to process")
        for qi, question in enumerate(questions, 1):
            print(f"  [{qi}/{len(questions)}] {question[:100]}")

            s2_papers: list[dict] = []
            # Pre-seed with locally extracted sections from --seed-pdf (always included)
            oa_fulltext: dict[str, dict] = dict(seed_pdf_fulltext)
            if not args.no_novelty_check:
                key_concepts = topic.get("_key_concepts") or []
                distilled_query = distil_s2_query(topic, client, client_model)
                distilled_papers = search_for_papers(distilled_query, result_limit=args.s2_papers) or []
                # Multi-query union: also search by raw topic title for recall
                title_query = topic.get("title", "")
                if title_query:
                    title_papers = search_for_papers(title_query, result_limit=args.s2_papers) or []
                else:
                    title_papers = []
                seen_pids = {p.get("paperId") for p in distilled_papers}
                text_papers = distilled_papers + [p for p in title_papers if p.get("paperId") not in seen_pids]
                print(f"    [S2] {len(text_papers)} unique paper(s) from distilled + title queries")
                # Union text-search results with DOI seed papers
                seed_papers = doi_seed_papers + [
                    p for p in text_papers
                    if p.get("paperId") not in {sp.get("paperId") for sp in doi_seed_papers}
                ]
                print(f"    [S2] {len(seed_papers)} seed paper(s) found "
                      f"({len(doi_seed_papers)} from DOI, {len(text_papers)} from search)")

                if args.recursive and seed_papers:
                    print(f"    [S2] Recursive expansion (cap={args.max_papers})...")
                    filtered = filter_relevant_seeds(
                        seed_papers, topic.get("title", ""), key_concepts, title_only=True
                    )
                    if not filtered:
                        print(f"    [S2] WARNING: relevance gate filtered all seeds — falling back to unfiltered list")
                        filtered = seed_papers
                    candidates = expand_papers_recursively(filtered, max_papers=9999)
                    post_filtered = filter_relevant_seeds(
                        candidates, topic.get("title", ""), key_concepts, title_only=True
                    )
                    if not post_filtered:
                        print(f"    [S2] WARNING: post-expansion relevance gate filtered all — using pre-expansion seeds")
                        post_filtered = filtered
                    s2_papers = post_filtered[:args.max_papers]
                    print(f"    [S2] {len(s2_papers)} paper(s) after expansion + relevance filtering")
                else:
                    s2_papers = seed_papers

            oa_papers, paywalled_papers = classify_papers(s2_papers)

            blocked_oa_papers: list[dict] = []
            downloaded_papers: list[tuple[dict, str]] = []
            if args.fetch_fulltext and oa_papers:
                oa_with_pdf = [p for p in oa_papers if (p.get("openAccessPdf") or {}).get("url")]
                print(f"    [PDF] {len(oa_with_pdf)} of {len(oa_papers)} OA paper(s) have PDF URLs"
                      f" ({len(s2_papers) - len(oa_papers)} paywalled); fetching full text...")
                pdfs_dir = Path(args.output).parent / f"{Path(args.output).stem}_pdfs"
                pdfs_dir.mkdir(exist_ok=True)
                for p in oa_with_pdf:
                    oa_url = (p.get("openAccessPdf") or {}).get("url")
                    authors = p.get("authors") or []
                    first = (authors[0].get("name") or "").split()[-1] if authors else "Unknown"
                    year = str(p.get("year") or "0000")
                    bib_key = re.sub(r"[^a-z0-9]", "", f"{first.lower()}{year}")
                    pdf_dest = pdfs_dir / f"{bib_key}.pdf"
                    # Download once; save to pdfs/ then extract sections from local copy
                    if not pdf_dest.exists():
                        try:
                            import requests as _req
                            r = _req.get(oa_url, timeout=30)
                            r.raise_for_status()
                            pdf_dest.write_bytes(r.content)
                        except Exception as exc:
                            print(f"      [PDF] {bib_key}: download failed ({exc})")
                            blocked_oa_papers.append(p)
                            continue
                    downloaded_papers.append((p, pdf_dest.name))
                    sections = extract_sections(str(pdf_dest), citation_key=bib_key)
                    if sections:
                        oa_fulltext[bib_key] = sections
                        print(f"      [PDF] {bib_key}: {list(sections.keys())} → saved {pdf_dest.name}")

            print(f"\n[STAGE 3/4] LLM idea translation (model={args.model})")
            idea = translate_to_idea(topic, question, s2_papers, args.model)
            if idea is None:
                print("    WARNING: LLM returned invalid JSON — skipping this question")
                continue

            ideas.append(attach_private_keys(idea, topic, s2_papers, paywalled_papers, oa_fulltext,
                                              blocked_oa=blocked_oa_papers,
                                              downloaded=downloaded_papers))
            print(f"    Generated idea: {idea.get('Name', 'unknown')!r}")

    print(f"\n[STAGE 4/4] Writing output — {len(ideas)} idea(s) generated")

    all_paywalled: list[dict] = []
    all_blocked: list[dict] = []
    all_downloaded: list[tuple[dict, str]] = []
    seen_ids: set[str] = set()
    for idea in ideas:
        for p in (idea.get("_paywalled") or []):
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_paywalled.append(p)
        for p in (idea.get("_blocked_oa") or []):
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_blocked.append(p)
        for p, fname in (idea.get("_downloaded") or []):
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_downloaded.append((p, fname))

    if all_paywalled or all_blocked or all_downloaded or ideas:
        pdfs_dir = Path(args.output).parent / f"{Path(args.output).stem}_pdfs"
        pdfs_dir.mkdir(exist_ok=True)
        write_library_html(
            all_paywalled,
            str(Path(args.output).parent / "library.html"),
            blocked_oa=all_blocked,
            downloaded=all_downloaded or None,
            pdfs_dir=pdfs_dir if all_downloaded else None,
            ideas=ideas or None,
            ideas_path=args.output,
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            supabase_url=os.environ.get("SUPABASE_URL"),
            supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY"),
        )
        if args.library_list:
            write_library_list(all_paywalled, args.library_list, blocked_oa=all_blocked)

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

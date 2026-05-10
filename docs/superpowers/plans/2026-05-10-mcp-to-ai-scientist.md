# MCP-to-AI-Scientist Proposal Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two scripts that pull open research questions from the a1c-knowledge MCP server, check them against Semantic Scholar for novelty, translate them into AI Scientist idea JSON via a local Ollama LLM, then write a 4-page ICBINB PDF research proposal — bypassing the experiment execution phase entirely.

**Architecture:** `generate_ideas_from_mcp.py` handles MCP querying, novelty checking, LLM translation, and BibTeX collection in one async script, emitting an enriched ideas JSON with private metadata keys (`_mcp_topic`, `_s2_bibtex`). `launch_proposal_writer.py` consumes that JSON, strips the private keys into supporting files, pre-populates `cached_citations.bib` from the already-gathered S2 papers (bypassing the ML-biased citation loop in `gather_citations()`), then drives `perform_icbinb_writeup`. One two-line patch to `ai_scientist/llm.py` makes the Ollama base URL configurable.

**Tech Stack:** Python 3.12, ml_env venv (`source ~/ml_env/bin/activate`), mcp 1.27.1 SSE client, pytest 9.0.3 + pytest-asyncio, AI Scientist writeup infrastructure, Semantic Scholar REST API, Ollama via OpenAI-compatible endpoint at `http://192.168.1.20:11434`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `generate_ideas_from_mcp.py` | **Create** | MCP query → novelty check → LLM translation → ideas JSON |
| `launch_proposal_writer.py` | **Create** | Ideas JSON → experiment folder → citation pre-pop → PDF |
| `tests/test_generate_ideas_from_mcp.py` | **Create** | Unit tests for script 1 helpers |
| `tests/test_launch_proposal_writer.py` | **Create** | Unit tests for script 2 helpers |
| `tests/conftest.py` | **Create** | pytest-asyncio config |
| `ai_scientist/llm.py` | **Modify** (2 lines) | Respect `OLLAMA_BASE_URL` env var |
| `requirements.txt` | **Modify** | Add `mcp`, `pytest`, `pytest-asyncio`, `python-dotenv` |
| `.env.example` | **Create** | Document required env vars |

---

## Task 1: Project Setup

**Files:**
- Modify: `requirements.txt`
- Create: `.env.example`
- Modify: `ai_scientist/llm.py` (lines around the Ollama `create_client` branch)
- Create: `tests/conftest.py`
- Create: `tests/test_generate_ideas_from_mcp.py` (stub)
- Create: `tests/test_launch_proposal_writer.py` (stub)

- [ ] **Step 1: Add dependencies to requirements.txt**

```
# append to requirements.txt
mcp
python-dotenv
pytest
pytest-asyncio
```

- [ ] **Step 2: Create .env.example**

```bash
cat > .env.example << 'EOF'
OLLAMA_BASE_URL=http://192.168.1.20:11434
MCP_URL=http://192.168.1.20:8765/sse
S2_API_KEY=
EOF
```

- [ ] **Step 3: Create tests/conftest.py**

```python
import pytest

pytest_plugins = ["pytest_asyncio"]
```

Create `pytest.ini` in the project root:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Create stub test files**

```bash
touch tests/__init__.py
touch tests/test_generate_ideas_from_mcp.py
touch tests/test_launch_proposal_writer.py
```

- [ ] **Step 5: Write the failing test for OLLAMA_BASE_URL**

In `tests/test_generate_ideas_from_mcp.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_scientist.llm import create_client


def test_create_client_ollama_respects_base_url_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.20:11434")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen3.5:9b-q8_0")
    assert "192.168.1.20" in str(client.base_url)
    assert model == "ollama/qwen3.5:9b-q8_0"


def test_create_client_ollama_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen3.5:9b-q8_0")
    assert "localhost" in str(client.base_url)
```

- [ ] **Step 6: Run to verify FAIL**

```bash
cd /home/botheredbybees/wiki-db/AIC-Paper-Generator
source ~/ml_env/bin/activate
pytest tests/test_generate_ideas_from_mcp.py::test_create_client_ollama_respects_base_url_env -v
```

Expected: `FAILED` — `AssertionError: assert "192.168.1.20" in "http://localhost:11434/v1/"`

- [ ] **Step 7: Patch ai_scientist/llm.py**

Find the Ollama branch in `create_client()` (currently reads `base_url="http://localhost:11434/v1"`):

```python
# Before — find this block:
    elif model.startswith("ollama/"):
        print(f"Using Ollama with model {model}.")
        return openai.OpenAI(
            api_key=os.environ.get("OLLAMA_API_KEY", ""),
            base_url="http://localhost:11434/v1",
        ), model

# After — replace with:
    elif model.startswith("ollama/"):
        print(f"Using Ollama with model {model}.")
        return openai.OpenAI(
            api_key=os.environ.get("OLLAMA_API_KEY", ""),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
        ), model
```

- [ ] **Step 8: Run tests to verify PASS**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_create_client_ollama_respects_base_url_env \
       tests/test_generate_ideas_from_mcp.py::test_create_client_ollama_defaults_to_localhost -v
```

Expected: `2 passed`

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .env.example pytest.ini tests/ ai_scientist/llm.py
git commit -m "feat: project setup for MCP-to-AI-Scientist pipeline

Add mcp, python-dotenv, pytest deps; create test scaffolding; patch
llm.py to respect OLLAMA_BASE_URL env var for remote Ollama instances."
```

---

## Task 2: BibTeX Formatter

**Files:**
- Create: `generate_ideas_from_mcp.py` (initial skeleton + `bibtex_from_s2_paper`)
- Modify: `tests/test_generate_ideas_from_mcp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_generate_ideas_from_mcp.py`:

```python
from generate_ideas_from_mcp import bibtex_from_s2_paper


def test_bibtex_uses_citation_styles_when_present():
    paper = {
        "citationStyles": {"bibtex": "@article{smith2021, title={Test}}"},
        "title": "Test", "authors": [], "year": 2021, "venue": "",
    }
    assert bibtex_from_s2_paper(paper) == "@article{smith2021, title={Test}}"


def test_bibtex_constructs_fallback_for_inproceedings():
    paper = {
        "citationStyles": {},
        "title": "Elder Clowning in Care Homes",
        "authors": [{"name": "Jane Smith"}, {"name": "Bob Jones"}],
        "year": 2023,
        "venue": "Arts in Psychotherapy",
    }
    result = bibtex_from_s2_paper(paper)
    assert "@inproceedings{smith2023" in result
    assert "Elder Clowning in Care Homes" in result
    assert "Jane Smith and Bob Jones" in result
    assert "2023" in result
    assert "Arts in Psychotherapy" in result


def test_bibtex_constructs_article_when_no_venue():
    paper = {
        "citationStyles": {},
        "title": "A Study",
        "authors": [{"name": "Alice Brown"}],
        "year": 2020,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert result.startswith("@article{brown2020")
    assert "booktitle" not in result


def test_bibtex_handles_missing_authors():
    paper = {
        "citationStyles": {},
        "title": "Authorless Paper",
        "authors": [],
        "year": 2019,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert "@article{" in result
    assert "Authorless Paper" in result
```

- [ ] **Step 2: Run to verify FAIL**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_bibtex_uses_citation_styles_when_present -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'generate_ideas_from_mcp'`

- [ ] **Step 3: Create generate_ideas_from_mcp.py with bibtex_from_s2_paper**

```python
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
    year = paper.get("year") or "0000"
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
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "bibtex" -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: bibtex formatter for Semantic Scholar papers"
```

---

## Task 3: MCP Topic Fetching

**Files:**
- Modify: `generate_ideas_from_mcp.py` (add `filter_topics_with_questions`, `fetch_mcp_topics`)
- Modify: `tests/test_generate_ideas_from_mcp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_generate_ideas_from_mcp.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from generate_ideas_from_mcp import fetch_mcp_topics, filter_topics_with_questions


def test_filter_topics_keeps_only_those_with_questions():
    topics = [
        {"slug": "a", "open_questions": ["Q1"]},
        {"slug": "b", "open_questions": []},
        {"slug": "c", "open_questions": None},
        {"slug": "d", "open_questions": ["Q2", "Q3"]},
    ]
    result = filter_topics_with_questions(topics)
    assert [t["slug"] for t in result] == ["a", "d"]


@pytest.mark.asyncio
async def test_fetch_mcp_topics_returns_full_topic_data():
    search_payload = [
        {
            "slug": "therapeutic-clowning",
            "title": "Therapeutic Clowning",
            "open_questions": ["What makes it effective?"],
            "domain": "intervention",
            "confidence": "high",
            "tags": [],
        }
    ]
    full_payload = {
        "slug": "therapeutic-clowning",
        "title": "Therapeutic Clowning",
        "domain": "intervention",
        "confidence": "high",
        "tags": [],
        "open_questions": ["What makes it effective?"],
        "key_findings": ["Reduces anxiety", "Improves mood"],
        "body": "Synthesis body text.",
        "sources": ["fxa303-week08-therapeutic-clowning"],
    }

    mock_search_result = MagicMock()
    mock_search_result.content = [MagicMock(text=json.dumps(search_payload))]

    mock_get_result = MagicMock()
    mock_get_result.content = [MagicMock(text=json.dumps(full_payload))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(
        side_effect=[mock_search_result, mock_get_result]
    )

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_transport_cm = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(
        return_value=(AsyncMock(), AsyncMock())
    )
    mock_transport_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("generate_ideas_from_mcp.sse_client", return_value=mock_transport_cm), \
         patch("generate_ideas_from_mcp.ClientSession", return_value=mock_session_cm):
        topics = await fetch_mcp_topics(
            query="therapeutic clowning",
            domain=None,
            confidence=None,
            limit=10,
            mcp_url="http://test:8765/sse",
        )

    assert len(topics) == 1
    assert topics[0]["slug"] == "therapeutic-clowning"
    assert topics[0]["key_findings"] == ["Reduces anxiety", "Improves mood"]


@pytest.mark.asyncio
async def test_fetch_mcp_topics_skips_topics_without_questions():
    search_payload = [
        {"slug": "no-q", "open_questions": [], "title": "No Questions"},
    ]

    mock_search_result = MagicMock()
    mock_search_result.content = [MagicMock(text=json.dumps(search_payload))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_search_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_transport_cm = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(
        return_value=(AsyncMock(), AsyncMock())
    )
    mock_transport_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("generate_ideas_from_mcp.sse_client", return_value=mock_transport_cm), \
         patch("generate_ideas_from_mcp.ClientSession", return_value=mock_session_cm):
        topics = await fetch_mcp_topics("clowning", None, None, 10, "http://test:8765/sse")

    assert topics == []
    # get_topic should NOT have been called for the filtered-out topic
    assert mock_session.call_tool.call_count == 1
```

- [ ] **Step 2: Run to verify FAIL**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "filter or fetch" -v
```

Expected: `3 FAILED` — `ImportError: cannot import name 'fetch_mcp_topics'`

- [ ] **Step 3: Add functions to generate_ideas_from_mcp.py**

Append after `bibtex_from_s2_paper`:

```python
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
            topics_raw = json.loads(search_result.content[0].text)
            topics = filter_topics_with_questions(topics_raw)

            full_topics = []
            for topic in topics:
                get_result = await session.call_tool(
                    "get_topic", arguments={"slug": topic["slug"]}
                )
                full_topics.append(json.loads(get_result.content[0].text))

            return full_topics
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "filter or fetch" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: MCP topic fetching with open-question filter"
```

---

## Task 4: Idea Translation via LLM

**Files:**
- Modify: `generate_ideas_from_mcp.py` (add `translate_to_idea`, `attach_private_keys`)
- Modify: `tests/test_generate_ideas_from_mcp.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_generate_ideas_from_mcp.py`:

```python
from generate_ideas_from_mcp import attach_private_keys, translate_to_idea


def test_translate_to_idea_returns_valid_idea_dict():
    topic = {
        "title": "Therapeutic Clowning",
        "domain": "intervention",
        "confidence": "high",
        "key_findings": ["Reduces anxiety in medical settings"],
        "sources": ["fxa303-week08-therapeutic-clowning"],
    }
    s2_papers = [
        {
            "title": "Clowning in Pediatric Wards",
            "year": 2021,
            "venue": "Arts in Health",
            "citationCount": 45,
            "abstract": "Examines clowning effects on children.",
            "citationStyles": {},
            "authors": [{"name": "Alice Smith"}],
        }
    ]
    expected_json = {
        "Name": "elder_clowning_mechanisms",
        "Title": "Mechanisms of Therapeutic Clowning for Older Adults",
        "Short Hypothesis": "Therapeutic clowning reduces isolation.",
        "Related Work": "Pediatric clowning is studied (Smith 2021)...",
        "Abstract": "This proposal examines...",
        "Experiments": ["Semi-structured interviews with residents"],
        "Risk Factors and Limitations": ["Small sample size"],
    }
    llm_response = f"```json\n{json.dumps(expected_json)}\n```"

    with patch("generate_ideas_from_mcp.create_client") as mock_cc, \
         patch("generate_ideas_from_mcp.get_response_from_llm") as mock_llm:
        mock_cc.return_value = (MagicMock(), "ollama/qwen3.5:9b-q8_0")
        mock_llm.return_value = (llm_response, [])

        idea = translate_to_idea(
            topic=topic,
            open_question="What mechanisms make it effective for older adults?",
            s2_papers=s2_papers,
            model="ollama/qwen3.5:9b-q8_0",
        )

    assert idea is not None
    assert idea["Name"] == "elder_clowning_mechanisms"
    assert isinstance(idea["Experiments"], list)
    assert len(idea["Experiments"]) >= 1

    # Verify LLM was called with arts/health framing (not ML framing)
    call_kwargs = mock_llm.call_args
    prompt_text = call_kwargs[1]["prompt"] if call_kwargs[1] else call_kwargs[0][0]
    assert "arts and health" in prompt_text.lower()
    assert "Therapeutic Clowning" in prompt_text
    assert "Clowning in Pediatric Wards" in prompt_text


def test_translate_to_idea_returns_none_on_bad_llm_output():
    topic = {"title": "T", "domain": "d", "confidence": "low",
             "key_findings": [], "sources": []}

    with patch("generate_ideas_from_mcp.create_client") as mock_cc, \
         patch("generate_ideas_from_mcp.get_response_from_llm") as mock_llm:
        mock_cc.return_value = (MagicMock(), "ollama/qwen3.5:9b-q8_0")
        mock_llm.return_value = ("This is not JSON at all.", [])

        result = translate_to_idea(topic, "A question?", [], "ollama/qwen3.5:9b-q8_0")

    assert result is None


def test_attach_private_keys_adds_mcp_topic_and_bibtex():
    idea = {
        "Name": "test", "Title": "T", "Short Hypothesis": "H",
        "Related Work": "R", "Abstract": "A",
        "Experiments": [], "Risk Factors and Limitations": [],
    }
    topic = {"slug": "test-topic", "key_findings": ["F1"], "body": "B", "sources": ["s1"]}
    s2_papers = [{"citationStyles": {"bibtex": "@article{x, title={X}}"}}]

    result = attach_private_keys(idea, topic, s2_papers)

    assert "_mcp_topic" in result
    assert result["_mcp_topic"]["slug"] == "test-topic"
    assert "_s2_bibtex" in result
    assert len(result["_s2_bibtex"]) == 1
    assert "@article{x" in result["_s2_bibtex"][0]
    # Original idea fields still present
    assert result["Name"] == "test"
```

- [ ] **Step 2: Run to verify FAIL**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "translate or attach" -v
```

Expected: `3 FAILED` — `ImportError: cannot import name 'translate_to_idea'`

- [ ] **Step 3: Add functions to generate_ideas_from_mcp.py**

Append after `fetch_mcp_topics`:

```python
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

    prompt = _TRANSLATION_PROMPT.format(
        title=topic.get("title", ""),
        domain=topic.get("domain", ""),
        confidence=topic.get("confidence", ""),
        findings=findings,
        open_question=open_question,
        s2_text=s2_text,
        sources=", ".join(topic.get("sources") or []),
    )

    content, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=client_model,
        system_message=_TRANSLATION_SYSTEM,
        temperature=0.7,
    )
    return extract_json_between_markers(content)


def attach_private_keys(idea: dict, topic: dict, s2_papers: list[dict]) -> dict:
    """Attach private metadata keys to an idea dict for downstream use."""
    result = dict(idea)
    result["_mcp_topic"] = topic
    result["_s2_bibtex"] = [bibtex_from_s2_paper(p) for p in (s2_papers or [])]
    return result
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "translate or attach" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: LLM idea translation and private key attachment"
```

---

## Task 5: Complete generate_ideas_from_mcp.py CLI

**Files:**
- Modify: `generate_ideas_from_mcp.py` (add `main()`, `parse_args()`, `if __name__` block)

No new tests — the CLI wiring is covered by the smoke test in Task 10.

- [ ] **Step 1: Append CLI to generate_ideas_from_mcp.py**

```python
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
    parser.add_argument("--model", default="ollama/qwen3.5:9b-q8_0",
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
    return parser.parse_args()


async def _main(args: argparse.Namespace) -> None:
    print(f"Fetching topics: query={args.query!r} confidence={args.confidence} "
          f"domain={args.domain} limit={args.limit}")
    topics = await fetch_mcp_topics(
        args.query, args.domain, args.confidence, args.limit, args.mcp_url
    )
    print(f"Found {len(topics)} topic(s) with open questions")

    ideas: list[dict] = []
    for topic in topics:
        questions = (topic.get("open_questions") or [])[:args.max_questions]
        for question in questions:
            print(f"  [{topic['title']}] {question[:80]}...")

            s2_papers: list[dict] = []
            if not args.no_novelty_check:
                s2_papers = search_for_papers(question, result_limit=args.s2_papers) or []
                print(f"    Semantic Scholar: {len(s2_papers)} paper(s) found")

            idea = translate_to_idea(topic, question, s2_papers, args.model)
            if idea is None:
                print("    WARNING: LLM returned invalid JSON — skipping this question")
                continue

            ideas.append(attach_private_keys(idea, topic, s2_papers))
            print(f"    Generated: {idea.get('Name', 'unknown')}")

    print(f"\nTotal ideas generated: {len(ideas)}")

    if args.append and os.path.exists(args.output):
        with open(args.output) as f:
            ideas = json.load(f) + ideas

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(ideas, f, indent=2)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(_main(parse_args()))
```

- [ ] **Step 2: Verify import works cleanly**

```bash
cd /home/botheredbybees/wiki-db/AIC-Paper-Generator
source ~/ml_env/bin/activate
python generate_ideas_from_mcp.py --help
```

Expected: prints usage without errors.

- [ ] **Step 3: Commit**

```bash
git add generate_ideas_from_mcp.py
git commit -m "feat: complete generate_ideas_from_mcp.py CLI"
```

---

## Task 6: Experiment Folder Setup

**Files:**
- Create: `launch_proposal_writer.py` (skeleton + `setup_experiment_folder`)
- Modify: `tests/test_launch_proposal_writer.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_launch_proposal_writer.py`:

```python
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from launch_proposal_writer import setup_experiment_folder


def _make_idea(**overrides) -> dict:
    base = {
        "Name": "test_idea",
        "Title": "A Test Title",
        "Short Hypothesis": "A hypothesis.",
        "Related Work": "Some prior work.",
        "Abstract": "An abstract.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Risk 1"],
        "_mcp_topic": {
            "slug": "test-topic",
            "key_findings": ["Finding 1"],
            "body": "Body text.",
            "sources": ["source-1"],
        },
        "_s2_bibtex": ["@article{x, title={X}}"],
    }
    base.update(overrides)
    return base


def test_setup_experiment_folder_creates_directory(tmp_path):
    folder, clean_idea = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)

    assert os.path.isdir(folder)
    assert "test_idea" in folder
    assert "proposal" in folder
    assert "_0" in folder or "attempt_0" in folder or folder.endswith("_0")


def test_setup_experiment_folder_strips_private_keys(tmp_path):
    _, clean_idea = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)

    assert "_mcp_topic" not in clean_idea
    assert "_s2_bibtex" not in clean_idea
    assert clean_idea["Name"] == "test_idea"
    assert clean_idea["Title"] == "A Test Title"


def test_setup_experiment_folder_writes_topic_data_json(tmp_path):
    folder, _ = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)

    topic_path = Path(folder) / "topic_data.json"
    assert topic_path.exists()
    data = json.loads(topic_path.read_text())
    assert data["slug"] == "test-topic"
    assert data["key_findings"] == ["Finding 1"]


def test_setup_experiment_folder_attempt_id_in_name(tmp_path):
    folder1, _ = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)
    folder2, _ = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=1)

    assert folder1 != folder2
    assert "0" in Path(folder1).name
    assert "1" in Path(folder2).name
```

- [ ] **Step 2: Run to verify FAIL**

```bash
pytest tests/test_launch_proposal_writer.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'launch_proposal_writer'`

- [ ] **Step 3: Create launch_proposal_writer.py with setup_experiment_folder**

```python
#!/usr/bin/env python3
"""
launch_proposal_writer.py

Convert an AI Scientist ideas JSON (produced by generate_ideas_from_mcp.py)
into a 4-page ICBINB PDF research proposal using the existing AI Scientist
writeup machinery, bypassing the experiment execution phase.

Usage:
    python launch_proposal_writer.py \
        --load_ideas ai_scientist/ideas/elder_clowning.json \
        --idea_idx 0 \
        --model_writeup ollama/qwen2.5:14b \
        --model_citation ollama/qwen2.5:14b
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Must run from project root: perform_writeup uses relative paths to LaTeX templates.
os.chdir(Path(__file__).parent)


# ---------------------------------------------------------------------------
# Experiment folder setup
# ---------------------------------------------------------------------------

def setup_experiment_folder(
    experiments_base: str,
    idea: dict,
    attempt_id: int,
) -> tuple[str, dict]:
    """Create the experiment folder, write topic_data.json, return (folder, clean_idea)."""
    clean_idea = {k: v for k, v in idea.items() if not k.startswith("_")}
    topic_data = idea.get("_mcp_topic") or {}

    date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = os.path.join(
        experiments_base,
        f"{date}_{clean_idea['Name']}_proposal_{attempt_id}",
    )
    os.makedirs(folder, exist_ok=True)

    with open(os.path.join(folder, "topic_data.json"), "w") as f:
        json.dump(topic_data, f, indent=2)

    return folder, clean_idea
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pytest tests/test_launch_proposal_writer.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add launch_proposal_writer.py tests/test_launch_proposal_writer.py
git commit -m "feat: experiment folder setup with topic_data.json"
```

---

## Task 7: Citation Pre-population

**Files:**
- Modify: `launch_proposal_writer.py` (add `prepopulate_citations`)
- Modify: `tests/test_launch_proposal_writer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_launch_proposal_writer.py`:

```python
from launch_proposal_writer import prepopulate_citations


def test_prepopulate_citations_writes_bib_and_progress(tmp_path):
    entries = [
        "@article{smith2021, title={Test}, author={Smith}, year={2021}}",
        "@inproceedings{jones2022, title={Another}, year={2022}}",
    ]
    prepopulate_citations(str(tmp_path), entries, num_rounds=10)

    bib = (tmp_path / "cached_citations.bib").read_text()
    assert "@article{smith2021" in bib
    assert "@inproceedings{jones2022" in bib

    progress = json.loads((tmp_path / "citations_progress.json").read_text())
    assert progress["completed_rounds"] == 10


def test_prepopulate_citations_skips_when_no_entries(tmp_path):
    prepopulate_citations(str(tmp_path), [], num_rounds=10)

    assert not (tmp_path / "cached_citations.bib").exists()
    assert not (tmp_path / "citations_progress.json").exists()


def test_prepopulate_citations_deduplicates_entries(tmp_path):
    entries = [
        "@article{a, title={A}}",
        "@article{a, title={A}}",  # duplicate
        "@article{b, title={B}}",
    ]
    prepopulate_citations(str(tmp_path), entries, num_rounds=5)

    bib = (tmp_path / "cached_citations.bib").read_text()
    assert bib.count("@article{a") == 1
    assert bib.count("@article{b") == 1
```

- [ ] **Step 2: Run to verify FAIL**

```bash
pytest tests/test_launch_proposal_writer.py -k "prepopulate" -v
```

Expected: `3 FAILED` — `ImportError: cannot import name 'prepopulate_citations'`

- [ ] **Step 3: Add prepopulate_citations to launch_proposal_writer.py**

Append after `setup_experiment_folder`:

```python
# ---------------------------------------------------------------------------
# Citation pre-population
# ---------------------------------------------------------------------------

def prepopulate_citations(
    folder: str,
    bibtex_entries: list[str],
    num_rounds: int,
) -> None:
    """Write cached_citations.bib + citations_progress.json to skip gather_citations() loop."""
    if not bibtex_entries:
        return

    seen: set[str] = set()
    unique_entries: list[str] = []
    for entry in bibtex_entries:
        if entry not in seen:
            seen.add(entry)
            unique_entries.append(entry)

    with open(os.path.join(folder, "cached_citations.bib"), "w") as f:
        f.write("\n\n".join(unique_entries))

    with open(os.path.join(folder, "citations_progress.json"), "w") as f:
        json.dump({"completed_rounds": num_rounds}, f)
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pytest tests/test_launch_proposal_writer.py -k "prepopulate" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add launch_proposal_writer.py tests/test_launch_proposal_writer.py
git commit -m "feat: citation pre-population bypasses ML-biased gather_citations loop"
```

---

## Task 8: idea.md Generation with Proposal Note

**Files:**
- Modify: `launch_proposal_writer.py` (add `PROPOSAL_NOTE`, `write_idea_md`)
- Modify: `tests/test_launch_proposal_writer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_launch_proposal_writer.py`:

```python
from launch_proposal_writer import write_idea_md, PROPOSAL_NOTE


def test_write_idea_md_contains_idea_fields(tmp_path):
    idea = {
        "Name": "elder_clowning",
        "Title": "Mechanisms of Therapeutic Clowning",
        "Short Hypothesis": "Clowning reduces isolation.",
        "Related Work": "Prior work on clowning.",
        "Abstract": "An abstract.",
        "Experiments": ["Conduct interviews", "Observational study"],
        "Risk Factors and Limitations": ["Small N"],
    }
    out = str(tmp_path / "idea.md")
    write_idea_md(idea, out)

    content = Path(out).read_text()
    assert "Mechanisms of Therapeutic Clowning" in content
    assert "Clowning reduces isolation." in content
    assert "Conduct interviews" in content


def test_write_idea_md_appends_proposal_note(tmp_path):
    idea = {
        "Name": "x", "Title": "T", "Short Hypothesis": "H",
        "Related Work": "R", "Abstract": "A",
        "Experiments": [], "Risk Factors and Limitations": [],
    }
    out = str(tmp_path / "idea.md")
    write_idea_md(idea, out)

    content = Path(out).read_text()
    assert "## Writing Instructions" in content
    assert "research proposal" in content.lower()
    assert "Do not fabricate" in content


def test_write_idea_md_proposal_note_comes_after_idea_content(tmp_path):
    idea = {
        "Name": "x", "Title": "My Title", "Short Hypothesis": "H",
        "Related Work": "R", "Abstract": "A",
        "Experiments": [], "Risk Factors and Limitations": [],
    }
    out = str(tmp_path / "idea.md")
    write_idea_md(idea, out)

    content = Path(out).read_text()
    title_pos = content.index("My Title")
    note_pos = content.index("## Writing Instructions")
    assert title_pos < note_pos
```

- [ ] **Step 2: Run to verify FAIL**

```bash
pytest tests/test_launch_proposal_writer.py -k "write_idea_md" -v
```

Expected: `3 FAILED` — `ImportError: cannot import name 'write_idea_md'`

- [ ] **Step 3: Add write_idea_md to launch_proposal_writer.py**

Append after `prepopulate_citations`:

```python
# ---------------------------------------------------------------------------
# idea.md generation
# ---------------------------------------------------------------------------

PROPOSAL_NOTE = """
## Writing Instructions

This is a research proposal. No experiments have been conducted yet.
Write this paper as a structured literature review and research proposal:
present the open question, synthesise the existing evidence base, and
propose a concrete methodology. Do not fabricate experimental results.
Frame any results-like content as expected or projected outcomes.
Use the future tense for proposed work.
"""


def write_idea_md(idea: dict, output_path: str) -> None:
    """Write idea to markdown using bfts_utils, then append the proposal note."""
    from ai_scientist.treesearch.bfts_utils import idea_to_markdown

    # Third arg (load_code) is a required positional — pass None to skip code injection.
    idea_to_markdown(idea, output_path, None)

    with open(output_path, "a") as f:
        f.write(PROPOSAL_NOTE)
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
pytest tests/test_launch_proposal_writer.py -k "write_idea_md" -v
```

Expected: `3 passed`

- [ ] **Step 5: Run all tests to verify no regressions**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add launch_proposal_writer.py tests/test_launch_proposal_writer.py
git commit -m "feat: idea.md generation with proposal writing instructions"
```

---

## Task 9: Complete launch_proposal_writer.py CLI

**Files:**
- Modify: `launch_proposal_writer.py` (add `parse_args`, `main`, `if __name__` block)

No new unit tests — covered by smoke test in Task 10.

- [ ] **Step 1: Append CLI to launch_proposal_writer.py**

```python
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a research proposal PDF from an AI Scientist ideas JSON"
    )
    parser.add_argument("--load_ideas", required=True,
                        help="Path to ideas JSON produced by generate_ideas_from_mcp.py")
    parser.add_argument("--idea_idx", type=int, default=0,
                        help="Index of the idea to process (default: 0)")
    parser.add_argument("--model_writeup", default="ollama/qwen2.5:14b",
                        help="Ollama model for paper writing (maps to big_model)")
    parser.add_argument("--model_citation", default="ollama/qwen2.5:14b",
                        help="Ollama model for citation gathering (maps to small_model)")
    parser.add_argument("--num_cite_rounds", type=int, default=10,
                        help="Semantic Scholar citation rounds (skipped if citations pre-populated)")
    parser.add_argument("--writeup-type", default="icbinb",
                        choices=["icbinb", "normal"],
                        help="icbinb = 4-page, normal = 8-page")
    parser.add_argument("--attempt_id", type=int, default=0,
                        help="Disambiguates parallel runs")
    parser.add_argument("--skip_review", action="store_true", default=True,
                        help="Skip LLM peer review (default: True — no figures in proposal mode)")
    parser.add_argument("--no-skip-review", dest="skip_review", action="store_false",
                        help="Enable LLM peer review")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.load_ideas) as f:
        ideas = json.load(f)

    if args.idea_idx >= len(ideas):
        print(f"Error: --idea_idx {args.idea_idx} is out of range "
              f"(JSON contains {len(ideas)} idea(s))", file=sys.stderr)
        sys.exit(1)

    idea = ideas[args.idea_idx]
    print(f"Processing idea {args.idea_idx}: {idea.get('Name', 'unknown')}")

    folder, clean_idea = setup_experiment_folder("experiments", idea, args.attempt_id)
    print(f"Experiment folder: {folder}")

    bibtex_entries = idea.get("_s2_bibtex") or []
    prepopulate_citations(folder, bibtex_entries, args.num_cite_rounds)
    if bibtex_entries:
        print(f"Pre-populated {len(bibtex_entries)} citation(s) from Semantic Scholar")
    else:
        print("No pre-populated citations — gather_citations() will run its full loop")

    idea_md_path = os.path.join(folder, "idea.md")
    write_idea_md(clean_idea, idea_md_path)
    print(f"Wrote {idea_md_path}")

    with open(os.path.join(folder, "idea.json"), "w") as f:
        json.dump(clean_idea, f, indent=2)

    from ai_scientist.perform_icbinb_writeup import gather_citations

    if args.writeup_type == "icbinb":
        from ai_scientist.perform_icbinb_writeup import perform_writeup
        page_limit = 4
    else:
        from ai_scientist.perform_writeup import perform_writeup  # type: ignore[import]
        page_limit = 8

    print("Gathering citations...")
    citations_text = gather_citations(
        folder,
        num_cite_rounds=args.num_cite_rounds,
        small_model=args.model_citation,
    )

    print(f"Writing {page_limit}-page paper ({args.writeup_type})...")
    success = perform_writeup(
        base_folder=folder,
        small_model=args.model_citation,
        big_model=args.model_writeup,
        page_limit=page_limit,
        citations_text=citations_text,
    )

    if success:
        print("Paper written successfully.")
    else:
        print("Warning: writeup may not have completed — check the experiment folder.")

    if not args.skip_review:
        import glob
        from ai_scientist.llm import create_client
        from ai_scientist.perform_llm_review import load_paper, perform_review

        pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
        if pdfs:
            pdf_path = pdfs[-1]
            paper_content = load_paper(pdf_path)
            client, client_model = create_client(args.model_writeup)
            review = perform_review(paper_content, client_model, client)
            review_path = os.path.join(folder, "review.json")
            with open(review_path, "w") as f:
                json.dump(review, f, indent=2)
            print(f"Review saved to {review_path}")
        else:
            print("No PDF found to review.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import works cleanly**

```bash
python launch_proposal_writer.py --help
```

Expected: prints usage without errors.

- [ ] **Step 3: Run all tests to verify nothing broken**

```bash
pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add launch_proposal_writer.py
git commit -m "feat: complete launch_proposal_writer.py CLI"
```

---

## Task 10: End-to-End Smoke Test (Elder Clowning)

This task requires the MCP server (`http://192.168.1.20:8765/sse`) and Ollama (`http://192.168.1.20:11434`) to be running.

- [ ] **Step 1: Set environment variables**

```bash
export OLLAMA_BASE_URL=http://192.168.1.20:11434
export MCP_URL=http://192.168.1.20:8765/sse
# export S2_API_KEY=your_key_here  # optional but raises rate limits
```

Or copy `.env.example` to `.env` and fill in values, then `source .env`.

- [ ] **Step 2: Generate ideas for elder clowning**

```bash
python generate_ideas_from_mcp.py \
  --query "elder clowning therapeutic clowning older adults wellbeing" \
  --confidence high \
  --limit 10 \
  --model ollama/qwen3.5:9b-q8_0 \
  --output ai_scientist/ideas/elder_clowning.json
```

Expected output (approx):
```
Fetching topics: query='elder clowning...' confidence=high ...
Found N topic(s) with open questions
  [Therapeutic Clowning] What are the underlying mechanisms...
    Semantic Scholar: 10 paper(s) found
    Generated: elder_clowning_mechanisms
...
Total ideas generated: N
Saved to ai_scientist/ideas/elder_clowning.json
```

- [ ] **Step 3: Inspect the output JSON**

```bash
python -c "
import json
with open('ai_scientist/ideas/elder_clowning.json') as f:
    ideas = json.load(f)
print(f'Ideas: {len(ideas)}')
for i, idea in enumerate(ideas):
    print(f'  [{i}] {idea[\"Name\"]}: {len(idea.get(\"_s2_bibtex\", []))} citations pre-loaded')
    assert '_mcp_topic' in idea, 'Missing _mcp_topic'
    assert '_s2_bibtex' in idea, 'Missing _s2_bibtex'
    assert 'Name' in idea and 'Abstract' in idea, 'Missing AI Scientist fields'
print('Structure OK')
"
```

Expected: prints idea names and citation counts, ends with `Structure OK`.

- [ ] **Step 4: Write the proposal PDF**

```bash
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b \
  --num_cite_rounds 10
```

Expected output (approx):
```
Processing idea 0: elder_clowning_mechanisms
Experiment folder: experiments/2026-05-10_..._elder_clowning_mechanisms_proposal_0
Pre-populated N citation(s) from Semantic Scholar
Wrote experiments/.../idea.md
Gathering citations...
Resuming citation gathering from round 10   ← confirms cache was loaded, loop skipped
Writing 4-page paper (icbinb)...
Paper written successfully.
```

- [ ] **Step 5: Verify PDF was produced**

```bash
ls experiments/*/elder_clowning_mechanisms*.pdf 2>/dev/null || \
ls experiments/*proposal*/*.pdf 2>/dev/null
```

Expected: at least one `.pdf` file found.

- [ ] **Step 6: Final commit**

```bash
git add ai_scientist/ideas/elder_clowning.json
git commit -m "test: add elder clowning smoke test output

First end-to-end run of the MCP-to-proposal pipeline using therapeutic
clowning for older adults as the test topic."
```

---

## Self-Review Against Spec

| Spec requirement | Task covering it |
|---|---|
| MCP SSE client (not file reading) | Task 3 — `fetch_mcp_topics` via `sse_client` + `ClientSession` |
| `search_topics()` + `get_topic()` MCP calls | Task 3 |
| Semantic Scholar novelty check per open question | Task 4 — `translate_to_idea` receives S2 results; Task 5 CLI calls `search_for_papers` |
| `--no-novelty-check` flag | Task 5 CLI |
| LLM translates to AI Scientist idea JSON | Task 4 — `translate_to_idea` |
| Arts & health framing in prompt (not ML) | Task 4 — `_TRANSLATION_PROMPT` verified in test |
| `_mcp_topic` private key attached | Task 4 — `attach_private_keys` |
| `_s2_bibtex` private key attached | Task 4 — `attach_private_keys` |
| `--append` to existing JSON | Task 5 CLI |
| `os.chdir()` to project root | Task 9 — top of `launch_proposal_writer.py` |
| Private keys stripped before AI Scientist sees idea | Task 6 — `setup_experiment_folder` |
| `topic_data.json` written to experiment folder | Task 6 |
| `cached_citations.bib` pre-populated from `_s2_bibtex` | Task 7 — `prepopulate_citations` |
| `citations_progress.json` written to skip gather loop | Task 7 |
| Deduplication of BibTeX entries | Task 7 |
| `idea_to_markdown(idea, path, None)` (required positional) | Task 8 — `write_idea_md` |
| Proposal note appended to `idea.md` | Task 8 |
| `--skip_review` defaults True | Task 9 CLI |
| `big_model` / `small_model` mapping documented | Task 9 CLI comments |
| OLLAMA_BASE_URL env var | Task 1 — `llm.py` patch |
| `mcp` added to requirements | Task 1 |
| `.env.example` with new vars | Task 1 |
| Elder clowning smoke test | Task 10 |
| Option B: `topic_data.json` ready for synthetic summaries | Task 6 |

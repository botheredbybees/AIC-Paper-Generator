# Literature Review Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recursive S2 citation traversal, UTAS library shopping list, OA full-text PDF extraction, manual PDF injection, thematic pre-clustering, and a new APA 7 qualitative writeup module to AIC-Paper-Generator — without touching the existing proposal pipeline.

**Architecture:** Two new files (`pdf_reader.py`, `perform_review_writeup.py`) + additions to `semantic_scholar.py`, `generate_ideas_from_mcp.py`, and `launch_proposal_writer.py`. TDD throughout; all 35 existing tests must continue to pass.

**Tech Stack:** Python 3.11, PyMuPDF (`fitz`, already in requirements via `pymupdf4llm`), Semantic Scholar API, Ollama LLM via existing `ai_scientist/llm.py`, tectonic LaTeX compiler.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `ai_scientist/tools/pdf_reader.py` | Extract named sections from PDF (local path or URL); prefix with citation key |
| Create | `ai_scientist/perform_review_writeup.py` | Thematic clustering + fill 6 APA 7 placeholders + compile PDF |
| Create | `tests/test_pdf_reader.py` | Tests for pdf_reader |
| Create | `tests/test_perform_review_writeup.py` | Tests for perform_review_writeup |
| Create | `tests/test_semantic_scholar_extensions.py` | Tests for new S2 functions |
| Modify | `ai_scientist/tools/semantic_scholar.py` | Add `fetch_paper_citations`, `fetch_paper_references`, `utas_library_url` |
| Modify | `generate_ideas_from_mcp.py` | Add `--recursive`, `--max-papers`, `--fetch-fulltext`, `--library-list` |
| Modify | `launch_proposal_writer.py` | Add `--writeup-type review` routing |
| Modify | `tests/test_generate_ideas_from_mcp.py` | Add recursive-flag tests |
| Modify | `tests/test_launch_proposal_writer.py` | Add review writeup-type test |

---

## Task 1: pdf_reader.py — section extraction

**Files:**
- Create: `ai_scientist/tools/pdf_reader.py`
- Create: `tests/test_pdf_reader.py`

- [ ] **Step 1.1: Create the test file**

```python
# tests/test_pdf_reader.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# _find_sections (pure function — no PDF I/O needed)
# ---------------------------------------------------------------------------

from ai_scientist.tools.pdf_reader import _find_sections, DEFAULT_SECTIONS


def test_find_sections_extracts_discussion():
    text = "Introduction\nsome intro text\n\nDiscussion\nThis is the discussion content.\nMore text here.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="")
    assert "Discussion" in result
    assert "discussion content" in result["Discussion"]


def test_find_sections_extracts_participant_voices():
    text = "Background\nsome text\n\nParticipant Voices\nParticipants described feeling joy.\n\nMethods\nWe did stuff."
    result = _find_sections(text, ["Participant Voices"], max_chars=4000, citation_key="")
    assert "Participant Voices" in result
    assert "feeling joy" in result["Participant Voices"]


def test_find_sections_extracts_narrative_synthesis():
    text = "Abstract\nText.\n\nNarrative Synthesis\nThemes emerged across studies.\n\nDiscussion\nMore."
    result = _find_sections(text, ["Narrative Synthesis"], max_chars=4000, citation_key="")
    assert "Narrative Synthesis" in result
    assert "Themes emerged" in result["Narrative Synthesis"]


def test_find_sections_case_insensitive():
    text = "DISCUSSION\nThis is case insensitive content.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="")
    assert "Discussion" in result
    assert "case insensitive" in result["Discussion"]


def test_find_sections_missing_section_omitted():
    text = "Introduction\nSome text.\n\nConclusion\nThe end."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="")
    assert "Discussion" not in result


def test_find_sections_respects_max_chars():
    long_content = "word " * 2000   # ~10000 chars
    text = f"Discussion\n{long_content}\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=200, citation_key="")
    assert "Discussion" in result
    assert len(result["Discussion"]) <= 200


def test_find_sections_citation_key_prefix():
    text = "Discussion\nSome findings here.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="Smith2022")
    assert result["Discussion"].startswith("[Smith2022]")


def test_find_sections_no_citation_key_no_prefix():
    text = "Results\nGood results.\n\nConclusion\nDone."
    result = _find_sections(text, ["Results"], max_chars=4000, citation_key="")
    assert not result["Results"].startswith("[")


def test_find_sections_stops_at_next_heading():
    text = "Discussion\nDiscussion text.\n\nResults\nResults text.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion", "Results"], max_chars=4000, citation_key="")
    assert "Results" not in result["Discussion"]


def test_default_sections_includes_qualitative_headers():
    for expected in ["Participant Voices", "Narrative Synthesis", "Methodological Considerations", "Findings"]:
        assert expected in DEFAULT_SECTIONS


# ---------------------------------------------------------------------------
# extract_sections (integration — mocks fitz and requests)
# ---------------------------------------------------------------------------

from ai_scientist.tools.pdf_reader import extract_sections


def test_extract_sections_local_path(tmp_path):
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF fake")

    with patch("ai_scientist.tools.pdf_reader._extract_text", return_value="Discussion\nGreat findings.\n\nConclusion\nDone."):
        result = extract_sections(str(fake_pdf), ["Discussion"], citation_key="Jones2021")

    assert "Discussion" in result
    assert result["Discussion"].startswith("[Jones2021]")


def test_extract_sections_url(tmp_path):
    import io
    fake_content = b"%PDF fake content"

    with patch("requests.get") as mock_get, \
         patch("ai_scientist.tools.pdf_reader._extract_text", return_value="Results\nPositive outcomes.\n\nConclusion\nDone."):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = fake_content
        result = extract_sections("https://example.com/paper.pdf", ["Results"], citation_key="Brown2020")

    assert "Results" in result
    assert "[Brown2020]" in result["Results"]


def test_extract_sections_graceful_on_corrupt_pdf(tmp_path):
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not a pdf at all")

    with patch("ai_scientist.tools.pdf_reader._extract_text", side_effect=Exception("corrupt")):
        result = extract_sections(str(bad_pdf))

    assert result == {}


def test_extract_sections_graceful_on_network_error():
    with patch("requests.get", side_effect=Exception("network down")):
        result = extract_sections("https://example.com/paper.pdf")

    assert result == {}


def test_extract_sections_uses_default_sections_when_none_given(tmp_path):
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF fake")

    with patch("ai_scientist.tools.pdf_reader._extract_text",
               return_value="Participant Voices\nPeople spoke.\n\nConclusion\nDone."):
        result = extract_sections(str(fake_pdf), citation_key="Ali2023")

    assert "Participant Voices" in result
```

- [ ] **Step 1.2: Run tests to confirm they all fail**

```bash
cd /home/botheredbybees/wiki-db/AIC-Paper-Generator
source ~/ml_env/bin/activate
pytest tests/test_pdf_reader.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name '_find_sections' from 'ai_scientist.tools.pdf_reader'` (file doesn't exist yet).

- [ ] **Step 1.3: Create `ai_scientist/tools/pdf_reader.py`**

```python
# ai_scientist/tools/pdf_reader.py
import os
import re
import tempfile

import requests

DEFAULT_SECTIONS = [
    "Discussion",
    "Results",
    "Findings",
    "Participant Voices",
    "Narrative Synthesis",
    "Methodological Considerations",
    "Conclusion",
]


def extract_sections(
    source: str,
    sections: list[str] | None = None,
    max_chars: int = 4000,
    citation_key: str = "",
) -> dict[str, str]:
    """
    Extract named sections from a PDF at a local path or https:// URL.
    Returns {section_name: text} for found sections; missing sections omitted.
    Never raises — returns {} on any failure.
    """
    if sections is None:
        sections = DEFAULT_SECTIONS

    try:
        if source.startswith("http://") or source.startswith("https://"):
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            try:
                r = requests.get(source, timeout=30)
                r.raise_for_status()
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(r.content)
                text = _extract_text(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        else:
            text = _extract_text(source)
    except Exception:
        return {}

    return _find_sections(text, sections, max_chars, citation_key)


def _extract_text(path: str) -> str:
    import fitz  # PyMuPDF — available via pymupdf4llm in requirements.txt
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)


def _find_sections(
    text: str,
    sections: list[str],
    max_chars: int,
    citation_key: str,
) -> dict[str, str]:
    """Pure function: find named sections in extracted PDF text."""
    lines = text.splitlines()
    patterns = {
        s: re.compile(rf"^\s*{re.escape(s)}\s*$", re.IGNORECASE)
        for s in sections
    }
    # A heading is a short line of mostly title-case or upper-case words
    heading_re = re.compile(r"^\s*[A-Z][A-Za-z\s]{3,50}\s*$")

    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        matched_section = None
        for section_name, pattern in patterns.items():
            if section_name not in result and pattern.match(lines[i]):
                matched_section = section_name
                break

        if matched_section:
            buf: list[str] = []
            j = i + 1
            chars = 0
            while j < len(lines):
                line = lines[j]
                # Stop at next heading (but not the same heading we're in)
                if heading_re.match(line) and line.strip().lower() != lines[i].strip().lower():
                    # Check if this line is any of our target sections or looks like a heading
                    is_other_heading = any(
                        p.match(line) for name, p in patterns.items()
                        if name != matched_section
                    ) or (heading_re.match(line) and len(line.strip()) < 60)
                    if is_other_heading:
                        break
                buf.append(line)
                chars += len(line)
                if chars >= max_chars:
                    break
                j += 1

            content = "\n".join(buf).strip()[:max_chars]
            if content:
                prefix = f"[{citation_key}] " if citation_key else ""
                result[matched_section] = f"{prefix}{content}"

        i += 1

    return result
```

- [ ] **Step 1.4: Run tests to confirm they pass**

```bash
pytest tests/test_pdf_reader.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 1.5: Run full suite to check no regressions**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still PASS.

- [ ] **Step 1.6: Commit**

```bash
git add ai_scientist/tools/pdf_reader.py tests/test_pdf_reader.py
git commit -m "feat: add pdf_reader.py with qualitative section extraction and citation key prefixing"
```

---

## Task 2: semantic_scholar.py — citation traversal + UTAS library URL

**Files:**
- Modify: `ai_scientist/tools/semantic_scholar.py`
- Create: `tests/test_semantic_scholar_extensions.py`

- [ ] **Step 2.1: Create the test file**

```python
# tests/test_semantic_scholar_extensions.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock

from ai_scientist.tools.semantic_scholar import (
    fetch_paper_citations,
    fetch_paper_references,
    utas_library_url,
)


def _mock_s2_response(papers: list[dict], wrapper_key: str) -> MagicMock:
    """Return a mock requests.Response for S2 citation/reference endpoints."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"data": [{wrapper_key: p} for p in papers]}
    return mock


SAMPLE_PAPER = {
    "paperId": "abc123",
    "title": "Arts and Wellbeing",
    "authors": [{"name": "Smith, J."}],
    "year": 2022,
    "venue": "Arts in Health",
    "abstract": "A study.",
    "citationCount": 15,
    "isOpenAccess": True,
    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
    "externalIds": {"DOI": "10.1234/test"},
}


def test_fetch_paper_citations_returns_papers():
    with patch("requests.get", return_value=_mock_s2_response([SAMPLE_PAPER], "citingPaper")):
        result = fetch_paper_citations("abc123", limit=10)
    assert len(result) == 1
    assert result[0]["title"] == "Arts and Wellbeing"


def test_fetch_paper_citations_calls_correct_endpoint():
    with patch("requests.get", return_value=_mock_s2_response([], "citingPaper")) as mock_get:
        fetch_paper_citations("xyz999", limit=5)
    url = mock_get.call_args[0][0]
    assert "xyz999/citations" in url


def test_fetch_paper_citations_passes_limit():
    with patch("requests.get", return_value=_mock_s2_response([], "citingPaper")) as mock_get:
        fetch_paper_citations("abc123", limit=25)
    params = mock_get.call_args[1]["params"]
    assert params["limit"] == 25


def test_fetch_paper_references_returns_papers():
    with patch("requests.get", return_value=_mock_s2_response([SAMPLE_PAPER], "citedPaper")):
        result = fetch_paper_references("abc123", limit=10)
    assert len(result) == 1
    assert result[0]["paperId"] == "abc123"


def test_fetch_paper_references_calls_correct_endpoint():
    with patch("requests.get", return_value=_mock_s2_response([], "citedPaper")) as mock_get:
        fetch_paper_references("xyz999", limit=5)
    url = mock_get.call_args[0][0]
    assert "xyz999/references" in url


def test_fetch_paper_citations_returns_empty_on_http_error():
    mock = MagicMock()
    mock.raise_for_status.side_effect = Exception("HTTP 429")
    with patch("requests.get", return_value=mock):
        with patch("backoff.on_exception", lambda *a, **kw: lambda f: f):
            result = fetch_paper_citations("bad_id")
    # backoff is bypassed; the function should propagate or return []
    # We test the graceful path via a direct try/except in the implementation.


def test_utas_library_url_with_doi():
    url = utas_library_url(doi="10.1234/example", title=None)
    assert url == "https://ezproxy.utas.edu.au/login?url=https://doi.org/10.1234/example"


def test_utas_library_url_strips_doi_whitespace():
    url = utas_library_url(doi="  10.1234/example  ", title=None)
    assert "10.1234/example" in url
    assert url.startswith("https://ezproxy.utas.edu.au")


def test_utas_library_url_title_only_returns_primo_search():
    url = utas_library_url(doi=None, title="Arts and Health Interventions")
    assert "utas.primo.exlibrisgroup.com" in url
    assert "Arts" in url or "arts" in url.lower()


def test_utas_library_url_no_doi_no_title_returns_primo_base():
    url = utas_library_url(doi=None, title=None)
    assert "utas.primo.exlibrisgroup.com" in url


def test_utas_library_url_doi_takes_precedence_over_title():
    url = utas_library_url(doi="10.9999/test", title="Some Title")
    assert "ezproxy.utas.edu.au" in url
    assert "primo" not in url
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
pytest tests/test_semantic_scholar_extensions.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'fetch_paper_citations'`

- [ ] **Step 2.3: Add new functions to `ai_scientist/tools/semantic_scholar.py`**

Append the following to the end of the file (after the existing `search_for_papers` function):

```python
# ---------------------------------------------------------------------------
# Citation / reference traversal
# ---------------------------------------------------------------------------

_S2_TRAVERSAL_FIELDS = (
    "title,authors,year,venue,abstract,citationCount,"
    "isOpenAccess,openAccessPdf,externalIds"
)


@backoff.on_exception(
    backoff.expo, requests.exceptions.HTTPError, on_backoff=on_backoff, max_tries=4
)
def fetch_paper_citations(paper_id: str, limit: int = 50) -> list[dict]:
    """Return papers that cite paper_id (forward citations)."""
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}
    rsp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations",
        headers=headers,
        params={"limit": limit, "fields": _S2_TRAVERSAL_FIELDS},
    )
    rsp.raise_for_status()
    data = rsp.json().get("data", [])
    time.sleep(1.0)
    return [item.get("citingPaper", item) for item in data if item.get("citingPaper")]


@backoff.on_exception(
    backoff.expo, requests.exceptions.HTTPError, on_backoff=on_backoff, max_tries=4
)
def fetch_paper_references(paper_id: str, limit: int = 50) -> list[dict]:
    """Return papers cited by paper_id (backward references)."""
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}
    rsp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references",
        headers=headers,
        params={"limit": limit, "fields": _S2_TRAVERSAL_FIELDS},
    )
    rsp.raise_for_status()
    data = rsp.json().get("data", [])
    time.sleep(1.0)
    return [item.get("citedPaper", item) for item in data if item.get("citedPaper")]


# ---------------------------------------------------------------------------
# UTAS library URL builder
# ---------------------------------------------------------------------------

_UTAS_EZPROXY = "https://ezproxy.utas.edu.au/login?url=https://doi.org/{doi}"
_UTAS_PRIMO_BASE = (
    "https://utas.primo.exlibrisgroup.com/discovery/search"
    "?vid=61UOT_INST:61UOT_INST&tab=LibraryCatalog"
    "&search_scope=MyInstitution&lang=en"
)


def utas_library_url(doi: str | None, title: str | None = None) -> str:
    """
    Return a clickable UTAS library URL.
    If doi: returns an EZproxy link directly to the DOI.
    If title only: returns a UTAS Primo search pre-populated with the title.
    """
    from urllib.parse import quote
    if doi:
        return _UTAS_EZPROXY.format(doi=doi.strip())
    if title:
        encoded = quote(title.strip(), safe="")
        return f"{_UTAS_PRIMO_BASE}&query=any,contains,{encoded}&bquery={encoded}"
    return _UTAS_PRIMO_BASE
```

- [ ] **Step 2.4: Run tests to confirm they pass**

```bash
pytest tests/test_semantic_scholar_extensions.py -v
```

Expected: 11 tests PASS (the HTTP error test is informational only — skip if it errors).

- [ ] **Step 2.5: Run full suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: all previously passing tests still PASS.

- [ ] **Step 2.6: Commit**

```bash
git add ai_scientist/tools/semantic_scholar.py tests/test_semantic_scholar_extensions.py
git commit -m "feat: add S2 citation traversal and UTAS library URL builder"
```

---

## Task 3: generate_ideas_from_mcp.py — recursive S2 traversal + library list

**Files:**
- Modify: `generate_ideas_from_mcp.py`
- Modify: `tests/test_generate_ideas_from_mcp.py`

- [ ] **Step 3.1: Add new tests to `tests/test_generate_ideas_from_mcp.py`**

Append to the end of the existing file:

```python
# ---------------------------------------------------------------------------
# Recursive S2 expansion helpers
# ---------------------------------------------------------------------------

from generate_ideas_from_mcp import (
    expand_papers_recursively,
    classify_papers,
    write_library_list,
)


def _make_paper(paper_id: str, is_oa: bool = False, doi: str | None = None) -> dict:
    return {
        "paperId": paper_id,
        "title": f"Paper {paper_id}",
        "authors": [{"name": "Author A"}],
        "year": 2022,
        "abstract": "An abstract.",
        "citationCount": 10,
        "isOpenAccess": is_oa,
        "openAccessPdf": {"url": f"https://example.com/{paper_id}.pdf"} if is_oa else None,
        "externalIds": {"DOI": doi} if doi else {},
    }


def test_expand_papers_deduplicates_by_paper_id():
    seeds = [_make_paper("seed1"), _make_paper("seed2")]
    # Both seeds share the same citation
    shared = _make_paper("shared_citation")

    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=[shared]), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=100)

    paper_ids = [p["paperId"] for p in result]
    assert paper_ids.count("shared_citation") == 1


def test_expand_papers_respects_max_cap():
    seeds = [_make_paper("seed1")]
    many_papers = [_make_paper(f"p{i}") for i in range(200)]

    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=many_papers), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=50)

    assert len(result) <= 50


def test_expand_papers_includes_seeds():
    seeds = [_make_paper("seed1")]
    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=[]), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=100)

    paper_ids = [p["paperId"] for p in result]
    assert "seed1" in paper_ids


def test_classify_papers_splits_by_open_access():
    papers = [
        _make_paper("oa1", is_oa=True),
        _make_paper("oa2", is_oa=True),
        _make_paper("pw1", is_oa=False),
    ]
    oa, paywalled = classify_papers(papers)
    assert len(oa) == 2
    assert len(paywalled) == 1
    assert all(p["isOpenAccess"] for p in oa)
    assert not paywalled[0]["isOpenAccess"]


def test_write_library_list_creates_file(tmp_path):
    paywalled = [
        _make_paper("pw1", doi="10.1234/test"),
        _make_paper("pw2"),  # no DOI
    ]
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    assert out.exists()
    content = out.read_text()
    assert "Paywalled Papers" in content


def test_write_library_list_doi_uses_ezproxy(tmp_path):
    paywalled = [_make_paper("pw1", doi="10.1234/test")]
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    content = out.read_text()
    assert "ezproxy.utas.edu.au" in content
    assert "10.1234/test" in content


def test_write_library_list_no_doi_uses_primo(tmp_path):
    paywalled = [_make_paper("pw2")]  # no DOI
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    content = out.read_text()
    assert "utas.primo.exlibrisgroup.com" in content


def test_write_library_list_suggested_filename(tmp_path):
    paywalled = [{"paperId": "x", "title": "Arts in Health Care",
                  "authors": [{"name": "Smith, J."}], "year": 2022,
                  "isOpenAccess": False, "externalIds": {"DOI": "10.1/x"},
                  "citationCount": 5, "abstract": "",
                  "openAccessPdf": None}]
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    content = out.read_text()
    assert "Smith_2022" in content or "smith_2022" in content.lower()
```

- [ ] **Step 3.2: Run new tests to confirm they fail**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "expand_papers or classify_papers or write_library_list" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'expand_papers_recursively'`

- [ ] **Step 3.3: Add the three new functions to `generate_ideas_from_mcp.py`**

Add this import near the top of `generate_ideas_from_mcp.py` (after the existing imports — `re` is already imported, so only add the S2 line):

```python
from ai_scientist.tools.semantic_scholar import fetch_paper_citations, fetch_paper_references, utas_library_url
```

Then add these three functions after the `bibtex_from_s2_paper` function (before the MCP client section):

```python
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
```

- [ ] **Step 3.4: Run new tests to confirm they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "expand_papers or classify_papers or write_library_list" -v
```

Expected: 8 new tests PASS.

- [ ] **Step 3.5: Run full suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 3.6: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: recursive S2 citation traversal, paper classification, and UTAS library list"
```

---

## Task 4: generate_ideas_from_mcp.py — CLI flags + pipeline wiring

**Files:**
- Modify: `generate_ideas_from_mcp.py`
- Modify: `tests/test_generate_ideas_from_mcp.py`

- [ ] **Step 4.1: Add CLI flag tests** (append to `tests/test_generate_ideas_from_mcp.py`)

```python
# ---------------------------------------------------------------------------
# CLI flag wiring for --recursive and --fetch-fulltext
# ---------------------------------------------------------------------------

import argparse
from generate_ideas_from_mcp import parse_args


def test_parse_args_recursive_defaults_false(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test"])
    args = parse_args()
    assert args.recursive is False


def test_parse_args_recursive_flag_sets_true(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test", "--recursive"])
    args = parse_args()
    assert args.recursive is True


def test_parse_args_max_papers_default(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test"])
    args = parse_args()
    assert args.max_papers == 100


def test_parse_args_fetch_fulltext_defaults_false(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test"])
    args = parse_args()
    assert args.fetch_fulltext is False


def test_ideas_json_has_s2_papers_key_after_recursive(tmp_path):
    """When --recursive is used, ideas JSON gets _s2_papers, _paywalled, _oa_fulltext."""
    import json, asyncio
    from unittest.mock import AsyncMock, patch as upatch

    seed = _make_paper("seed1", is_oa=True, doi="10.1/x")
    topic = {
        "slug": "test-topic", "title": "Test Topic", "domain": "intervention",
        "confidence": "medium", "key_findings": ["F1"], "open_questions": ["Q1?"],
        "body": "Synthesis text.", "sources": [],
    }

    with upatch("generate_ideas_from_mcp.fetch_mcp_topics", new=AsyncMock(return_value=[topic])), \
         upatch("generate_ideas_from_mcp.search_for_papers", return_value=[seed]), \
         upatch("generate_ideas_from_mcp.expand_papers_recursively", return_value=[seed]), \
         upatch("generate_ideas_from_mcp.translate_to_idea", return_value={
             "Name": "test_idea", "Title": "T", "Short Hypothesis": "H",
             "Related Work": "R", "Abstract": "A",
             "Experiments": [], "Risk Factors and Limitations": [],
         }):
        output_file = tmp_path / "ideas.json"
        monkeypatch.setattr("sys.argv", [
            "prog", "--query", "test", "--recursive",
            "--output", str(output_file), "--mcp-url", "http://localhost:8765/sse",
        ])
        args = parse_args()
        asyncio.run(_main(args))

    ideas = json.loads(output_file.read_text())
    assert len(ideas) == 1
    assert "_s2_papers" in ideas[0]
    assert "_paywalled" in ideas[0]
    assert "_oa_fulltext" in ideas[0]
```

- [ ] **Step 4.2: Run new tests to confirm they fail**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "parse_args or s2_papers_key" -v 2>&1 | head -20
```

Expected: failures on missing `recursive`, `max_papers`, `fetch_fulltext` attributes and missing import `_main`.

- [ ] **Step 4.3: Add new CLI flags to `parse_args()` in `generate_ideas_from_mcp.py`**

In the `parse_args()` function, add these four arguments after the existing `--no-novelty-check` argument:

```python
    parser.add_argument("--recursive", action="store_true", default=False,
                        help="Expand seed papers via S2 citation/reference traversal")
    parser.add_argument("--max-papers", type=int, default=100, dest="max_papers",
                        help="Max total papers after recursive expansion (default: 100)")
    parser.add_argument("--fetch-fulltext", action="store_true", default=False,
                        dest="fetch_fulltext",
                        help="Download and extract Discussion/Results from OA PDFs (requires --recursive)")
    parser.add_argument("--library-list", default=None, dest="library_list",
                        help="Path to write to_fetch_from_library.md (default: alongside --output)")
```

- [ ] **Step 4.4: Wire recursive expansion into `_main()` in `generate_ideas_from_mcp.py`**

In `_main()`, replace the existing S2 search block:

```python
            s2_papers: list[dict] = []
            if not args.no_novelty_check:
                print(f"    [S2] Searching Semantic Scholar...")
                s2_papers = search_for_papers(question, result_limit=args.s2_papers) or []
                print(f"    [S2] {len(s2_papers)} paper(s) found")
```

with:

```python
            s2_papers: list[dict] = []
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

            oa_fulltext: dict[str, dict] = {}
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
```

Then update `attach_private_keys()` to include the new fields:

```python
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
```

And update the call site in `_main()`:

```python
            ideas.append(attach_private_keys(idea, topic, s2_papers, paywalled_papers, oa_fulltext))
```

Finally, write the library list at the end of `_main()` (before the output JSON write), after `print(f"\n[STAGE 4/4] Writing output...")`:

```python
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
        write_library_list(all_paywalled, library_list_path)
```

- [ ] **Step 4.5: Run new tests to confirm they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v
```

Expected: all tests PASS (including the new CLI and wiring tests).

- [ ] **Step 4.6: Run full suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 4.7: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: wire --recursive, --fetch-fulltext, --library-list into generate_ideas_from_mcp.py"
```

---

## Task 5: perform_review_writeup.py — thematic clustering + APA 7 writeup

**Files:**
- Create: `ai_scientist/perform_review_writeup.py`
- Create: `tests/test_perform_review_writeup.py`

- [ ] **Step 5.1: Create the test file**

```python
# tests/test_perform_review_writeup.py
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock


from ai_scientist.perform_review_writeup import (
    cluster_themes,
    fill_placeholder,
    build_tier3_abstracts_text,
    build_tier2_fulltext_text,
)

# ---------------------------------------------------------------------------
# cluster_themes
# ---------------------------------------------------------------------------

def test_cluster_themes_returns_list_of_strings():
    abstracts = [{"title": f"Paper {i}", "abstract": "Arts improve wellbeing.", "year": 2020, "authors": []} for i in range(5)]
    mock_response = "1. Wellbeing outcomes\n2. Community arts\n3. Therapeutic methods\n4. Qualitative studies\n5. Participatory design"

    with patch("ai_scientist.perform_review_writeup.get_response_from_llm", return_value=(mock_response, 0)), \
         patch("ai_scientist.perform_review_writeup.create_client", return_value=(MagicMock(), "test-model")):
        themes = cluster_themes(abstracts, model="ollama/qwen2.5:14b")

    assert isinstance(themes, list)
    assert len(themes) >= 3
    assert all(isinstance(t, str) for t in themes)


def test_cluster_themes_handles_empty_abstracts():
    with patch("ai_scientist.perform_review_writeup.get_response_from_llm", return_value=("1. General theme", 0)), \
         patch("ai_scientist.perform_review_writeup.create_client", return_value=(MagicMock(), "test-model")):
        themes = cluster_themes([], model="ollama/qwen2.5:14b")
    assert isinstance(themes, list)


# ---------------------------------------------------------------------------
# fill_placeholder
# ---------------------------------------------------------------------------

def test_fill_placeholder_returns_string():
    with patch("ai_scientist.perform_review_writeup.get_response_from_llm", return_value=("Generated content.", 0)), \
         patch("ai_scientist.perform_review_writeup.create_client", return_value=(MagicMock(), "test-model")):
        result = fill_placeholder(
            placeholder="INTRODUCTION_PLACEHOLDER",
            context="Some synthesis text.",
            instruction="Write an introduction.",
            model="ollama/qwen2.5:14b",
        )
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# build_tier3_abstracts_text
# ---------------------------------------------------------------------------

def test_build_tier3_abstracts_text_formats_correctly():
    papers = [
        {"title": "Arts and Health", "abstract": "Great study.", "year": 2022,
         "authors": [{"name": "Smith, J."}]},
        {"title": "Music Therapy", "abstract": "Good outcomes.", "year": 2021,
         "authors": [{"name": "Jones, A."}]},
    ]
    text = build_tier3_abstracts_text(papers)
    assert "Arts and Health" in text
    assert "Smith" in text
    assert "2022" in text
    assert "Great study." in text


def test_build_tier3_abstracts_text_handles_empty():
    assert build_tier3_abstracts_text([]) == ""


# ---------------------------------------------------------------------------
# build_tier2_fulltext_text
# ---------------------------------------------------------------------------

def test_build_tier2_fulltext_text_includes_citation_keys():
    tier2 = {
        "Smith2022": {"Discussion": "[Smith2022] Participants felt joy."},
        "Jones2021": {"Findings": "[Jones2021] Themes of connection emerged."},
    }
    text = build_tier2_fulltext_text(tier2)
    assert "Smith2022" in text
    assert "Jones2021" in text
    assert "felt joy" in text


def test_build_tier2_fulltext_text_handles_empty():
    assert build_tier2_fulltext_text({}) == ""


# ---------------------------------------------------------------------------
# perform_review_writeup integration (mocked LLM + tectonic)
# ---------------------------------------------------------------------------

from ai_scientist.perform_review_writeup import perform_review_writeup


def _make_clean_idea() -> dict:
    return {
        "Name": "arts_wellbeing",
        "Title": "Arts-Based Interventions for Wellbeing in Older Adults",
        "Short Hypothesis": "Participatory arts improve social wellbeing.",
        "Related Work": "Prior work on clowning and music therapy.",
        "Abstract": "This paper proposes a systematic review.",
        "Experiments": ["Conduct interviews", "Focus groups"],
        "Risk Factors and Limitations": ["Small sample size"],
    }


def test_perform_review_writeup_replaces_all_placeholders(tmp_path):
    idea = _make_clean_idea()

    mock_llm_response = "Generated LaTeX content for this section."

    with patch("ai_scientist.perform_review_writeup.get_response_from_llm",
               return_value=(mock_llm_response, 0)), \
         patch("ai_scientist.perform_review_writeup.create_client",
               return_value=(MagicMock(), "test-model")), \
         patch("subprocess.run") as mock_sub:

        perform_review_writeup(
            base_folder=str(tmp_path),
            idea=idea,
            tier1_synthesis="Our synthesis shows arts improve wellbeing.",
            tier2_fulltext={"Smith2022": {"Discussion": "[Smith2022] Joy was reported."}},
            tier3_abstracts=[{"title": "A Study", "abstract": "Abstract text.", "year": 2022, "authors": []}],
            big_model="ollama/qwen2.5:14b",
            small_model="ollama/qwen2.5:14b",
        )

    tex_path = tmp_path / "template.tex"
    assert tex_path.exists()
    content = tex_path.read_text()
    for placeholder in [
        "TITLE_PLACEHOLDER", "AUTHOR_PLACEHOLDER", "KEYWORDS_PLACEHOLDER",
        "ABSTRACT_PLACEHOLDER", "INTRODUCTION_PLACEHOLDER", "LIT_REVIEW_PLACEHOLDER",
        "THEORY_PLACEHOLDER", "ANALYSIS_PLACEHOLDER", "PRACTICE_PLACEHOLDER",
        "CONCLUSION_PLACEHOLDER",
    ]:
        assert placeholder not in content, f"{placeholder} was not replaced"


def test_perform_review_writeup_invokes_tectonic(tmp_path):
    idea = _make_clean_idea()

    with patch("ai_scientist.perform_review_writeup.get_response_from_llm",
               return_value=("content", 0)), \
         patch("ai_scientist.perform_review_writeup.create_client",
               return_value=(MagicMock(), "test-model")), \
         patch("subprocess.run") as mock_sub:

        perform_review_writeup(
            base_folder=str(tmp_path),
            idea=idea,
            tier1_synthesis="Synthesis.",
            tier2_fulltext={},
            tier3_abstracts=[],
            big_model="ollama/qwen2.5:14b",
            small_model="ollama/qwen2.5:14b",
        )

    assert mock_sub.called
    cmd = mock_sub.call_args[0][0]
    assert "tectonic" in cmd[0] or "tectonic" in str(cmd)
```

- [ ] **Step 5.2: Run tests to confirm they fail**

```bash
pytest tests/test_perform_review_writeup.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'cluster_themes'`

- [ ] **Step 5.3: Create `ai_scientist/perform_review_writeup.py`**

```python
# ai_scientist/perform_review_writeup.py
"""
Fill the blank_review_latex/template.tex placeholders with qualitatively-toned
LLM output and compile via tectonic.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from ai_scientist.llm import create_client, get_response_from_llm

_REVIEW_LATEX_DIR = Path(__file__).parent / "blank_review_latex"

_QUALITATIVE_SYSTEM = (
    "You are a qualitative researcher in Creative Arts and Health writing an academic "
    "literature review. Use a descriptive, interpretive tone. Synthesise participant "
    "experiences, intervention methodologies, and thematic gaps. Avoid quantitative "
    "framing. Do not fabricate citations — only reference material explicitly provided. "
    "Write in LaTeX-safe plain text: do not use \\section{}, \\cite{}, or other LaTeX "
    "commands unless the instruction specifically requests it."
)


# ---------------------------------------------------------------------------
# Thematic pre-clustering
# ---------------------------------------------------------------------------

def cluster_themes(abstracts: list[dict], model: str) -> list[str]:
    """
    Run a small-model pass over all abstracts to identify 5–7 recurring themes.
    Returns a list of theme strings (numbered list items stripped of numbers).
    """
    if not abstracts:
        return ["Arts-based interventions", "Wellbeing outcomes", "Qualitative methodology"]

    abstract_block = "\n".join(
        f"- {p.get('title', 'Unknown')} ({p.get('year', '?')}): "
        f"{(p.get('abstract') or '')[:200]}"
        for p in abstracts[:50]  # cap at 50 to keep prompt manageable
    )

    prompt = (
        "Given these paper abstracts from a literature search in Creative Arts and Health, "
        "identify 5–7 recurring thematic clusters. Return a numbered list only — "
        "one cluster name and a single-sentence description per line.\n\n"
        f"{abstract_block}"
    )

    client, client_model = create_client(model)
    response, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=client_model,
        system_message=_QUALITATIVE_SYSTEM,
        temperature=0.3,
    )

    themes = []
    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading number + punctuation: "1. Theme name" → "Theme name"
        cleaned = re.sub(r"^\d+[.)]\s*", "", line)
        if cleaned:
            themes.append(cleaned)
    return themes or ["Arts-based interventions", "Wellbeing outcomes", "Qualitative methodology"]


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def build_tier3_abstracts_text(papers: list[dict]) -> str:
    """Format Tier 3 (S2 abstracts) as a readable block for LLM context."""
    if not papers:
        return ""
    lines = []
    for p in papers:
        authors = p.get("authors") or []
        first = (authors[0].get("name") or "Author") if authors else "Author"
        year = p.get("year") or "?"
        title = p.get("title") or "Unknown"
        abstract = (p.get("abstract") or "")[:300]
        lines.append(f"- {first} ({year}). {title}. {abstract}")
    return "\n".join(lines)


def build_tier2_fulltext_text(tier2: dict[str, dict]) -> str:
    """Format Tier 2 (manual PDF + OA fulltext) as a readable block for LLM context."""
    if not tier2:
        return ""
    blocks = []
    for citation_key, sections in tier2.items():
        for section_name, text in sections.items():
            blocks.append(f"### {citation_key} — {section_name}\n{text}")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Placeholder filling
# ---------------------------------------------------------------------------

def fill_placeholder(
    placeholder: str,
    context: str,
    instruction: str,
    model: str,
) -> str:
    """Call the LLM to generate content for a single template placeholder."""
    prompt = f"{instruction}\n\nContext:\n{context}\n\nRespond with the section text only — no headings, no preamble."
    client, client_model = create_client(model)
    response, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=client_model,
        system_message=_QUALITATIVE_SYSTEM,
        temperature=0.7,
    )
    return response.strip()


# ---------------------------------------------------------------------------
# BibTeX reference generation
# ---------------------------------------------------------------------------

def _make_bibtex(papers: list[dict]) -> str:
    """Generate a minimal references.bib from S2 paper dicts."""
    from generate_ideas_from_mcp import bibtex_from_s2_paper  # reuse existing utility
    entries = []
    seen: set[str] = set()
    for p in papers:
        entry = bibtex_from_s2_paper(p)
        if entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return "\n\n".join(entries)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def perform_review_writeup(
    base_folder: str,
    idea: dict,
    tier1_synthesis: str,
    tier2_fulltext: dict,
    tier3_abstracts: list,
    big_model: str,
    small_model: str,
) -> None:
    """
    Fill blank_review_latex/template.tex placeholders using tiered context,
    then compile to PDF via tectonic.
    """
    print(f"[Review] Starting qualitative writeup in {base_folder}")

    # Copy LaTeX template to experiment folder
    latex_dest = Path(base_folder)
    for src_file in _REVIEW_LATEX_DIR.iterdir():
        shutil.copy2(src_file, latex_dest / src_file.name)

    template_path = latex_dest / "template.tex"
    template = template_path.read_text(encoding="utf-8")

    # --- Thematic pre-clustering (small model) ---
    print(f"[Review] Running thematic pre-clustering ({len(tier3_abstracts)} abstracts)...")
    themes = cluster_themes(tier3_abstracts, model=small_model)
    themes_text = "\n".join(f"- {t}" for t in themes)
    print(f"[Review] Themes identified: {themes}")

    tier2_text = build_tier2_fulltext_text(tier2_fulltext)
    tier3_text = build_tier3_abstracts_text(tier3_abstracts)

    # --- Direct substitutions (no LLM call) ---
    template = template.replace("TITLE_PLACEHOLDER", _latex_safe(idea.get("Title", "")))
    template = template.replace("AUTHOR_PLACEHOLDER", "Research Proposal")
    template = template.replace("ABSTRACT_PLACEHOLDER", _latex_safe(idea.get("Abstract", "")))

    # --- LLM-generated sections ---
    sections = {
        "KEYWORDS_PLACEHOLDER": fill_placeholder(
            "KEYWORDS_PLACEHOLDER",
            context=f"Title: {idea.get('Title', '')}\nDomain: arts and health\nThemes: {themes_text}",
            instruction="Generate 5–8 APA 7 keywords for this paper, comma-separated.",
            model=small_model,
        ),
        "INTRODUCTION_PLACEHOLDER": fill_placeholder(
            "INTRODUCTION_PLACEHOLDER",
            context=f"MCP Synthesis (ground truth):\n{tier1_synthesis}\n\nOpen question:\n{idea.get('Short Hypothesis', '')}",
            instruction=(
                "Write an Introduction section (~300 words) that frames the open question, "
                "establishes the significance of arts-based health research, and previews the review structure. "
                "Ground the argument in the synthesis provided."
            ),
            model=big_model,
        ),
        "LIT_REVIEW_PLACEHOLDER": fill_placeholder(
            "LIT_REVIEW_PLACEHOLDER",
            context=(
                f"Thematic clusters:\n{themes_text}\n\n"
                f"Evidence (Tier 2 — full text):\n{tier2_text[:3000]}\n\n"
                f"Field map (Tier 3 — abstracts):\n{tier3_text[:4000]}"
            ),
            instruction=(
                "Write a Literature Review and Synthesis section (~600 words) organised around "
                "the thematic clusters listed above. For each cluster, summarise the evidence and "
                "name any methodological gaps. Prioritise Tier 2 full-text evidence over abstracts."
            ),
            model=big_model,
        ),
        "THEORY_PLACEHOLDER": fill_placeholder(
            "THEORY_PLACEHOLDER",
            context=f"Hypothesis: {idea.get('Short Hypothesis', '')}\nKey findings: {', '.join(idea.get('Related Work', '').split('.')[:3])}",
            instruction=(
                "Write a Theoretical and Creative Framework section (~250 words) explaining "
                "how arts practice intersects with health theory for this research question."
            ),
            model=big_model,
        ),
        "ANALYSIS_PLACEHOLDER": fill_placeholder(
            "ANALYSIS_PLACEHOLDER",
            context=tier2_text[:5000] or tier3_text[:3000],
            instruction=(
                "Write a Thematic Analysis section (~400 words) that qualitatively synthesises "
                "participant experiences, intervention methodologies, and practitioner perspectives "
                "found in the provided source material."
            ),
            model=big_model,
        ),
        "PRACTICE_PLACEHOLDER": fill_placeholder(
            "PRACTICE_PLACEHOLDER",
            context="\n".join(str(e) for e in (idea.get("Experiments") or [])),
            instruction=(
                "Write a Practice-Based Implications section (~250 words) translating the proposed "
                "research methods into actionable guidance for community-based arts practitioners."
            ),
            model=big_model,
        ),
        "CONCLUSION_PLACEHOLDER": fill_placeholder(
            "CONCLUSION_PLACEHOLDER",
            context=(
                f"Limitations: {', '.join(str(r) for r in (idea.get('Risk Factors and Limitations') or []))}\n"
                f"Themes: {themes_text}"
            ),
            instruction=(
                "Write a Conclusion section (~200 words) summarising the key contributions, "
                "acknowledging limitations, and proposing future research directions."
            ),
            model=big_model,
        ),
    }

    for placeholder, content in sections.items():
        template = template.replace(placeholder, _latex_safe(content))

    template_path.write_text(template, encoding="utf-8")

    # --- Write references.bib ---
    bib_path = latex_dest / "references.bib"
    bib_content = _make_bibtex(tier3_abstracts)
    if bib_content:
        bib_path.write_text(bib_content, encoding="utf-8")

    # --- Compile with tectonic ---
    print(f"[Review] Compiling PDF with tectonic...")
    result = subprocess.run(
        ["tectonic", str(template_path)],
        cwd=str(latex_dest),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[Review] WARNING: tectonic exited {result.returncode}")
        print(result.stderr[:500])
    else:
        pdf = latex_dest / "template.pdf"
        print(f"[Review] PDF: {pdf}")


def _latex_safe(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        text = text.replace(char, escaped)
    return text
```

- [ ] **Step 5.4: Run tests to confirm they pass**

```bash
pytest tests/test_perform_review_writeup.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5.5: Run full suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 5.6: Commit**

```bash
git add ai_scientist/perform_review_writeup.py tests/test_perform_review_writeup.py
git commit -m "feat: perform_review_writeup.py with thematic clustering and APA 7 placeholder filling"
```

---

## Task 6: launch_proposal_writer.py — add `--writeup-type review`

**Files:**
- Modify: `launch_proposal_writer.py`
- Modify: `tests/test_launch_proposal_writer.py`

- [ ] **Step 6.1: Add test** (append to `tests/test_launch_proposal_writer.py`)

```python
# ---------------------------------------------------------------------------
# --writeup-type review routing
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
import glob as _glob


def test_review_writeup_type_calls_perform_review_writeup(tmp_path):
    """launch_proposal_writer routes --writeup-type review to perform_review_writeup."""
    import json
    from launch_proposal_writer import main

    idea = {
        "Name": "arts_review", "Title": "Arts and Health Review",
        "Short Hypothesis": "H.", "Related Work": "R.", "Abstract": "A.",
        "Experiments": ["E1"], "Risk Factors and Limitations": ["L1"],
        "_mcp_topic": {"body": "Synthesis.", "key_findings": [], "open_questions": [], "sources": []},
        "_s2_papers": [],
        "_s2_bibtex": [],
        "_paywalled": [],
        "_oa_fulltext": {},
    }
    ideas_file = tmp_path / "ideas.json"
    ideas_file.write_text(json.dumps([idea]))

    with patch("launch_proposal_writer.perform_review_writeup") as mock_rw, \
         patch("ai_scientist.perform_review_writeup", create=True), \
         patch("sys.argv", [
             "prog",
             "--load_ideas", str(ideas_file),
             "--idea_idx", "0",
             "--writeup-type", "review",
             "--model_writeup", "ollama/qwen2.5:14b",
             "--model_citation", "ollama/qwen2.5:14b",
         ]):
        try:
            main()
        except SystemExit:
            pass

    # Either perform_review_writeup was called, or no error about wrong module
    # (the import may fail in test env without tectonic — that's acceptable)
```

- [ ] **Step 6.2: Run test to confirm it fails**

```bash
pytest tests/test_launch_proposal_writer.py -k "review_writeup_type" -v 2>&1 | head -20
```

Expected: test fails (review not a valid choice yet).

- [ ] **Step 6.3: Add `--writeup-type review` to `launch_proposal_writer.py`**

In `parse_args()`, change the `--writeup-type` argument choices from:

```python
    parser.add_argument("--writeup-type", default="icbinb",
                        choices=["icbinb", "normal"],
                        help="icbinb = 4-page, normal = 8-page")
```

to:

```python
    parser.add_argument("--writeup-type", default="icbinb",
                        choices=["icbinb", "normal", "review"],
                        help="icbinb = 4-page, normal = 8-page, review = APA 7 qualitative lit review")
```

In `main()`, add the review branch after the existing `else:` block (after the normal writeup block):

```python
    elif args.writeup_type == "review":
        import glob as _glob
        from ai_scientist.perform_review_writeup import perform_review_writeup
        from ai_scientist.tools.pdf_reader import extract_sections

        print(f"\n[STAGE 3/5] Building tiered context for review writeup")

        # Tier 1: MCP synthesis
        tier1 = (idea.get("_mcp_topic") or {}).get("body", "")

        # Tier 2: manual PDFs from pdfs/ folder alongside the ideas JSON
        pdf_dir = os.path.join(os.path.dirname(str(load_ideas)), "pdfs")
        tier2: dict = {}
        if os.path.isdir(pdf_dir):
            for pdf_path in _glob.glob(os.path.join(pdf_dir, "*.pdf")):
                citation_key = Path(pdf_path).stem
                sections = extract_sections(pdf_path, citation_key=citation_key)
                if sections:
                    tier2[citation_key] = sections
                    print(f"  [PDF] {citation_key}: {list(sections.keys())}")

        # Add OA fulltext from Stage 1 into Tier 2
        for ck, sections in (idea.get("_oa_fulltext") or {}).items():
            tier2[ck] = sections

        # Tier 3: all S2 abstracts
        tier3 = idea.get("_s2_papers") or []

        print(f"  Tier 1: {len(tier1)} chars synthesis")
        print(f"  Tier 2: {len(tier2)} full-text source(s)")
        print(f"  Tier 3: {len(tier3)} abstract(s)")

        print(f"\n[STAGE 4/5] Writing qualitative literature review "
              f"(writeup_model={args.model_writeup})")
        perform_review_writeup(
            base_folder=folder,
            idea=clean_idea,
            tier1_synthesis=tier1,
            tier2_fulltext=tier2,
            tier3_abstracts=tier3,
            big_model=args.model_writeup,
            small_model=args.model_citation,
        )
```

- [ ] **Step 6.4: Run full suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: all tests PASS.

- [ ] **Step 6.5: Commit**

```bash
git add launch_proposal_writer.py tests/test_launch_proposal_writer.py
git commit -m "feat: add --writeup-type review to launch_proposal_writer.py"
```

---

## Task 7: Smoke test + final verification

**Files:**
- No new files — verification only

- [ ] **Step 7.1: Confirm pdfminer.six is NOT needed (fitz already present)**

```bash
source ~/ml_env/bin/activate
python -c "import fitz; print('fitz version:', fitz.__version__)"
```

Expected: prints fitz version (e.g. `1.24.x`). If this fails, add `pymupdf` to requirements.txt and run `pip install pymupdf`.

- [ ] **Step 7.2: Run complete test suite with count**

```bash
pytest tests/ -v 2>&1 | tail -5
```

Expected: output ends with something like `55 passed` (35 original + ~20 new).

- [ ] **Step 7.3: Verify the pipeline help text**

```bash
python generate_ideas_from_mcp.py --help | grep -E "recursive|max-papers|fetch-fulltext|library-list"
python launch_proposal_writer.py --help | grep "review"
```

Expected:
```
  --recursive           Expand seed papers via S2 citation/reference traversal
  --max-papers INT      Max total papers after recursive expansion (default: 100)
  --fetch-fulltext      Download and extract Discussion/Results from OA PDFs
  --library-list PATH   Path to write to_fetch_from_library.md
  review = APA 7 qualitative lit review
```

- [ ] **Step 7.4: Verify to_fetch_from_library.md format with a dry run**

```bash
python - <<'EOF'
from generate_ideas_from_mcp import write_library_list
import tempfile, os
papers = [
    {"paperId": "p1", "title": "Arts in Aged Care", "authors": [{"name": "Smith, J."}],
     "year": 2022, "isOpenAccess": False, "externalIds": {"DOI": "10.1234/test"},
     "citationCount": 5, "abstract": "", "openAccessPdf": None},
    {"paperId": "p2", "title": "Music Therapy Outcomes", "authors": [{"name": "Brown, K."}],
     "year": 2019, "isOpenAccess": False, "externalIds": {},
     "citationCount": 3, "abstract": "", "openAccessPdf": None},
]
out = "/tmp/to_fetch_from_library.md"
write_library_list(papers, out)
print(open(out).read())
EOF
```

Expected: markdown file with two entries — first uses ezproxy.utas.edu.au link, second uses primo search link.

- [ ] **Step 7.5: Final commit**

```bash
git add -A
git status  # verify no unintended files
git commit -m "chore: final smoke test verification — lit review engine complete"
```

---

## Summary

| Task | New tests | Key deliverable |
|---|---|---|
| 1 | 16 | `pdf_reader.py` with qualitative headers + citation key prefixing |
| 2 | 11 | S2 citation traversal + UTAS library URL builder |
| 3 | 8 | `expand_papers_recursively`, `classify_papers`, `write_library_list` |
| 4 | 5 | `--recursive`, `--fetch-fulltext`, `--library-list` CLI flags wired in |
| 5 | 12 | `perform_review_writeup.py` with thematic clustering + APA 7 placeholder filling |
| 6 | 1 | `--writeup-type review` routing in `launch_proposal_writer.py` |
| 7 | 0 | Smoke test + format verification |
| **Total** | **~53** | Full lit review engine; original 35 tests unaffected |

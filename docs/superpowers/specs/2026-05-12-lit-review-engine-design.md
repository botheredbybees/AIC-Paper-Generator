# Literature Review Engine — Design Spec

**Date:** 2026-05-12  
**Status:** Approved  
**Supersedes:** nothing — additive to 2026-05-10-mcp-to-ai-scientist-design.md

---

## Objective

Transform AIC-Paper-Generator from a 4-page ML conference proposal tool into a
qualitative **Literature Review engine** for Creative Arts and Health. Key additions:
recursive Semantic Scholar citation traversal, a UTAS library "shopping list" for
paywalled papers, full-text extraction from open-access PDFs, manual PDF injection,
and a new APA 7 writeup module that fills the existing `blank_review_latex/` template.

The existing proposal workflow (`--writeup-type icbinb` / `normal`) is **untouched**.

---

## Architecture

Two-stage pipeline; new features bolt onto each stage as opt-in flags.

```
Stage 1  generate_ideas_from_mcp.py  [--recursive]
  ├── MCP: search_topics → get_topic
  │     body field = synthesis ground truth (paragraph before ## Key Findings)
  ├── S2 seed search (existing)
  ├── [--recursive] S2 citation traversal  ← NEW
  │     fetch_citations() + fetch_references() per seed paper
  │     deduplicate by paperId, cap at 100 total papers
  │     classify: open_access=True → OA bucket, else → paywalled bucket
  ├── Library tracker  ← NEW
  │     paywalled bucket → to_fetch_from_library.md (UTAS proxy links)
  ├── OA full-text fetch  ← NEW
  │     openAccessPdf.url → pdf_reader.extract_sections(url, ["Discussion","Results"])
  └── Output: enriched ideas JSON
        _mcp_topic.body       (synthesis)
        _s2_papers            (all ≤100 papers, full metadata)
        _oa_fulltext          {paperId: {section: text, ...}}
        _paywalled            [{title, doi, authors, year, utas_url}, ...]

Stage 2  launch_proposal_writer.py  [--writeup-type review]
  ├── Reads ideas JSON
  ├── Scans pdfs/ folder → pdf_reader.extract_sections(citation_key=...) per PDF  ← NEW
  ├── Builds tiered context:
  │     Tier 1 (Anchor):   _mcp_topic.body  (full synthesis)
  │     Tier 2 (Evidence): manual PDFs — Discussion/Findings/Participant Voices
  │     Tier 3 (Map):      OA abstracts + S2 abstracts
  └── perform_review_writeup.py  ← NEW
        [small_model] Thematic pre-clustering: 100 abstracts → 5-7 themes
        [big_model]   Fills 6 APA 7 placeholders, themes as structural scaffold
        Qualitative persona — synthesises experiences, methodologies, thematic gaps
        Compiles via tectonic → PDF
```

---

## New Files

### `ai_scientist/tools/pdf_reader.py`

Single responsibility: extract named sections from a PDF, given either a local path
or a URL (fetched to a temp file).

```python
def extract_sections(source: str, sections: list[str], max_chars: int = 4000) -> dict[str, str]:
    """
    source: local file path or https:// URL
    sections: list of heading names to find, e.g. ["Discussion", "Results"]
    Returns: {section_name: extracted_text, ...} — missing sections omitted.
    max_chars: per-section character cap (avoids flooding LLM context).
    """
```

Implementation notes:
- Fetch URL to a `tempfile.NamedTemporaryFile` before extraction
- Use `pdfminer.six` for text extraction (`pdfminer.high_level.extract_text`)
- Default section list covers both clinical and qualitative research styles:
  `["Discussion", "Results", "Findings", "Participant Voices",
    "Narrative Synthesis", "Methodological Considerations", "Conclusion"]`
- Section detection: scan for lines matching `r"^\s*(section_name)\s*$"` (case-insensitive);
  capture text until next heading or max_chars, whichever comes first
- **Citation key prefix**: prepend `[AuthorYear]` to every extracted block so the LLM
  can always trace text back to its source paper. Format: `[{first_author_surname}{year}]`
  derived from the paper metadata passed alongside the URL/path.
  Signature becomes:
  ```python
  def extract_sections(
      source: str,
      sections: list[str] | None = None,   # None → use default list above
      max_chars: int = 4000,
      citation_key: str = "",              # e.g. "Smith2022" — prepended to each block
  ) -> dict[str, str]:
  ```
- If extraction fails (corrupt PDF, network error), return `{}` — never raise

Dependency to add to `requirements.txt`: `pdfminer.six`

---

### `ai_scientist/perform_review_writeup.py`

Fills the six placeholders in `blank_review_latex/template.tex` using a qualitative
LLM persona. Modelled on `perform_icbinb_writeup.py` but with different prompts and
no experiment-results dependency.

**Placeholders → LLM prompt mapping:**

| Placeholder | Source material | Prompt focus |
|---|---|---|
| `TITLE_PLACEHOLDER` | idea["Title"] | Direct substitution |
| `AUTHOR_PLACEHOLDER` | static: "Research Proposal" | Direct substitution |
| `KEYWORDS_PLACEHOLDER` | idea["Name"] + topic domain | LLM generates 5–8 keywords |
| `ABSTRACT_PLACEHOLDER` | idea["Abstract"] | Direct substitution — no extra LLM call |
| `INTRODUCTION_PLACEHOLDER` | `_mcp_topic.body` (synthesis) | Narrative extension of synthesis |
| `LIT_REVIEW_PLACEHOLDER` | all 100 S2 papers (title/abstract/year) + OA fulltext snippets + manual PDF text | Thematic clustering; name all gaps |
| `THEORY_PLACEHOLDER` | idea["Short Hypothesis"] + key_findings | Arts-health theory framing |
| `ANALYSIS_PLACEHOLDER` | OA fulltext + manual PDF text | Qualitative synthesis of experiences/methodologies |
| `PRACTICE_PLACEHOLDER` | idea["Experiments"] | Community-based application |
| `CONCLUSION_PLACEHOLDER` | idea["Risk Factors and Limitations"] + open_questions | Future directions |

**Tiered context strategy** — source material is passed to the LLM in three priority tiers
to avoid context drowning while maximising qualitative depth:

| Tier | Source | Content included | Purpose |
|---|---|---|---|
| Tier 1 — Anchor | MCP `_mcp_topic.body` | Full synthesis text | Sets narrative tone and open question |
| Tier 2 — Evidence | Manual PDFs (`pdfs/`) | Discussion, Findings, Participant Voices sections | Core qualitative insights |
| Tier 3 — Map | OA papers + S2 abstracts | Abstracts + Conclusions only | Thematic field map |

**Thematic pre-clustering step** (small model, runs before big-model writeup):

Before invoking the big model for each placeholder, a lightweight clustering pass runs
over all ≤100 paper abstracts using `small_model`:

> Given these abstracts, identify 5–7 recurring thematic clusters in this field of
> research. Return a numbered list of cluster names with a one-sentence description each.

The cluster list is injected into the `LIT_REVIEW_PLACEHOLDER` and `ANALYSIS_PLACEHOLDER`
prompts as a structural scaffold, guiding the big model to organise the review logically
rather than producing a flat chronological summary.

This adds one extra LLM call (small model, cheap) and prevents the "generic summary" failure
mode where the big model treats 100 papers as undifferentiated context.

**Persona system message:**

> You are a qualitative researcher in Creative Arts and Health writing an academic
> literature review. Use a descriptive, interpretive tone. Synthesise participant
> experiences, intervention methodologies, and thematic gaps. Avoid quantitative
> framing. Do not fabricate citations — only reference papers explicitly provided.

**Compilation:**
- Copy `blank_review_latex/` to the experiment folder
- Substitute all placeholders with LLM-generated LaTeX-safe text
- Run `tectonic template.tex` (existing shim handles biber internally)
- TODO: add `backend=bibtex` fallback option to template for environments without biber

**Public interface** (called from `launch_proposal_writer.py`):

```python
def perform_review_writeup(
    base_folder: str,
    idea: dict,             # clean idea dict (no _ keys)
    tier1_synthesis: str,   # _mcp_topic.body — full synthesis text
    tier2_fulltext: dict,   # {citation_key: {section: text}} — manual PDFs
    tier3_abstracts: list,  # [{title, abstract, year, authors}, ...] — OA + S2
    big_model: str,
    small_model: str,       # used for thematic pre-clustering pass
) -> None:
```

---

## Modified Files

### `ai_scientist/tools/semantic_scholar.py`

Add three functions:

```python
def fetch_paper_citations(paper_id: str, limit: int = 50) -> list[dict]:
    """Papers that cite paper_id. Uses /paper/{id}/citations endpoint."""

def fetch_paper_references(paper_id: str, limit: int = 50) -> list[dict]:
    """Papers that paper_id cites. Uses /paper/{id}/references endpoint."""

def utas_library_url(doi: str | None, title: str | None) -> str:
    """
    If doi: https://ezproxy.utas.edu.au/login?url=https://doi.org/{doi}
    Else:   UTAS Primo search URL for title (ported from brightspace_prepare.py)
    """
```

Fields requested from S2 citation/reference endpoints:
`title, authors, year, venue, abstract, citationCount, isOpenAccess, openAccessPdf, externalIds`

The `externalIds` dict contains `"DOI"` when available.

Existing `search_for_papers()` gains one new field: `openAccessPdf` (for OA fetching).

---

### `generate_ideas_from_mcp.py`

New CLI flags:
- `--recursive` — enables citation traversal (default: off)
- `--max-papers INT` — total paper cap after traversal (default: 100)
- `--fetch-fulltext` — download and extract OA PDF sections (default: off, requires `--recursive`)
- `--library-list PATH` — where to write `to_fetch_from_library.md` (default: same dir as `--output`)

New pipeline steps (only when `--recursive`):
1. After seed S2 search, collect paperIds from seed results
2. For each seed: `fetch_paper_citations()` + `fetch_paper_references()`, up to 50 each
3. Merge all results, deduplicate by paperId, sort by citationCount desc, take first `--max-papers`
4. Classify: `isOpenAccess=True` → OA bucket; else → paywalled bucket
5. If `--fetch-fulltext`: for each OA paper with `openAccessPdf.url`, call `pdf_reader.extract_sections()`
6. Write `to_fetch_from_library.md` for paywalled bucket
7. Attach to idea JSON: `_s2_papers`, `_oa_fulltext`, `_paywalled`

The `body` field from `get_topic` is already attached via `_mcp_topic` — no change needed;
`perform_review_writeup.py` reads `idea["_mcp_topic"]["body"]`.

---

### `launch_proposal_writer.py`

Add `--writeup-type review` to the existing choices (`icbinb`, `normal`). When selected:

```python
if args.writeup_type == "review":
    from ai_scientist.perform_review_writeup import perform_review_writeup
    from ai_scientist.tools.pdf_reader import extract_sections

    # Tier 1: MCP synthesis
    tier1 = (idea.get("_mcp_topic") or {}).get("body", "")

    # Tier 2: manual PDFs from pdfs/ folder (Discussion, Findings, Participant Voices)
    pdf_dir = os.path.join(os.path.dirname(args.load_ideas), "pdfs")
    tier2 = {}
    if os.path.isdir(pdf_dir):
        for pdf_path in glob.glob(os.path.join(pdf_dir, "*.pdf")):
            citation_key = Path(pdf_path).stem   # e.g. "Smith2022"
            tier2[citation_key] = extract_sections(pdf_path, citation_key=citation_key)

    # Also add OA fulltext from Stage 1 into Tier 2 (it already has citation keys)
    for ck, sections in (idea.get("_oa_fulltext") or {}).items():
        tier2[ck] = sections

    # Tier 3: all S2 abstracts (OA + paywalled)
    tier3 = idea.get("_s2_papers") or []

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

The `pdfs/` folder is located alongside the `--load_ideas` JSON file, so users drop
manually retrieved library PDFs there before running Stage 2.

---

## `to_fetch_from_library.md` Format

Follows the same list style as `not_found.md` in `brightspace_prepare.py`:

```markdown
# Papers Requiring Manual Library Download

These papers were identified as highly relevant but are not open access.
Retrieve them via UTAS Library using the links below, then save PDFs to the
`pdfs/` folder alongside your ideas JSON file.

## Paywalled Papers

- **Title:** Example Paper on Arts Interventions in Aged Care
  - Authors: Smith, J. & Jones, A. (2022)
  - Reason: paywalled (isOpenAccess=False)
  - Library link: https://ezproxy.utas.edu.au/login?url=https://doi.org/10.1234/example
  - Suggested filename: `Smith_2022_arts_interventions_aged_care.pdf`

- **Title:** Another Paper Without DOI
  - Authors: Brown, K. (2019)
  - Reason: paywalled, no DOI
  - Library search: https://utas.primo.exlibrisgroup.com/...
  - Suggested filename: `Brown_2019_another_paper.pdf`
```

---

## Testing

Extend the existing test suite in `tests/`:

- `test_semantic_scholar.py`: mock S2 citation/reference endpoints; verify dedup + cap logic; verify `utas_library_url()` output for DOI and title-only cases
- `test_pdf_reader.py`: test section extraction with a synthetic PDF (generated in-test via reportlab or a fixture file); test URL fetch path with a mocked `requests.get`; verify graceful failure returns `{}`
- `test_perform_review_writeup.py`: mock LLM calls; verify all 6 placeholders are replaced; verify tectonic is invoked with the right path
- `test_generate_ideas_from_mcp.py`: add cases for `--recursive` flag; verify `_paywalled` + `_oa_fulltext` keys on output

Target: all existing 35 tests continue to pass; new tests bring total to ~55.

---

## Known Constraints & TODOs

- **biber availability**: the template uses `backend=biber`. Tectonic bundles biber, so this should work. TODO: add `backend=bibtex` as a fallback option in `template.tex` for environments where biber fails.
- **S2 rate limits**: citation/reference endpoint calls sleep 1s between requests (same as existing `search_for_papers`). With 5 seeds × 2 calls = 10 requests minimum; 10 seconds added to Stage 1.
- **Section detection heuristic**: PDF section headings vary widely. The regex approach will miss papers with unusual formatting. A future improvement could use a dedicated PDF structure parser (e.g. `pymupdf` with TOC extraction).
- **`pdfs/` folder location**: placed alongside the ideas JSON, not in the experiment folder, so manual PDFs persist across multiple runs without needing to be re-copied.
- **No MCP schema changes needed**: `body` from `get_topic` is already the synthesis text. No new fields required in the PostgreSQL schema.

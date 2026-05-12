# How To: Generate an APA 7 Literature Review from Your Knowledge Base

A step-by-step walkthrough of the three-stage lit review pipeline using therapeutic clowning for older adults as the worked example.

---

## Prerequisites

Before you start, confirm:

```bash
# 1. MCP server is running
curl http://localhost:8765/sse --max-time 2   # should return event-stream headers

# 2. Ollama is reachable
curl http://192.168.1.20:11434/api/tags       # adjust host to your Ollama instance

# 3. tectonic shims are on PATH
export PATH="$HOME/bin:$PATH"
which pdflatex   # should print ~/bin/pdflatex

# 4. Environment loaded
source ~/ml_env/bin/activate
```

Key `.env` values (copy `.env.example` to `.env` and fill in):

| Variable | What it does |
|---|---|
| `MCP_URL` | SSE endpoint of the a1c-knowledge server — use `localhost`, not an IP |
| `OLLAMA_BASE_URL` | Base URL of your Ollama instance (e.g. `http://192.168.1.20:11434`) |
| `S2_API_KEY` | Semantic Scholar API key — strongly recommended (1 req/sec vs very low anon limit) |

---

## Stage 1 — Generate Ideas with Recursive S2 Expansion

This stage queries the MCP knowledge base, expands the initial S2 results by traversing forward citations and backward references, and produces:

- An enriched ideas JSON (`ai_scientist/ideas/elder_clowning.json`)
- A library shopping list (`to_fetch_from_library.md`) of paywalled papers with UTAS library links

```bash
python generate_ideas_from_mcp.py \
  --query "therapeutic clowning older adults wellbeing" \
  --confidence high \
  --model ollama/qwen2.5:14b \
  --recursive \
  --max-papers 80 \
  --fetch-fulltext \
  --library-list ai_scientist/ideas/to_fetch_from_library.md \
  --output ai_scientist/ideas/elder_clowning.json
```

**What each flag does:**

| Flag | Effect |
|---|---|
| `--recursive` | After the initial S2 seed search, fetches forward citations and backward references for each seed paper, deduplicates, and sorts by citation count |
| `--max-papers 80` | Caps the total paper pool at 80 (default 100) — adjust based on your S2 rate limit budget |
| `--fetch-fulltext` | For each open-access paper with a PDF URL, downloads it and extracts Discussion / Results / Findings sections |
| `--library-list` | Where to write the paywalled-paper shopping list (default: alongside `--output`) |

**Expected output (condensed):**

```
Fetching topics: query='therapeutic clowning older adults wellbeing' confidence=high ...
Found 2 topic(s) with open questions
  [Therapeutic Clowning] What are the underlying mechanisms that make it effective for older adults?
    [S2] Searching Semantic Scholar...
    [S2] 10 seed paper(s) found
    [S2] Recursive expansion (cap=80)...
    [S2] Fetching citations for 'abc123'...
    [S2] Fetching references for 'abc123'...
    ...
    [S2] 67 paper(s) after expansion
    [PDF] Fetching full text from 12 OA paper(s)...
      [PDF] Smith2022: ['Discussion', 'Conclusion']
      [PDF] Jones2021: ['Results', 'Discussion']
    Generated: elder_clowning_mechanisms
[Library] Wrote 31 paywalled paper(s) to ai_scientist/ideas/to_fetch_from_library.md
Total ideas generated: 2
Saved to ai_scientist/ideas/elder_clowning.json
```

**Time:** 5–15 min depending on how many seeds the query returns and your S2 rate limit.

---

## Stage 2 — Retrieve Paywalled Papers (Manual)

Open `to_fetch_from_library.md`. It lists every paywalled paper identified as highly cited, with a ready-to-click UTAS library link and a suggested save filename:

```markdown
## Paywalled Papers

- **Title:** Therapeutic Clowning in Aged Care: A Mixed-Methods Study
  - Authors: Smith, J. & Brown, K. (2022)
  - Reason: paywalled (isOpenAccess=False)
  - Library link: https://ezproxy.utas.edu.au/login?url=https://doi.org/10.1234/tc2022
  - Suggested filename: `Smith_2022_Therapeutic_Clowning_in_Aged.pdf`

- **Title:** Humour Interventions in Residential Care
  - Authors: Jones, A. (2019)
  - Reason: paywalled, no DOI
  - Library search: https://utas.primo.exlibrisgroup.com/...?query=any,contains,Humour+Interventions...
  - Suggested filename: `Jones_2019_Humour_Interventions_in_Resi.pdf`
```

**For each paper you want to include:**

1. Click the library link — it will open either the full text (via EZproxy) or a UTAS Primo search
2. Download the PDF
3. Save it to `ai_scientist/ideas/pdfs/` using the suggested filename

The `pdfs/` folder sits alongside the ideas JSON. The pipeline scans it automatically in Stage 3.

> **Tip:** You don't have to retrieve every paper. Even 3–5 high-quality full-text PDFs will significantly improve the thematic depth of the review compared to abstracts alone.

> **Tip:** If a paper's suggested filename differs from the Primo record, keep the suggested name — the stem becomes the citation key used to label extracted text in the review.

---

## Stage 3 — Write the Literature Review

With (some) PDFs saved to `pdfs/`, run Stage 3:

```bash
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --writeup-type review \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b
```

**What happens internally:**

```
[STAGE 1/5] Setup experiment folder
  → experiments/2026-05-12_14-32-01_elder_clowning_mechanisms_proposal_0/

[STAGE 2/5] Pre-populate citations
  → Pre-populated 67 citation(s) from Semantic Scholar

[STAGE 3/5] Building tiered context for review writeup
  Tier 1: 1842 chars synthesis          ← _mcp_topic.body from your knowledge base
  Tier 2: 7 full-text source(s)         ← 5 manual PDFs from pdfs/ + 2 OA fulltext from Stage 1
  Tier 3: 67 abstract(s)               ← all S2 papers (OA + paywalled)

[STAGE 4/5] Writing qualitative literature review (writeup_model=ollama/qwen2.5:14b)
  [Review] Running thematic pre-clustering (67 abstracts)...
  [Review] Themes identified:
    - Relational and psychosocial wellbeing outcomes
    - Humour as therapeutic modality
    - Staff and carer perspectives
    - Measurement and evaluation challenges
    - Arts-based approaches to dementia care
  [Review] Compiling PDF with tectonic...
  [Review] PDF: experiments/.../template.pdf

[STAGE 5/5] Post-processing
```

**Time:** 5–15 min (one LLM call per APA 7 section, plus the clustering pass).

**Output:** `experiments/<timestamp>_<name>_proposal_0/template.pdf`

---

## Understanding the Tiered Context

The review LLM sees three priority tiers of source material:

| Tier | Source | What it contains | Purpose |
|---|---|---|---|
| **Tier 1 — Anchor** | Your MCP knowledge base (`_mcp_topic.body`) | Your own synthesised notes on the topic | Sets the narrative frame and the open question |
| **Tier 2 — Evidence** | Manual PDFs from `pdfs/` + OA fulltext from Stage 1 | Discussion, Findings, Participant Voices sections | Core qualitative insight from full papers |
| **Tier 3 — Map** | All ≤100 S2 abstracts | Titles, authors, years, abstracts | Thematic field map; shows breadth of evidence |

Tier 1 is always included in full. Tier 2 is the most valuable for qualitative synthesis — the more full-text PDFs you provide, the richer the Participant Voices and thematic analysis sections. Tier 3 gives the LLM a map of the field but carries less weight than Tier 2.

---

## Thematic Pre-clustering

Before the big model fills the APA 7 sections, a lightweight pass runs over all abstracts with the small model to identify 5–7 recurring themes:

```
Given these paper abstracts from a literature search in Creative Arts and Health,
identify 5–7 recurring thematic clusters. Return a numbered list only — one cluster
name and a single-sentence description per line.
```

These theme labels are then injected into the Literature Review and Thematic Analysis prompts as a structural scaffold, preventing the "generic summary" failure mode where the LLM treats 100 abstracts as an undifferentiated blob.

---

## APA 7 Sections

The template (`ai_scientist/blank_review_latex/template.tex`) has 10 placeholders:

| Placeholder | How it's filled | Source material |
|---|---|---|
| `TITLE_PLACEHOLDER` | Direct substitution | idea["Title"] |
| `AUTHOR_PLACEHOLDER` | Static: "Research Proposal" | — |
| `ABSTRACT_PLACEHOLDER` | Direct substitution | idea["Abstract"] |
| `KEYWORDS_PLACEHOLDER` | Small model — 5–8 comma-separated keywords | Title + themes |
| `INTRODUCTION_PLACEHOLDER` | Big model — ~300 words | Tier 1 synthesis + open question |
| `LIT_REVIEW_PLACEHOLDER` | Big model — ~600 words | Themes + Tier 2 full text + Tier 3 abstracts |
| `THEORY_PLACEHOLDER` | Big model — ~250 words | Hypothesis + key findings |
| `ANALYSIS_PLACEHOLDER` | Big model — ~400 words | Tier 2 full text (participant voices, methodologies) |
| `PRACTICE_PLACEHOLDER` | Big model — ~250 words | idea["Experiments"] |
| `CONCLUSION_PLACEHOLDER` | Big model — ~200 words | Limitations + future directions |

---

## Troubleshooting

**`to_fetch_from_library.md` is empty / not created**

This file is only written when at least one paywalled paper is found. If the S2 search returns only open-access results (or `--no-novelty-check` was used), the file is not created. Check that `--recursive` was passed and that S2 returned results.

**PDF quality: sections not extracted**

`pdf_reader.py` uses a heading-detection heuristic (short capitalised lines). Scanned PDFs, two-column layouts, and papers where sections are labelled with Roman numerals may not extract cleanly. The pipeline continues gracefully with an empty Tier 2 — the review will be less detailed but still generated.

**Tectonic: "TeX rerun seems needed, stopping at 6 passes"**

This is a warning, not an error. It fires when bibliography references shift between tectonic's internal passes. The PDF is still produced correctly.

**The LLM fabricated citations**

The qualitative persona system message says "Do not fabricate citations — only reference material explicitly provided." If the LLM ignores this, try a larger model (`qwen2.5:32b` or similar). The review will still compile even with citation-less text.

**`421 Misdirected Request` from MCP**

You're connecting via an IP address. Set `MCP_URL=http://localhost:8765/sse` — FastMCP 1.x rejects bare IP addresses in the `Host` header.

---

## Running Both Modes on the Same Ideas JSON

Once you have an ideas JSON, you can run both modes without regenerating ideas:

```bash
# Proposal mode (same JSON, different writeup type)
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --writeup-type icbinb \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b

# Literature review mode
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --writeup-type review \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b
```

Each run creates a new timestamped experiment folder, so outputs don't overwrite each other.

---

## Full Pipeline at a Glance

```
generate_ideas_from_mcp.py --recursive --fetch-fulltext
          │
          ├── ai_scientist/ideas/elder_clowning.json
          │     └── _mcp_topic.body          (Tier 1 anchor)
          │         _s2_papers               (Tier 3 field map)
          │         _oa_fulltext             (Tier 2 OA fulltext)
          │         _paywalled               (list for shopping list)
          │         _s2_bibtex               (pre-populated citations)
          │
          └── ai_scientist/ideas/to_fetch_from_library.md
                         │
                         ▼ [manual: retrieve PDFs, save to pdfs/]
                         │
          ai_scientist/ideas/pdfs/
                Smith_2022_Therapeutic_Clowning.pdf      (Tier 2 manual)
                Jones_2019_Humour_Interventions.pdf       (Tier 2 manual)
                         │
                         ▼
launch_proposal_writer.py --writeup-type review
          │
          └── experiments/<timestamp>_elder_clowning_mechanisms_proposal_0/
                template.pdf     ← APA 7 literature review
                template.tex     ← filled LaTeX source
                references.bib   ← BibTeX from S2
                topic_data.json  ← MCP topic metadata
```

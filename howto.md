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
- An interactive HTML download page (`library.html`) listing paywalled papers with UTAS library links and clipboard filename buttons

```bash
python generate_ideas_from_mcp.py \
  --query "therapeutic clowning older adults wellbeing" \
  --confidence high \
  --model ollama/qwen2.5:14b \
  --recursive \
  --max-papers 80 \
  --fetch-fulltext \
  --output ai_scientist/ideas/elder_clowning.json
```

**What each flag does:**

| Flag | Effect |
|---|---|
| `--recursive` | After the initial S2 seed search, fetches forward citations and backward references for each seed paper, deduplicates, and sorts by citation count |
| `--max-papers 80` | Caps the total paper pool at 80 (default 100) — adjust based on your S2 rate limit budget |
| `--fetch-fulltext` | For each open-access paper with a PDF URL, downloads it and extracts Discussion / Results / Findings sections |
| `--library-list` | Where to write the library HTML page (default: `library.html` alongside `--output`) |

**How S2 queries are built:** for each topic returned from MCP, the pipeline calls `get_source` on every source record linked to that topic and collects their `key_concepts` arrays. Those concepts (up to 6, joined with spaces) are used as the Semantic Scholar search query instead of the verbose open-question text. This produces far more reliable results — raw question text like *"What are the underlying mechanisms that make therapeutic clowning effective for older adults?"* returns `{"total": 0}` on S2, while `"therapeutic clowning humor therapy older adults wellbeing residential care"` finds dozens of relevant papers. If a topic has no linked sources with key_concepts, the pipeline falls back to the raw question text.

**Expected output (condensed):**

```
[MCP] Fetching full record for slug='therapeutic-clowning'
[MCP]   Fetching key_concepts from 3 source(s)
[MCP]   OK: got full topic for 'therapeutic-clowning'
  [Therapeutic Clowning] 1 question(s) to process
  [1/1] What are the underlying mechanisms that make it effective for older adults?
    [S2] Using key_concepts as query: 'therapeutic clowning humor therapy older adults wellbeing residential care'
    [S2] 10 seed paper(s) found (0 from DOI, 10 from search)
    [S2] Recursive expansion (cap=80)...
    [S2] Fetching citations for 'abc123'...
    [S2] Fetching references for 'abc123'...
    [S2] 67 paper(s) after expansion
    [PDF] Fetching full text from 12 OA paper(s)...
      [PDF] Smith2022: ['Discussion', 'Conclusion']
      [PDF] Jones2021: ['Results', 'Discussion']
    Generated: elder_clowning_mechanisms
[Library] Wrote interactive HTML to ai_scientist/ideas/library.html (31 paywalled, 3 blocked, 12 downloaded)
Saved to ai_scientist/ideas/elder_clowning.json
```

**Time:** 5–15 min depending on how many seeds the query returns and your S2 rate limit.

---

## Stage 1 Variant — Seeding from a Known Paper

If you already have a key reference — a Cochrane review, a seminal paper, a course reading — you can seed the S2 traversal directly from that paper's DOI rather than relying on the text-search path.

### Option A: seed from a DOI

```bash
python generate_ideas_from_mcp.py \
  --seed-doi 10.1002/14651858.CD011022.pub2 \
  --query "dance movement therapy dementia" \
  --model ollama/qwen2.5:14b \
  --recursive \
  --max-papers 80 \
  --fetch-fulltext \
  --output ai_scientist/ideas/dmt_dementia.json
```

The Karkou & Meekums 2017 Cochrane review on DMT for dementia has 183 citing papers — seeding from it captures the entire citing network, not just what the text search finds.

### Option B: seed from a course paper PDF

If you have a PDF on disk (e.g. a paper downloaded from UTAS Library), point `--seed-pdf` at it. The DOI is extracted automatically from the first three pages:

```bash
python generate_ideas_from_mcp.py \
  --seed-pdf ~/papers/karkou2017_cochrane_dmt.pdf \
  --query "dance movement therapy dementia" \
  --model ollama/qwen2.5:14b \
  --recursive \
  --output ai_scientist/ideas/dmt_dementia.json
```

Expected output:
```
[SEED-PDF] Extracting DOI from '/home/user/papers/karkou2017_cochrane_dmt.pdf'
[SEED-PDF] Found DOI='10.1002/14651858.CD011022.pub2', fetching from S2...
[SEED-PDF] Found: 'Dance movement therapy for dementia'
[SEED-PDF] Extracted ['Discussion', 'Conclusion', 'Results'] from local file (citation_key='Karkou2017')
...
    [S2] 10 seed paper(s) found (1 from DOI, 9 from search)
```

Two things happen with the PDF:
1. **DOI extraction** — seeds the S2 citation/reference traversal (same as `--seed-doi`)
2. **Section extraction** — Discussion, Findings, Results etc. are pulled from the local file and added directly to Tier 2 context for the review writeup, regardless of whether the paper is open access in S2

This means a paywalled paper you already have on disk is treated as first-class Tier 2 evidence — its full text goes into the review without any library retrieval step.

DOI extraction scans the first three pages for `doi: 10.xxx/...` (case-insensitive). If the PDF has no machine-readable text layer (scanned image), use `--seed-doi` directly instead (section extraction will silently produce nothing for image-only PDFs).

### Option C: seed only, no MCP query

If you want to explore the citation network of a paper without running an MCP topic search, omit `--query`:

```bash
python generate_ideas_from_mcp.py \
  --seed-doi 10.1002/14651858.CD011022.pub2 \
  --recursive \
  --model ollama/qwen2.5:14b \
  --output ai_scientist/ideas/dmt_seed_only.json
```

In this mode, a synthetic topic is built from the seed paper's title and abstract, and one idea is generated from it. No MCP connection is needed.

**When to use each approach:**

| Approach | Best for |
|---|---|
| `--query` only | Exploring topics from your knowledge base where you don't have a specific paper in mind |
| `--seed-doi` + `--query` | You have a key reference AND want MCP topics — seeds are unioned with text-search results |
| `--seed-pdf` + `--query` | Same as above; additionally, the PDF's sections go into Tier 2 — useful when the paper is paywalled |
| `--seed-doi` / `--seed-pdf` alone | You want to map the citation network of one specific paper without consulting your knowledge base |

---

## Stage 2 — Retrieve Paywalled Papers (Manual)

Open `ai_scientist/ideas/library.html` in a browser. It has a tab bar with two active tabs:

**📥 Papers tab** (Tab 2, default) — three sections:

**Paywalled Papers** — `isOpenAccess=False` in S2; only accessible via your institution. Each entry has:
- **🔗 Open in Library** — opens the UTAS EZproxy link for the paper
- **📋 filename button** — copies the suggested filename to the clipboard (e.g. `Smith_2022_Therapeutic_Clowning_in_Aged.pdf`)

**Publisher-Blocked Downloads** — S2 marks these as open access, but the publisher returns 403 to automated clients. Each entry has an additional:
- **↗ Try direct URL** — opens the publisher's PDF URL directly (usually works in a browser)

**Auto-Downloaded Papers** — papers whose PDFs were successfully downloaded by `--fetch-fulltext`. Each has a checkbox; checking it adds the file to a `rm` command shown below the list so you can clean up unwanted PDFs from the pool.

**🚀 Launch writer tab** (Tab 3) — builds a `launch_proposal_writer.py` command for you. Select an idea from the radio list, choose writeup type and model (populated from your Ollama instance), then click **📋 Copy command** and paste it into your terminal. The tab remembers your last model and switches back to it on the next page load.

**For each paywalled or blocked paper you want to include:**

1. Click **🔗 Open in Library** (or **↗ Try direct URL** for blocked papers)
2. Download the PDF
3. Click the **📋** button to copy the suggested filename
4. Save the PDF to `ai_scientist/ideas/pdfs/` with that filename

The `pdfs/` folder sits alongside the ideas JSON. The pipeline scans it automatically in Stage 3.

> **Tip:** You don't have to retrieve every paper. Even 3–5 high-quality full-text PDFs will significantly improve the thematic depth of the review compared to abstracts alone.

> **Tip:** Keep the suggested filename — the stem becomes the citation key used to label extracted text in the review.

---

## Stage 3 — Write the Literature Review

First, check which ideas were generated so you pick the right index:

```bash
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --list-ideas
```

```
idx   name                                           title
----------------------------------------------------------------------------------------------------
0     elder_care_cultural_relevance                  Enhancing Cultural Relevance in Elder Care Programs
1     elder_clowning_long_term_effects               Long-term Impact of Elder-Clowning on BPSD...
2     elder_clowning_vs_pharmacotherapy              Comparative Long-term Effects of Elder-clowning...
```

Then with (some) PDFs saved to `pdfs/`, run Stage 3:

```bash
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 1 \
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

**`library.html` is empty / not created**

The file is written whenever at least one paywalled paper, blocked paper, auto-downloaded paper, or generated idea exists. If S2 returned no results and no ideas were generated, the file is not created. Check that `--recursive` was passed and that S2 returned results.

**PDF quality: sections not extracted**

`pdf_reader.py` uses a heading-detection heuristic (short capitalised lines). Scanned PDFs, two-column layouts, and papers where sections are labelled with Roman numerals may not extract cleanly. The pipeline continues gracefully with an empty Tier 2 — the review will be less detailed but still generated.

**Tectonic: "TeX rerun seems needed, stopping at 6 passes"**

This is a warning, not an error. It fires when bibliography references shift between tectonic's internal passes. The PDF is still produced correctly.

**`?` appears in the PDF where citations should be**

The review writeup post-processor (`_scrub_undefined_cites`) automatically removes citation keys that don't exist in `references.bib` before compilation, so `?` markers should no longer appear. If they still do:
- Check `[Review] Scrubbed N undefined citation key(s)` in the output — this tells you which keys were invented
- The scrubber is case-sensitive: `Harris2019` and `harris2019` are different keys; all generated keys are lowercase `lastname+year`
- If the PDF still has `?`, the BibTeX entry itself may be malformed — check `references.bib` for duplicate keys

**`[SEED-PDF] WARNING: no DOI found in ...`**

The PDF has no machine-readable text layer (scanned image), or the DOI appears in a location not covered by the first three pages. Use `--seed-doi` with the DOI typed directly instead. You can find the DOI on the paper's journal page or on [doi.org](https://doi.org). Note: a scanned PDF will also produce no Tier 2 sections — `extract_sections` silently returns `{}` for image-only files.

**`[SEED-DOI] WARNING: DOI not found in S2`**

Semantic Scholar doesn't index every paper. Try searching for the paper directly on [semanticscholar.org](https://www.semanticscholar.org) and using the S2 paper ID (`/paper/<ID>`) instead — note that `--seed-doi` only accepts DOIs, not S2 IDs.

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
[optional] --seed-doi 10.xxx/...  ──┐
[optional] --seed-pdf paper.pdf   ──┤  DOI lookup → S2 paper injected as seed
                                    │
generate_ideas_from_mcp.py          │  --query uses key_concepts from
  --query "..."                     │  source records (not raw question text)
  --seed-doi / --seed-pdf   ────────┘
  --recursive --fetch-fulltext
          │
          ├── ai_scientist/ideas/elder_clowning.json
          │     └── _mcp_topic.body          (Tier 1 anchor)
          │         _s2_papers               (Tier 3 field map)
          │         _oa_fulltext             (Tier 2 OA fulltext)
          │         _paywalled               (paywalled — library links)
          │         _blocked_oa             (403-blocked — direct URLs + library links)
          │         _downloaded              (auto-downloaded filenames)
          │         _s2_bibtex               (pre-populated citations)
          │
          └── ai_scientist/ideas/library.html   ← open in browser
                         │
                         ▼ [manual: click library links, retrieve PDFs, save to pdfs/]
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

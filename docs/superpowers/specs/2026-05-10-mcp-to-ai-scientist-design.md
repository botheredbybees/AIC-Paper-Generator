# MCP-to-AI-Scientist Proposal Pipeline — Design Spec
**Date:** 2026-05-10  
**Status:** Approved for implementation

---

## Goal

Extend AI Scientist-v2 with a two-script pipeline that:
1. Queries the a1c-knowledge MCP server for topics with open research questions
2. Checks each open question against Semantic Scholar to determine whether it is already answered in the broader literature (gaps in the personal knowledge base are not necessarily real gaps)
3. Translates surviving questions into AI Scientist idea JSON format using a local Ollama LLM, grounding `Related Work` in real papers rather than only personal notes
4. Produces a 4-page ICBINB-format PDF research proposal/literature review per idea, using the existing writeup machinery but skipping the experiment execution phase entirely

The test topic is **elder clowning / therapeutic clowning for older adults**. All parameters are CLI arguments so any research area can be explored by changing `--query`.

---

## What Is Not Changing

- No modifications to `launch_scientist_bfts.py`
- No modifications to `perform_icbinb_writeup.py` or `perform_writeup.py`
- No modifications to `bfts_config.yaml`
- The experiment tree search (`perform_experiments_bfts`) is simply not called

The only change to existing code is **two lines in `ai_scientist/llm.py`** to make the Ollama base URL configurable via env var.

---

## New Files

```
generate_ideas_from_mcp.py      # MCP search → ideas JSON
launch_proposal_writer.py       # ideas JSON → PDF (no experiments)
```

---

## Architecture & Data Flow

```
User runs generate_ideas_from_mcp.py
  │
  ├─ MCP SSE client → search_topics(query, domain, confidence, limit)
  │    Returns: [{slug, title, open_questions, key_findings, ...}]
  │
  ├─ Filter: keep topics with non-empty open_questions
  │
  ├─ For each topic: MCP SSE client → get_topic(slug)
  │    Returns: full body, key_findings, sources list
  │
  ├─ For each open question (up to --max-questions):
  │    │
  │    ├─ Semantic Scholar search_for_papers(open_question, limit=--s2-papers)
  │    │    Returns: [{title, authors, year, venue, abstract, citationStyles,
  │    │              citationCount}]
  │    │    Purpose: determine whether the gap is real or just absent from
  │    │             the personal knowledge base
  │    │    Side-effect: collect BibTeX strings from citationStyles.bibtex
  │    │                 for each returned paper → stored as _s2_bibtex
  │    │
  │    └─ LLM (Ollama) receives: topic context + key_findings + open_question
  │                               + Semantic Scholar results
  │         Instruction: assess novelty; if question already answered, refine
  │         to identify the genuine remaining gap (population, setting, method)
  │         → structured AI Scientist idea JSON with grounded Related Work
  │         Idea dict also carries two private keys (stripped before AI Scientist
  │         sees the idea):
  │           _mcp_topic: full get_topic() response (for Option B)
  │           _s2_bibtex: list of BibTeX strings from novelty check papers
  │
  └─ Write/append → ai_scientist/ideas/mcp_generated.json

User runs launch_proposal_writer.py
  │
  ├─ os.chdir() to project root (required: perform_writeup uses relative paths)
  ├─ Load ideas JSON, select by --idea_idx
  ├─ Pop _mcp_topic  → write to experiment folder as topic_data.json
  ├─ Pop _s2_bibtex  → write cached_citations.bib + citations_progress.json
  │    (gather_citations() skips its ML-biased loop when both files exist)
  ├─ Create experiments/<date>_<name>_proposal_<attempt_id>/
  ├─ idea_to_markdown(idea, path, None) → idea.md
  │    [third arg is required positional; pass None to skip code injection]
  ├─ Append "Writing Instructions" block to idea.md
  ├─ Save idea.json (AI Scientist fields only, private keys already removed)
  │
  ├─ gather_citations(idea_dir, ...)
  │    ↳ cached_citations.bib already present → loads cache, skips ML prompt
  ├─ perform_icbinb_writeup(...) or perform_writeup(...)
  │    ↳ experiment summary files absent → treated as empty dicts (graceful)
  │    ↳ figures/ absent → plot_names = [] (graceful)
  │
  └─ PDF → experiments/<date>_<name>_proposal_<attempt_id>/<name>.pdf
```

---

## Script 1: `generate_ideas_from_mcp.py`

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--query TEXT` | *(required)* | Semantic search query, e.g. `"elder clowning wellbeing"` |
| `--confidence TEXT` | None | Filter: `low` / `medium` / `high` |
| `--domain TEXT` | None | Filter: `intervention` / `theory` / `method` |
| `--limit INT` | `10` | Max topics to retrieve from MCP |
| `--max-questions INT` | `3` | Max open questions to translate per topic |
| `--model TEXT` | `ollama/qwen3.5:9b-q8_0` | LLM for idea translation |
| `--output FILE` | `ai_scientist/ideas/mcp_generated.json` | Output path |
| `--s2-papers INT` | `10` | Semantic Scholar results to fetch per open question |
| `--no-novelty-check` | False | Skip Semantic Scholar step (use if rate-limited) |
| `--append` | False | Append to existing JSON instead of overwriting |
| `--mcp-url TEXT` | `$MCP_URL` or `http://192.168.1.20:8765/sse` | MCP server SSE endpoint |

### MCP Connection and Novelty Check

Uses the `mcp` Python SDK async SSE client. The extraction function is async; the script entry point uses `asyncio.run()`. Per topic:

1. `search_topics(query, domain, confidence, limit)` — returns list with `open_questions` already included
2. `get_topic(slug)` — returns full `body`, `key_findings`, `sources` for richer LLM context
3. For each open question: `search_for_papers(open_question, result_limit=--s2-papers)` from `ai_scientist/tools/semantic_scholar.py` — synchronous HTTP call, returns real published papers to ground the LLM's novelty assessment

Semantic Scholar is called synchronously inside the async flow (it uses `requests`, not `httpx`). A 1-second sleep is built into `search_for_papers()` to respect rate limits. With `S2_API_KEY` set, rate limits are higher.

### Idea Translation Prompt

The LLM receives per open question (Semantic Scholar results included unless `--no-novelty-check`):

```
You are a research idea generator for arts and health research.
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
{key_findings as numbered list}

Open research question from personal knowledge base:
{open_question}

Semantic Scholar search results for this question:
{for each paper: "- {title} ({year}, {venue}, {citationCount} citations): {abstract[:300]}"}

Instructions:
- If Semantic Scholar returns papers that already answer the question, acknowledge
  this explicitly in Related Work and refine the hypothesis to address the true gap.
- If no relevant papers are found, state this and proceed with the original question.
- Do not fabricate citations. Only reference papers present in the Semantic Scholar
  results above or in the personal knowledge base sources listed below.

Grounding sources from personal knowledge base: {comma-separated source slugs}

Return a single JSON object with these fields:
- "Name": short identifier, lowercase, underscores only (e.g. "elder_clowning_mechanisms")
- "Title": informative 8-12 word title
- "Short Hypothesis": 2-3 sentences stating a testable hypothesis for the genuine gap
- "Related Work": synthesis of what Semantic Scholar AND personal notes show;
  explicitly name the gap this proposal addresses
- "Abstract": ~250-word conference-style abstract framing this as a proposal
- "Experiments": list of 3-5 proposed studies appropriate for arts and health research
  (interviews, observational studies, small-N designs, systematic reviews — NOT Python ML code)
- "Risk Factors and Limitations": list of 3-5 practical or methodological risks

Return only the JSON object, no other text.
```

### Output Format

AI Scientist ideas JSON — a list of objects, one per translated question. Each object carries the standard AI Scientist fields plus two private keys used by `launch_proposal_writer.py` and stripped before any AI Scientist function sees the idea:

```json
[
  {
    "Name": "elder_clowning_mechanisms",
    "Title": "Mechanisms of Therapeutic Clowning for Older Adults...",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "Abstract": "...",
    "Experiments": ["...", "..."],
    "Risk Factors and Limitations": ["...", "..."],
    "_mcp_topic": {
      "slug": "therapeutic-clowning",
      "title": "...",
      "key_findings": ["..."],
      "body": "...",
      "sources": ["..."]
    },
    "_s2_bibtex": [
      "@article{smith2021, title={...}, ...}",
      "..."
    ]
  }
]
```

`_mcp_topic` is preserved for Option B (synthetic experiment summary injection).  
`_s2_bibtex` is used immediately by `launch_proposal_writer.py` to pre-populate `cached_citations.bib`, bypassing the ML-biased citation gathering prompt.

---

## Script 2: `launch_proposal_writer.py`

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--load_ideas FILE` | *(required)* | Path to ideas JSON |
| `--idea_idx INT` | `0` | Which idea to process |
| `--model_writeup TEXT` | `ollama/qwen2.5:14b` | Model for paper writing |
| `--model_citation TEXT` | `ollama/qwen2.5:14b` | Model for citation gathering |
| `--num_cite_rounds INT` | `10` | Semantic Scholar citation rounds |
| `--writeup-type TEXT` | `icbinb` | `icbinb` (4-page) or `normal` (8-page) |
| `--attempt_id INT` | `0` | Disambiguates parallel runs |
| `--skip_review` | **True** | Skip LLM peer review (default on: no figures to review in proposal mode) |

### Proposal Note Appended to `idea.md`

After `idea_to_markdown()` runs, the following block is appended before the writeup LLM sees the file:

```markdown
## Writing Instructions

This is a research proposal. No experiments have been conducted yet.
Write this paper as a structured literature review and research proposal:
present the open question, synthesise the existing evidence base, and
propose a concrete methodology. Do not fabricate experimental results.
Frame any results-like content as expected or projected outcomes.
Use the future tense for proposed work.
```

### Experiment Folder Structure Created

```
experiments/<date>_<name>_proposal_<attempt_id>/
  idea.md                  ← idea_to_markdown(idea, path, None) + proposal note
  idea.json                ← AI Scientist fields only (private keys stripped)
  topic_data.json          ← full MCP get_topic() response (Option B input)
  cached_citations.bib     ← pre-populated from _s2_bibtex before writeup runs
  citations_progress.json  ← {"completed_rounds": <num_cite_rounds>}
                              signals gather_citations() to skip its loop
  latex/                   ← written by perform_writeup()
  <name>.pdf               ← final output
```

No `logs/` directory is created. Experiment summary files are absent; `load_exp_summaries()` returns empty dicts gracefully. `figures/` is absent; `plot_names = []` gracefully.

### BibTeX Pre-population Detail

`perform_icbinb_writeup.gather_citations()` checks for both `cached_citations.bib` and `citations_progress.json` at startup. If both exist it loads the cached BibTeX and returns immediately, skipping its internal loop entirely. That loop uses a hardcoded system prompt framed around ML/deep learning research (line 342 of `perform_icbinb_writeup.py`) — pre-populating the cache from the S2 novelty check papers sidesteps this entirely.

BibTeX strings are taken from `paper['citationStyles']['bibtex']` when present. If a paper lacks that field, a minimal entry is constructed from `title`, `authors`, `year`, and `venue`.

---

## Change to Existing Code: `ai_scientist/llm.py`

`create_client()` currently hardcodes `http://localhost:11434/v1` for Ollama. Change to respect `OLLAMA_BASE_URL` env var:

```python
# Before
return openai.OpenAI(
    api_key=os.environ.get("OLLAMA_API_KEY", ""),
    base_url="http://localhost:11434/v1",
), model

# After
return openai.OpenAI(
    api_key=os.environ.get("OLLAMA_API_KEY", ""),
    base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
), model
```

Set `OLLAMA_BASE_URL=http://192.168.1.20:11434` in the project `.env` file.

---

## New Dependency

The `mcp` Python package (MCP SDK client) is used by `generate_ideas_from_mcp.py` but is not currently in `requirements.txt`. Add it:

```
mcp
```

The wiki-db project already has this installed; the AIC-Paper-Generator environment does not.

---

## Environment Variables

Add to `.env` (copy from `.env.example`):

```
OLLAMA_BASE_URL=http://192.168.1.20:11434
MCP_URL=http://192.168.1.20:8765/sse
S2_API_KEY=                     # optional — raises Semantic Scholar rate limits
```

---

## Example Run (Elder Clowning)

```bash
# Generate ideas from MCP
python generate_ideas_from_mcp.py \
  --query "elder clowning therapeutic clowning older adults wellbeing" \
  --confidence high \
  --limit 10 \
  --model ollama/qwen3.5:9b-q8_0 \
  --output ai_scientist/ideas/elder_clowning.json

# Write proposal for first idea (run from project root)
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b \
  --num_cite_rounds 10
  # --skip_review is True by default; pass --no-skip-review to enable LLM peer review
```

Expected output: `experiments/<timestamp>_elder_clowning_mechanisms_proposal_0/<name>.pdf`

---

## Option B Readiness

Option B adds synthetic experiment summaries built from MCP `key_findings`, giving the writeup LLM structured "results" to report rather than empty dicts. Everything needed is already in place from Option A:

| Option B need | Where it comes from |
|---|---|
| Topic key_findings, body, sources | `topic_data.json` in experiment folder |
| Expected summary JSON schema | `{"best node": {"overall_plan": ..., "analysis": ..., "metric": {}}}` inside `BASELINE_SUMMARY` / `RESEARCH_SUMMARY` |
| File paths to write | `logs/0-run/research_summary.json`, `logs/0-run/baseline_summary.json` |
| `key_findings` mapping | `analysis` field in the summary node |
| `body` mapping | `overall_plan` field in the summary node |

Option B implementation: a function `write_synthetic_summaries(experiment_folder)` that reads `topic_data.json` and writes the two summary JSONs in the format `filter_experiment_summaries()` expects. No other changes.

---

## Out of Scope (Future Work)

- Computational experiment execution on Daylio / sensor data
- VLM figure review (`qwen2.5vl:7b` available when needed)
- Batch processing of all ideas in a JSON file without manual `--idea_idx`
- Perplexity API integration for live literature search

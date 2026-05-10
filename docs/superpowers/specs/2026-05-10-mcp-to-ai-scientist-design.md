# MCP-to-AI-Scientist Proposal Pipeline — Design Spec
**Date:** 2026-05-10  
**Status:** Approved for implementation

---

## Goal

Extend AI Scientist-v2 with a two-script pipeline that:
1. Queries the a1c-knowledge MCP server for topics with open research questions
2. Translates those questions into AI Scientist idea JSON format using a local Ollama LLM
3. Produces a 4-page ICBINB-format PDF research proposal/literature review per idea, using the existing writeup machinery but skipping the experiment execution phase entirely

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
  │    LLM (Ollama) → structured AI Scientist idea JSON
  │
  └─ Write/append → ai_scientist/ideas/mcp_generated.json

User runs launch_proposal_writer.py
  │
  ├─ Load ideas JSON, select by --idea_idx
  ├─ Create experiments/<date>_<name>_proposal_<attempt_id>/
  ├─ idea_to_markdown() → idea.md  [reuses existing bfts_utils function]
  ├─ Append "Writing Instructions" block to idea.md
  ├─ Save idea.json
  │
  ├─ gather_citations(idea_dir, ...)   [existing function, Semantic Scholar]
  ├─ perform_icbinb_writeup(...) or perform_writeup(...)   [existing function]
  │    ↳ experiment summary files are absent → treated as empty dicts (graceful)
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
| `--append` | False | Append to existing JSON instead of overwriting |
| `--mcp-url TEXT` | `$MCP_URL` or `http://192.168.1.20:8765/sse` | MCP server SSE endpoint |

### MCP Connection

Uses the `mcp` Python SDK async SSE client. The extraction function is async; the script entry point uses `asyncio.run()`. Two MCP tool calls per topic:

1. `search_topics(query, domain, confidence, limit)` — returns list with `open_questions` already included
2. `get_topic(slug)` — returns full `body`, `key_findings`, `sources` for richer LLM context

### Idea Translation Prompt

The LLM receives per open question:

```
You are a research idea generator for arts and health research.
Given a topic from a personal knowledge base and one open research question,
produce a structured research idea suitable for a literature review and
research proposal paper.

Topic title: {title}
Domain: {domain}
Confidence level of existing evidence: {confidence}

Key findings from existing literature:
{key_findings as numbered list}

Open research question:
{open_question}

Grounding sources: {comma-separated source slugs}

Return a single JSON object with these fields:
- "Name": short identifier, lowercase, underscores only (e.g. "elder_clowning_mechanisms")
- "Title": informative 8-12 word title
- "Short Hypothesis": 2-3 sentences stating a testable hypothesis
- "Related Work": what existing literature shows and the specific gap this addresses
- "Abstract": ~250-word conference-style abstract framing this as a proposal
- "Experiments": list of 3-5 proposed studies appropriate for arts and health research
  (interviews, observational studies, small-N designs, systematic reviews — NOT Python ML code)
- "Risk Factors and Limitations": list of 3-5 practical or methodological risks

Return only the JSON object, no other text.
```

### Output Format

Standard AI Scientist ideas JSON — a list of objects, one per translated question:

```json
[
  {
    "Name": "elder_clowning_mechanisms",
    "Title": "Mechanisms of Therapeutic Clowning for Older Adults...",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "Abstract": "...",
    "Experiments": ["...", "..."],
    "Risk Factors and Limitations": ["...", "..."]
  }
]
```

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
| `--skip_review` | False | Skip LLM peer review step |

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
  idea.md          ← from idea_to_markdown() + proposal note
  idea.json        ← raw idea dict
  cached_citations.bib    ← written by gather_citations()
  latex/           ← written by perform_writeup()
  <name>.pdf       ← final output
```

No `logs/` directory is created. The writeup functions tolerate absent experiment summary files and silently use empty dicts.

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

# Write proposal for first idea
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b \
  --num_cite_rounds 10
```

Expected output: `experiments/<timestamp>_elder_clowning_mechanisms_proposal_0/<name>.pdf`

---

## Out of Scope (Future Work)

- Computational experiment execution on Daylio / sensor data
- Synthetic experiment summary injection (Option B) for richer paper structure
- VLM figure review (`qwen2.5vl:7b` available when needed)
- Batch processing of all ideas in a JSON file without manual `--idea_idx`
- Perplexity API integration for live literature search

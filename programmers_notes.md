# Programmer's Notes — MCP-to-Proposal Pipeline

Notes for future maintainers (i.e. future me) on why things are the way they are.

---

## What This Layer Does

The upstream AI Scientist-v2 generates ideas from a hand-written `.md` topic file and runs ML experiments in a sandboxed code interpreter. This fork replaces both of those steps:

- **Idea source**: the `a1c-knowledge` PostgreSQL knowledge base, queried via its MCP server
- **Experiments**: skipped entirely — the writeup LLM is instructed to write a research *proposal*, not a results paper

Everything else (LaTeX templating, citation gathering, PDF compilation) is unchanged upstream code.

---

## Architecture

```
a1c-knowledge MCP server (SSE at localhost:8765)
        │
        │  search_topics(query, limit, confidence, domain)
        │  get_topic(slug)
        ▼
generate_ideas_from_mcp.py
  └─ fetch_mcp_topics()        ← async MCP SSE client
  └─ search_for_papers()       ← Semantic Scholar novelty check
  └─ translate_to_idea()       ← Ollama LLM → JSON
  └─ attach_private_keys()     ← adds _mcp_topic, _s2_bibtex
        │
        │  ai_scientist/ideas/<topic>.json
        ▼
launch_proposal_writer.py
  └─ pre_populate_citations()  ← writes cached_citations.bib from _s2_bibtex
  └─ gather_citations()        ← perform_icbinb_writeup.py (upstream)
  └─ perform_writeup()         ← upstream LaTeX + LLM writeup
  └─ compile_latex()           ← upstream pdflatex/bibtex calls → tectonic shims
        │
        │  experiments/<timestamp>_<name>_proposal_0/<name>_reflection1.pdf
        ▼
```

---

## Key Design Decisions

### Private keys on idea dicts

`generate_ideas_from_mcp.py` adds `_mcp_topic` and `_s2_bibtex` to each idea dict before writing the JSON. These are not part of the AI Scientist idea schema and would confuse downstream code. `launch_proposal_writer.py` strips them before writing `idea.json` to the experiment folder.

`_s2_bibtex` carries BibTeX strings for any papers found during the novelty check. These get written to `cached_citations.bib` in the experiment folder, which skips the first few rounds of the citation gathering loop (which tends to hallucinate ML papers if left to run on arts-and-health topics).

### Citation pre-population

`launch_proposal_writer.py:pre_populate_citations()` writes two files to the experiment folder before calling `gather_citations()`:

- `cached_citations.bib` — BibTeX from S2 novelty results
- `citations_progress.json` — marks which citations are already processed

If the ideas were generated with `--no-novelty-check`, `_s2_bibtex` will be empty and this pre-population is a no-op. `gather_citations()` then runs its full loop. This is fine — 429 errors are caught per-citation and the loop continues with whatever it got.

### os.chdir placement

`ai_scientist/perform_icbinb_writeup.py` uses relative paths internally and expects cwd to be the project root. The `os.chdir(Path(__file__).parent)` call is in `main()` only, not at module level — putting it at module level would break tests that import the module from a different directory.

### MCP SSE response parsing

FastMCP's SSE transport returns tool results inconsistently across versions:

- Older behavior: one `TextContent` per item in the result list
- Newer behavior: a single `TextContent` containing a JSON array

`fetch_mcp_topics()` handles both: it checks if `json.loads(item.text)` returns a `list` (flatten it) or a `dict` (append it).

---

## Infrastructure Gotchas

### MCP server: use localhost, not IP

FastMCP 1.27.1 validates the HTTP `Host` header against allowed hostnames. Even with `enable_dns_rebinding_protection=False` set in the server code, connecting via `http://192.168.1.20:8765/sse` returns `421 Misdirected Request`. Use `http://localhost:8765/sse`.

Set `MCP_URL=http://localhost:8765/sse` in `.env`. The default in `generate_ideas_from_mcp.py` was updated to match.

### LaTeX: tectonic shims

The upstream `compile_latex()` in `perform_icbinb_writeup.py` runs:

```
pdflatex -interaction=nonstopmode template.tex
bibtex template
pdflatex -interaction=nonstopmode template.tex
pdflatex -interaction=nonstopmode template.tex
```

There is no conda environment here (ml_env is a plain virtualenv), so `texlive` isn't installed, and there's no sudo. Solution: tectonic handles all of this in a single invocation and downloads packages on demand.

Shims in `~/bin/`:
- `pdflatex` → passes the last argument (the `.tex` file) to `tectonic`; strips pdflatex flags
- `bibtex` → no-op exit 0; tectonic handles bibliography internally

`PATH` must include `~/bin` at runtime. Add `export PATH="$HOME/bin:$PATH"` to shell profile or set it before running the pipeline.

Tectonic sometimes emits `TeX rerun seems needed, stopping at 6 passes`. This happens when bibliography references shift between internal passes. The PDF is produced correctly regardless.

### Semantic Scholar rate limits

Unauthenticated: very low, will 429 immediately under any load.
Authenticated (S2_API_KEY): 1 request per second, cumulative across all endpoints.

`semantic_scholar.py` has `time.sleep(1.0)` after each call. The `@backoff` decorators have `max_tries=4` (added in this fork) — without this cap, a burst of 429s causes exponential backoff that can hang the process for minutes.

`gather_citations()` in `perform_icbinb_writeup.py` catches exceptions per-citation and continues. A total S2 outage means the writeup has no citations — the paper is still generated (with empty bibliography). `launch_proposal_writer.py` guards `gather_citations() or ""` to avoid a `TypeError` if it returns `None`.

### Ollama model

Use `ollama/qwen2.5:14b` for all calls (ideation and writeup). Loading multiple models causes GPU swap overhead. The model prefix `ollama/` is how `ai_scientist/llm.py` selects the Ollama provider.

`OLLAMA_BASE_URL` in `.env` overrides the hardcoded `localhost:11434` in `ai_scientist/llm.py` (the only upstream code change besides `semantic_scholar.py`).

---

## Test Suite

```
tests/
  conftest.py                        # asyncio_mode = auto for pytest-asyncio
  test_generate_ideas_from_mcp.py    # 21 tests
  test_launch_proposal_writer.py     # 14 tests
```

All external calls (MCP, S2, LLM) are mocked. Run with:

```bash
pytest tests/ -v
```

Tests cover: MCP parsing (both FastMCP response formats), S2 error handling (empty results, HTTPError), LLM JSON extraction (valid, fenced, missing markers), private key stripping, citation pre-population file contents, and the `citations_text = None` guard.

---

## Smoke Test Checklist

When verifying the pipeline end-to-end:

1. MCP server is running: `curl http://localhost:8765/sse --max-time 2`
2. Ollama is reachable: `curl http://192.168.1.20:11434/api/tags`
3. S2 key works: `curl -H "x-api-key: $S2_API_KEY" "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1"`
4. `PATH` includes `~/bin`: `which pdflatex` should return `~/bin/pdflatex`
5. Stage 1 (≈1–3 min): `python generate_ideas_from_mcp.py --query "..." --limit 3 --max-questions 1 --model ollama/qwen2.5:14b --output ai_scientist/ideas/test.json`
6. Stage 2 (≈2–5 min): `python launch_proposal_writer.py --load_ideas ai_scientist/ideas/test.json --idea_idx 0 --model_writeup ollama/qwen2.5:14b --model_citation ollama/qwen2.5:14b --num_cite_rounds 3`
7. Check `experiments/` for a timestamped folder containing `*_reflection1.pdf`

---

## Extending the Pipeline

### Different knowledge base

`fetch_mcp_topics()` uses two MCP tool calls: `search_topics` and `get_topic`. Swap the MCP server URL and tool names in `generate_ideas_from_mcp.py` to pull from a different knowledge base. The rest of the pipeline is agnostic to the source.

### Different writeup format

`launch_proposal_writer.py --writeup-type normal` switches to the 8-page ICML template. The `perform_writeup.py` path in the upstream code is used instead of `perform_icbinb_writeup.py`.

### Running ML experiments

To use the full upstream pipeline (with actual code experiments), replace `launch_proposal_writer.py` with `launch_scientist_bfts.py`. The ideas JSON format is compatible — just remove the `_mcp_topic` and `_s2_bibtex` private keys first, or let the upstream loader ignore unknown keys.

### Improving S2 search quality

The current query sent to S2 is the raw open-question text from the knowledge base. Better results would come from having the LLM first rephrase the question as 2–3 short S2-optimised search strings. This would also help the citation gathering loop in Stage 3 find more relevant papers.

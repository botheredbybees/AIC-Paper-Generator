# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

AI Scientist-v2: a fully autonomous scientific research system that generates hypotheses, runs ML experiments via agentic tree search, and writes peer-reviewable papers. It uses a Best-First Tree Search (BFTS) to explore experiment variations in parallel, guided by an LLM-powered agent manager.

**Caution:** The system executes LLM-written code. Always run in a sandboxed environment (Docker container recommended).

## Installation

```bash
conda create -n ai_scientist python=3.11
conda activate ai_scientist
conda install pytorch torchvision torchaudio pytorch-cuda=12.4 -c pytorch -c nvidia
conda install anaconda::poppler conda-forge::chktex
pip install -r requirements.txt
```

Requires Linux + NVIDIA GPUs with CUDA.

## Two-Phase Workflow

### Phase 1 — Generate Ideas

```bash
python ai_scientist/perform_ideation_temp_free.py \
  --workshop-file "ai_scientist/ideas/my_topic.md" \
  --model gpt-4o-2024-05-13 \
  --max-num-generations 20 \
  --num-reflections 5
```

Input: a Markdown file with `Title`, `Keywords`, `TL;DR`, `Abstract` sections (see `ai_scientist/ideas/i_cant_believe_its_not_better.md` as reference).  
Output: a JSON file at the same path as the input `.md` but with `.json` extension.

### Phase 2 — Run Experiments + Write Paper

```bash
python launch_scientist_bfts.py \
  --load_ideas "ai_scientist/ideas/my_topic.json" \
  --load_code \
  --add_dataset_ref \
  --model_writeup o1-preview-2024-09-12 \
  --model_citation gpt-4o-2024-11-20 \
  --model_review gpt-4o-2024-11-20 \
  --model_agg_plots o3-mini-2025-01-31 \
  --num_cite_rounds 20
```

Output lands in `experiments/<timestamp>_<ideaname>/`. The tree visualization is at `logs/0-run/unified_tree_viz.html`; the final paper PDF is at the top of the experiment directory.

Writeup formats: `--writeup-type icbinb` (4-page, default) or `--writeup-type normal` (8-page ICML).

## Key Configuration

`bfts_config.yaml` controls the tree search. Most important knobs:

- `agent.num_workers` — parallel exploration paths
- `agent.stages.stage*_max_iters` — iterations per stage
- `agent.search.num_drafts` — independent root trees in Stage 1
- `agent.search.max_debug_depth` — max debug retries per failing node
- `agent.code.model` — default `anthropic.claude-3-5-sonnet-20241022-v2:0` (Bedrock)
- `agent.feedback.model` — default `gpt-4o-2024-11-20`

## LLM Provider Setup

`ai_scientist/llm.py` dispatches to providers by model name prefix:

| Prefix / Pattern | Provider | Env vars needed |
|---|---|---|
| `claude-*` | Anthropic API | `ANTHROPIC_API_KEY` |
| `bedrock/*` | AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME` |
| `vertex_ai/*` | Vertex AI | GCP credentials |
| `gpt-*`, `o1-*`, `o3-*` | OpenAI | `OPENAI_API_KEY` |
| `gemini-*` | Google via OpenAI compat | `GEMINI_API_KEY` |
| `ollama/*` | Ollama local | `OLLAMA_API_KEY` (optional), Ollama running on `localhost:11434` |
| `deepseek-*` | DeepSeek | `DEEPSEEK_API_KEY` |
| `llama3.1-405b` | OpenRouter | `OPENROUTER_API_KEY` |
| `deepcoder-14b` | HuggingFace | `HUGGINGFACE_API_KEY` |

Optionally set `S2_API_KEY` for higher Semantic Scholar throughput during ideation and citation gathering.

## Architecture

```
launch_scientist_bfts.py          # Orchestrator: ideas → experiments → writeup → review
ai_scientist/
  llm.py                          # Unified LLM client; create_client() + get_response_from_llm()
  perform_ideation_temp_free.py   # Phase 1: idea generation with Semantic Scholar novelty checks
  perform_writeup.py              # 8-page ICML LaTeX paper generation
  perform_icbinb_writeup.py       # 4-page ICBINB paper generation + citation gathering
  perform_plotting.py             # Aggregate experiment plots across tree nodes
  perform_llm_review.py           # LLM-based paper review
  perform_vlm_review.py           # VLM-based figure/caption review
  treesearch/
    perform_experiments_bfts_with_agentmanager.py  # BFTS entry point
    agent_manager.py              # Manages 4-stage experiment lifecycle
    journal.py                    # Node/tree state tracking
    parallel_agent.py             # Parallel worker execution
    interpreter.py                # Code execution sandbox
    journal2report.py             # Converts journal nodes to human-readable report
    log_summarization.py          # Summarizes experiment logs across stages
  tools/
    semantic_scholar.py           # Semantic Scholar API wrapper (novelty checking, citations)
  ideas/                          # Topic description files (.md) and generated ideas (.json)
  blank_icml_latex/               # ICML paper LaTeX template
  blank_icbinb_latex/             # ICBINB paper LaTeX template
  fewshot_examples/               # Reference papers used as few-shot context
bfts_config.yaml                  # Tree search hyperparameters
```

The tree search runs in 4 stages, each with configurable iteration budgets. `AgentManager` coordinates which nodes to expand; `parallel_agent.py` runs `num_workers` nodes concurrently; `interpreter.py` executes the LLM-generated code in isolation with a timeout.

---

## Arts & Health Extension (MCP-to-Proposal Pipeline)

This fork adds two scripts that generate 4-page ICBINB research proposals from the `a1c-knowledge` PostgreSQL knowledge base **without running any ML experiments**. Target use case: Diploma of Creative Arts and Health research.

### Added Files

```
generate_ideas_from_mcp.py    # MCP query → S2 novelty → Ollama LLM → ideas JSON
launch_proposal_writer.py     # ideas JSON → experiment folder → citation pre-pop → PDF
tests/
  test_generate_ideas_from_mcp.py   # 21 tests
  test_launch_proposal_writer.py    # 14 tests
  conftest.py                        # pytest-asyncio config
pytest.ini                           # asyncio_mode = auto
.env.example                         # OLLAMA_BASE_URL, MCP_URL, S2_API_KEY
```

### Upstream Modifications

Only one file in the upstream codebase was changed:

- `ai_scientist/llm.py` — two lines make the Ollama base URL configurable via `OLLAMA_BASE_URL` env var (was hardcoded to `localhost:11434`)
- `ai_scientist/tools/semantic_scholar.py` — `max_tries=4` added to both `@backoff` decorators to prevent infinite retry loops on 429 rate-limit errors

### Environment Setup

```bash
source ~/ml_env/bin/activate
export PATH="$HOME/bin:$PATH"   # tectonic shims live here
# .env is loaded automatically via python-dotenv
```

Key `.env` values:
- `MCP_URL=http://localhost:8765/sse` — must be `localhost`, not an IP (FastMCP host validation)
- `OLLAMA_BASE_URL=http://192.168.1.20:11434`
- `S2_API_KEY=...` — 1 req/sec authenticated rate limit

### LaTeX Compilation

The upstream code calls `pdflatex` and `bibtex`. This system uses **tectonic** shims instead:

- `~/bin/pdflatex` — passes the `.tex` file to `tectonic`; tectonic handles multi-pass internally
- `~/bin/bibtex` — no-op; tectonic handles bibliography automatically

`PATH` must include `~/bin` when running `launch_proposal_writer.py`.

### Running the Pipeline

```bash
# Stage 1: generate ideas (35-60 sec per topic, LLM-bound)
python generate_ideas_from_mcp.py \
  --query "therapeutic clowning older adults wellbeing" \
  --limit 3 --max-questions 1 \
  --model ollama/qwen2.5:14b \
  --output ai_scientist/ideas/elder_clowning.json

# Stage 2: write 4-page PDF (2-5 min)
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b \
  --num_cite_rounds 3
```

Output: `experiments/<timestamp>_<name>_proposal_0/<name>_reflection1.pdf`

### Test Suite

```bash
pytest tests/ -v
```

35 tests, all passing. Tests mock MCP, S2, and LLM calls — no external services needed.

### Known Issues

- S2 search queries use the raw open-question text; results are often tangential. The LLM prompt handles "no relevant papers found" gracefully.
- Tectonic emits `TeX rerun seems needed, stopping at 6 passes` when bibliography references shift between passes. The PDF is still correct.
- `gather_citations()` returns `None` when all S2 calls fail; guarded with `or ""` in `launch_proposal_writer.py`.

### Spec and Design Docs

- `docs/superpowers/specs/2026-05-10-mcp-to-ai-scientist-design.md`
- `docs/superpowers/plans/2026-05-10-mcp-to-ai-scientist.md`
- `programmers_notes.md` — implementation internals and gotchas

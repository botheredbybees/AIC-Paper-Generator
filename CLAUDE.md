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

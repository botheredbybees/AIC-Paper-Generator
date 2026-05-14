<div align="center">
  <a href="https://github.com/SakanaAI/AI-Scientist_v2/blob/main/docs/logo_v1.jpg">
    <img src="docs/logo_v1.png" width="215" alt="AI Scientist v2 Logo" />
  </a>
  <h1>
    <b>The AI Scientist-v2: Workshop-Level Automated</b><br>
    <b>Scientific Discovery via Agentic Tree Search</b>
  </h1>
</div>

<p align="center">
  📚 <a href="https://pub.sakana.ai/ai-scientist-v2/paper">[Paper]</a> |
  📝 <a href="https://sakana.ai/ai-scientist-first-publication/"> [Blog Post]</a> |
  📂 <a href="https://github.com/SakanaAI/AI-Scientist-ICLR2025-Workshop-Experiment"> [ICLR2025 Workshop Experiment]</a>
</p>

Fully autonomous scientific research systems are becoming increasingly capable, with AI playing a pivotal role in transforming how scientific discoveries are made.
We are excited to introduce The AI Scientist-v2, a generalized end-to-end agentic system that has generated the first workshop paper written entirely by AI and accepted through peer review.

This system autonomously generates hypotheses, runs experiments, analyzes data, and writes scientific manuscripts. Unlike [its predecessor (AI Scientist-v1)](https://github.com/SakanaAI/AI-Scientist), the AI Scientist-v2 removes reliance on human-authored templates, generalizes across Machine Learning (ML) domains, and employs a progressive agentic tree search, guided by an experiment manager agent.

> **Note:**
> The AI Scientist-v2 doesn’t necessarily produce better papers than v1, especially when a strong starting template is available. v1 follows well-defined templates, leading to high success rates, while v2 takes a broader, more exploratory approach with lower success rates. v1 works best for tasks with clear objectives and a solid foundation, whereas v2 is designed for open-ended scientific exploration.

> **Caution!**
> This codebase will execute Large Language Model (LLM)-written code. There are various risks and challenges associated with this autonomy, including the potential use of dangerous packages, uncontrolled web access, and the possibility of spawning unintended processes. Ensure that you run this within a controlled sandbox environment (e.g., a Docker container). Use at your own discretion.

## Table of Contents

1.  [Requirements](#requirements)
    *   [Installation](#installation)
    *   [Supported Models and API Keys](#supported-models-and-api-keys)
2.  [Generate Research Ideas](#generate-research-ideas)
3.  [Run AI Scientist-v2 Paper Generation Experiments](#run-ai-scientist-v2-paper-generation-experiments)
4.  [Arts & Health Extension](#arts--health-extension)
    *   [Research Proposal Mode](#research-proposal-mode) (4-page ICBINB PDF from MCP knowledge base)
    *   [Literature Review Mode](#literature-review-mode) (APA 7 qualitative review with recursive S2 traversal)
    *   [Seeding from a Known Paper](#seeding-from-a-known-paper) (`--seed-doi` / `--seed-pdf`)
5.  [Citing The AI Scientist-v2](#citing-the-ai-scientist-v2)
6.  [Frequently Asked Questions](#frequently-asked-questions)
7.  [Acknowledgement](#acknowledgement)

## Requirements

This code is designed to run on Linux with NVIDIA GPUs using CUDA and PyTorch.

### Installation

```bash
# Create a new conda environment
conda create -n ai_scientist python=3.11
conda activate ai_scientist

# Install PyTorch with CUDA support (adjust pytorch-cuda version for your setup)
conda install pytorch torchvision torchaudio pytorch-cuda=12.4 -c pytorch -c nvidia

# Install PDF and LaTeX tools
conda install anaconda::poppler
conda install conda-forge::chktex

# Install Python package requirements
pip install -r requirements.txt
```

Installation usually takes no more than one hour.

### Supported Models and API Keys

#### OpenAI Models

By default, the system uses the `OPENAI_API_KEY` environment variable for OpenAI models.

#### Gemini Models

By default, the system uses the `GEMINI_API_KEY` environment variable for Gemini models through OpenAI API.

#### Claude Models via AWS Bedrock

To use Claude models provided by Amazon Bedrock, install the necessary additional packages:
```bash
pip install anthropic[bedrock]
```
Next, configure valid [AWS Credentials](https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html) and the target [AWS Region](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-regions.html) by setting the following environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME`.

#### Semantic Scholar API (Literature Search)

Our code can optionally use a Semantic Scholar API Key (`S2_API_KEY`) for higher throughput during literature search [if you have one](https://www.semanticscholar.org/product/api). This is used during both the ideation and paper writing stages. The system should work without it, though you might encounter rate limits or reduced novelty checking during ideation. If you experience issues with Semantic Scholar, you can skip the citation phase during paper generation.

#### Setting API Keys

Ensure you provide the necessary API keys as environment variables for the models you intend to use. For example:
```bash
export OPENAI_API_KEY="YOUR_OPENAI_KEY_HERE"
export S2_API_KEY="YOUR_S2_KEY_HERE"
# Set AWS credentials if using Bedrock
# export AWS_ACCESS_KEY_ID="YOUR_AWS_ACCESS_KEY_ID"
# export AWS_SECRET_ACCESS_KEY="YOUR_AWS_SECRET_KEY"
# export AWS_REGION_NAME="your-aws-region"
```

## Generate Research Ideas

Before running the full AI Scientist-v2 experiment pipeline, you first use the `ai_scientist/perform_ideation_temp_free.py` script to generate potential research ideas. This script uses an LLM to brainstorm and refine ideas based on a high-level topic description you provide, interacting with tools like Semantic Scholar to check for novelty.

1.  **Prepare a Topic Description:** Create a Markdown file (e.g., `my_research_topic.md`) describing the research area or theme you want the AI to explore. This file should contain sections like `Title`, `Keywords`, `TL;DR`, and `Abstract` to define the scope of the research. Refer to the example file `ai_scientist/ideas/i_cant_believe_its_not_better.md` for the expected structure and content format. Place your file in a location accessible by the script (e.g., the `ai_scientist/ideas/` directory).

2.  **Run the Ideation Script:** Execute the script from the main project directory, pointing it to your topic description file and specifying the desired LLM.

    ```bash
    python ai_scientist/perform_ideation_temp_free.py \
     --workshop-file "ai_scientist/ideas/my_research_topic.md" \
     --model gpt-4o-2024-05-13 \
     --max-num-generations 20 \
     --num-reflections 5
    ```
    *   `--workshop-file`: Path to your topic description Markdown file.
    *   `--model`: The LLM to use for generating ideas (ensure you have the corresponding API key set).
    *   `--max-num-generations`: How many distinct research ideas to attempt generating.
    *   `--num-reflections`: How many refinement steps the LLM should perform for each idea.

3.  **Output:** The script will generate a JSON file named after your input Markdown file (e.g., `ai_scientist/ideas/my_research_topic.json`). This file will contain a list of structured research ideas, including hypotheses, proposed experiments, and related work analysis.

4.  **Proceed to Experiments:** Once you have the generated JSON file containing research ideas, you can proceed to the next section to run the experiments.

This ideation step guides the AI Scientist towards specific areas of interest and produces concrete research directions to be tested in the main experimental pipeline.

## Run AI Scientist-v2 Paper Generation Experiments

Using the JSON file generated in the previous ideation step, you can now launch the main AI Scientist-v2 pipeline. This involves running experiments via agentic tree search, analyzing results, and generating a paper draft.

Specify the models used for the write-up and review phases via command-line arguments.
The configuration for the best-first tree search (BFTS) is located in `bfts_config.yaml`. Adjust parameters in this file as needed.

Key tree search configuration parameters in `bfts_config.yaml`:

-   `agent` config:
    -   Set `num_workers` (number of parallel exploration paths) and `steps` (maximum number of nodes to explore). For example, if `num_workers=3` and `steps=21`, the tree search will explore up to 21 nodes, expanding 3 nodes concurrently at each step.
    -   `num_seeds`: Should generally be the same as `num_workers` if `num_workers` is less than 3. Otherwise, set `num_seeds` to 3.
    -   Note: Other agent parameters like `k_fold_validation`, `expose_prediction`, and `data_preview` are not used in the current version.
-   `search` config:
    -   `max_debug_depth`: The maximum number of times the agent will attempt to debug a failing node before abandoning that search path.
    -   `debug_prob`: The probability of attempting to debug a failing node.
    -   `num_drafts`: The number of initial root nodes (i.e., the number of independent trees to grow) during Stage 1.

Example command to run AI-Scientist-v2 using a generated idea file (e.g., `my_research_topic.json`). Please review `bfts_config.yaml` for detailed tree search parameters (the default config includes `claude-3-5-sonnet` for experiments). Do not set `load_code` if you do not want to initialize experimentation with a code snippet.

```bash
python launch_scientist_bfts.py \
 --load_ideas "ai_scientist/ideas/my_research_topic.json" \
 --load_code \
 --add_dataset_ref \
 --model_writeup o1-preview-2024-09-12 \
 --model_citation gpt-4o-2024-11-20 \
 --model_review gpt-4o-2024-11-20 \
 --model_agg_plots o3-mini-2025-01-31 \
 --num_cite_rounds 20
```

Once the initial experimental stage is complete, you will find a timestamped log folder inside the `experiments/` directory. Navigate to `experiments/"timestamp_ideaname"/logs/0-run/` within that folder to find the tree visualization file `unified_tree_viz.html`.
After all experiment stages are complete, the writeup stage begins. The writeup stage typically takes about 20 to 30 minutes in total. Once it finishes, you should see `timestamp_ideaname.pdf` in the `timestamp_ideaname` folder.
For this example run, all stages typically finish within several hours.

## Arts & Health Extension

This fork extends AI Scientist-v2 with a two-script pipeline that generates academic papers from a personal knowledge base — without running any ML experiments. The target use case is **arts and health research** (e.g. therapeutic clowning for older adults), where "experiments" are interviews, observational studies, and systematic reviews rather than Python training loops.

Two output modes are available:

| Mode | Flag | Output | Use when |
|---|---|---|---|
| Research proposal | `--writeup-type icbinb` | 4-page ICBINB PDF | Pitching a study |
| Literature review | `--writeup-type review` | APA 7 qualitative review PDF | Synthesising existing work |

### Installation (Arts & Health Extension Only)

This pipeline does not need CUDA, PyTorch, or conda. A plain Python virtualenv works.

```bash
pip install -r requirements.txt

# LaTeX compiler — tectonic downloads packages automatically, no sudo required
mkdir -p ~/bin
curl -L "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.16.9/tectonic-0.16.9-x86_64-unknown-linux-musl.tar.gz" \
  -o /tmp/tectonic.tar.gz
tar xzf /tmp/tectonic.tar.gz -C ~/bin
chmod +x ~/bin/tectonic

# Create pdflatex/bibtex shims so AI Scientist's compile_latex() works unchanged
printf '#!/bin/bash\nexec "$(dirname "$0")/tectonic" "${@: -1}"\n' > ~/bin/pdflatex
printf '#!/bin/bash\necho "bibtex: handled by tectonic"; exit 0\n' > ~/bin/bibtex
chmod +x ~/bin/pdflatex ~/bin/bibtex
```

Copy `.env.example` to `.env` and fill in your values:

```
OLLAMA_BASE_URL=http://192.168.1.20:11434   # remote Ollama instance
MCP_URL=http://localhost:8765/sse            # use localhost — IP address rejected by FastMCP host check
S2_API_KEY=your_key_here                     # semanticscholar.org/product/api (1 req/sec authenticated)
```

> **MCP_URL note:** FastMCP 1.x rejects connections whose `Host` header contains a bare IP address. Always connect via `localhost` or a hostname.

### Research Proposal Mode

Generates a 4-page ICBINB-format research proposal from one open research question in the knowledge base.

```
a1c-knowledge MCP server          Semantic Scholar
        │                                 │
        ▼                                 │
generate_ideas_from_mcp.py  ─────────────┘
  • Queries MCP for topics with open research questions
  • Checks each question against Semantic Scholar for novelty
  • Translates surviving questions → AI Scientist idea JSON via Ollama
  • Attaches pre-gathered BibTeX citations as private metadata
        │
        ▼  ai_scientist/ideas/<topic>.json
        │
launch_proposal_writer.py --writeup-type icbinb
  • Strips private metadata, writes topic_data.json
  • Pre-populates cached_citations.bib (bypasses ML-biased citation loop)
  • Drives perform_icbinb_writeup to produce a 4-page PDF
        │
        ▼  experiments/<timestamp>_<name>_proposal_0/<name>.pdf
```

```bash
export PATH="$HOME/bin:$PATH"

# Stage 1: generate ideas (~1–3 min per topic, LLM-bound)
python generate_ideas_from_mcp.py \
  --query "elder clowning therapeutic clowning older adults wellbeing" \
  --confidence high \
  --limit 10 \
  --model ollama/qwen2.5:14b \
  --output ai_scientist/ideas/elder_clowning.json

# See what ideas were generated and pick an index
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --list-ideas

# Stage 2: write proposal PDF (~2–5 min)
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 1 \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b \
  --num_cite_rounds 10
```

Output: `experiments/<timestamp>_<idea_name>_proposal_0/<name>_reflection1.pdf`

### Literature Review Mode

Generates a full APA 7 qualitative literature review using recursive Semantic Scholar traversal and a tiered context strategy that separates your synthesised notes, full-text PDFs you retrieved from the library, and S2 abstracts.

```
generate_ideas_from_mcp.py --recursive --fetch-fulltext --library-list ...
  • Seed S2 search → fetch citations + references for each seed paper
  • Classify: open-access bucket (download full text) vs paywalled bucket
  • Write library.html — tabbed interactive page:
      Tab 2 "📥 Papers": paywalled (EZproxy links + clipboard filename), blocked (direct URL + library fallback),
        auto-downloaded (checkboxes + rm command builder)
      Tab 3 "🚀 Launch writer": idea selector, model/writeup-type form, live command textarea + copy button
  • Attach _s2_papers, _oa_fulltext, _paywalled, _blocked_oa to the ideas JSON
        │
        ▼  ai_scientist/ideas/<topic>.json
           ai_scientist/ideas/library.html   ← open in browser; retrieve paywalled PDFs manually
        │
        ▼  [manually save retrieved PDFs to ai_scientist/ideas/pdfs/]
        │
launch_proposal_writer.py --writeup-type review
  • Tier 1 (Anchor):   MCP _mcp_topic.body — your synthesis notes
  • Tier 2 (Evidence): Discussion / Findings / Participant Voices from manual + OA PDFs
  • Tier 3 (Map):      Abstracts from all ≤100 S2 papers
  • [small model] Thematic pre-clustering: 5–7 recurring themes across all abstracts
  • [big model]   Fills 10 APA 7 placeholders in blank_review_latex/template.tex
  • Compiles via tectonic → PDF
        │
        ▼  experiments/<timestamp>_<name>_proposal_0/template.pdf
```

```bash
export PATH="$HOME/bin:$PATH"

# Stage 1: generate ideas with recursive S2 expansion (~5–15 min depending on S2 rate limits)
python generate_ideas_from_mcp.py \
  --query "therapeutic clowning older adults wellbeing" \
  --confidence high \
  --model ollama/qwen2.5:14b \
  --recursive \
  --fetch-fulltext \
  --output ai_scientist/ideas/elder_clowning.json

# Stage 2 (manual): open ai_scientist/ideas/library.html in a browser; click library links,
# download paywalled PDFs, and save them to ai_scientist/ideas/pdfs/ using the suggested filenames.

# Stage 3: write APA 7 literature review PDF (~5–15 min, LLM-bound)
python launch_proposal_writer.py \
  --load_ideas ai_scientist/ideas/elder_clowning.json \
  --idea_idx 0 \
  --writeup-type review \
  --model_writeup ollama/qwen2.5:14b \
  --model_citation ollama/qwen2.5:14b
```

Output: `experiments/<timestamp>_<name>_proposal_0/template.pdf`

See [howto.md](howto.md) for a full walkthrough with annotated output.

### Seeding from a Known Paper

Use `--seed-doi` or `--seed-pdf` to bootstrap the Semantic Scholar traversal from a specific paper — useful when you already have a key reference (e.g. a Cochrane review) and want to map its citation network.

```bash
# Seed from a DOI (--query optional)
python generate_ideas_from_mcp.py \
  --seed-doi 10.1002/14651858.CD011022.pub2 \
  --query "dance movement therapy dementia" \
  --recursive \
  --model ollama/qwen2.5:14b \
  --output ai_scientist/ideas/dmt_dementia.json

# Seed from a course paper PDF — DOI is extracted automatically
python generate_ideas_from_mcp.py \
  --seed-pdf ~/papers/karkou2017_cochrane_dmt.pdf \
  --query "dance movement therapy dementia" \
  --recursive \
  --model ollama/qwen2.5:14b \
  --output ai_scientist/ideas/dmt_dementia.json

# Seed-only (no MCP query) — generates one idea from the seed paper's context
python generate_ideas_from_mcp.py \
  --seed-doi 10.1002/14651858.CD011022.pub2 \
  --recursive \
  --model ollama/qwen2.5:14b \
  --output ai_scientist/ideas/dmt_dementia.json
```

**How it works:**

1. If `--seed-doi` is given, the script fetches that paper from S2 by DOI and adds it to the seed list before `expand_papers_recursively()`.
2. If `--seed-pdf` is given, the DOI is extracted from the first three pages of the PDF (regex search for `doi: 10.xxx/...`), then the same DOI lookup runs. The PDF is also passed to `extract_sections()` so its Discussion, Findings, and Results sections go straight into the Tier 2 context of the review — even if the paper is paywalled in S2.
3. Seed papers are **unioned** with any papers from `--query` text search — duplicates are deduplicated by S2 `paperId`.
4. If `--query` is omitted, a synthetic topic is built from the seed paper's title and abstract, and one idea is generated from it.

**S2 query quality:** when `--query` is provided, the Semantic Scholar search now uses `key_concepts` collected from the source records linked to each MCP topic (rather than the raw open-question text). This produces more focused queries and avoids the `{"total": 0}` failures that occur when verbose question text is submitted verbatim.

### generate_ideas_from_mcp.py — all arguments

| Argument | Default | Description |
|---|---|---|
| `--query TEXT` | *(optional)* | MCP topic search query. Required unless `--seed-doi` or `--seed-pdf` is given |
| `--seed-doi TEXT` | None | DOI to seed S2 traversal from, e.g. `10.1002/14651858.CD011022.pub2` |
| `--seed-pdf PATH` | None | Local PDF: DOI extracted as seed + sections extracted into Tier 2 context |
| `--confidence` | None | Filter: `low` / `medium` / `high` |
| `--domain` | None | Filter: `intervention` / `theory` / `method` |
| `--limit INT` | `10` | Max topics to retrieve from MCP |
| `--max-questions INT` | `3` | Max open questions per topic to translate |
| `--model TEXT` | `ollama/qwen2.5:14b` | Ollama model for idea translation |
| `--no-novelty-check` | False | Skip Semantic Scholar step entirely |
| `--recursive` | False | Expand seed papers via S2 citation/reference traversal |
| `--max-papers INT` | `100` | Cap on total papers after recursive expansion |
| `--fetch-fulltext` | False | Download and extract Discussion/Results from OA PDFs |
| `--library-list PATH` | alongside `--output` | Where to write `library.html` (default: `library.html` next to `--output`) |
| `--append` | False | Append to existing ideas JSON instead of overwriting |
| `--mcp-url TEXT` | `$MCP_URL` | MCP server SSE endpoint |

### launch_proposal_writer.py — all arguments

| Argument | Default | Description |
|---|---|---|
| `--load_ideas FILE` | *(required)* | Path to ideas JSON |
| `--list-ideas` | False | Print all ideas with index and title, then exit — use before `--idea_idx` |
| `--idea_idx INT` | `0` | Which idea to process (0-based) |
| `--model_writeup TEXT` | `ollama/qwen2.5:14b` | Model for paper writing (big model) |
| `--model_citation TEXT` | `ollama/qwen2.5:14b` | Model for citation gathering / clustering (small model) |
| `--writeup-type TEXT` | `icbinb` | `icbinb` (4-page proposal), `normal` (8-page ICML), `review` (APA 7 lit review) |
| `--num_cite_rounds INT` | `10` | S2 citation rounds (skipped when citations are pre-populated) |
| `--skip_review` | True | Skip LLM peer review (default on — no figures in proposal mode) |

### Additional Dependencies

```
mcp             # MCP Python SDK (SSE client)
python-dotenv   # .env file loading
pytest          # test suite
pytest-asyncio  # async test support
```

---

## Citing The AI Scientist-v2

If you use **The AI Scientist-v2** in your research, please cite our work as follows:

```bibtex
@article{aiscientist_v2,
  title={The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search},
  author={Yamada, Yutaro and Lange, Robert Tjarko and Lu, Cong and Hu, Shengran and Lu, Chris and Foerster, Jakob and Clune, Jeff and Ha, David},
  journal={arXiv preprint arXiv:2504.08066},
  year={2025}
}
```

## Frequently Asked Questions

**Why wasn't a PDF or a review generated for my experiment?**

The AI Scientist-v2 completes experiments with a success rate that depends on the chosen foundation model, and the complexity of the idea. Higher success rates are generally observed when using powerful models like Claude 3.5 Sonnet for the experimentation phase.

**What is the estimated cost per experiment?**

The ideation step cost depends on the LLM used and the number of generations/reflections, but is generally low (a few dollars). For the main experiment pipeline, using Claude 3.5 Sonnet for the experimentation phase typically costs around $15–$20 per run. The subsequent writing phase adds approximately $5 when using the default models specified in the example command. Using GPT-4o for `model_citation` is recommended as it can help reduce writing costs.

**How do I run The AI Scientist-v2 for different subject fields?**

First, perform the [Generate Research Ideas](#generate-research-ideas) step. Create a new Markdown file describing your desired subject field or topic, following the structure of the example `ai_scientist/ideas/i_cant_believe_its_not_better.md`. Run the `perform_ideation_temp_free.py` script with this file to generate a corresponding JSON idea file. Then, proceed to the [Run AI Scientist-v2 Paper Generation Experiments](#run-ai-scientist-v2-paper-generation-experiments) step, using this JSON file with the `launch_scientist_bfts.py` script via the `--load_ideas` argument.

**What should I do if I have problems accessing the Semantic Scholar API?**

The Semantic Scholar API is used to assess the novelty of generated ideas and to gather citations during the paper write-up phase. If you don't have an API key, encounter rate limits, you may be able to skip these phases.

**I encountered a "CUDA Out of Memory" error. What can I do?**

This error typically occurs when the AI Scientist-v2 attempts to load or run a model that requires more GPU memory than available on your system. To resolve this, you can try updating your ideation prompt file (`ai_scientist/ideas/my_research_topic.md`) to suggest using smaller models for the experiments.

## Acknowledgement

The tree search component implemented within the `ai_scientist` directory is built on top of the [AIDE](https://github.com/WecoAI/aideml) project. We thank the AIDE developers for their valuable contributions and for making their work publicly available.


## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=SakanaAI/AI-Scientist-v2&type=Date)](https://star-history.com/#SakanaAI/AI-Scientist-v2&Date)

## ⚖️ License & Responsible Use

This project is licensed under **The AI Scientist Source Code License** (a derivative of the Responsible AI License). 

**Mandatory Disclosure:** By using this code, you are legally bound to clearly and prominently disclose the use of AI in any resulting scientific manuscripts or papers. 

We recommend the following attribution in your paper's Abstract or Methods section:
> "This manuscript was autonomously generated using [The AI Scientist](https://github.com/SakanaAI/AI-Scientist)."

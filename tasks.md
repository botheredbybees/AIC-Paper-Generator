# AIC-Paper-Generator — Backlog

## Enhancements

- [ ] **`--seed-doi` flag on `generate_ideas_from_mcp.py`** ⬅ do this next
  Start recursive S2 traversal from a known paper rather than relying solely on the MCP→S2 text-search path.
  S2 keyword search fails on verbose open-question text (returns `{"total": 0}`) — seed-doi bypasses this entirely.
  - Add `fetch_paper_by_doi(doi)` hitting `api.semanticscholar.org/graph/v1/paper/DOI:{doi}`
  - Inject result into seed list before `expand_papers_recursively()`; `--query` remains optional
  - Usage: `--seed-doi 10.1002/14651858.CD011022.pub2 --recursive`
  - First test case: Karkou & Meekums 2017 DMT for dementia Cochrane review — 183 citing papers + reference list as paper pool
  - `--query` optional in seed-doi mode (MCP query still runs if provided, seeds are unioned)

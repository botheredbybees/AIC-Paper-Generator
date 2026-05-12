# AIC-Paper-Generator — Backlog

## Enhancements

- [ ] **`--seed-doi` flag on `generate_ideas_from_mcp.py`**
  Start recursive S2 traversal from a known paper rather than relying solely on the MCP→S2 text-search path.
  - Add `fetch_paper_by_doi(doi)` hitting `api.semanticscholar.org/graph/v1/paper/DOI:{doi}`
  - Inject result into seed list before `expand_papers_recursively()`
  - Usage: `--seed-doi 10.1002/14651858.CD011022.pub2`
  - Can combine with `--query` (union of seeds) or run without `--query` (seed-only mode)
  - Cochrane reviews, systematic reviews with known DOIs are the primary use case

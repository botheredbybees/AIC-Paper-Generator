# AIC-Paper-Generator — Backlog

## Recently Completed

- [x] **`--seed-doi` flag** — `fetch_paper_by_doi(doi)` in `semantic_scholar.py`; injected into seed list before `expand_papers_recursively()`; `--query` now optional
- [x] **`--seed-pdf` flag** — `extract_doi_from_pdf(path)` in `pdf_reader.py`; extracts DOI via regex from first 3 pages; passes to `fetch_paper_by_doi`
- [x] **`key_concepts` as S2 query** — `fetch_source_key_concepts()` calls `get_source` for each source slug linked to a topic; aggregated key_concepts used as S2 search query (more focused than raw open-question text); falls back to question text if no concepts found

## Enhancements

- [ ] **`--tag` flag for `generate_ideas_from_mcp.py`** — pass tag slug to `search_topics` MCP call as a filter; wire to the `gen-tag` datalist field in Tab 1 so it is included in the generated command (currently the field is discovery-only)
- [ ] **S2 search query refinement** — currently uses first 6 key_concepts joined with spaces; could weight by frequency across sources or combine with topic title for better recall
- [ ] **No-query seed-only mode improvement** — synthetic topic from seed paper uses abstract as key_findings; could also use S2 paper's `tldr` field if available

# AIC-Paper-Generator — Backlog

## Recently Completed

- [x] **`--seed-doi` flag** — `fetch_paper_by_doi(doi)` in `semantic_scholar.py`; injected into seed list before `expand_papers_recursively()`; `--query` now optional
- [x] **`--seed-pdf` flag** — `extract_doi_from_pdf(path)` in `pdf_reader.py`; extracts DOI via regex from first 3 pages; passes to `fetch_paper_by_doi`
- [x] **`key_concepts` as S2 query** — `fetch_source_key_concepts()` calls `get_source` for each source slug linked to a topic; aggregated key_concepts used as S2 search query
- [x] **Named PDF output dir** — `{stem}_pdfs` instead of generic `pdfs/` (commits d56e016, 5c6521d)
- [x] **DB DOI seeding** — `fetch_db_dois_for_topics()` queries `topic_sources JOIN sources` per topic slug after MCP fetch; `--no-db-seeds` opt-out flag; `psycopg2-binary` in requirements.txt (commits c8f8dce, 5c6521d, 0d18121)
- [x] **Gemini model** — `GEMINI_API_KEY` documented in `.env.example`; Gemini branch already present in `llm.py` (commit f6bf4fa)

## Next (plan ready)

- [ ] **`--topic` flag** — Direct wiki topic slug lookup via `get_topic` MCP call, bypassing `search_topics`. New `fetch_topic_by_slug(slug, mcp_url)` function. Can be used alone or combined with `--query` (topics merged by slug). DB seeding fires for `--topic` runs. Tab 1 HTML form gets `--topic` field. Plan: `docs/superpowers/plans/2026-05-17-aic-topic-flag.md`

## Enhancements (backlog)

- [ ] **`--tag` flag for `generate_ideas_from_mcp.py`** — pass tag slug to `search_topics` MCP call as a filter; wire to the `gen-tag` datalist field in Tab 1 so it is included in the generated command (currently the field is discovery-only)
- [ ] **S2 search query refinement** — currently uses first 6 key_concepts joined with spaces; could weight by frequency across sources or combine with topic title for better recall
- [ ] **No-query seed-only mode improvement** — synthetic topic from seed paper uses abstract as key_findings; could also use S2 paper's `tldr` field if available

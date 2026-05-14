# library.html Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `to_fetch_from_library.md` with a self-contained interactive HTML page that shows library download links with clipboard filename buttons, and lets the user check auto-downloaded papers to generate a `rm` shell command.

**Architecture:** A single new function `write_library_html()` in `generate_ideas_from_mcp.py` generates all HTML, CSS, and JS inline. The download loop is updated to track `(paper_dict, filename)` tuples for successful downloads. `attach_private_keys` carries those tuples through to stage 4, where the call to `write_library_list()` is replaced by `write_library_html()`. `write_library_list()` is kept intact (4 tests depend on it directly).

**Tech Stack:** Python 3.11+, stdlib only (pathlib, json, re, datetime) — no new dependencies. Output is a standalone HTML5 file with inline CSS/JS.

---

## File Map

| File | Change |
|---|---|
| `generate_ideas_from_mcp.py` | Add `write_library_html()`; add `downloaded` kwarg to `attach_private_keys()`; update download loop to collect `(paper_dict, filename)` tuples; replace `write_library_list()` call; update `--library-list` default |
| `tests/test_generate_ideas_from_mcp.py` | Add 12 tests for `write_library_html()` |

---

## Task 1: `write_library_html()` — tests first, then implementation

**Files:**
- Modify: `tests/test_generate_ideas_from_mcp.py`
- Modify: `generate_ideas_from_mcp.py`

- [ ] **Step 1.1 — Add the import and test helper to the test file**

At the top of `tests/test_generate_ideas_from_mcp.py`, alongside the existing imports, add:

```python
from generate_ideas_from_mcp import write_library_html
```

Then, after the existing bibtex tests and before `from generate_ideas_from_mcp import fetch_mcp_topics`, add this helper and all 12 tests:

```python
# ---------------------------------------------------------------------------
# write_library_html tests
# ---------------------------------------------------------------------------

def _paper(title="Test Paper", year=2020, doi=None, venue="", authors=None, pdf_url=None):
    return {
        "title": title,
        "year": year,
        "authors": authors or [{"name": "Alice Smith"}],
        "venue": venue,
        "externalIds": {"DOI": doi} if doi else {},
        "openAccessPdf": {"url": pdf_url} if pdf_url else None,
    }


def test_write_library_html_creates_valid_html_file(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert out.exists()
    content = out.read_text()
    assert "<!DOCTYPE html>" in content
    assert "<html" in content


def test_write_library_html_paywalled_shows_full_title_and_year(tmp_path):
    p = _paper("Elder-Clowning in Long-Term Dementia Care", year=2016, doi="10.1000/x")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    content = out.read_text()
    assert "Elder-Clowning in Long-Term Dementia Care" in content
    assert "(2016)" in content


def test_write_library_html_library_link_uses_ezproxy(tmp_path):
    p = _paper(doi="10.1000/test")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    assert "ezproxy.utas.edu.au" in out.read_text()


def test_write_library_html_clipboard_button_has_suggested_filename(tmp_path):
    p = _paper("Elder Clowning Study", year=2023, authors=[{"name": "Jane Smith"}])
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    content = out.read_text()
    assert "btn-copy" in content
    assert "Jane_2023" in content  # first word of author name + year


def test_write_library_html_blocked_has_direct_url_button(tmp_path):
    p = _paper(pdf_url="https://example.com/paper.pdf")
    out = tmp_path / "library.html"
    write_library_html([], str(out), blocked_oa=[p])
    content = out.read_text()
    assert "btn-direct" in content
    assert "https://example.com/paper.pdf" in content


def test_write_library_html_paywalled_entry_has_no_direct_btn(tmp_path):
    p = _paper(doi="10.1/x")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    assert "btn-direct" not in out.read_text()


def test_write_library_html_downloaded_papers_rendered_as_checkboxes(tmp_path):
    p = _paper("Downloaded Paper", year=2021)
    out = tmp_path / "library.html"
    pdfs = tmp_path / "pdfs"
    write_library_html([], str(out), downloaded=[(p, "smith2021.pdf")], pdfs_dir=pdfs)
    content = out.read_text()
    assert "dl-paper" in content
    assert "Downloaded Paper" in content
    assert 'type="checkbox"' in content


def test_write_library_html_downloaded_files_in_js_array(tmp_path):
    p = _paper(year=2021)
    out = tmp_path / "library.html"
    pdfs = tmp_path / "pdfs"
    write_library_html([], str(out), downloaded=[(p, "alice2021.pdf")], pdfs_dir=pdfs)
    content = out.read_text()
    assert "DL_FILES" in content
    assert "alice2021.pdf" in content


def test_write_library_html_rm_textarea_present_when_downloaded(tmp_path):
    p = _paper()
    out = tmp_path / "library.html"
    pdfs = tmp_path / "pdfs"
    write_library_html([], str(out), downloaded=[(p, "alice2020.pdf")], pdfs_dir=pdfs)
    assert "rm-cmd" in out.read_text()
    assert "updateRm" in out.read_text()


def test_write_library_html_no_downloaded_omits_dl_section(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert "dl-list" not in content
    assert "rm-cmd" not in content


def test_write_library_html_escapes_ampersand_in_title(tmp_path):
    p = _paper("Arts & Health Research", doi="10.1/x")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    content = out.read_text()
    assert "&amp;" in content
    assert "Arts & Health" not in content


def test_write_library_html_pdfs_dir_path_used_in_rm_data(tmp_path):
    pdfs = tmp_path / "ai_scientist" / "ideas" / "pdfs"
    p = _paper()
    out = tmp_path / "library.html"
    write_library_html([], str(out), downloaded=[(p, "jones2020.pdf")], pdfs_dir=pdfs)
    assert str(pdfs) in out.read_text()
```

- [ ] **Step 1.2 — Run the tests to confirm they all fail (function not yet defined)**

```bash
source ~/ml_env/bin/activate
pytest tests/test_generate_ideas_from_mcp.py -k "write_library_html" -v 2>&1 | tail -20
```

Expected: 12 failures, all `ImportError` or `NameError` on `write_library_html`.

- [ ] **Step 1.3 — Add the `write_library_html` function to `generate_ideas_from_mcp.py`**

Add this function directly after `write_library_list` (around line 418). The CSS is a plain string (no f-string) so `{` and `}` don't need escaping. The JS blocks use `{{` / `}}` inside f-strings to produce literal `{` / `}` in the output.

```python
_LIBRARY_HTML_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:17px;max-width:860px;margin:0 auto;padding:24px 28px 60px;background:#fafafa;color:#1a1a1a}
h1{font-size:24px;margin-bottom:4px}
.meta{color:#666;font-size:14px;margin-bottom:32px}
h2{font-size:20px;border-bottom:2px solid #e0e0e0;padding-bottom:8px;margin-top:36px}
h3{font-size:15px;color:#555;font-weight:500;margin:24px 0 12px;text-transform:uppercase;letter-spacing:.05em}
.badge{display:inline-block;background:#e8f0fe;color:#1a73e8;font-size:12px;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle;font-weight:500}
.badge.blocked{background:#fff3e0;color:#e65100}
.badge.dl{background:#e8f5e9;color:#2e7d32}
.intro{color:#555;font-size:15px;margin-top:-4px}
.paper{border-bottom:1px solid #efefef;padding:18px 0}
.paper:last-child{border-bottom:none}
.paper-title{font-size:17px;font-weight:600;margin-bottom:5px;line-height:1.4}
.paper-year{color:#888;font-weight:400}
.paper-meta{color:#666;font-size:14px;margin-bottom:12px}
.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
a.btn-lib{color:#1a73e8;font-size:14px;text-decoration:none;border:1px solid #1a73e8;padding:5px 14px;border-radius:5px}
a.btn-lib:hover{background:#e8f0fe}
a.btn-direct{color:#2e7d32;font-size:14px;text-decoration:none;border:1px solid #2e7d32;padding:5px 14px;border-radius:5px}
a.btn-direct:hover{background:#e8f5e9}
button.btn-copy{font-size:14px;padding:5px 14px;border:1px solid #bbb;border-radius:5px;cursor:pointer;background:#f5f5f5;color:#333}
button.btn-copy:hover{background:#e8e8e8}
button.btn-copy.copied{background:#e8f5e9;border-color:#2e7d32;color:#2e7d32}
.dl-paper{display:flex;align-items:flex-start;gap:14px;padding:14px 0;border-bottom:1px solid #efefef;cursor:pointer}
.dl-paper:last-child{border-bottom:none}
.dl-paper input[type=checkbox]{width:20px;height:20px;flex-shrink:0;margin-top:3px;cursor:pointer;accent-color:#d32f2f}
.dl-paper-text{flex:1}
.dl-paper-title{font-size:16px;font-weight:500;line-height:1.4}
.dl-paper-meta{color:#888;font-size:13px;margin-top:3px}
.dl-paper.selected .dl-paper-title{color:#b71c1c;text-decoration:line-through}
.rm-box{margin-top:24px}
.rm-label{display:flex;justify-content:space-between;color:#555;font-size:13px;margin-bottom:6px}
.rm-empty{color:#999;font-size:14px;font-style:italic;padding:8px 0}
textarea.rm-cmd{width:100%;font-family:"SFMono-Regular",Consolas,monospace;font-size:13px;color:#ce9178;background:#1e1e1e;border:1px solid #444;border-radius:5px;padding:10px;resize:vertical;min-height:56px;box-sizing:border-box}
"""


def write_library_html(
    paywalled: list[dict],
    output_path: str,
    *,
    blocked_oa: list[dict] | None = None,
    downloaded: list[tuple[dict, str]] | None = None,
    pdfs_dir: "Path | None" = None,
) -> None:
    """Write a standalone interactive HTML library download page."""
    import json as _json
    from datetime import date as _date

    def _esc(s: str) -> str:
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;"))

    def _authors_str(p: dict, n: int = 3) -> str:
        authors = p.get("authors") or []
        names = [a.get("name", "") for a in authors[:n]]
        result = ", ".join(names)
        if len(authors) > n:
            result += " et al."
        return result

    def _suggested(p: dict) -> str:
        authors = p.get("authors") or []
        first = ""
        if authors:
            parts = (authors[0].get("name") or "").replace(",", " ").split()
            first = parts[0] if parts else "Unknown"
        year = p.get("year") or "0000"
        title = p.get("title") or ""
        safe = re.sub(r"[^\w\s]", "", title)[:40].strip().replace(" ", "_")
        return f"{first}_{year}_{safe}.pdf"

    def _fetch_entry(p: dict, *, is_blocked: bool = False) -> str:
        title = _esc(p.get("title") or "Unknown Title")
        year = p.get("year") or ""
        authors = _esc(_authors_str(p))
        venue = _esc(p.get("venue") or "")
        doi = (p.get("externalIds") or {}).get("DOI")
        lib_url = _esc(utas_library_url(doi=doi, title=(p.get("title") or "") if not doi else None))
        fname = _esc(_suggested(p))
        meta = authors + (" · " + venue if venue else "")
        direct = ""
        if is_blocked:
            pdf_url = ((p.get("openAccessPdf") or {}).get("url") or "")
            if pdf_url:
                direct = f'<a class="btn-direct" href="{_esc(pdf_url)}" target="_blank">↗ Try direct URL</a>\n    '
        return (
            f'<div class="paper">'
            f'<div class="paper-title">{title} <span class="paper-year">({year})</span></div>'
            f'<div class="paper-meta">{meta}</div>'
            f'<div class="actions">'
            f'<a class="btn-lib" href="{lib_url}" target="_blank">🔗 Open in Library</a>'
            f'{direct}'
            f'<button class="btn-copy" data-filename="{fname}" onclick="copyFilename(this)">📋 {fname}</button>'
            f'</div></div>'
        )

    def _dl_entry(p: dict, idx: int) -> str:
        title = _esc(p.get("title") or "Unknown Title")
        year = p.get("year") or ""
        authors = _esc(_authors_str(p))
        return (
            f'<div class="dl-paper" onclick="togglePaper(this)">'
            f'<input type="checkbox" id="dl-{idx}">'
            f'<div class="dl-paper-text">'
            f'<div class="dl-paper-title">{title} <span class="paper-year">({year})</span></div>'
            f'<div class="dl-paper-meta">{authors}</div>'
            f'</div></div>'
        )

    n_pw = len(paywalled)
    n_bl = len(blocked_oa or [])
    n_dl = len(downloaded or [])
    today = _date.today().isoformat()
    stem = Path(output_path).stem

    fetch_html = ""
    if paywalled:
        entries = "\n".join(_fetch_entry(p) for p in paywalled)
        fetch_html += f'<h3>Paywalled <span class="badge">{n_pw} papers</span></h3>\n{entries}\n'
    if blocked_oa:
        entries = "\n".join(_fetch_entry(p, is_blocked=True) for p in blocked_oa)
        fetch_html += (
            f'<h3>Publisher-Blocked (open access but 403)'
            f' <span class="badge blocked">{n_bl} papers</span></h3>\n{entries}\n'
        )

    dl_html = ""
    if downloaded:
        prefix = (str(pdfs_dir) + "/") if pdfs_dir else "pdfs/"
        rm_paths = _json.dumps([prefix + fname for _, fname in downloaded])
        items = "\n".join(_dl_entry(p, i) for i, (p, _) in enumerate(downloaded))
        dl_html = f"""
<h2>&#x2705; Auto-Downloaded Papers <span class="badge dl">{n_dl} papers</span></h2>
<p class="intro">Check papers to remove from the PDF pool. The shell command updates below.</p>
<div id="dl-list">
{items}
</div>
<div class="rm-box">
  <div class="rm-label">
    <span>Shell command &mdash; copy and paste to remove selected papers from the pool</span>
    <span id="sel-count">0 selected</span>
  </div>
  <div id="rm-empty" class="rm-empty">Select papers above to generate the rm command.</div>
  <textarea id="rm-cmd" class="rm-cmd" style="display:none" readonly></textarea>
</div>
<script>
const DL_FILES = {rm_paths};
function togglePaper(el) {{
  const cb = el.querySelector('input[type=checkbox]');
  cb.checked = !cb.checked;
  el.classList.toggle('selected', cb.checked);
  updateRm();
}}
function updateRm() {{
  const sel = [];
  document.querySelectorAll('.dl-paper').forEach(function(el, i) {{
    if (el.querySelector('input').checked) sel.push(DL_FILES[i]);
  }});
  document.getElementById('sel-count').textContent = sel.length + ' selected';
  const ta = document.getElementById('rm-cmd');
  const empty = document.getElementById('rm-empty');
  if (sel.length === 0) {{
    ta.style.display = 'none'; empty.style.display = 'block';
  }} else {{
    empty.style.display = 'none'; ta.style.display = 'block';
    ta.value = 'rm ' + sel.join(' ');
  }}
}}
</script>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Library downloads &mdash; {stem}</title>
<style>{_LIBRARY_HTML_CSS}</style>
</head>
<body>
<h1>&#x1F4DA; Library download list</h1>
<div class="meta">Generated {today} &middot; {stem} &middot; {n_pw + n_bl} to fetch, {n_dl} auto-downloaded</div>
<h2>&#x1F4E5; Papers to Fetch Manually</h2>
{fetch_html}
{dl_html}
<script>
function copyFilename(btn) {{
  navigator.clipboard.writeText(btn.dataset.filename).then(function() {{
    var orig = btn.textContent;
    btn.textContent = '✓ Copied';
    btn.classList.add('copied');
    setTimeout(function() {{ btn.textContent = orig; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    print(
        f"[Library] Wrote interactive HTML to {output_path} "
        f"({n_pw} paywalled, {n_bl} blocked, {n_dl} downloaded)"
    )
```

- [ ] **Step 1.4 — Run the tests to confirm they all pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py -k "write_library_html" -v 2>&1 | tail -20
```

Expected: 12 passed.

- [ ] **Step 1.5 — Run the full suite to confirm nothing broke**

```bash
pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass (previously 157; now 169).

- [ ] **Step 1.6 — Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "$(cat <<'EOF'
feat: add write_library_html() — interactive standalone download page

Replaces write_library_list() in the pipeline. Generates self-contained
HTML with library links, clipboard filename buttons, and a checkbox-driven
rm command builder for the auto-downloaded PDF pool.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Track successful downloads in the fetch loop

**Files:**
- Modify: `generate_ideas_from_mcp.py` (download loop ~line 631; `attach_private_keys` ~line 420; call site ~line 660)

- [ ] **Step 2.1 — Add `downloaded` kwarg to `attach_private_keys`**

Change the function signature and body (around line 420):

```python
def attach_private_keys(
    idea: dict,
    topic: dict,
    s2_papers: list[dict],
    paywalled: list[dict] | None = None,
    oa_fulltext: dict | None = None,
    blocked_oa: list[dict] | None = None,
    downloaded: list[tuple[dict, str]] | None = None,
) -> dict:
    """Attach private metadata keys to an idea dict for downstream use."""
    result = dict(idea)
    result["_mcp_topic"] = topic
    result["_s2_bibtex"] = [bibtex_from_s2_paper(p) for p in (s2_papers or [])]
    result["_s2_papers"] = s2_papers or []
    result["_paywalled"] = paywalled or []
    result["_blocked_oa"] = blocked_oa or []
    result["_oa_fulltext"] = oa_fulltext or {}
    result["_downloaded"] = downloaded or []
    return result
```

- [ ] **Step 2.2 — Add `downloaded_papers` accumulation to the download loop**

In the per-topic loop (around line 624), add `downloaded_papers` before the `for p in oa_with_pdf` loop and append each success:

```python
            blocked_oa_papers: list[dict] = []
            downloaded_papers: list[tuple[dict, str]] = []          # ← add this line
            if args.fetch_fulltext and oa_papers:
                oa_with_pdf = [p for p in oa_papers if (p.get("openAccessPdf") or {}).get("url")]
                print(f"    [PDF] {len(oa_with_pdf)} of {len(oa_papers)} OA paper(s) have PDF URLs"
                      f" ({len(s2_papers) - len(oa_papers)} paywalled); fetching full text...")
                pdfs_dir = Path(args.output).parent / "pdfs"
                pdfs_dir.mkdir(exist_ok=True)
                for p in oa_with_pdf:
                    oa_url = (p.get("openAccessPdf") or {}).get("url")
                    authors = p.get("authors") or []
                    first = (authors[0].get("name") or "").split()[-1] if authors else "Unknown"
                    year = str(p.get("year") or "0000")
                    bib_key = re.sub(r"[^a-z0-9]", "", f"{first.lower()}{year}")
                    pdf_dest = pdfs_dir / f"{bib_key}.pdf"
                    if not pdf_dest.exists():
                        try:
                            import requests as _req
                            r = _req.get(oa_url, timeout=30)
                            r.raise_for_status()
                            pdf_dest.write_bytes(r.content)
                        except Exception as exc:
                            print(f"      [PDF] {bib_key}: download failed ({exc})")
                            blocked_oa_papers.append(p)
                            continue
                    downloaded_papers.append((p, pdf_dest.name))    # ← add this line
                    sections = extract_sections(str(pdf_dest), citation_key=bib_key)
                    if sections:
                        oa_fulltext[bib_key] = sections
                        print(f"      [PDF] {bib_key}: {list(sections.keys())} → saved {pdf_dest.name}")
```

- [ ] **Step 2.3 — Pass `downloaded_papers` through `attach_private_keys`**

Update the `ideas.append(...)` call (around line 660):

```python
            ideas.append(attach_private_keys(idea, topic, s2_papers, paywalled_papers, oa_fulltext,
                                              blocked_oa=blocked_oa_papers,
                                              downloaded=downloaded_papers))
```

- [ ] **Step 2.4 — Run the full test suite to confirm nothing broke**

```bash
pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass (same count as after Task 1).

- [ ] **Step 2.5 — Commit**

```bash
git add generate_ideas_from_mcp.py
git commit -m "$(cat <<'EOF'
feat: track successful PDF downloads for library HTML

Accumulates (paper_dict, filename) tuples during the OA fetch loop
and threads them through attach_private_keys → write_library_html.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Wire up the call site and update the CLI default

**Files:**
- Modify: `generate_ideas_from_mcp.py` (stage 4 block ~line 664; `--library-list` argparse ~line 510)

- [ ] **Step 3.1 — Replace the `write_library_list` call with `write_library_html`**

The current stage-4 block (around line 666) reads:

```python
    if any(idea.get("_paywalled") or idea.get("_blocked_oa") for idea in ideas):
        library_list_path = args.library_list or str(Path(args.output).parent / "to_fetch_from_library.md")
        all_paywalled: list[dict] = []
        all_blocked: list[dict] = []
        seen_ids: set[str] = set()
        for idea in ideas:
            for p in (idea.get("_paywalled") or []):
```

Replace that entire block (through the `write_library_list(...)` call) with:

```python
    all_paywalled: list[dict] = []
    all_blocked: list[dict] = []
    all_downloaded: list[tuple[dict, str]] = []
    seen_ids: set[str] = set()
    for idea in ideas:
        for p in (idea.get("_paywalled") or []):
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_paywalled.append(p)
        for p in (idea.get("_blocked_oa") or []):
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_blocked.append(p)
        for p, fname in (idea.get("_downloaded") or []):
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_downloaded.append((p, fname))

    if all_paywalled or all_blocked or all_downloaded:
        library_list_path = args.library_list or str(Path(args.output).parent / "library.html")
        pdfs_dir = Path(args.output).parent / "pdfs"
        write_library_html(
            all_paywalled,
            library_list_path,
            blocked_oa=all_blocked,
            downloaded=all_downloaded or None,
            pdfs_dir=pdfs_dir if all_downloaded else None,
        )
```

- [ ] **Step 3.2 — Update the `--library-list` argument default description**

Find the `add_argument("--library-list", ...)` line (around line 510) and update its `help` string:

```python
    parser.add_argument("--library-list", default=None, dest="library_list",
                        help="Path to write library.html (default: alongside --output)")
```

- [ ] **Step 3.3 — Run the full test suite**

```bash
pytest tests/ -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 3.4 — Smoke-test the output with a small dry run**

Check the function generates a valid HTML file with no runtime errors:

```bash
source ~/ml_env/bin/activate && python - <<'EOF'
from pathlib import Path
from generate_ideas_from_mcp import write_library_html
p = {"title": "Test Paper & More", "year": 2023,
     "authors": [{"name": "Jane Smith"}, {"name": "Bob Jones"}],
     "venue": "Journal of Testing", "externalIds": {"DOI": "10.1/test"},
     "openAccessPdf": None}
blocked = {"title": "Open But Blocked", "year": 2022,
           "authors": [{"name": "Alice"}], "venue": "",
           "externalIds": {}, "openAccessPdf": {"url": "https://example.com/x.pdf"}}
dl_p = {"title": "Downloaded Fine", "year": 2021,
        "authors": [{"name": "Carol"}], "venue": "", "externalIds": {}}
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "library.html")
    pdfs = Path(d) / "pdfs"
    write_library_html([p], out, blocked_oa=[blocked],
                       downloaded=[(dl_p, "carol2021.pdf")], pdfs_dir=pdfs)
    content = Path(out).read_text()
    assert "Test Paper &amp; More" in content, "ampersand not escaped"
    assert "ezproxy.utas.edu.au" in content, "no library link"
    assert "btn-direct" in content, "no direct URL button"
    assert "carol2021.pdf" in content, "no downloaded paper"
    assert "DL_FILES" in content, "no JS data"
    assert "rm-cmd" in content, "no rm textarea"
    print("OK — all assertions passed, HTML is", len(content), "bytes")
EOF
```

Expected output: `OK — all assertions passed, HTML is <N> bytes`

- [ ] **Step 3.5 — Commit**

```bash
git add generate_ideas_from_mcp.py
git commit -m "$(cat <<'EOF'
feat: wire library.html into pipeline, replace write_library_list call

Stage 4 now calls write_library_html() and accumulates downloaded papers
alongside paywalled/blocked. --library-list default is now library.html.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

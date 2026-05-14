# library.html — Tabs + Launch Writer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `library.html` from a flat page into a 3-tab shell; Tab 3 (Launch Writer) generates a `launch_proposal_writer.py` command from ideas data embedded at generation time.

**Architecture:** All HTML, CSS, and JS remain inline in `generate_ideas_from_mcp.py`. The tab bar and Tab 2 panel wrap the existing library content. Tab 3 is rendered only when `ideas` is passed; it bakes `IDEA_LIST`, `LOAD_IDEAS_PATH`, and `OLLAMA_BASE_URL` as JS constants and builds a live command textarea. Ollama model list is fetched at page-load from the embedded URL, falling back to a text input on failure. Tab state, last model, and last ideas path are all persisted in `localStorage`.

**Tech Stack:** Python 3.11+ stdlib (no new deps); inline HTML5/CSS/JS; existing `write_library_html()` in `generate_ideas_from_mcp.py`, existing tests in `tests/test_generate_ideas_from_mcp.py`.

---

## File Map

| File | Change |
|---|---|
| `generate_ideas_from_mcp.py` | Extend `_LIBRARY_HTML_CSS`; add `ideas`, `ideas_path`, `ollama_base_url` params to `write_library_html()`; add `_idea_row()` helper; restructure HTML body with tab bar + Tab 2 panel + conditional Tab 3; update call site and generation trigger |
| `tests/test_generate_ideas_from_mcp.py` | Add `_idea()` helper and 13 new tests after the existing 12 `write_library_html` tests |

---

## Task 1: Add 13 failing tests (TDD)

**Files:**
- Modify: `tests/test_generate_ideas_from_mcp.py` (after line 285, before `from generate_ideas_from_mcp import fetch_mcp_topics`)

- [ ] **Step 1.1 — Insert `_idea()` helper and 13 new tests**

Insert the following block into `tests/test_generate_ideas_from_mcp.py` after `test_write_library_html_pdfs_dir_path_used_in_rm_data` (line 285) and before `from generate_ideas_from_mcp import fetch_mcp_topics` (line 288):

```python
def _idea(idx=0, name="test_idea", title="Test Idea Title"):
    return {"Name": name, "Title": title}


def test_write_library_html_tab_bar_present(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "clown_study", "Clown Study in Care Homes")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    assert "tab-bar" in out.read_text()


def test_write_library_html_papers_tab_present(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea()]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "Papers" in content or "\U0001f4e5" in content


def test_write_library_html_launch_tab_present(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "my_idea", "My Idea Title")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    assert "Launch" in out.read_text()


def test_write_library_html_idea_radio_buttons_rendered(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "idea_a", "Idea A"), _idea(1, "idea_b", "Idea B")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    assert out.read_text().count('type="radio"') >= 2


def test_write_library_html_idea_titles_in_tab3(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "idea_a", "Therapeutic Clowning Study"),
             _idea(1, "idea_b", "DMT Dementia Research")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "Therapeutic Clowning Study" in content
    assert "DMT Dementia Research" in content


def test_write_library_html_ideas_path_embedded(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/elder_clowning.json")
    assert "ai_scientist/ideas/elder_clowning.json" in out.read_text()


def test_write_library_html_ollama_url_embedded(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json",
                       ollama_base_url="http://192.168.1.20:11434")
    assert "http://192.168.1.20:11434" in out.read_text()


def test_write_library_html_writeup_type_options(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "icbinb" in content
    assert "review" in content
    assert "normal" in content


def test_write_library_html_launch_cmd_textarea(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    assert "launch-cmd" in out.read_text()


def test_write_library_html_no_ideas_omits_launch_tab(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert "launch-cmd" not in out.read_text()


def test_write_library_html_generated_when_only_ideas(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    assert out.exists()


def test_write_library_html_localStorage_script_present(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "localStorage" in content
    assert "activeTab" in content


def test_write_library_html_lastIdeasPath_written_on_load(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/elder_clowning.json")
    content = out.read_text()
    assert "lastIdeasPath" in content
```

- [ ] **Step 1.2 — Run new tests to confirm all 13 fail**

```bash
source ~/ml_env/bin/activate
pytest tests/test_generate_ideas_from_mcp.py -k "tab_bar or papers_tab or launch_tab or radio_buttons or titles_in_tab3 or ideas_path_embedded or ollama_url or writeup_type or launch_cmd or no_ideas_omits or generated_when_only or localStorage or lastIdeasPath" -v 2>&1 | tail -20
```

Expected: 13 failures with `TypeError: write_library_html() got an unexpected keyword argument 'ideas'`.

- [ ] **Step 1.3 — Confirm existing 169 tests still pass**

```bash
pytest tests/ -q 2>&1 | tail -5
```

Expected: `169 passed` (13 new tests collected but erroring, not counted in passed).

- [ ] **Step 1.4 — Commit tests**

```bash
git add tests/test_generate_ideas_from_mcp.py
git commit -m "$(cat <<'EOF'
test: add 13 failing tests for library.html tabs + launch writer (TDD)

Red phase: write_library_html() gains ideas, ideas_path, ollama_base_url
params and a Tab 3 Launch Writer form. Tests written before implementation.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement tabs + Launch Writer in `write_library_html()`

**Files:**
- Modify: `generate_ideas_from_mcp.py` (lines 420–638)

- [ ] **Step 2.1 — Extend `_LIBRARY_HTML_CSS` with tab bar CSS**

Append the following CSS to `_LIBRARY_HTML_CSS` (inside the `"""` block, before the closing `"""`). These classes are always included — the tab bar always renders.

```css
.tab-bar{display:flex;border-bottom:2px solid #e0e0e0;margin-bottom:28px}
.tab-btn{padding:10px 20px;border:none;background:none;cursor:pointer;font-size:15px;color:#555;border-bottom:3px solid transparent;margin-bottom:-2px}
.tab-btn.active{color:#1a73e8;border-bottom-color:#1a73e8;font-weight:600}
.tab-btn.disabled{color:#bbb;cursor:default;pointer-events:none}
.tab-panel{display:none}
.tab-panel.active{display:block}
.idea-row{display:flex;align-items:flex-start;gap:12px;padding:12px 0;border-bottom:1px solid #efefef;cursor:pointer}
.idea-row:last-child{border-bottom:none}
.idea-title{font-size:17px;font-weight:600;line-height:1.4}
.idea-slug{font-size:13px;color:#888;margin-top:3px}
.form-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.field{display:flex;flex-direction:column;gap:6px}
.field label{font-size:14px;color:#555;font-weight:500}
.field select,.field input[type=number]{font-size:15px;padding:6px 10px;border:1px solid #ccc;border-radius:5px;min-width:180px}
.field-help{font-weight:400;color:#888}
textarea.launch-cmd{width:100%;font-family:"SFMono-Regular",Consolas,monospace;font-size:13px;color:#ce9178;background:#1e1e1e;border:1px solid #444;border-radius:5px;padding:10px;resize:vertical;box-sizing:border-box}
.soon-badge{font-size:11px;background:#f0f0f0;color:#999;padding:2px 6px;border-radius:8px;margin-left:6px;vertical-align:middle}
```

- [ ] **Step 2.2 — Add 3 new params to `write_library_html()` signature**

Replace the function signature at line 464 (keep the docstring, change only the `def` and params):

```python
def write_library_html(
    paywalled: list[dict],
    output_path: str,
    *,
    blocked_oa: list[dict] | None = None,
    downloaded: list[tuple[dict, str]] | None = None,
    pdfs_dir: "Path | None" = None,
    ideas: list[dict] | None = None,
    ideas_path: str | None = None,
    ollama_base_url: str | None = None,
) -> None:
    """Write a standalone interactive HTML library download page."""
```

- [ ] **Step 2.3 — Add `_idea_row()` helper inside the function**

Insert this helper inside `write_library_html()` after `_dl_entry()` and before `n_pw = len(paywalled)`:

```python
    def _idea_row(idea: dict, idx: int) -> str:
        title = _esc(idea.get("Title") or "Untitled")
        name = _esc(idea.get("Name") or "")
        checked = " checked" if idx == 0 else ""
        return (
            f'<label class="idea-row">'
            f'<input type="radio" name="idea" value="{idx}"{checked} onchange="updateCmd()">'
            f'<div class="idea-text">'
            f'<div class="idea-title">{title}</div>'
            f'<div class="idea-slug">{name} &middot; idx {idx}</div>'
            f'</div></label>'
        )
```

- [ ] **Step 2.4 — Build Tab 3 fragments conditionally**

Insert the following block inside `write_library_html()`, after `stem = Path(output_path).stem` and before `extra_css = ""`:

```python
    js_constants = ""
    tab3_btn = ""
    tab3_panel = ""
    localstorage_lastpath = ""
    tab3_restore_js = ""
    tab3_init_js = ""
    tab3_update_js = ""
    if ideas:
        import json as _json2
        idea_items = [
            {"idx": i, "name": idea.get("Name", ""), "title": idea.get("Title", "")}
            for i, idea in enumerate(ideas)
        ]
        safe_path = (ideas_path or "").replace("\\", "/")
        safe_ollama = (ollama_base_url or "http://localhost:11434").replace("\\", "/")
        js_constants = (
            f'const LOAD_IDEAS_PATH = "{_esc(safe_path)}";\n'
            f'const OLLAMA_BASE_URL = "{_esc(safe_ollama)}";\n'
            f'const IDEA_LIST = {_json2.dumps(idea_items)};'
        )
        idea_rows = "\n".join(_idea_row(idea, i) for i, idea in enumerate(ideas))
        tab3_btn = (
            '<button class="tab-btn" id="tab3-btn"'
            " onclick=\"showTab('tab3', this)\">&#x1F680; Launch writer</button>"
        )
        tab3_panel = f"""<div id="tab3-panel" class="tab-panel">
<h2>&#x1F680; Launch Proposal Writer</h2>
<p class="intro">Select an idea and configure the run, then copy the command to your terminal.</p>
<div id="idea-list">
{idea_rows}
</div>
<div class="form-row" style="margin-top:20px">
  <div class="field">
    <label>Writeup type</label>
    <select id="writeup-type" onchange="updateCmd()">
      <option value="icbinb" selected>icbinb &mdash; 4-page proposal</option>
      <option value="review">review &mdash; APA 7 lit review</option>
      <option value="normal">normal &mdash; 8-page ICML</option>
    </select>
  </div>
  <div class="field">
    <label>Model <span class="field-help">Sets --model_writeup and --model_citation</span></label>
    <select id="model-select" onchange="updateCmd()"></select>
  </div>
  <div class="field">
    <label>Cite rounds <span class="field-help">(optional)</span></label>
    <input type="number" id="cite-rounds" value="10" min="1" oninput="updateCmd()">
  </div>
</div>
<div class="field" style="margin-top:4px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <label>Generated command</label>
    <button class="btn-copy" onclick="copyCmd(this)">&#x1F4CB; Copy command</button>
  </div>
  <textarea id="launch-cmd" class="launch-cmd" readonly rows="7"></textarea>
</div>
</div>"""
        localstorage_lastpath = "localStorage.setItem('lastIdeasPath', LOAD_IDEAS_PATH);"
        tab3_restore_js = """  var lastTab = localStorage.getItem('activeTab') || 'tab2';
  if (lastTab === 'tab3' && document.getElementById('tab3-panel')) {
    document.getElementById('tab2-btn').classList.remove('active');
    document.getElementById('tab3-btn').classList.add('active');
    document.getElementById('tab2-panel').classList.remove('active');
    document.getElementById('tab3-panel').classList.add('active');
  }"""
        tab3_init_js = """  var lastModel = localStorage.getItem('lastModel');
  fetch(OLLAMA_BASE_URL + '/api/tags')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var sel = document.getElementById('model-select');
      (data.models || []).forEach(function(m) {
        var opt = document.createElement('option');
        opt.value = 'ollama/' + m.name; opt.textContent = 'ollama/' + m.name;
        sel.appendChild(opt);
      });
      if (lastModel && sel.querySelector('option[value="' + lastModel + '"]')) sel.value = lastModel;
      updateCmd();
    })
    .catch(function() {
      var sel = document.getElementById('model-select');
      var inp = document.createElement('input');
      inp.type = 'text'; inp.id = 'model-select';
      inp.value = localStorage.getItem('lastModel') || 'ollama/qwen2.5:14b';
      inp.addEventListener('input', updateCmd);
      sel.parentNode.replaceChild(inp, sel);
      updateCmd();
    });"""
        tab3_update_js = r"""
function updateCmd() {
  var radios = document.getElementsByName('idea');
  var idx = '0';
  for (var i = 0; i < radios.length; i++) { if (radios[i].checked) { idx = radios[i].value; break; } }
  var writeupType = document.getElementById('writeup-type').value;
  var modelEl = document.getElementById('model-select');
  var model = modelEl.value || 'ollama/qwen2.5:14b';
  var citeRounds = document.getElementById('cite-rounds').value || '10';
  var path = localStorage.getItem('lastIdeasPath') || LOAD_IDEAS_PATH;
  document.getElementById('launch-cmd').value =
    'python launch_proposal_writer.py \\\n' +
    '  --load_ideas ' + path + ' \\\n' +
    '  --idea_idx ' + idx + ' \\\n' +
    '  --writeup-type ' + writeupType + ' \\\n' +
    '  --model_writeup ' + model + ' \\\n' +
    '  --model_citation ' + model + ' \\\n' +
    '  --num_cite_rounds ' + citeRounds;
  localStorage.setItem('lastModel', model);
}
function copyCmd(btn) {
  navigator.clipboard.writeText(document.getElementById('launch-cmd').value).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✓ Copied'; btn.classList.add('copied');
    setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
  });
}"""
```

- [ ] **Step 2.5 — Replace the `html = f"""..."""` block**

Replace everything from `fetch_html = ""` down to `Path(output_path).write_text(html, encoding="utf-8")` with:

```python
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

    tab2_content = (
        f'<h2>&#x1F4E5; Papers to Fetch Manually</h2>\n'
        f'{fetch_html}'
        f'{dl_html}'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Library downloads &mdash; {stem}</title>
<style>{_LIBRARY_HTML_CSS}{extra_css}</style>
</head>
<body>
<h1>&#x1F4DA; Library download list</h1>
<div class="meta">Generated {today} &middot; {stem} &middot; {n_pw + n_bl} to fetch, {n_dl} auto-downloaded</div>
<div class="tab-bar">
  <button class="tab-btn disabled" tabindex="-1">&#9881;&#65039; Generate ideas <span class="soon-badge">soon</span></button>
  <button class="tab-btn active" id="tab2-btn" onclick="showTab('tab2', this)">&#x1F4E5; Papers</button>
  {tab3_btn}
</div>
<div id="tab2-panel" class="tab-panel active">
{tab2_content}
</div>
{tab3_panel}
<script>
{js_constants}
function showTab(tab, btn) {{
  document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
  document.querySelectorAll('.tab-btn:not(.disabled)').forEach(function(b) {{ b.classList.remove('active'); }});
  document.getElementById(tab + '-panel').classList.add('active');
  btn.classList.add('active');
  localStorage.setItem('activeTab', tab);
}}
document.addEventListener('DOMContentLoaded', function() {{
  {localstorage_lastpath}
{tab3_restore_js}
{tab3_init_js}
}});
function copyFilename(btn) {{
  navigator.clipboard.writeText(btn.dataset.filename).then(function() {{
    var orig = btn.textContent;
    btn.textContent = '&#x2713; Copied';
    btn.classList.add('copied');
    setTimeout(function() {{ btn.textContent = orig; btn.classList.remove('copied'); }}, 2000);
  }});
}}
{tab3_update_js}
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

**Note:** Step 2.5 replaces the existing `fetch_html = ""` ... `write_text` block entirely. The `fetch_html` and `dl_html` construction is identical to the existing code — it is included here so the executor can replace the whole block in one edit without needing to locate the exact split point.

- [ ] **Step 2.6 — Run 13 new tests to confirm they pass**

```bash
source ~/ml_env/bin/activate
pytest tests/test_generate_ideas_from_mcp.py -k "tab_bar or papers_tab or launch_tab or radio_buttons or titles_in_tab3 or ideas_path_embedded or ollama_url or writeup_type or launch_cmd or no_ideas_omits or generated_when_only or localStorage or lastIdeasPath" -v 2>&1 | tail -20
```

Expected: 13 passed.

- [ ] **Step 2.7 — Run full suite to confirm 182 tests pass**

```bash
pytest tests/ -q 2>&1 | tail -5
```

Expected: `182 passed`.

- [ ] **Step 2.8 — Commit**

```bash
git add generate_ideas_from_mcp.py
git commit -m "$(cat <<'EOF'
feat: add tab bar and Launch Writer to library.html

write_library_html() now accepts ideas, ideas_path, ollama_base_url.
When ideas given: renders 3-tab shell — Papers tab wraps existing content,
Launch Writer tab embeds IDEA_LIST + builds a live launch_proposal_writer.py
command. Ollama model list fetched on page load with text-input fallback.
Tab state, model, and ideas path persisted in localStorage.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update call site and broaden generation trigger

**Files:**
- Modify: `generate_ideas_from_mcp.py` (the stage-4 block, ~line 913)

- [ ] **Step 3.1 — Replace the `write_library_html()` call site**

Find and replace the stage-4 block. The current block reads:

```python
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

Replace it with:

```python
    import os as _os
    if all_paywalled or all_blocked or all_downloaded or ideas:
        library_list_path = args.library_list or str(Path(args.output).parent / "library.html")
        pdfs_dir = Path(args.output).parent / "pdfs"
        write_library_html(
            all_paywalled,
            library_list_path,
            blocked_oa=all_blocked,
            downloaded=all_downloaded or None,
            pdfs_dir=pdfs_dir if all_downloaded else None,
            ideas=ideas or None,
            ideas_path=args.output,
            ollama_base_url=_os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
```

- [ ] **Step 3.2 — Run full test suite**

```bash
source ~/ml_env/bin/activate
pytest tests/ -q 2>&1 | tail -5
```

Expected: `182 passed`.

- [ ] **Step 3.3 — Smoke-test Tab 3 renders correctly**

```bash
source ~/ml_env/bin/activate && python - <<'EOF'
from generate_ideas_from_mcp import write_library_html
import tempfile, pathlib

ideas = [
    {"Name": "clown_study", "Title": "Elder Clowning in Care Homes"},
    {"Name": "dmt_wellbeing", "Title": "DMT and Dementia Wellbeing"},
]
with tempfile.TemporaryDirectory() as d:
    out = pathlib.Path(d) / "library.html"
    write_library_html([], str(out), ideas=ideas,
                       ideas_path="ai_scientist/ideas/elder_clowning.json",
                       ollama_base_url="http://192.168.1.20:11434")
    content = out.read_text()
    checks = [
        ("tab-bar", "tab bar present"),
        ("Launch", "launch tab button"),
        ("launch-cmd", "command textarea"),
        ("IDEA_LIST", "JS IDEA_LIST constant"),
        ("elder_clowning.json", "ideas path embedded"),
        ("192.168.1.20:11434", "ollama URL embedded"),
        ("icbinb", "writeup type option"),
        ("lastIdeasPath", "localStorage key"),
        ('type="radio"', "idea radio buttons"),
        ("Elder Clowning in Care Homes", "first idea title"),
        ("DMT and Dementia Wellbeing", "second idea title"),
    ]
    for needle, label in checks:
        assert needle in content, f"FAIL: {label} not found"
    print(f"OK — {len(checks)} checks passed, HTML is {len(content)} bytes")
EOF
```

Expected output: `OK — 11 checks passed, HTML is <N> bytes`

- [ ] **Step 3.4 — Commit**

```bash
git add generate_ideas_from_mcp.py
git commit -m "$(cat <<'EOF'
feat: pass ideas to write_library_html() from pipeline, broaden trigger

Pipeline now passes ideas list, ideas_path (args.output), and
OLLAMA_BASE_URL env var to write_library_html(). library.html is generated
even when no papers need fetching — Tab 3 alone is sufficient reason.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

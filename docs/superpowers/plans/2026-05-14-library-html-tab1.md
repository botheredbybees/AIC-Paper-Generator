# Library HTML Tab 1 (Generate Ideas) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate Tab 1 in `library.html` as a fully functional command builder for `generate_ideas_from_mcp.py`, with Supabase-powered tag type-ahead, domain/confidence dropdowns, and a seed DOI → source lookup that pre-fills the query field.

**Architecture:** All Tab 1 HTML/JS is generated inside `write_library_html()` in `generate_ideas_from_mcp.py` — the same pattern as Tab 3. Supabase URL and anon key are baked in as JS constants at generation time. Tag data is fetched live from PostgREST on page load using a `<datalist>` for type-ahead search. The seed DOI field triggers a `sources` table lookup on blur to pre-populate the query field and tag input.

**Tech Stack:** Python 3.11, pytest, vanilla JS (no external dependencies), Supabase PostgREST v12 via Kong proxy.

---

## File map

| File | Change |
|---|---|
| `generate_ideas_from_mcp.py` | Add `supabase_url`/`supabase_anon_key` params; move CSS to always-included; activate Tab 1 button; add `tab1-panel` HTML; add all Tab 1 JS; update `_main()` call site |
| `tests/test_generate_ideas_from_mcp.py` | Add 14 new tests (TDD — written before implementation in each task) |
| `.env.example` | Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` entries |

---

## Task 1: Supabase params + .env.example

**Files:**
- Modify: `generate_ideas_from_mcp.py` — `write_library_html()` signature + `_main()` call site
- Modify: `tests/test_generate_ideas_from_mcp.py`
- Modify: `.env.example`

- [ ] **Step 1.1: Write two failing tests**

Add to `tests/test_generate_ideas_from_mcp.py` (after the existing `write_library_html` tests):

```python
def test_write_library_html_supabase_constants_embedded(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out),
                       supabase_url="http://192.168.1.20:8000",
                       supabase_anon_key="eyJtestkey")
    content = out.read_text()
    assert "http://192.168.1.20:8000" in content
    assert "eyJtestkey" in content


def test_write_library_html_no_supabase_no_tag_fetch(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert "gen-tag-list" not in content
    assert "SUPABASE_URL" not in content
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /home/botheredbybees/wiki-db/AIC-Paper-Generator
source ~/ml_env/bin/activate
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_supabase_constants_embedded tests/test_generate_ideas_from_mcp.py::test_write_library_html_no_supabase_no_tag_fetch -v
```

Expected: both FAIL with `TypeError` (unexpected keyword argument).

- [ ] **Step 1.3: Add params to `write_library_html()` signature**

In `generate_ideas_from_mcp.py`, change the `write_library_html` signature (around line 483):

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
    supabase_url: str | None = None,
    supabase_anon_key: str | None = None,
) -> None:
```

- [ ] **Step 1.4: Embed Supabase constants in the JS block**

Inside `write_library_html()`, find the block that builds `js_constants` (currently inside `if ideas:`). Move `OLLAMA_BASE_URL` out of that block so it is always set, and add Supabase constants. Replace the current `js_constants` construction with:

```python
safe_ollama = (ollama_base_url or "http://localhost:11434").replace("\\", "/")
js_constants = f'const OLLAMA_BASE_URL = "{_esc(safe_ollama)}";\n'

if ideas:
    idea_items = [
        {"idx": i, "name": idea.get("Name", ""), "title": idea.get("Title", "")}
        for i, idea in enumerate(ideas)
    ]
    safe_path = (ideas_path or "").replace("\\", "/")
    js_constants += (
        f'const LOAD_IDEAS_PATH = "{_esc(safe_path)}";\n'
        f'const IDEA_LIST = {_json.dumps(idea_items)};'
    )

if supabase_url and supabase_anon_key:
    safe_sb_url = supabase_url.replace("\\", "/")
    js_constants += (
        f'\nconst SUPABASE_URL = "{_esc(safe_sb_url)}";\n'
        f'const SUPABASE_ANON_KEY = "{_esc(supabase_anon_key)}";'
    )
```

Also remove the `safe_ollama` and `OLLAMA_BASE_URL` line from inside the `if ideas:` block (it is now above it). The `safe_path` and `idea_items` remain inside `if ideas:`.

- [ ] **Step 1.5: Update `_main()` call site**

In `_main()`, update the `write_library_html(...)` call (around line 1092):

```python
write_library_html(
    all_paywalled,
    library_list_path,
    blocked_oa=all_blocked,
    downloaded=all_downloaded or None,
    pdfs_dir=pdfs_dir if all_downloaded else None,
    ideas=ideas or None,
    ideas_path=args.output,
    ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    supabase_url=os.environ.get("SUPABASE_URL"),
    supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY"),
)
```

- [ ] **Step 1.6: Update `.env.example`**

Append to `.env.example`:

```
SUPABASE_URL=http://192.168.1.20:8000
SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

- [ ] **Step 1.7: Run tests to verify they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_supabase_constants_embedded tests/test_generate_ideas_from_mcp.py::test_write_library_html_no_supabase_no_tag_fetch -v
```

Expected: both PASS.

- [ ] **Step 1.8: Run full suite to check no regressions**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v
```

Expected: all previously passing tests still PASS.

- [ ] **Step 1.9: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py .env.example
git commit -m "feat: add supabase_url/supabase_anon_key params to write_library_html"
```

---

## Task 2: Activate Tab 1 button + add tab1-panel

**Files:**
- Modify: `generate_ideas_from_mcp.py` — CSS always-included, tab button, panel, localStorage restore

- [ ] **Step 2.1: Write two failing tests**

Add to `tests/test_generate_ideas_from_mcp.py`:

```python
def test_write_library_html_tab1_active(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    # Tab 1 button must NOT have the disabled class or soon-badge
    assert 'class="tab-btn disabled"' not in content
    assert "soon-badge" not in content


def test_write_library_html_tab1_panel_present(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="tab1-panel"' in out.read_text()
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_active tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_panel_present -v
```

Expected: both FAIL.

- [ ] **Step 2.3: Move `_LIBRARY_HTML_CSS_LAUNCH` to always-included**

In `write_library_html()`, replace:

```python
extra_css = ""
...
if ideas:
    extra_css += _LIBRARY_HTML_CSS_LAUNCH
    ...
```

with:

```python
extra_css = _LIBRARY_HTML_CSS_LAUNCH   # always needed — Tab 1 is always active
...
if ideas:
    # (keep existing Tab 3 HTML generation here, remove the extra_css line)
    ...
```

The `if blocked_oa:` and `if downloaded:` CSS lines remain unchanged.

- [ ] **Step 2.4: Replace the disabled Tab 1 button with an active one**

In the HTML template string inside `write_library_html()`, replace:

```python
'  <button class="tab-btn disabled" tabindex="-1">&#9881;&#65039; Generate ideas <span class="soon-badge">soon</span></button>\n'
```

with:

```python
'  <button class="tab-btn" id="tab1-btn" onclick="showTab(\'tab1\', this)">&#9881;&#65039; Generate ideas</button>\n'
```

- [ ] **Step 2.5: Add `tab1-panel` to the HTML template**

In the HTML template, add `tab1-panel` before `tab2-panel`. Replace:

```python
html = f"""...
<div id="tab2-panel" class="tab-panel active">
{tab2_content}
</div>
{tab3_panel}
...
```

with:

```python
html = f"""...
<div id="tab1-panel" class="tab-panel">
{tab1_panel}
</div>
<div id="tab2-panel" class="tab-panel active">
{tab2_content}
</div>
{tab3_panel}
...
```

Set `tab1_panel = ""` as a placeholder at the top of the function (before the `if ideas:` block). It will be populated in Tasks 3–5.

- [ ] **Step 2.6: Generalise the activeTab localStorage restore**

Replace the existing `tab3_restore_js` variable (set only when `ideas` is truthy) with a single `tab_restore_js` that is always included and handles all three tabs:

```python
tab_restore_js = """  var lastTab = localStorage.getItem('activeTab') || 'tab2';
  var panelEl = document.getElementById(lastTab + '-panel');
  var btnEl = document.getElementById(lastTab + '-btn');
  if (panelEl && btnEl) {
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
    panelEl.classList.add('active');
    btnEl.classList.add('active');
  }"""
```

Remove the old `tab3_restore_js` variable and its conditional assignment. Update the `DOMContentLoaded` block in the HTML template to use `tab_restore_js` unconditionally.

- [ ] **Step 2.7: Run tests to verify they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_active tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_panel_present -v
```

Expected: both PASS.

- [ ] **Step 2.8: Run full suite**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v
```

Expected: all PASS.

- [ ] **Step 2.9: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: activate Tab 1 button and add tab1-panel to library.html"
```

---

## Task 3: Section 1 form fields + tag datalist fetch

**Files:**
- Modify: `generate_ideas_from_mcp.py` — `tab1_panel` HTML + tag fetch JS

- [ ] **Step 3.1: Write four failing tests**

Add to `tests/test_generate_ideas_from_mcp.py`:

```python
def test_write_library_html_query_field_present(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="gen-query"' in out.read_text()


def test_write_library_html_domain_options(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert "intervention" in content
    assert "theory" in content
    assert "method" in content


def test_write_library_html_confidence_options(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert ">low<" in content
    assert ">medium<" in content
    assert ">high<" in content


def test_write_library_html_supabase_tag_fetch_js(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out),
                       supabase_url="http://192.168.1.20:8000",
                       supabase_anon_key="eyJtest")
    content = out.read_text()
    assert 'id="gen-tag-list"' in content
    assert "Content-Profile" in content
    assert "/rest/v1/tags" in content
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_query_field_present tests/test_generate_ideas_from_mcp.py::test_write_library_html_domain_options tests/test_generate_ideas_from_mcp.py::test_write_library_html_confidence_options tests/test_generate_ideas_from_mcp.py::test_write_library_html_supabase_tag_fetch_js -v
```

Expected: all FAIL.

- [ ] **Step 3.3: Build `tab1_section1_html` and the tag fetch JS**

Near the top of `write_library_html()`, after setting `tab1_panel = ""`, add:

```python
# --- Tab 1 tag fetch JS (conditional on supabase) ---
tab1_tag_fetch_js = ""
if supabase_url and supabase_anon_key:
    tab1_tag_fetch_js = f"""  fetch(SUPABASE_URL + '/rest/v1/tags?select=slug&order=slug', {{
    headers: {{
      'apikey': SUPABASE_ANON_KEY,
      'Authorization': 'Bearer ' + SUPABASE_ANON_KEY,
      'Content-Profile': 'a1c-wiki-db'
    }}
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(rows) {{
    var dl = document.getElementById('gen-tag-list');
    rows.forEach(function(row) {{
      var opt = document.createElement('option');
      opt.value = row.slug;
      dl.appendChild(opt);
    }});
  }})
  .catch(function() {{
    var inp = document.getElementById('gen-tag');
    inp.placeholder = 'tags unavailable';
    inp.disabled = true;
  }});"""
```

Then build the Section 1 HTML. Add this variable (it will be assembled into `tab1_panel` in Task 5):

```python
tag_datalist_html = (
    '<input type="text" id="gen-tag" list="gen-tag-list"'
    ' placeholder="type to search tags…" oninput="updateGenCmd()">\n'
    '<datalist id="gen-tag-list"></datalist>'
    if (supabase_url and supabase_anon_key) else
    '<input type="text" id="gen-tag" placeholder="(Supabase not configured)"'
    ' disabled>'
)

tab1_section1 = f"""<h3>&#x1F50D; What to search for</h3>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Query text</label>
    <input type="text" id="gen-query" placeholder="music therapy dementia wellbeing"
           oninput="updateGenCmd()" style="min-width:260px">
  </div>
  <div class="field">
    <label>Domain</label>
    <select id="gen-domain" onchange="updateGenCmd()">
      <option value="">&mdash; any &mdash;</option>
      <option value="intervention">intervention</option>
      <option value="theory">theory</option>
      <option value="method">method</option>
    </select>
  </div>
  <div class="field">
    <label>Confidence</label>
    <select id="gen-confidence" onchange="updateGenCmd()">
      <option value="">&mdash; any &mdash;</option>
      <option value="low">low</option>
      <option value="medium">medium</option>
      <option value="high">high</option>
    </select>
  </div>
</div>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Tag <span class="field-help">(discovery aid &mdash; type to search)</span></label>
    {tag_datalist_html}
  </div>
  <div class="field" style="flex:2">
    <label>Seed DOI <span class="field-help">(optional)</span></label>
    <input type="text" id="gen-seed-doi" placeholder="10.1002/14651858.CD011022.pub2"
           oninput="updateGenCmd()">
  </div>
</div>"""
```

- [ ] **Step 3.4: Set `tab1_panel` to `tab1_section1` (placeholder for remaining sections)**

```python
tab1_panel = f"""<h2>&#9881;&#65039; Generate Ideas</h2>
<p class="intro">Configure the run, then copy the command to your terminal.</p>
{tab1_section1}"""
```

- [ ] **Step 3.5: Wire `tab1_tag_fetch_js` into the `DOMContentLoaded` block**

In the HTML template's `DOMContentLoaded` handler, add `tab1_tag_fetch_js` after the tab restore JS:

```python
document.addEventListener('DOMContentLoaded', function() {{
  {localstorage_lastpath}
{tab_restore_js}
{tab1_tag_fetch_js}
{tab3_init_js}
}});
```

- [ ] **Step 3.6: Run tests to verify they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_query_field_present tests/test_generate_ideas_from_mcp.py::test_write_library_html_domain_options tests/test_generate_ideas_from_mcp.py::test_write_library_html_confidence_options tests/test_generate_ideas_from_mcp.py::test_write_library_html_supabase_tag_fetch_js -v
```

Expected: all PASS.

- [ ] **Step 3.7: Run full suite**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v
```

Expected: all PASS.

- [ ] **Step 3.8: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: add Tab 1 Section 1 fields and Supabase tag datalist fetch"
```

---

## Task 4: Section 2 + 3 fields, model fetch, lastIdeasPath wiring

**Files:**
- Modify: `generate_ideas_from_mcp.py`

- [ ] **Step 4.1: Write three failing tests**

Add to `tests/test_generate_ideas_from_mcp.py`:

```python
def test_write_library_html_model_select_in_tab1(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="model-select-gen"' in out.read_text()


def test_write_library_html_output_path_field(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert 'id="gen-output"' in content
    assert "mcp_generated.json" in content


def test_write_library_html_tab1_localstorage_lastpath(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    # The output path field must update lastIdeasPath on input
    assert "lastIdeasPath" in content
    assert "gen-output" in content
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_model_select_in_tab1 tests/test_generate_ideas_from_mcp.py::test_write_library_html_output_path_field tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_localstorage_lastpath -v
```

Expected: all FAIL.

- [ ] **Step 4.3: Build Section 2 and Section 3 HTML**

Add these variables in `write_library_html()`, after `tab1_section1`:

```python
tab1_section2 = """<h3>&#x2699;&#xFE0F; Run settings</h3>
<div class="form-row">
  <div class="field" style="flex:2">
    <label>Model <span class="field-help">sets --model</span></label>
    <select id="model-select-gen" onchange="updateGenCmd()"></select>
  </div>
  <div class="field">
    <label>Limit</label>
    <input type="number" id="gen-limit" value="10" min="1" oninput="updateGenCmd()">
  </div>
  <div class="field">
    <label>Max questions</label>
    <input type="number" id="gen-max-q" value="3" min="1" oninput="updateGenCmd()">
  </div>
</div>
<div class="form-row">
  <div class="field">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input type="checkbox" id="gen-recursive" checked onchange="updateGenCmd()">
      --recursive
    </label>
  </div>
  <div class="field">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input type="checkbox" id="gen-fetch-fulltext" onchange="updateGenCmd()">
      --fetch-fulltext
    </label>
  </div>
</div>
<div class="form-row">
  <div class="field" style="flex:1">
    <label>Seed PDF path <span class="field-help">(optional — full path)</span></label>
    <input type="text" id="gen-seed-pdf"
           placeholder="/home/…/ai_scientist/ideas/pdfs/Smith2023.pdf"
           oninput="updateGenCmd()" style="min-width:340px">
  </div>
</div>"""

tab1_section3 = """<h3>&#x1F4C1; Output</h3>
<div class="form-row">
  <div class="field" style="flex:1">
    <label>Output path</label>
    <input type="text" id="gen-output"
           value="ai_scientist/ideas/mcp_generated.json"
           oninput="updateGenCmd(); localStorage.setItem('lastIdeasPath', this.value);"
           style="min-width:340px">
  </div>
</div>"""
```

- [ ] **Step 4.4: Build the Tab 1 model fetch JS**

Add this variable (always included — Tab 1 always needs models):

```python
tab1_model_fetch_js = """  var lastModelGen = localStorage.getItem('lastModel');
  fetch(OLLAMA_BASE_URL + '/api/tags')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var sel = document.getElementById('model-select-gen');
      (data.models || []).forEach(function(m) {
        var opt = document.createElement('option');
        opt.value = 'ollama/' + m.name; opt.textContent = 'ollama/' + m.name;
        sel.appendChild(opt);
      });
      if (lastModelGen && sel.querySelector('option[value="' + lastModelGen + '"]')) {
        sel.value = lastModelGen;
      }
      updateGenCmd();
    })
    .catch(function() {
      var sel = document.getElementById('model-select-gen');
      var inp = document.createElement('input');
      inp.type = 'text'; inp.id = 'model-select-gen';
      inp.value = localStorage.getItem('lastModel') || 'ollama/qwen2.5:14b';
      inp.addEventListener('input', updateGenCmd);
      sel.parentNode.replaceChild(inp, sel);
      updateGenCmd();
    });"""
```

- [ ] **Step 4.5: Update `tab1_panel` to include all three sections**

```python
tab1_panel = f"""<h2>&#9881;&#65039; Generate Ideas</h2>
<p class="intro">Configure the run, then copy the command to your terminal.</p>
{tab1_section1}
{tab1_section2}
{tab1_section3}"""
```

- [ ] **Step 4.6: Add `tab1_model_fetch_js` to the `DOMContentLoaded` block**

```python
document.addEventListener('DOMContentLoaded', function() {{
  {localstorage_lastpath}
{tab_restore_js}
{tab1_tag_fetch_js}
{tab1_model_fetch_js}
{tab3_init_js}
}});
```

- [ ] **Step 4.7: Run tests to verify they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_model_select_in_tab1 tests/test_generate_ideas_from_mcp.py::test_write_library_html_output_path_field tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_localstorage_lastpath -v
```

Expected: all PASS.

- [ ] **Step 4.8: Run full suite**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v
```

Expected: all PASS.

- [ ] **Step 4.9: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: add Tab 1 sections 2+3 (run settings, output, model fetch)"
```

---

## Task 5: Generated command textarea + updateGenCmd()

**Files:**
- Modify: `generate_ideas_from_mcp.py`

- [ ] **Step 5.1: Write two failing tests**

Add to `tests/test_generate_ideas_from_mcp.py`:

```python
def test_write_library_html_generate_cmd_textarea(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="generate-cmd"' in out.read_text()


def test_write_library_html_tab1_copy_btn(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    # Copy button must appear near the generate-cmd textarea
    assert "generate-cmd" in content
    assert "copyGenCmd" in content
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_generate_cmd_textarea tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_copy_btn -v
```

Expected: both FAIL.

- [ ] **Step 5.3: Build the command textarea HTML**

Add a `tab1_cmd_html` variable:

```python
tab1_cmd_html = """<div class="field" style="margin-top:8px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <label>Generated command</label>
    <button class="btn-copy" onclick="copyGenCmd(this)">&#x1F4CB; Copy command</button>
  </div>
  <textarea id="generate-cmd" class="launch-cmd" readonly rows="8"></textarea>
</div>"""
```

- [ ] **Step 5.4: Update `tab1_panel` to include the command section**

```python
tab1_panel = f"""<h2>&#9881;&#65039; Generate Ideas</h2>
<p class="intro">Configure the run, then copy the command to your terminal.</p>
{tab1_section1}
{tab1_section2}
{tab1_section3}
{tab1_cmd_html}"""
```

- [ ] **Step 5.5: Add `updateGenCmd()` and `copyGenCmd()` JS functions**

Add a new variable `tab1_update_js`:

```python
tab1_update_js = r"""
function updateGenCmd() {
  var query = (document.getElementById('gen-query') || {}).value || '';
  var domain = (document.getElementById('gen-domain') || {}).value || '';
  var confidence = (document.getElementById('gen-confidence') || {}).value || '';
  var modelEl = document.getElementById('model-select-gen');
  var model = modelEl ? (modelEl.value || 'ollama/qwen2.5:14b') : 'ollama/qwen2.5:14b';
  var limit = (document.getElementById('gen-limit') || {}).value || '10';
  var maxQ = (document.getElementById('gen-max-q') || {}).value || '3';
  var recursive = document.getElementById('gen-recursive') && document.getElementById('gen-recursive').checked;
  var fetchFull = document.getElementById('gen-fetch-fulltext') && document.getElementById('gen-fetch-fulltext').checked;
  var seedDoi = (document.getElementById('gen-seed-doi') || {}).value || '';
  var seedPdf = (document.getElementById('gen-seed-pdf') || {}).value || '';
  var output = (document.getElementById('gen-output') || {}).value || 'ai_scientist/ideas/mcp_generated.json';

  var cmd = 'python generate_ideas_from_mcp.py';
  var seedOnly = !query && (seedDoi || seedPdf);
  if (!query && !seedDoi && !seedPdf) {
    cmd = '# WARNING: provide --query, --seed-doi, or --seed-pdf\n' + cmd;
  }
  if (query) cmd += ' \\\n  --query "' + query.replace(/"/g, '\\"') + '"';
  if (domain) cmd += ' \\\n  --domain ' + domain;
  if (confidence) cmd += ' \\\n  --confidence ' + confidence;
  cmd += ' \\\n  --model ' + model;
  cmd += ' \\\n  --limit ' + limit;
  cmd += ' \\\n  --max-questions ' + maxQ;
  if (recursive) cmd += ' \\\n  --recursive';
  if (fetchFull) cmd += ' \\\n  --fetch-fulltext';
  if (seedDoi) cmd += ' \\\n  --seed-doi ' + seedDoi;
  if (seedPdf) cmd += ' \\\n  --seed-pdf ' + seedPdf;
  cmd += ' \\\n  --output ' + output;

  var ta = document.getElementById('generate-cmd');
  if (ta) ta.value = cmd;
  localStorage.setItem('lastModel', model);
}
function copyGenCmd(btn) {
  var ta = document.getElementById('generate-cmd');
  if (!ta) return;
  navigator.clipboard.writeText(ta.value).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✓ Copied'; btn.classList.add('copied');
    setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
  });
}"""
```

- [ ] **Step 5.6: Add `tab1_update_js` to the HTML template**

In the HTML template's `<script>` block, add `tab1_update_js` after `tab3_update_js`:

```python
{tab3_update_js}
{tab1_update_js}
```

- [ ] **Step 5.7: Call `updateGenCmd()` at end of Tab 1 model fetch**

The `tab1_model_fetch_js` already calls `updateGenCmd()` after populating the model select. Verify the `catch` branch also calls it (it does — Step 4.4 included it). Also add a bare call at the end of the `DOMContentLoaded` handler so the command is populated on first load even before the Ollama fetch returns:

In the `DOMContentLoaded` block, append:

```python
  updateGenCmd();
```

after `{tab1_model_fetch_js}`.

- [ ] **Step 5.8: Run tests to verify they pass**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_generate_cmd_textarea tests/test_generate_ideas_from_mcp.py::test_write_library_html_tab1_copy_btn -v
```

Expected: both PASS.

- [ ] **Step 5.9: Run full suite**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v
```

Expected: all PASS.

- [ ] **Step 5.10: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: add Tab 1 generate-cmd textarea, updateGenCmd(), copy button"
```

---

## Task 6: Seed DOI → Supabase source lookup

**Files:**
- Modify: `generate_ideas_from_mcp.py`

- [ ] **Step 6.1: Write one failing test**

Add to `tests/test_generate_ideas_from_mcp.py`:

```python
def test_write_library_html_seed_doi_lookup_js(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out),
                       supabase_url="http://192.168.1.20:8000",
                       supabase_anon_key="eyJtest")
    content = out.read_text()
    assert "sources?doi=eq." in content
    assert "key_concepts" in content
    assert "gen-query" in content
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_seed_doi_lookup_js -v
```

Expected: FAIL.

- [ ] **Step 6.3: Build the seed DOI lookup JS**

Add this variable after `tab1_tag_fetch_js`:

```python
tab1_doi_lookup_js = ""
if supabase_url and supabase_anon_key:
    tab1_doi_lookup_js = """
function lookupSeedDoi() {
  var doi = (document.getElementById('gen-seed-doi') || {}).value || '';
  if (!doi) return;
  fetch(SUPABASE_URL + '/rest/v1/sources?doi=eq.' + encodeURIComponent(doi)
        + '&select=key_concepts,tags', {
    headers: {
      'apikey': SUPABASE_ANON_KEY,
      'Authorization': 'Bearer ' + SUPABASE_ANON_KEY,
      'Content-Profile': 'a1c-wiki-db'
    }
  })
  .then(function(r) { return r.json(); })
  .then(function(rows) {
    if (!rows || !rows.length) return;
    var src = rows[0];
    var queryEl = document.getElementById('gen-query');
    var concepts = (src.key_concepts || []).slice(0, 8).join(' ');
    if (concepts && queryEl && !queryEl.value) {
      queryEl.value = concepts;
      updateGenCmd();
    }
    var firstTag = (src.tags || [])[0];
    var tagEl = document.getElementById('gen-tag');
    if (firstTag && tagEl && !tagEl.value) tagEl.value = firstTag;
  })
  .catch(function() {});  // silent — best-effort assist
}"""
```

- [ ] **Step 6.4: Wire `lookupSeedDoi` to the seed DOI input's `onblur`**

In `tab1_section1`, update the seed DOI input to add `onblur`:

```python
    '<input type="text" id="gen-seed-doi" '
    'placeholder="10.1002/14651858.CD011022.pub2" '
    'oninput="updateGenCmd()" onblur="lookupSeedDoi()">'
```

(Replace the existing `oninput="updateGenCmd()"` line in `tab1_section1`.)

- [ ] **Step 6.5: Add `tab1_doi_lookup_js` to the HTML template script block**

In the `<script>` block, add after `tab1_update_js`:

```python
{tab1_update_js}
{tab1_doi_lookup_js}
```

- [ ] **Step 6.6: Run test to verify it passes**

```bash
pytest tests/test_generate_ideas_from_mcp.py::test_write_library_html_seed_doi_lookup_js -v
```

Expected: PASS.

- [ ] **Step 6.7: Run full suite and verify final count**

```bash
pytest tests/test_generate_ideas_from_mcp.py -v 2>&1 | tail -5
```

Expected: 196 passed (182 + 14 new).

- [ ] **Step 6.8: Commit**

```bash
git add generate_ideas_from_mcp.py tests/test_generate_ideas_from_mcp.py
git commit -m "feat: add seed DOI Supabase lookup to pre-populate Tab 1 query field"
```

---

## Task 7: Smoke-test the generated HTML in a browser

No automated tests for this — manual check.

- [ ] **Step 7.1: Generate a test `library.html`**

```bash
cd /home/botheredbybees/wiki-db/AIC-Paper-Generator
source ~/ml_env/bin/activate
export PATH="$HOME/bin:$PATH"
SUPABASE_URL=http://192.168.1.20:8000 \
SUPABASE_ANON_KEY=$(grep SUPABASE_ANON_KEY .env | cut -d= -f2) \
OLLAMA_BASE_URL=http://192.168.1.20:11434 \
python -c "
from generate_ideas_from_mcp import write_library_html
import os
write_library_html(
    [],
    '/tmp/tab1_smoke.html',
    supabase_url=os.environ.get('SUPABASE_URL'),
    supabase_anon_key=os.environ.get('SUPABASE_ANON_KEY'),
    ollama_base_url=os.environ.get('OLLAMA_BASE_URL'),
)"
echo "Open http://192.168.1.20:<port>/tab1_smoke.html or copy /tmp/tab1_smoke.html to a served directory"
```

- [ ] **Step 7.2: Verify in browser**

Open the file. Check:
- Tab 1 is clickable and shows the form
- Domain / Confidence selects have the right options
- Tag field: typing a few characters shows matching tag suggestions from the database
- Seed DOI field: paste a known DOI (e.g. one from `ai_scientist/ideas/*.json`), tab out → query field pre-fills
- Model select: populated from Ollama
- Output path field: changing it updates the command textarea
- Copy button: flashes `✓ Copied`
- Tab 2 (Papers) and Tab 3 (Launch writer, if ideas present) still work
- Refresh: active tab is restored from localStorage

- [ ] **Step 7.3: Final commit if smoke test reveals any fixes needed**

```bash
git add generate_ideas_from_mcp.py
git commit -m "fix: Tab 1 smoke test corrections"
```

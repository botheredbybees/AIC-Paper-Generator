# library.html — Tabbed UI with Launch Writer Design Spec

**Date:** 2026-05-14  
**Status:** Approved  
**Builds on:** `2026-05-14-library-html-design.md`

---

## Goal

Extend `library.html` from a single-page paper list into a tabbed shell that will eventually host the full pipeline UI. This iteration adds Tab 3 (Launch Proposal Writer): an interactive form that builds the `launch_proposal_writer.py` command from the ideas JSON embedded at generation time.

---

## Tab Structure

Three tabs rendered as `<button>` elements switching three `<div>` panels via `display:none/block`. No frameworks — pure JS.

| Tab | Label | State | Content |
|---|---|---|---|
| 1 | ⚙️ Generate ideas | Disabled (greyed, "coming soon" badge) | Empty placeholder |
| 2 | 📥 Papers | Active | Current library content (paywalled, blocked, downloaded) |
| 3 | 🚀 Launch writer | Active | New form (this spec) |

- Active tab stored in `localStorage` key `activeTab` with string values `"tab2"` or `"tab3"` — page returns to the last-visited tab on refresh.
- Tab 2 (`"tab2"`) is the default when no `localStorage` entry exists.
- Tab 1 is visually disabled: `pointer-events:none`, greyed label, small "soon" badge. It has no content panel in the DOM — the tab-switching JS only switches between `tab2` and `tab3` panels and ignores tab 1 clicks entirely.

---

## Python API Changes

### `write_library_html()` — new parameters

```python
def write_library_html(
    paywalled: list[dict],
    output_path: str,
    *,
    blocked_oa: list[dict] | None = None,
    downloaded: list[tuple[dict, str]] | None = None,
    pdfs_dir: "Path | None" = None,
    ideas: list[dict] | None = None,        # NEW
    ideas_path: str | None = None,          # NEW
    ollama_base_url: str | None = None,     # NEW
) -> None:
```

All new parameters are keyword-only with `None` defaults — existing callers and all 12 existing tests are unaffected.

### Call site (stage 4)

```python
import os as _os
write_library_html(
    all_paywalled,
    library_list_path,
    blocked_oa=all_blocked,
    downloaded=all_downloaded or None,
    pdfs_dir=pdfs_dir if all_downloaded else None,
    ideas=ideas,
    ideas_path=args.output,
    ollama_base_url=_os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
)
```

### Page generation trigger

Broadened from:
```python
if all_paywalled or all_blocked or all_downloaded:
```
to:
```python
if all_paywalled or all_blocked or all_downloaded or ideas:
```

This ensures `library.html` is generated even when no papers need fetching (Tab 3 is still useful).

---

## JS Embedded Data

Three constants baked into the HTML at generation time:

```js
const LOAD_IDEAS_PATH = "ai_scientist/ideas/elder_clowning.json";
const OLLAMA_BASE_URL = "http://192.168.1.20:11434";
const IDEA_LIST = [
  {"idx": 0, "name": "standardized_clown_practices_healthcare",
   "title": "Standardizing Therapeutic Clown Practices Across Healthcare Settings"},
  ...
];
```

`IDEA_LIST` is built from `ideas` by extracting `idx` (position in list), `idea["Name"]`, and `idea["Title"]`. Private keys (`_mcp_topic`, `_s2_papers`, etc.) are not embedded.

---

## Tab 3 — Launch Writer Form

### Idea selector

One `<label><input type="radio" name="idea" value="N">` row per idea in `IDEA_LIST`. Each row shows:
- Full title (large, bold)
- Slug + ` · idx N` (small, grey)

First idea pre-selected. Selecting a radio immediately updates the command textarea.

### Writeup type

`<select id="writeup-type">` with options:
- `icbinb` — 4-page proposal (default, pre-selected)
- `review` — APA 7 lit review
- `normal` — 8-page ICML

### Model select

`<select id="model-select">` populated by `fetch(OLLAMA_BASE_URL + '/api/tags')` on `DOMContentLoaded`. Each model name is prefixed with `ollama/` (e.g. `ollama/qwen2.5:14b`). 

**Fallback:** if the fetch fails (Ollama unreachable, CORS error), the `<select>` is replaced by a plain `<input type="text">` pre-filled with `ollama/qwen2.5:14b`.

**Persistence:** on any model change, `localStorage.setItem('lastModel', value)`. On page load, after populating the select, set its value to `localStorage.getItem('lastModel')` if that option exists.

Helper text below the select: "Sets both --model_writeup and --model_citation"

### Cite rounds

`<input type="number" id="cite-rounds" value="10" min="1">` — optional, labelled as such.

### Generated command textarea

```
<textarea id="launch-cmd" readonly rows="7">
python launch_proposal_writer.py \
  --load_ideas <LOAD_IDEAS_PATH> \
  --idea_idx <selected-idx> \
  --writeup-type <writeup-type> \
  --model_writeup <model> \
  --model_citation <model> \
  --num_cite_rounds <cite-rounds>
</textarea>
```

Updates live (`oninput` / `onchange`) on any form element change.

**Copy button:** `📋 Copy command` — uses `navigator.clipboard.writeText()`, flashes `✓ Copied` for 2 s (same pattern as the existing filename copy buttons).

---

## CSS

New CSS classes added to `_LIBRARY_HTML_CSS` (always included — tabs always render):

```css
.tab-bar { display:flex; border-bottom:2px solid #e0e0e0; margin-bottom:28px; }
.tab-btn { ... }
.tab-btn.active { ... }
.tab-btn.disabled { ... }
.tab-panel { display:none; }
.tab-panel.active { display:block; }
.idea-row { ... }   /* radio button rows */
.form-row { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px; }
.field { ... }      /* label + control block */
.launch-cmd { ... } /* dark monospace textarea */
```

`_LIBRARY_HTML_CSS_BLOCKED` and `_LIBRARY_HTML_CSS_DL` remain conditional (only included when those sections are non-empty).

---

## Conditional CSS note

`_LIBRARY_HTML_CSS_BLOCKED` and `_LIBRARY_HTML_CSS_DL` stay conditional so the absence-of-section tests (`btn-direct not in content`, `rm-cmd not in content`) continue to pass.

---

## Tests

12 new tests added to `tests/test_generate_ideas_from_mcp.py` (TDD — written before implementation):

| Test | Asserts |
|---|---|
| `test_write_library_html_tab_bar_present` | `tab-bar` in content when ideas given |
| `test_write_library_html_papers_tab_present` | `📥` or `Papers` tab label in content |
| `test_write_library_html_launch_tab_present` | `Launch` tab label in content when ideas given |
| `test_write_library_html_idea_radio_buttons_rendered` | one radio per idea in IDEA_LIST |
| `test_write_library_html_idea_titles_in_tab3` | each idea title appears in content |
| `test_write_library_html_ideas_path_embedded` | `LOAD_IDEAS_PATH` with correct path in content |
| `test_write_library_html_ollama_url_embedded` | `OLLAMA_BASE_URL` in content when ollama_base_url given |
| `test_write_library_html_writeup_type_options` | `icbinb`, `review`, `normal` all in content |
| `test_write_library_html_launch_cmd_textarea` | `launch-cmd` in content when ideas given |
| `test_write_library_html_no_ideas_omits_launch_tab` | no `launch-cmd` when ideas=None |
| `test_write_library_html_generated_when_only_ideas` | file created when only ideas given (no papers) |
| `test_write_library_html_localStorage_script_present` | `localStorage` and `activeTab` in content |

Total after this phase: 169 + 12 = 181 tests.

---

## Future Tab 1

When Tab 1 is built, `LOAD_IDEAS_PATH` will be read from Tab 1's form state (the output path field) rather than baked in at generation time. The JS constant becomes a default/fallback. No Python changes needed at that point — it's a pure JS concern.

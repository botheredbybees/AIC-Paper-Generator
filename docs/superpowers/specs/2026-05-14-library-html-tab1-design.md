# library.html — Tab 1 (Generate Ideas) Design Spec

**Date:** 2026-05-14
**Status:** Approved
**Builds on:** `2026-05-14-library-html-tabs-design.md`

---

## Goal

Activate Tab 1 ("⚙️ Generate ideas") as a fully functional command builder for
`generate_ideas_from_mcp.py` — same pattern as Tab 3's Launch Writer. The user
configures the run via form fields; the page produces a ready-to-paste terminal
command.

---

## Tab activation

The existing disabled stub is replaced by a real panel. Changes:

- Tab 1 button: remove `disabled` class, remove `pointer-events:none` and greyed
  style, remove the "soon" badge
- Add `id="tab1-panel"` div to the DOM alongside `tab2-panel` and `tab3-panel`
- `activeTab` localStorage key now accepts `"tab1"` and is restored on refresh
- Default tab remains `"tab2"` when no localStorage entry exists

---

## Python API changes

### `write_library_html()` — new parameters

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
    supabase_url: str | None = None,        # NEW — e.g. "http://192.168.1.20:8000"
    supabase_anon_key: str | None = None,   # NEW — Supabase anon JWT
) -> None:
```

All new parameters are keyword-only with `None` defaults — existing callers and
all 182 existing tests are unaffected.

### Call site in `_main()`

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

### `.env.example` additions

```
SUPABASE_URL=http://192.168.1.20:8000
SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

---

## JS constants baked in at generation time

```js
const SUPABASE_URL = "http://192.168.1.20:8000";
const SUPABASE_ANON_KEY = "eyJ...";
```

Both are included only when the corresponding Python params are non-`None`. When
`supabase_url` is `None`, the constants are omitted and no Supabase fetch runs.

---

## Supabase tag fetch

### Tag field — `<datalist>` with type-ahead search

The database has ~3000 tags, making a plain `<select>` unusable. The tag field
uses a `<datalist>`-backed text input instead — the browser provides native
type-ahead filtering with zero external dependencies:

```html
<input type="text" id="gen-tag" list="gen-tag-list" placeholder="type to search…">
<datalist id="gen-tag-list"></datalist>
```

On `DOMContentLoaded`, if `SUPABASE_URL` is defined:

```js
fetch(SUPABASE_URL + '/rest/v1/tags?select=slug&order=slug', {
  headers: {
    'apikey': SUPABASE_ANON_KEY,
    'Authorization': 'Bearer ' + SUPABASE_ANON_KEY,
    'Content-Profile': 'a1c-wiki-db'
  }
})
.then(r => r.json())
.then(rows => {
  const dl = document.getElementById('gen-tag-list');
  rows.forEach(row => {
    const opt = document.createElement('option');
    opt.value = row.slug;
    dl.appendChild(opt);
  });
})
.catch(() => {
  document.getElementById('gen-tag').placeholder = 'tags unavailable';
  document.getElementById('gen-tag').disabled = true;
});
```

The tag value is a discovery aid only (see Section 1 note). When `--tag` support
is added to `generate_ideas_from_mcp.py` (tracked in `tasks.md`), the field will
be wired to that flag and included in the generated command.

Domain (`intervention` / `theory` / `method`) and confidence (`low` / `medium` /
`high`) are hardcoded `<option>` elements — they are fixed enums in the CLI.

### Seed DOI → source lookup → pre-populate query

When the seed DOI field loses focus (`onblur`) and is non-empty, JS queries the
`sources` table for a matching record:

```js
fetch(SUPABASE_URL + '/rest/v1/sources?doi=eq.' + encodeURIComponent(doi)
      + '&select=key_concepts,tags', {
  headers: {
    'apikey': SUPABASE_ANON_KEY,
    'Authorization': 'Bearer ' + SUPABASE_ANON_KEY,
    'Content-Profile': 'a1c-wiki-db'
  }
})
.then(r => r.json())
.then(rows => {
  if (!rows.length) return;
  const src = rows[0];
  const concepts = (src.key_concepts || []).slice(0, 8).join(' ');
  if (concepts && !document.getElementById('gen-query').value) {
    document.getElementById('gen-query').value = concepts;
    updateGenCmd();
  }
  const firstTag = (src.tags || [])[0];
  if (firstTag) {
    document.getElementById('gen-tag').value = firstTag;
  }
});
```

Behaviour:
- Pre-populates query field only when it is currently empty (never overwrites
  user input).
- Pre-fills the tag field with the source's first tag.
- Silently skips if no matching source is found (DOI not yet in the database).
- No error surfaced to the user on lookup failure — it is a best-effort assist.

---

## Tab 1 form structure

Three named sections rendered as labelled groups (matching the Option A layout).

### Section 1 — 🔍 What to search for

| Field | Element | CLI flag | Default |
|---|---|---|---|
| Query text | `<input type="text" id="gen-query">` | `--query` | `""` |
| Domain | `<select id="gen-domain">` | `--domain` | `— any —` |
| Confidence | `<select id="gen-confidence">` | `--confidence` | `— any —` |
| Tag | `<input type="text" id="gen-tag" list="gen-tag-list">` | _(discovery aid — see note)_ | `""` |
| Seed DOI | `<input type="text" id="gen-seed-doi">` | `--seed-doi` | `""` |

**Tag field note:** `generate_ideas_from_mcp.py` has no `--tag` flag yet (tracked
in `tasks.md`). The field is a type-ahead search input backed by `<datalist>` (see
Supabase tag fetch section). It is not included in the generated command until
`--tag` support is added to the CLI. Its primary value now is helping the user
pick a focused query term and triggering the seed DOI lookup's tag pre-fill.

**Seed DOI auto-populate:** on blur, if the DOI matches a record in the `sources`
table, `key_concepts` pre-fills the query field (when empty) and the first tag
pre-fills the tag input. See the Supabase section for the full lookup behaviour.

### Section 2 — ⚙️ Run settings

| Field | Element | CLI flag | Default |
|---|---|---|---|
| Model | `<select id="model-select-gen">` | `--model` | `ollama/qwen2.5:14b` |
| Limit | `<input type="number" id="gen-limit">` | `--limit` | `10` |
| Max questions | `<input type="number" id="gen-max-q">` | `--max-questions` | `3` |
| Recursive | `<input type="checkbox" id="gen-recursive" checked>` | `--recursive` | **checked** |
| Fetch fulltext | `<input type="checkbox" id="gen-fetch-fulltext">` | `--fetch-fulltext` | unchecked |
| Seed PDF path | `<input type="text" id="gen-seed-pdf">` | `--seed-pdf` | `""` |

`--recursive` is **checked by default** — it produces richer paper sets and is
the typical usage.

### Section 3 — 📁 Output

| Field | Element | Notes |
|---|---|---|
| Output path | `<input type="text" id="gen-output">` | Default `ai_scientist/ideas/mcp_generated.json` |

Any change to the output path field immediately fires:
```js
localStorage.setItem('lastIdeasPath', genOutput.value);
```
This keeps Tab 3's `--load_ideas` field in sync without any page reload.

---

## Model select

`<select id="model-select-gen">` is populated by the same Ollama fetch as Tab 3
(`fetch(OLLAMA_BASE_URL + '/api/tags')`). Same fallback (replaced by `<input
type="text">` if Ollama is unreachable). Same `lastModel` localStorage key —
changing the model in either tab updates both.

---

## Generated command

Readonly `<textarea id="generate-cmd" class="launch-cmd">`, dark monospace style
(reuses existing `.launch-cmd` CSS class from Tab 3).

Updates live (`oninput` / `onchange`) on every field change via `updateGenCmd()`.

### Command construction rules

```
python generate_ideas_from_mcp.py \
  [--query <query>]               # omitted if blank AND seed-doi or seed-pdf present
  [--domain <domain>]             # omitted when "— any —"
  [--confidence <confidence>]     # omitted when "— any —"
  --model <model> \
  --limit <limit> \               # always included
  --max-questions <max-q> \       # always included
  [--recursive]                   # included when checked (default: checked)
  [--fetch-fulltext]              # included when checked
  [--seed-doi <doi>]              # included when non-empty
  [--seed-pdf <path>]             # included when non-empty
  --output <output-path>
```

`--query` is required by the CLI unless `--seed-doi` or `--seed-pdf` is present.
If the query field is blank and neither seed field is filled, the textarea shows
a warning line `# WARNING: provide --query, --seed-doi, or --seed-pdf` above the
command.

### Copy button

`📋 Copy command` — `navigator.clipboard.writeText()`, flashes `✓ Copied` for
2 s (same pattern as Tab 3 and the filename copy buttons).

---

## CSS

No new CSS classes needed. Tab 1 reuses:
- `.tab-panel`, `.tab-btn` — existing tab infrastructure
- `.form-row`, `.field`, `.field-help` — from `_LIBRARY_HTML_CSS_LAUNCH`
- `.launch-cmd` — dark monospace textarea, already defined

Tab 1 is always present in the DOM (it was previously a stub; now it is a real
panel). `_LIBRARY_HTML_CSS_LAUNCH` must therefore be included unconditionally.
Remove the `if ideas:` gate and merge it into `_LIBRARY_HTML_CSS`:

```python
# Before (conditional):
if ideas:
    extra_css += _LIBRARY_HTML_CSS_LAUNCH

# After (unconditional — Tab 1 always needs these classes):
# Move _LIBRARY_HTML_CSS_LAUNCH content into _LIBRARY_HTML_CSS
```

`_LIBRARY_HTML_CSS_BLOCKED` and `_LIBRARY_HTML_CSS_DL` remain conditional so
the existing absence-of-section tests continue to pass.

---

## Tests (TDD — 13 new tests)

Written in `tests/test_generate_ideas_from_mcp.py` before implementation.

| Test | Asserts |
|---|---|
| `test_write_library_html_tab1_active` | Tab 1 button has no `disabled` class |
| `test_write_library_html_tab1_panel_present` | `tab1-panel` in content |
| `test_write_library_html_generate_cmd_textarea` | `generate-cmd` in content |
| `test_write_library_html_supabase_constants_embedded` | `SUPABASE_URL` and `SUPABASE_ANON_KEY` in content when both params given |
| `test_write_library_html_supabase_tag_fetch_js` | `gen-tag-list` datalist populated by fetch JS when `supabase_url` given |
| `test_write_library_html_seed_doi_lookup_js` | source lookup JS (`sources?doi=eq.`) present when `supabase_url` given |
| `test_write_library_html_domain_options` | `intervention`, `theory`, `method` in tab1 content |
| `test_write_library_html_confidence_options` | `low`, `medium`, `high` in tab1 content |
| `test_write_library_html_query_field_present` | `gen-query` in content |
| `test_write_library_html_output_path_field` | `gen-output` in content with default path |
| `test_write_library_html_tab1_localstorage_lastpath` | `lastIdeasPath` in JS `oninput` handler for output field |
| `test_write_library_html_no_supabase_no_tag_fetch` | no `gen-tag` fetch JS when `supabase_url=None` |
| `test_write_library_html_model_select_in_tab1` | `model-select-gen` in content |
| `test_write_library_html_tab1_copy_btn` | copy button adjacent to `generate-cmd` |

Total after this phase: 182 + 14 = 196 tests.

---

## Interaction with Tab 3

Tab 1 and Tab 3 share two localStorage keys:

| Key | Written by | Read by |
|---|---|---|
| `lastIdeasPath` | Tab 1 (output path change) + page load (`LOAD_IDEAS_PATH`) | Tab 3 (`--load_ideas` value) |
| `lastModel` | Tab 1 + Tab 3 (model change) | Tab 1 + Tab 3 (model restore on load) |

The flow: user sets output path in Tab 1 → runs the command → new `library.html`
generated with fresh `LOAD_IDEAS_PATH` → opening that page writes `lastIdeasPath`
→ Tab 3 automatically has the right ideas path.

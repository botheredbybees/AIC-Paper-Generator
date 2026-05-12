# ai_scientist/tools/pdf_reader.py
import os
import re
import tempfile

import requests

DEFAULT_SECTIONS = [
    "Discussion",
    "Results",
    "Findings",
    "Participant Voices",
    "Narrative Synthesis",
    "Methodological Considerations",
    "Conclusion",
]


def extract_sections(
    source: str,
    sections: list[str] | None = None,
    max_chars: int = 4000,
    citation_key: str = "",
) -> dict[str, str]:
    """
    Extract named sections from a PDF at a local path or https:// URL.
    Returns {section_name: text} for found sections; missing sections omitted.
    Never raises — returns {} on any failure.
    """
    if sections is None:
        sections = DEFAULT_SECTIONS

    try:
        if source.startswith("http://") or source.startswith("https://"):
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            fd_consumed = False
            try:
                r = requests.get(source, timeout=30)
                r.raise_for_status()
                with os.fdopen(tmp_fd, "wb") as f:
                    fd_consumed = True
                    f.write(r.content)
                text = _extract_text(tmp_path)
            finally:
                if not fd_consumed:
                    try:
                        os.close(tmp_fd)
                    except OSError:
                        pass
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        else:
            text = _extract_text(source)
    except Exception:
        return {}

    return _find_sections(text, sections, max_chars, citation_key)


def _extract_text(path: str) -> str:
    import fitz  # PyMuPDF — available via pymupdf4llm in requirements.txt
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _find_sections(
    text: str,
    sections: list[str],
    max_chars: int,
    citation_key: str,
) -> dict[str, str]:
    """Pure function: find named sections in extracted PDF text.

    Note: numbered headings like "3 Discussion" are not matched — the heading
    must occupy its own line with no prefix.
    """
    lines = text.splitlines()
    patterns = {
        s: re.compile(rf"^\s*{re.escape(s)}\s*$", re.IGNORECASE)
        for s in sections
    }
    # A heading is a short line of mostly title-case or upper-case words
    heading_re = re.compile(r"^\s*[A-Z][A-Za-z\s]{3,50}\s*$")

    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        matched_section = None
        for section_name, pattern in patterns.items():
            if section_name not in result and pattern.match(lines[i]):
                matched_section = section_name
                break

        if matched_section:
            buf: list[str] = []
            j = i + 1
            chars = 0
            while j < len(lines):
                line = lines[j]
                # Stop at next heading (but not the same heading we're in)
                if heading_re.match(line) and line.strip().lower() != lines[i].strip().lower():
                    break
                buf.append(line)
                chars += len(line)
                if chars >= max_chars:
                    break
                j += 1

            content = "\n".join(buf).strip()[:max_chars]
            if content:
                prefix = f"[{citation_key}] " if citation_key else ""
                result[matched_section] = f"{prefix}{content}"

        i += 1

    return result

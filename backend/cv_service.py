import json
import os
import re
import shutil
import pdfplumber

_BASE = os.path.dirname(os.path.abspath(__file__))
CV_DIR = os.path.join(_BASE, "cvs")
CONFIG_PATH = os.path.join(_BASE, "cv_config.json")
LEGACY_PATH = os.path.join(_BASE, "cv.md")


def _ensure_dir():
    os.makedirs(CV_DIR, exist_ok=True)


def load_config() -> dict:
    _ensure_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Auto-migrate legacy cv.md on first run
    cfg = {"active_id": None, "cvs": []}
    if os.path.exists(LEGACY_PATH):
        dest = os.path.join(CV_DIR, "cv_1.md")
        if not os.path.exists(dest):
            shutil.copy2(LEGACY_PATH, dest)
        cfg = {
            "active_id": "cv_1",
            "cvs": [{"id": "cv_1", "name": "CV1", "filename": "cv_1.md"}],
        }
        save_config(cfg)
    return cfg


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def list_cvs() -> list:
    cfg = load_config()
    active_id = cfg.get("active_id")
    return [
        {
            "id": cv["id"],
            "name": cv["name"],
            "filename": cv["filename"],
            "has_file": os.path.exists(os.path.join(CV_DIR, cv["filename"])),
            "is_active": cv["id"] == active_id,
        }
        for cv in cfg.get("cvs", [])
    ]


def get_cv_text(cv_id: str = None) -> str:
    cfg = load_config()
    cid = cv_id or cfg.get("active_id")
    if not cid:
        return ""
    cv = next((c for c in cfg.get("cvs", []) if c["id"] == cid), None)
    if not cv:
        return ""
    fpath = os.path.join(CV_DIR, cv["filename"])
    if not os.path.exists(fpath):
        return ""
    if fpath.endswith(".pdf"):
        try:
            with pdfplumber.open(fpath) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            return ""
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _next_id(cfg: dict) -> str:
    existing = {c["id"] for c in cfg.get("cvs", [])}
    i = 1
    while f"cv_{i}" in existing:
        i += 1
    return f"cv_{i}"


def add_cv(name: str) -> dict:
    cfg = load_config()
    new_id = _next_id(cfg)
    entry = {"id": new_id, "name": name, "filename": f"{new_id}.md"}
    cfg["cvs"].append(entry)
    if not cfg.get("active_id"):
        cfg["active_id"] = new_id
    save_config(cfg)
    active_id = cfg.get("active_id")
    return {
        "id": new_id,
        "name": name,
        "filename": entry["filename"],
        "has_file": False,
        "is_active": new_id == active_id,
    }


def upload_file(cv_id: str, content: bytes, orig_filename: str) -> bool:
    cfg = load_config()
    cv = next((c for c in cfg["cvs"] if c["id"] == cv_id), None)
    if not cv:
        return False
    ext = os.path.splitext(orig_filename)[1].lower()
    if ext not in (".md", ".txt", ".tex", ".pdf"):
        ext = ".md"
    new_filename = f"{cv_id}{ext}"
    old_path = os.path.join(CV_DIR, cv["filename"])
    if os.path.exists(old_path) and cv["filename"] != new_filename:
        os.remove(old_path)
    cv["filename"] = new_filename
    with open(os.path.join(CV_DIR, new_filename), "wb") as f:
        f.write(content)
    save_config(cfg)
    return True


def rename(cv_id: str, name: str) -> bool:
    cfg = load_config()
    cv = next((c for c in cfg["cvs"] if c["id"] == cv_id), None)
    if not cv:
        return False
    cv["name"] = name
    save_config(cfg)
    return True


def activate(cv_id: str) -> bool:
    cfg = load_config()
    if not any(c["id"] == cv_id for c in cfg.get("cvs", [])):
        return False
    cfg["active_id"] = cv_id
    save_config(cfg)
    return True


_SUMMARY_SECTION_RE = re.compile(
    r'\\(?:section|cvsection|subsection)\*?\s*\{'
    r'(summary|profile|objective|about|overview|özet|profil|hakkımda|professional summary|career objective|kişisel özet)'
    r'\}',
    re.IGNORECASE,
)
_RSECTION_RE = re.compile(
    r'(\\begin\{rSection\}\{'
    r'(?:summary|profile|objective|about|overview|özet|profil|hakkımda)'
    r'\})(.*?)(\\end\{rSection\})',
    re.IGNORECASE | re.DOTALL,
)
_NEXT_SECTION_RE = re.compile(
    r'\\(?:section|cvsection|subsection)\*?\s*\{|\\end\{document\}',
    re.IGNORECASE,
)
_BEGIN_DOCUMENT_RE = re.compile(r'\\begin\{document\}')

# Standard summary block added when no summary section exists in the CV.
_SUMMARY_BLOCK = (
    '\n%-----------SUMMARY-----------\n'
    '\\section{Professional Summary}\n'
    '\\begin{itemize}[leftmargin=0.15in, label={}]\n'
    '  \\small{\\item{\\mysummary}}\n'
    '\\end{itemize}\n\n'
)


def _strip_latex(text: str) -> str:
    text = re.sub(r'%[^\n]*', '', text)                                          # comments
    text = re.sub(r'\\(?:newcommand|renewcommand|def)\s*\{?\\?\w+\}?[^\n]*', '', text)  # definitions
    text = re.sub(r'\\begin\{[^}]+\}(?:\[[^\]]*\])?', '', text)                  # \begin{env}[opt]
    text = re.sub(r'\\end\{[^}]+\}', '', text)                                   # \end{env}
    text = re.sub(r'\\(?:textbf|textit|emph|underline|mbox|text)\{([^}]*)\}', r'\1', text)  # formatting → content
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)                   # \href{url}{text} → text
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])*\{[^}]*\}', '', text)          # \cmd[opt]{arg}
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])+', '', text)                   # \cmd[opt]
    text = re.sub(r'\\[a-zA-Z]+\*?', ' ', text)                                  # bare \cmd
    text = re.sub(r'\[[^\]]*\]', '', text)                                        # leftover [...]
    text = re.sub(r'[{}&$\\|#]', ' ', text)                                      # special chars
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _find_def_range(tex_content: str, def_name: str = "mysummary"):
    """Balanced-brace scan to find content of \\def\\<name>{...}.
    Returns (content_start, content_end) or None."""
    marker = '\\def\\' + def_name + '{'
    idx = tex_content.find(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    depth = 1
    i = start
    while i < len(tex_content) and depth > 0:
        c = tex_content[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    return (start, i - 1) if depth == 0 else None


def _insert_before_begin_document(tex: str, line: str) -> str:
    """Insert `line` immediately before \\begin{document}."""
    m = _BEGIN_DOCUMENT_RE.search(tex)
    if m:
        return tex[:m.start()] + line + tex[m.start():]
    return tex  # No \begin{document} found — return unchanged


def normalize_latex_cv(tex_content: str) -> str:
    """Ensure every .tex CV uses \\def\\mysummary{...} as the sole injection point.

    Rules (applied in order, idempotent):
    1. \\def\\mysummary already present → return unchanged.
    2. \\begin{rSection}{Summary/Profile/...} found → extract body text,
       add \\def\\mysummary{BODY} before \\begin{document},
       replace section body with just \\mysummary.
    3. \\section{Professional Summary/...} found → extract section body text,
       add \\def\\mysummary{BODY} before \\begin{document},
       replace entire section body with standard itemize+\\mysummary block.
    4. No summary section at all → add \\def\\mysummary{} to preamble
       and insert a standard Professional Summary section after \\begin{document}.
    """
    if _find_def_range(tex_content) is not None:
        return tex_content

    # Case 2: rSection style
    rm = _RSECTION_RE.search(tex_content)
    if rm:
        body_text = _strip_latex(rm.group(2).strip()).replace('%', r'\%')
        def_line = f'\\def\\mysummary{{{body_text}}}\n'
        tex = tex_content[:rm.start(2)] + '\n\\mysummary\n' + tex_content[rm.end(2):]
        return _insert_before_begin_document(tex, def_line)

    # Case 3: \section{...summary...} style
    sm = _SUMMARY_SECTION_RE.search(tex_content)
    if sm:
        content_start = sm.end()
        next_m = _NEXT_SECTION_RE.search(tex_content, content_start)
        content_end = next_m.start() if next_m else len(tex_content)
        body_text = _strip_latex(tex_content[content_start:content_end].strip()).replace('%', r'\%')
        def_line = f'\\def\\mysummary{{{body_text}}}\n'
        new_body = (
            '\n\\begin{itemize}[leftmargin=0.15in, label={}]\n'
            '  \\small{\\item{\\mysummary}}\n'
            '\\end{itemize}\n\n'
        )
        tex = tex_content[:content_start] + new_body + tex_content[content_end:]
        return _insert_before_begin_document(tex, def_line)

    # Case 4: No summary section at all
    tex = _insert_before_begin_document(tex_content, '\\def\\mysummary{}\n')
    bd = _BEGIN_DOCUMENT_RE.search(tex)
    if bd:
        insert_pos = bd.end()
        tex = tex[:insert_pos] + _SUMMARY_BLOCK + tex[insert_pos:]
    return tex


def _extract_document_body(tex: str) -> str:
    """Return only the content between \\begin{document} and \\end{document}."""
    m = re.search(r'\\begin\{document\}(.*?)(?:\\end\{document\}|$)', tex, re.DOTALL)
    return m.group(1) if m else tex


def parse_latex_cv(tex_content: str):
    """Returns (summary_text, cv_without_summary, cv_plain_text).

    Always normalizes the CV to \\def\\mysummary{} first.
    The AI receives only cv_plain_text (LaTeX stripped, document body only) — never raw LaTeX.
    The injection point is always \\def\\mysummary{[PLACEHOLDER]}.
    """
    tex = normalize_latex_cv(tex_content)
    dr = _find_def_range(tex)
    if dr:
        s, e = dr
        summary_text = _strip_latex(tex[s:e].strip())
        cv_without_summary = tex[:s] + '[PLACEHOLDER]' + tex[e:]
        no_summary = tex[:s] + tex[e:]
        return summary_text, cv_without_summary, _strip_latex(_extract_document_body(no_summary))
    return '', tex, _strip_latex(_extract_document_body(tex))


def get_cv_path(cv_id: str = None) -> str:
    cfg = load_config()
    cid = cv_id or cfg.get("active_id")
    if not cid:
        return ""
    cv = next((c for c in cfg.get("cvs", []) if c["id"] == cid), None)
    if not cv:
        return ""
    return os.path.join(CV_DIR, cv["filename"])


def delete(cv_id: str) -> bool:
    cfg = load_config()
    cv = next((c for c in cfg["cvs"] if c["id"] == cv_id), None)
    if not cv:
        return False
    fpath = os.path.join(CV_DIR, cv["filename"])
    if os.path.exists(fpath):
        os.remove(fpath)
    cfg["cvs"] = [c for c in cfg["cvs"] if c["id"] != cv_id]
    if cfg.get("active_id") == cv_id:
        cfg["active_id"] = cfg["cvs"][0]["id"] if cfg["cvs"] else None
    save_config(cfg)
    return True
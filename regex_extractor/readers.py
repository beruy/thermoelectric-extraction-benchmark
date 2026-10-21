"""
Document readers: turn a PDF or an arXiv (LaTeXML) HTML file into a list of
normalized paragraphs.

Each paragraph is a dict: {"para_id": str, "kind": "abstract"|"body"|"caption", "text": str}

READER_VERSION 2 (2026-10-13): PDF line blocks are merged into paragraphs by
layout (short last line, indentation) as well as by sentence cues; page
numbers are dropped; a paragraph interrupted by a figure or caption continues.
"""

READER_VERSION = 2

import re
import unicodedata
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Text normalization (shared by both readers)
# ---------------------------------------------------------------------------

_CHAR_MAP = {
    "\u2212": "-",   # minus sign
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u2013": "\u2013",  # en dash kept: used as range marker
    "\u223c": "~",   # tilde operator
    "\u02dc": "~",
    "\u00b5": "\u03bc",  # micro sign -> Greek mu
    "\u2126": "\u03a9",  # ohm sign -> Greek Omega
    "\u00a0": " ",
    "\u2009": " ",
    "\u200b": "",
    "\u2032": "'",
    "\u2217": "*",
}


_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_SUPERSCRIPT_RUN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+")


def normalize_text(text: str) -> str:
    """Unicode-normalize and collapse whitespace."""
    if not text:
        return ""
    # Keep exponents explicit BEFORE NFKC, which would flatten them:
    # '10⁵' -> '10^5' (not '105'), 'm⁻¹' -> 'm^-1'
    text = _SUPERSCRIPT_RUN.sub(lambda m: "^" + m.group(0).translate(_SUPERSCRIPTS), text)
    text = unicodedata.normalize("NFKC", text)   # ligatures, subscripts (Bi₂Te₃ -> Bi2Te3)
    text = "".join(_CHAR_MAP.get(ch, ch) for ch in text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    # Unit prefixes split from the unit by math rendering: 'μ V/K' -> 'μV/K'
    text = re.sub(r"(?<![A-Za-z])([μm])\s+(?=[VWΩS](?![a-z]))", r"\1", text)
    return text.strip()


_LATEX_SYMBOLS = {
    r"\mu": "μ", r"\kappa": "κ", r"\sigma": "σ", r"\rho": "ρ", r"\Omega": "Ω",
    r"\times": "×", r"\approx": "≈", r"\simeq": "≈", r"\sim": "~", r"\cdot": "·",
    r"\circ": "°", r"\%": "%", r"\pm": "±", r"\leq": "≤", r"\geq": "≥",
    r"\le": "≤", r"\ge": "≥", r"\lesssim": "≲", r"\gtrsim": "≳", r"\delta": "δ",
    r"\Delta": "Δ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\eta": "η",
    r"\lambda": "λ", r"\tau": "τ", r"\theta": "θ", r"\ell": "l",
    r"\textendash": "–", r"\textdegree": "°", r"\degree": "°",
}


def latex_to_text(tex: str) -> str:
    """Convert a LaTeX math snippet (LaTeXML 'alttext') to plain text."""
    s = tex
    # Font / text wrappers: keep the argument
    s = re.sub(r"\\(?:mathrm|text|textrm|mathit|mathbf|mathsf|operatorname|rm|it|bf|mbox|textit|textbf)\s*", "", s)
    # Spacing commands
    s = re.sub(r"\\[,;:! ]|\\quad|\\qquad|~", " ", s)
    # Symbols (longest first so '\simeq' wins over '\sim')
    for cmd in sorted(_LATEX_SYMBOLS, key=len, reverse=True):
        s = re.sub(re.escape(cmd) + r"(?![A-Za-z])", _LATEX_SYMBOLS[cmd], s)
    s = s.replace(r"\left", "").replace(r"\right", "")
    # Superscripts: ^{-1} -> ^-1 ; subscripts: _{2} -> 2 (formula subscripts)
    s = re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
    s = re.sub(r"_\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"_(\w)", r"\1", s)
    # Drop any remaining commands and braces
    s = re.sub(r"\\[A-Za-z]+", "", s)
    s = s.replace("{", "").replace("}", "")
    return normalize_text(s)


# ---------------------------------------------------------------------------
# HTML reader (arXiv / LaTeXML)
# ---------------------------------------------------------------------------

def read_html(path) -> list:
    from bs4 import BeautifulSoup  # imported lazily so PDF-only use has no bs4 dependency

    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")

    # Remove non-content parts
    for sel in [".ltx_bibliography", "header", "footer", "nav", ".ltx_page_footer",
                ".ltx_authors", ".ltx_dates", ".ltx_classification", "script", "style",
                ".ltx_TOC", ".ltx_role_footnote .ltx_tag"]:
        for el in soup.select(sel):
            el.decompose()

    # Replace every <math> with its plain-text alttext
    for m in soup.find_all("math"):
        alt = m.get("alttext") or m.get_text(" ")
        m.replace_with(" " + latex_to_text(alt) + " ")

    # Chemical subscripts / superscripts outside math: Bi<sub>2</sub>Te<sub>3</sub> -> Bi2Te3
    for el in soup.find_all("sub"):
        el.replace_with(el.get_text("").strip())
    for el in soup.find_all("sup"):
        el.replace_with("^" + el.get_text("").strip())

    root = soup.select_one(".ltx_page_content") or soup.body or soup
    paragraphs = []
    idx = 0

    for el in root.find_all(["p", "figcaption"]):
        if el.name == "p":
            if el.find_parent("figcaption") is not None:
                continue  # counted with its caption
            if "ltx_p" not in (el.get("class") or []) and el.find_parent(class_="ltx_para") is None \
                    and el.find_parent(class_="ltx_abstract") is None:
                continue
            kind = "abstract" if el.find_parent(class_="ltx_abstract") is not None else "body"
        else:
            kind = "caption"
        text = normalize_text(el.get_text(""))
        text = re.sub(r"\s+([,.;:)])", r"\1", text)
        text = re.sub(r"\(\s+", "(", text)
        if len(text) < 25:
            continue
        idx += 1
        pid = el.get("id") or f"p{idx:04d}"
        paragraphs.append({"para_id": f"{idx:04d}:{pid}", "kind": kind, "text": text})
    return paragraphs


# ---------------------------------------------------------------------------
# PDF reader
# ---------------------------------------------------------------------------

_REF_HEADING = re.compile(r"^\s*(?:\d+\.?\s*)?(references|bibliography|references and notes|literature cited)\s*:?\s*$", re.I)
_ACK_HEADING = re.compile(r"^\s*(?:\d+\.?\s*)?acknowledge?ments?\b", re.I)
# A caption starts "Figure 3." / "Fig. 3:" / "Table 2 Thermal ..." ; body text such
# as "Figure 4(a) shows ..." or "Fig. 3 shows ..." is not a caption.
_CAPTION = re.compile(r"^\s*(?:fig\.|figs\.|figure|table|tab\.)\s*[\dIVX]+[a-z]?"
                      r"(?:\s*[.:|]|\s+(?!shows?\b|presents?\b|illustrates?\b|depicts?\b|"
                      r"displays?\b|gives?\b|lists?\b|compares?\b|summari[sz]es?\b)(?-i:[A-Z(]))",
                      re.I)
# First entry of a numbered reference list without a heading: "(1) Rowe, D. M." / "[1] A. B. ..."
_REF_ENTRY = re.compile(r"^\s*(?:\((\d{1,3})\)|\[(\d{1,3})\])\s+\S")


def _clean_block(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", lambda m: m.group(1) + m.group(2)
                  if m.group(2).islower() else m.group(1) + "-" + m.group(2), text)
    text = text.replace("\n", " ")
    return normalize_text(text)


def _read_pdf_blocks_pymupdf(path):
    """Text blocks per page with geometry: {text, x0, y0, x1, y1, size}."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # older PyMuPDF
    pages = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            blocks = []
            for bl in page.get_text("dict")["blocks"]:
                if bl.get("type") != 0:
                    continue
                lines, sizes, boxes = [], [], []
                for ln in bl["lines"]:
                    lines.append("".join(sp["text"] for sp in ln["spans"]))
                    sizes += [sp["size"] for sp in ln["spans"] if sp["text"].strip()]
                    boxes.append(ln["bbox"])
                x0, y0, x1, y1 = bl["bbox"]
                blocks.append({"text": "\n".join(lines), "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                               "size": sorted(sizes)[len(sizes) // 2] if sizes else None,
                               # first-line start and last-line end: paragraph boundary cues
                               "first_x0": boxes[0][0] if boxes else x0,
                               "last_x1": boxes[-1][2] if boxes else x1})
            pages.append(blocks)
    return pages


def _read_pdf_blocks_pypdf(path):
    """Fallback without geometry: blank-line separated chunks per page."""
    from pypdf import PdfReader
    pages = []
    for page in PdfReader(str(path)).pages:
        txt = page.extract_text() or ""
        pages.append([{"text": c, "x0": None, "y0": None, "x1": None, "y1": None, "size": None,
                       "first_x0": None, "last_x1": None}
                      for c in re.split(r"\n\s*\n", txt)])
    return pages


_SENT_END = re.compile(r"[.!?:]\s*$")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?\s*$", re.I)


def _should_merge(para, nxt, prev_text, next_text):
    """Decide whether block `nxt` continues paragraph `para` (READER_VERSION 2).

    `para` holds the paragraph built so far: its last block ("last") and its
    left/right edges ("left", "right"). Many author manuscripts emit one block
    per LINE, often double-spaced, so lines are joined unless a paragraph
    boundary is visible:
      * the previous line is short (ends before the right edge), or
      * the next line is indented, or
      * the next block is a caption, a heading that ends the body, or text of
        a different font size / column.
    Text cues decide when geometry is missing or the paragraph crosses a
    column or page: the previous text ends mid-sentence AND the next one starts
    in lower case.
    """
    prev = para["last"]
    if _REF_HEADING.match(prev_text) or _ACK_HEADING.match(prev_text) \
            or _REF_HEADING.match(next_text) or _ACK_HEADING.match(next_text):
        return False
    if _CAPTION.match(next_text):
        return False
    open_end = not _SENT_END.search(prev_text) or prev_text.endswith("-")
    lower_start = bool(re.match(r"[a-z(,;]", next_text))
    text_cue = open_end and lower_start
    if prev["x0"] is None or nxt["x0"] is None:
        return text_cue

    size = prev["size"] or nxt["size"] or 10.0
    same_size = (prev["size"] is None or nxt["size"] is None
                 or abs(prev["size"] - nxt["size"]) <= 1.5)
    if not same_size:
        return text_cue

    if prev["page"] == nxt["page"]:
        # Pieces of one line (inline equations split into separate blocks)
        same_line = nxt["y0"] < prev["y1"] - 0.3 * size and nxt["x0"] >= prev["x1"] - 2 * size
        if same_line:
            return True
        overlap = min(prev["x1"], nxt["x1"]) - max(prev["x0"], nxt["x0"])
        narrow = max(1.0, min(prev["x1"] - prev["x0"], nxt["x1"] - nxt["x0"]))
        gap = nxt["y0"] - prev["y1"]
        if not (overlap >= 0.5 * narrow and -2.0 <= gap <= 2.6 * size):
            return text_cue                   # other column, or far below
    elif not open_end:
        return text_cue                       # crossing a page needs an open sentence

    width = max(1.0, para["right"] - para["left"])
    full_line = prev["last_x1"] >= para["right"] - max(1.5 * size, 0.04 * width)
    indented = nxt["first_x0"] > para["left"] + 0.8 * size
    if full_line and not indented:
        return True
    return text_cue


def _join(a: str, b: str) -> str:
    if a.endswith("-") and b[:1].islower():
        return a[:-1] + b          # de-hyphenate across lines
    return a + " " + b


def _starts_reference_list(text, following, pno, n_pages):
    """A numbered list "(1) ..." / "[1] ..." whose entries 2 and 3 follow within a
    few blocks, after page 2: a reference list without a heading."""
    m = _REF_ENTRY.match(text)
    if not m or (m.group(1) or m.group(2)) != "1" or pno < 3:
        return False
    def has(n):
        return any(re.match(r"^\s*(?:\(%d\)|\[%d\])\s+\S" % (n, n), t) for t in following)
    return has(2) and has(3)


def read_pdf(path, backend: str = "auto") -> list:
    if backend in ("auto", "pymupdf"):
        try:
            pages = _read_pdf_blocks_pymupdf(path)
        except ImportError:
            if backend == "pymupdf":
                raise
            pages = _read_pdf_blocks_pypdf(path)
    else:
        pages = _read_pdf_blocks_pypdf(path)

    # Running headers/footers: identical short blocks on >= 3 pages
    counts = Counter()
    for blocks in pages:
        for t in set(_clean_block(b["text"]) for b in blocks):
            if len(t) < 120:
                counts[t] += 1
    repeated = {t for t, c in counts.items() if c >= 3}

    # 1) Clean blocks in reading order, drop headers/footers, stop at references
    seq = []
    for pno, blocks in enumerate(pages, start=1):
        stop = False
        cleaned = [_clean_block(b["text"]) for b in blocks]
        for bno, b in enumerate(blocks):
            text = cleaned[bno]
            if not text or text in repeated or text.startswith("arXiv:") or _PAGE_NUMBER.match(text):
                continue
            if _REF_HEADING.match(text) or _starts_reference_list(text, cleaned[bno + 1:bno + 12],
                                                                    pno, len(pages)):
                stop = True
                break
            seq.append({**b, "page": pno, "bno": bno, "clean": text})
        if stop:
            break

    # 2) Merge line-level blocks into paragraphs
    merged = []
    last_body = None      # body paragraph that a figure or caption may have interrupted

    def extend(m, b):
        m["text"] = _join(m["text"], b["clean"])
        m["last"] = b
        m["n_blocks"] += 1
        if b["x0"] is not None and m["left"] is not None:
            m["left"] = min(m["left"], b["x0"])
            m["right"] = max(m["right"], b["x1"])

    for b in seq:
        is_caption = bool(_CAPTION.match(b["clean"]))
        if merged and _should_merge(merged[-1], b, merged[-1]["text"], b["clean"]):
            extend(merged[-1], b)
            continue
        # Body text resuming after a caption or figure label: continue the
        # interrupted paragraph when it ended mid-sentence.
        if (not is_caption and last_body is not None and last_body is not merged[-1]
                and not _SENT_END.search(last_body["text"])
                and re.match(r"[a-z(,;]", b["clean"])):
            extend(last_body, b)
            continue
        m = {"text": b["clean"], "first": b, "last": b, "n_blocks": 1,
             "left": b["x0"], "right": b["x1"], "caption": is_caption}
        merged.append(m)
        if not is_caption:
            last_body = m

    # 3) Emit paragraphs
    paragraphs = []
    idx = 0
    for m in merged:
        text, first = m["text"], m["first"]
        if _ACK_HEADING.match(text) or len(text) < 25:
            continue
        idx += 1
        pno = first["page"]
        kind = "caption" if _CAPTION.match(text) else (
            "abstract" if pno == 1 and re.search(r"\babstract\b", text[:40], re.I) else "body")
        paragraphs.append({"para_id": f"{idx:04d}:p{pno}b{first['bno']}", "kind": kind, "text": text,
                           "n_blocks": m["n_blocks"]})
    return paragraphs


def read_document(path, pdf_backend: str = "auto") -> list:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return read_pdf(p, backend=pdf_backend)
    if p.suffix.lower() in (".html", ".htm"):
        return read_html(p)
    raise ValueError(f"Unsupported file type: {p}")

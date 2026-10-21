"""
Rule-based (regex) candidate extractor for thermoelectric properties.

Purpose in the study
--------------------
1. "Baseline 0": a deterministic, zero-cost lower bound that the NER
   (MaterialsBERT) and LLM methods are compared against.
2. Sampling frame: the paragraphs it flags (and the ones it does NOT flag but
   that look relevant) are the pool the gold-standard sample is drawn from.

Design choices
--------------
* Unit-bearing properties (S, kappa, sigma, rho, PF, carrier concentration)
  are anchored on the UNIT, which identifies the property almost uniquely.
* ZT is unitless, so it is anchored on the keyword (ZT / zT / figure of merit).
* Doping is anchored on 'X-doped', 'doped with X', 'at.%/mol%/wt%' and
  carrier concentration (cm-3).
* Material and temperature are attached by proximity inside the sentence.
* High recall is preferred over precision: suspicious hits are FLAGGED, not
  dropped, so the error analysis can see them.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
FLAG_OUT_OF_RANGE = "out_of_range"
FLAG_DERIVED_RHO = "derived_from_resistivity"
FLAG_COMPUTED = "computational_context"        # calculated / predicted / DFT in sentence
FLAG_CITATION = "citation_in_sentence"         # value may belong to cited work
FLAG_RT_APPROX = "room_temperature_as_300K"
FLAG_UNIT_EXP_MISSING = "unit_exponent_missing"  # e.g. 'μV K' where '-1' was lost in PDF
FLAG_NO_MATERIAL = "no_material_found"
FLAG_SUPERSCRIPT_GUESS = "pdf_flattened_exponent_guess"  # '10-4' read as 10^-4, '1017' as 10^17
FLAG_EXP_AMBIGUOUS = "ambiguous_flattened_exponent"      # both readings plausible; see value_alt

# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
_NUM = (r"(?:10\s*\^\s*\(?\s*[-+]?\d{1,2}\s*\)?(?![\d.])|(?:[-+±]\s?)?(?:\d+(?:\.\d+)?|\.\d+)"
        r"(?:\s*(?:×|\*)\s*10\s*\^?\s*\(?\s*[-+]?\s*\d{1,2}\s*\)?|[eE][-+]?\d{1,2})?)")
_RANGE_SEP = r"\s*(?:–|—|-|to|~)\s*"
_VAL = rf"(?P<v1>{_NUM})(?:{_RANGE_SEP}(?P<v2>{_NUM}))?(?:\s*±\s*{_NUM})?"
_SP = r"\s*"
_MUL = r"\s*[·.\s]?\s*"                      # 'W m', 'W·m', 'Wm'
_INV1 = r"\s*\^?\s*\(?\s*-\s*1\s*\)?"        # '-1', '^-1', '^(-1)'
_INV2 = r"\s*\^?\s*\(?\s*-\s*2\s*\)?"
_SQ = r"\s*\^?\s*2"
_MU = r"[μu]"

_UNITS = {
    # property -> list of (regex, unit_id)
    "S_uVK": [
        (rf"(?P<pfx>{_MU}|m)?V(?:\s*/\s*K|{_MUL}K{_INV1})(?![a-zA-Z])", "V/K"),
        (rf"(?P<pfx>{_MU})V\s?K(?![a-zA-Z0-9\-^])", "V/K?"),      # '-1' lost in PDF extraction
    ],
    "PF": [
        (rf"(?P<pfx>{_MU}|m)?W(?:\s*/\s*\(?\s*(?P<len>cm|m){_MUL}K{_SQ}\s*\)?"
         rf"|\s*/\s*(?P<len2>cm|m)\s*/\s*K{_SQ}"
         rf"|{_MUL}(?P<len3>cm|m){_INV1}{_MUL}K{_INV2})(?![a-zA-Z0-9])", "W/lenK2"),
    ],
    "kappa": [
        (rf"(?P<pfx>m)?W(?:\s*/\s*\(?\s*(?P<len>cm|m){_MUL}K\s*\)?(?!\s*\^?\s*2)"
         rf"|\s*/\s*(?P<len2>cm|m)\s*/\s*K(?!\s*\^?\s*2)"
         rf"|{_MUL}(?P<len3>cm|m){_INV1}{_MUL}K{_INV1})(?![a-zA-Z0-9])", "W/lenK"),
    ],
    "sigma": [
        (rf"(?P<pfx>k|M)?S(?:\s*/\s*(?P<len>cm|m)|{_MUL}(?P<len2>cm|m){_INV1})(?![a-zA-Z0-9\-])", "S/len"),
        (rf"\(\s*Ω{_MUL}(?P<len>cm|m)\s*\){_INV1}|Ω{_INV1}{_MUL}(?P<len2>cm|m){_INV1}", "S/len"),
    ],
    "rho": [
        (rf"(?P<pfx>{_MU}|m)?Ω{_MUL}(?P<len>cm|m)(?![a-zA-Z0-9\-^)])", "Ohm*len"),
    ],
    "carrier": [
        (r"cm\s*\^?\s*\(?\s*-\s*3\s*\)?(?![0-9])", "cm-3"),
    ],
}

_ZT_KEY = r"(?P<key>(?<![A-Za-z])[zZ]\s?T(?:\s?_?\s?(?P<zq>max|avg|ave|av|peak|dev|eng|ave\.))?(?![A-Za-z(])|figures?[- ]of[- ]merit(?:\s*\(\s*[zZ]T\s*\))?)"
_ZT_GAP = r"(?P<gap>(?:[^.;:\d\[\]()]|\((?![^)]*\d)[^)]*\)){0,45}?)"
_ZT_RE = re.compile(
    rf"{_ZT_KEY}{_ZT_GAP}(?<![A-Za-zα-ωΑ-Ω^/_\d.])(?P<val>{_VAL})"
    rf"(?P<more>(?:\s*(?:,|and|or|,\s*and)\s*{_NUM}(?![\d.]))*)",
    re.UNICODE,
)
# Things that, right after a ZT number, show it was not a ZT value
_ZT_BAD_TAIL = re.compile(r"^\s*(?:K(?![a-z])|°|%|μ|u[VW]|W|S\b|cm|nm|mm|eV|meV|GPa|h\b|min|s\b|years?|times|fold|orders?|×\s*10)")

_TEMP_RE = re.compile(
    rf"(?P<t1>\d+(?:\.\d+)?)(?:{_RANGE_SEP}(?P<t2>\d+(?:\.\d+)?))?\s*(?P<u>K|°\s?C)(?![a-zA-Z\-^/0-9])"
)
_RT_RE = re.compile(r"\broom[- ]temperature\b|\bRT\b", re.I)

_DOPED_RE = re.compile(r"(?<![A-Za-z])(?P<el>[A-Z][a-z]?)\s?-\s?(?:co-)?doped\b|\bdoped with\s+(?P<el2>[A-Z][a-z]?)(?![a-z])")
_ATPCT_RE = re.compile(rf"(?P<v>\d+(?:\.\d+)?)(?:{_RANGE_SEP}\d+(?:\.\d+)?)?\s*(?P<u>at\.?\s?%|mol\s?%|wt\.?\s?%)(?:\s*(?:of\s+)?(?P<el>[A-Z][a-z]?)(?![a-z]))?")
_XEQ_RE = re.compile(rf"\b[xyδ]\s*=\s*(?P<v>\d*\.?\d+(?:\s*,\s*\d*\.?\d+)*(?:\s*,?\s*and\s*\d*\.?\d+)?)")
_DOPING_CONTEXT = re.compile(r"dop|substitut|content|concentration|alloy", re.I)

_COMPUTED_RE = re.compile(r"calculat|predict|first[- ]principles|\bDFT\b|ab[- ]initio|theoretic|simulat|BoltzTraP|model(?:ed|led)", re.I)
_CITE_RE = re.compile(r"\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]|\bRefs?\.\s*\d|\bet al\.")

# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga
Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb
Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu""".split())

_FORMULA_TOKEN = re.compile(r"(?<![A-Za-z0-9])[(\[]?[A-Z][A-Za-z0-9.()\[\],+\-δ]*[A-Za-z0-9)δ\]]")
_ELEMENT_PART = re.compile(r"([A-Z][a-z]?)((?:\d+(?:\.\d+)?)?(?:[-+][\d.]*[xyzδ])?(?:[\d.]*[xyzδ])?)")


def is_formula(token: str) -> bool:
    t = token.strip("()[],")
    if len(t) < 2 or len(t) > 40:
        return False
    if t.isupper() and not any(c.isdigit() for c in t):
        return False                                   # acronyms: PF, IV, UV, SC ...
    core = re.sub(r"[()\[\],]", "", t)
    parts = _ELEMENT_PART.findall(core)
    if "".join(a + b for a, b in parts) != core:
        return False
    if any(el not in ELEMENTS for el, _ in parts):
        return False
    return len(parts) >= 2


def find_materials(text: str):
    """Return list of (start, end, formula)."""
    out = []
    for m in _FORMULA_TOKEN.finditer(text):
        tok = m.group(0)
        # Split off trailing '-based', '-type' etc. that the token regex may keep
        tok = re.split(r"-(?=[a-z])", tok)[0]
        cleaned = tok.rstrip(".,-")
        if is_formula(cleaned):
            out.append((m.start(), m.start() + len(cleaned), cleaned.strip("()[]")))
    return out

# ---------------------------------------------------------------------------
# Numbers and units
# ---------------------------------------------------------------------------

def parse_number(s: str) -> Optional[float]:
    if s is None:
        return None
    s = s.replace(" ", "").replace("±", "")
    pm = re.match(r"^10\^\(?([-+]?\d{1,2})\)?$", s)
    if pm:
        return 10.0 ** int(pm.group(1))
    m = re.match(r"^([-+]?(?:\d+(?:\.\d+)?|\.\d+))(?:(?:×|\*)10\^?\(?([-+]?\d{1,2})\)?|[eE]([-+]?\d{1,2}))?$", s)
    if not m:
        return None
    base = float(m.group(1))
    exp = m.group(2) or m.group(3)
    return base * (10 ** int(exp)) if exp else base


_PFX = {None: 1.0, "": 1.0, "μ": 1e-6, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6}


def _len_of(m):
    for g in ("len", "len2", "len3"):
        try:
            if m.group(g):
                return m.group(g)
        except IndexError:
            pass
    return "m"


def to_canonical(prop: str, value: float, unit_match) -> Optional[float]:
    """Convert a value to the canonical unit defined in schema.CANONICAL_UNITS."""
    gd = unit_match.groupdict()
    pfx = _PFX.get(gd.get("pfx"), 1.0)
    length = _len_of(unit_match)
    if prop == "S_uVK":                      # -> μV/K
        return value * pfx / 1e-6
    if prop == "kappa":                      # -> W m-1 K-1
        return value * pfx * (100.0 if length == "cm" else 1.0)
    if prop == "PF":                         # -> μW cm-1 K-2
        per_m = value * pfx * (100.0 if length == "cm" else 1.0)   # W m-1 K-2
        return per_m * 1e6 / 100.0
    if prop == "sigma":                      # -> S m-1
        return value * pfx * (100.0 if length == "cm" else 1.0)
    if prop == "rho":                        # -> Ohm m
        return value * pfx * (0.01 if length == "cm" else 1.0)
    if prop == "carrier":                    # cm-3
        return value
    return value


_RANGES = {  # plausible ranges in canonical units (outside -> flagged)
    "ZT": (0.0, 5.0),
    "S_uVK": (-2000.0, 2000.0),
    "kappa": (0.01, 3000.0),
    "sigma": (1e-4, 1e9),
    "PF": (0.01, 500.0),
    "carrier": (1e13, 1e23),
}


def _out_value(prop, value, unit_match):
    """Canonical value in the OUTPUT property (rho is reported as sigma = 1/rho)."""
    c = to_canonical(prop, value, unit_match)
    if prop == "rho":
        return 1.0 / c if c else None
    return c


def _plausible_out(prop, value, unit_match):
    out_prop = {"rho": "sigma"}.get(prop, prop)
    c = _out_value(prop, value, unit_match)
    lo, hi = _RANGES[out_prop]
    if c is None:
        return False
    return lo <= (abs(c) if out_prop == "S_uVK" else c) <= hi


# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------
_NO_SPLIT_BEFORE = re.compile(r"(?:\b(?:Fig|Figs|Eq|Eqs|Ref|Refs|al|e\.g|i\.e|vs|ca|approx|No|Tab|Sec|resp|cf|Ph\.D|et)\.)$")


def sentence_spans(text: str):
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?=\s+[A-Z(\[])", text):
        if _NO_SPLIT_BEFORE.search(text[max(0, m.start() - 8): m.end()]):
            continue
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    return spans


def _sentence_of(spans, pos):
    for s, e in spans:
        if s <= pos < e:
            return s, e
    return spans[-1]

# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    property: str
    value: Optional[float]
    value_max: Optional[float]
    unit: str
    value_text: str
    start: int
    end: int
    qualifier: Optional[str] = None
    dopant: Optional[str] = None
    T_K: Optional[float] = None
    T_text: Optional[str] = None
    material: Optional[str] = None
    material_link: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    sentence: str = ""
    value_alt: Optional[float] = None   # alternative reading (flattened exponent)

    def to_dict(self):
        return asdict(self)

    def tidy(self):
        """Round float noise from unit conversion and strip raw text."""
        if self.value is not None:
            self.value = float(f"{self.value:.6g}")
        if self.value_max is not None:
            self.value_max = float(f"{self.value_max:.6g}")
        if self.value_alt is not None:
            self.value_alt = float(f"{self.value_alt:.6g}")
        self.value_text = self.value_text.strip()
        if self.value_text.endswith(")") and "(" not in self.value_text:
            self.value_text = self.value_text[:-1].rstrip()
        return self


_CANON_UNIT = {"ZT": "dimensionless", "S_uVK": "uV K-1", "kappa": "W m-1 K-1",
               "sigma": "S m-1", "PF": "uW cm-1 K-2", "doping": "text"}


class RegexExtractor:
    """Extract thermoelectric property candidates from normalized paragraph text."""

    def __init__(self, temp_window: int = 90):
        self.temp_window = temp_window
        self._unit_res = {p: [(re.compile(rf"(?P<val>{_VAL})\s*(?:{u})", re.UNICODE), uid)
                              for u, uid in lst] for p, lst in _UNITS.items()}

    # -- public -----------------------------------------------------------
    def extract(self, text: str) -> List[Candidate]:
        spans = sentence_spans(text)
        materials = find_materials(text)
        cands = []
        cands += self._extract_unit_props(text)
        cands += self._extract_zt(text)
        cands += self._extract_doping(text)
        cands = self._resolve_overlaps(cands)
        for c in cands:
            self._attach_context(c, text, spans, materials)
        cands.sort(key=lambda c: c.start)
        return [c.tidy() for c in cands]

    # -- unit-anchored properties -------------------------------------------
    def _extract_unit_props(self, text):
        out = []
        for prop, res in self._unit_res.items():
            for rx, uid in res:
                for m in rx.finditer(text):
                    v1 = parse_number(m.group("v1"))
                    if v1 is None:
                        continue
                    v2 = parse_number(m.group("v2")) if m.group("v2") else None
                    flags = []
                    # '5-25 × 10^19': exponent written once for the whole range
                    if v2 is not None and re.search(r"×|\*|[eE]|\^", m.group("v2")) \
                            and not re.search(r"×|\*|[eE]|\^", m.group("v1")):
                        mantissa = parse_number(re.split(r"\s*(?:×|\*|[eE])", m.group("v2"))[0])
                        if mantissa:  # skip scaling when the mantissa is 0 or unparsable
                            v1 = v1 * (v2 / mantissa)
                    # PDF superscripts flattened: '10-4 W' (=10^-4), '1017 cm-3' (=10^17).
                    # The exponent reading is adopted only if the literal reading is
                    # implausible AND the exponent reading is plausible, both judged in
                    # the OUTPUT property's canonical unit (i.e. after rho -> sigma).
                    # If both readings are plausible, the literal one is kept, the
                    # candidate is flagged and the alternative is stored in value_alt.
                    guess, value_alt = None, None
                    val_txt = m.group("val").strip()
                    fm = re.match(r"^10\s?-\s?(\d{1,2})$", val_txt)
                    if fm:
                        guess = 10.0 ** -int(fm.group(1))
                    fm = re.match(r"^10(\d{2})$", val_txt)
                    if fm and prop == "carrier":
                        guess = 10.0 ** int(fm.group(1))
                    if guess is not None:
                        literal_ok = all(_plausible_out(prop, v, m) for v in (v1, v2) if v is not None)
                        guess_ok = _plausible_out(prop, guess, m)
                        if guess_ok and not literal_ok:
                            v1, v2 = guess, None
                            flags.append(FLAG_SUPERSCRIPT_GUESS)
                        elif guess_ok and literal_ok:
                            value_alt = _out_value(prop, guess, m)
                            flags.append(FLAG_EXP_AMBIGUOUS)
                    if v2 is not None and v2 < v1:
                        v1, v2 = v2, v1
                    c1 = to_canonical(prop, v1, m)
                    c2 = to_canonical(prop, v2, m) if v2 is not None else None
                    if uid == "V/K?":
                        flags.append(FLAG_UNIT_EXP_MISSING)
                    out_prop, qual = prop, None
                    if prop == "rho":                     # convert to sigma
                        if not c1:
                            continue
                        c1, c2 = 1.0 / c1, (1.0 / c2 if c2 else None)
                        if c2 is not None:
                            c1, c2 = min(c1, c2), max(c1, c2)
                        out_prop = "sigma"
                        flags.append(FLAG_DERIVED_RHO)
                    elif prop == "carrier":
                        out_prop, qual = "doping", "carrier_concentration"
                    rng = _RANGES.get("carrier" if prop == "carrier" else out_prop)
                    if rng and not (rng[0] <= abs(c1) <= rng[1] if out_prop == "S_uVK" else rng[0] <= c1 <= rng[1]):
                        flags.append(FLAG_OUT_OF_RANGE)
                    out.append(Candidate(
                        property=out_prop, value=c1, value_max=c2,
                        unit="cm-3" if prop == "carrier" else _CANON_UNIT[out_prop],
                        value_text=m.group(0), start=m.start(), end=m.end(),
                        qualifier=qual, flags=flags, value_alt=value_alt))
        return out

    # -- ZT ------------------------------------------------------------------
    def _extract_zt(self, text):
        out = []
        for m in _ZT_RE.finditer(text):
            gap = m.group("gap") or ""
            if re.search(r"\b(?:at|from|between|in|for|with|than)\b\s*$", gap) or \
                    re.search(r"(?:\bFig(?:ure)?s?\.?|\bEq(?:uation)?s?\.?|\bTable|\bRefs?\.?|\bSec(?:tion)?\.?|\b[xyδ]\s*=)\s*$", gap):
                # 'ZT at 300 K' / 'ZT in 2012' -> the number is not ZT
                continue
            val_end = m.end("val")
            if _ZT_BAD_TAIL.match(text[val_end:val_end + 12]):
                continue
            v1 = parse_number(m.group("v1"))
            if v1 is None or v1 < 0 or v1 > 10:
                continue
            v2 = parse_number(m.group("v2")) if m.group("v2") else None
            if v2 is not None and (v2 > 10 or v2 < v1):
                v2 = None
            qual = None
            zq = (m.group("zq") or "").lower()
            ctx = text[max(0, m.start() - 30): m.start()].lower() + gap.lower()
            if zq in ("max", "peak") or re.search(r"\b(?:max(?:imum)?|peak|highest|record)\b", ctx):
                qual = "max"
            elif zq.startswith("av") or re.search(r"\baverage\b", ctx):
                qual = "avg"
            flags = [FLAG_OUT_OF_RANGE] if v1 > _RANGES["ZT"][1] else []
            out.append(Candidate("ZT", v1, v2, "dimensionless", text[m.start():val_end],
                                 m.start(), val_end, qualifier=qual, flags=flags))
            # enumerations: 'ZT values of 0.8, 1.1 and 1.4'
            more = m.group("more") or ""
            if more:
                base = m.end("val")
                for nm in re.finditer(_NUM, more):
                    v = parse_number(nm.group(0))
                    if v is None or v > 10:
                        continue
                    s = base + nm.start()
                    out.append(Candidate("ZT", v, None, "dimensionless", nm.group(0), s,
                                         base + nm.end(), qualifier=qual, flags=[]))
        return out

    # -- doping ----------------------------------------------------------------
    def _extract_doping(self, text):
        out = []
        for m in _DOPED_RE.finditer(text):
            el = m.group("el") or m.group("el2")
            if el in ELEMENTS:
                out.append(Candidate("doping", None, None, "text", m.group(0), m.start(), m.end(),
                                     qualifier="dopant", dopant=el))
        for m in _ATPCT_RE.finditer(text):
            v = parse_number(m.group("v"))
            el = m.group("el") if m.group("el") in ELEMENTS else None
            out.append(Candidate("doping", v, None, re.sub(r"\s", "", m.group("u")), m.group(0),
                                 m.start(), m.end(), qualifier="level", dopant=el))
        for m in _XEQ_RE.finditer(text):
            s, e = max(0, m.start() - 120), min(len(text), m.end() + 60)
            if not _DOPING_CONTEXT.search(text[s:e]):
                continue
            for nm in re.finditer(r"\d*\.?\d+", m.group("v")):
                v = parse_number(nm.group(0))
                if v is not None and v <= 1.0:
                    out.append(Candidate("doping", v, None, "x", f"x = {nm.group(0)}",
                                         m.start(), m.end(), qualifier="composition_x"))
        return out

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _resolve_overlaps(cands):
        """Keep the longest match when unit-anchored matches overlap (e.g. PF vs kappa)."""
        numeric = [c for c in cands if c.property != "doping" or c.qualifier == "carrier_concentration"]
        others = [c for c in cands if c not in numeric]
        numeric.sort(key=lambda c: (c.start, -(c.end - c.start)))
        kept = []
        for c in numeric:
            clash = next((k for k in kept if c.start < k.end and k.start < c.end), None)
            if clash is None:
                kept.append(c)
            elif (c.end - c.start) > (clash.end - clash.start) and c.property != "ZT":
                kept.remove(clash)
                kept.append(c)
        # dedupe identical doping hits
        seen, uniq = set(), []
        for c in others:
            key = (c.start, c.value, c.dopant, c.qualifier)
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        return kept + uniq

    def _attach_context(self, c: Candidate, text, spans, materials):
        s, e = _sentence_of(spans, c.start)
        sent = text[s:e]
        c.sentence = sent.strip()

        # Temperature: forward inside the sentence, then backward
        if c.property != "doping":
            fwd = text[c.end: min(e, c.end + self.temp_window)]
            tm = _TEMP_RE.search(fwd)
            if tm and not re.search(r"[;]", fwd[:tm.start()]):
                c.T_K, c.T_text = self._temp(tm), tm.group(0)
            else:
                back = text[max(s, c.start - self.temp_window): c.start]
                tms = [x for x in _TEMP_RE.finditer(back)]
                if tms:
                    c.T_K, c.T_text = self._temp(tms[-1]), tms[-1].group(0)
                elif _RT_RE.search(sent):
                    c.T_K, c.T_text = 300.0, _RT_RE.search(sent).group(0)
                    c.flags.append(FLAG_RT_APPROX)

        # Kappa sub-type
        if c.property == "kappa":
            pre = text[max(s, c.start - 70): c.start]
            if re.search(r"κ\s?_?\s?(?:L|l|lat|ph)\b|lattice", pre):
                c.qualifier = "lattice"
            elif re.search(r"κ\s?_?\s?(?:e|el)\b|electronic", pre):
                c.qualifier = "electronic"
            elif re.search(r"bipolar", pre):
                c.qualifier = "bipolar"
            else:
                c.qualifier = c.qualifier or "total_or_unspecified"

        # Material: nearest formula before the value in the sentence, else after, else paragraph
        in_sent = [mt for mt in materials if s <= mt[0] < e]
        before = [mt for mt in in_sent if mt[1] <= c.start]
        after = [mt for mt in in_sent if mt[0] >= c.end]
        if before:
            c.material, c.material_link = before[-1][2], "sentence_before"
        elif after:
            c.material, c.material_link = after[0][2], "sentence_after"
        else:
            para_before = [mt for mt in materials if mt[1] <= c.start]
            if para_before:
                c.material, c.material_link = para_before[-1][2], "paragraph"
            elif materials:
                c.material, c.material_link = materials[0][2], "paragraph"
            else:
                c.flags.append(FLAG_NO_MATERIAL)

        if _COMPUTED_RE.search(sent):
            c.flags.append(FLAG_COMPUTED)
        if _CITE_RE.search(sent):
            c.flags.append(FLAG_CITATION)

    @staticmethod
    def _temp(m):
        t = float(m.group("t1"))
        if m.group("u").replace(" ", "") == "°C":
            t += 273.15
        return round(t, 2)


# Keywords that make a paragraph "relevant" even without a regex hit.
# Used to build the 'possible miss' stratum for recall estimation.
RELEVANCE_RE = re.compile(
    r"thermoelectric|seebeck|figure[- ]of[- ]merit|\b[zZ]T\b|power factor|thermal conductivity|"
    r"electrical conductivity|resistivity|carrier concentration|dop(?:ed|ing|ant)", re.I)

# Explicit evaluation scope. The SAME rule is applied to every paragraph in the
# sample (whatever its stratum) and to every method's output when scoring, so
# "in-scope precision/recall" means the same thing for all methods.
SCOPE_RULE = ("in_scope = RELEVANCE_RE matches (thermoelectric keyword) "
              "AND the paragraph contains at least one digit")


def in_scope(text: str) -> bool:
    return bool(RELEVANCE_RE.search(text)) and bool(re.search(r"\d", text))


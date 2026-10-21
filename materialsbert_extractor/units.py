"""
Unit parsing and conversion to the contract's canonical units (method M2).

Pure Python, no dependencies, so it is unit-tested in the main environment.

parse_unit("μW cm^{-1} K^{-2}") -> (factor to SI, {base: exponent})
to_canonical("PF", 25.0, "μW cm^{-1} K^{-2}") -> 25.0

Bases: V, W, S, m, K (Ω is stored as S^-1). Temperature differences in °C equal
those in K, so "μV/°C" is accepted for the Seebeck coefficient.
"""

import re

# atom -> (factor to SI, base, exponent of the base per atom)
_ATOMS = {}
for prefix, f in (("", 1.0), ("m", 1e-3), ("μ", 1e-6), ("u", 1e-6), ("k", 1e3), ("n", 1e-9)):
    for base in ("V", "W", "S"):
        _ATOMS[prefix + base] = (f, base, 1)
    _ATOMS[prefix + "Ω"] = (f, "S", -1)
for name, f in (("m", 1.0), ("cm", 1e-2), ("mm", 1e-3), ("μm", 1e-6), ("nm", 1e-9)):
    _ATOMS[name] = (f, "m", 1)
_ATOMS["K"] = (1.0, "K", 1)
_ATOMS["°C"] = (1.0, "K", 1)
_ATOMS["ohm"] = _ATOMS["Ohm"] = (1.0, "S", -1)
_SORTED = sorted(_ATOMS, key=len, reverse=True)

TARGETS = {   # property -> (dimension signature, SI -> canonical factor)
    "S_uVK": ({"V": 1, "K": -1}, 1e6),
    "kappa": ({"W": 1, "m": -1, "K": -1}, 1.0),
    "sigma": ({"S": 1, "m": -1}, 1.0),
    "PF": ({"W": 1, "m": -1, "K": -2}, 1e4),
    "doping": ({"m": -3}, 1e-6),
    "ZT": ({}, 1.0),
}
RESISTIVITY = {"S": -1, "m": 1}


def normalise_unit_text(u):
    u = (u or "").strip()
    u = u.replace("µ", "μ").replace("−", "-").replace("–", "-").replace("Ω", "Ω")
    sup = str.maketrans("⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "-0123456789")
    u = re.sub(r"[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^" + m.group(0).translate(sup), u)
    u = u.replace("{", "").replace("}", "").replace("^", "")
    u = re.sub(r"[·⋅*.]", " ", u)
    u = re.sub(r"\b[Dd]eg\.?\s*C\b|°\s*C|℃", "°C", u)
    return u.strip()


def _split_atom(word):
    """'Wm' -> ['W', 'm']; 'mK' -> ['m', 'K']; None if not decomposable."""
    if word in _ATOMS and word != "mK":
        return [word]
    for a in _SORTED:
        if word.startswith(a) and a != word:
            rest = _split_atom(word[len(a):])
            if rest is not None:
                return [a] + rest
    return None


_TOKEN = re.compile(r"\(|\)\s*-?\d*|/|[A-Za-zΩμ°]+\s*-?\d*")


def _tokenize(s):
    pos, tokens = 0, []
    for m in _TOKEN.finditer(s):
        if s[pos:m.start()].strip():
            return None          # something the grammar does not cover
        t = m.group(0).replace(" ", "")
        if t.startswith(")") and len(t) > 1:
            tokens += [")", t[1:]]   # "(Ω cm)-1": closing parenthesis and its exponent
        else:
            tokens.append(t)
        pos = m.end()
    if s[pos:].strip():
        return None
    return tokens


def parse_unit(text):
    """Return (factor to SI, {base: exponent}) or None if the unit is not understood.

    Grammar: atoms with an optional integer exponent ("K-1", "cm-3"), glued atoms
    ("Wm-1K-1", "W/mK"), parenthesised groups with an exponent ("(Ω cm)-1"), and
    "/" which inverts every following factor ("μW/cm K2")."""
    s = normalise_unit_text(text)
    if not s:
        return 1.0, {}
    tokens = _tokenize(s)
    if tokens is None:
        return None

    def group(i, depth):
        factor, dims, sign = 1.0, {}, 1
        while i < len(tokens):
            t = tokens[i]
            if t == "(":
                f, d, i = group(i + 1, depth + 1)
                exp = 1
                if i < len(tokens) and re.fullmatch(r"-?\d+", tokens[i]):
                    exp = int(tokens[i])
                    i += 1
                factor *= f ** (exp * sign)
                for b, e in d.items():
                    dims[b] = dims.get(b, 0) + e * exp * sign
                continue
            if t == ")":
                if depth == 0:
                    raise ValueError("unbalanced")
                return factor, dims, i + 1
            if t == "/":
                sign = -1
                i += 1
                continue
            m = re.fullmatch(r"([A-Za-zΩμ°]+)(-?\d+)?", t)
            pieces = _split_atom(m.group(1)) if m else None
            if pieces is None:
                raise ValueError(t)
            exp_last = int(m.group(2)) if m.group(2) else 1
            for k, p in enumerate(pieces):
                f, base, e = _ATOMS[p]
                exp = exp_last if k == len(pieces) - 1 else 1
                factor *= f ** (exp * sign)
                dims[base] = dims.get(base, 0) + e * exp * sign
            i += 1
        if depth:
            raise ValueError("unbalanced")
        return factor, dims, i

    try:
        factor, dims, _ = group(0, 0)
    except (ValueError, IndexError):
        return None
    return factor, {b: e for b, e in dims.items() if e}


def to_canonical(prop, value, unit, resistivity=False):
    """Convert value in `unit` to the canonical unit of `prop`.

    Returns (value, None) or (None, reason). For sigma, a resistivity unit (or
    resistivity=True with a resistivity unit) gives sigma = 1/rho."""
    if value is None:
        return None, "no numeric value"
    parsed = parse_unit(unit)
    if parsed is None:
        return None, f"unit not understood: {unit!r}"
    factor, dims = parsed
    target, out = TARGETS[prop]
    if prop == "ZT":
        return (value, None) if not dims else (None, f"ZT with a unit: {unit!r}")
    if not dims:
        return None, "no unit"
    if prop == "sigma" and dims == RESISTIVITY:
        si = value * factor
        if si == 0:
            return None, "zero resistivity"
        return 1.0 / si, None
    if dims != target:
        return None, f"unit {unit!r} does not fit {prop}"
    return value * factor * out, None

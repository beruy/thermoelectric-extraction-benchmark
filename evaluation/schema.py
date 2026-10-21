"""
Method-independent contract for the thermoelectric extraction benchmark.

Every extraction method reads INPUT_FIELDS and writes PREDICTION_FIELDS in the
canonical units below. Gold labels use GOLD_RECORD_FIELDS and are read only by
evaluation/score.py. See evaluation/PROTOCOL.md for the rules behind each field.

This module is the single source of truth. regex_extractor/schema.py re-exports
it for backward compatibility.
"""

# ---------------------------------------------------------------------------
# Target properties and canonical units
# ---------------------------------------------------------------------------
TE_SCHEMA = {
    "material": {
        "type": "str",
        "unit": None,
        "description": "Chemical formula or name of the material the values refer to "
                       "(e.g. 'Bi2Te3', 'SnSe', 'Mg3Sb1.5Bi0.5').",
    },
    "ZT": {
        "type": "float",
        "unit": "dimensionless",
        "description": "Thermoelectric figure of merit zT / ZT.",
    },
    "T_K": {
        "type": "float",
        "unit": "K",
        "description": "Temperature at which the property values were reported. "
                       "An attribute of a record, never a property of its own.",
    },
    "S_uVK": {
        "type": "float",
        "unit": "uV K-1",
        "description": "Seebeck coefficient (signed; negative for n-type).",
    },
    "kappa": {
        "type": "float",
        "unit": "W m-1 K-1",
        "description": "Thermal conductivity. Sub-type in 'kappa_type'.",
    },
    "sigma": {
        "type": "float",
        "unit": "S m-1",
        "description": "Electrical conductivity. Values reported as resistivity are "
                       "converted (sigma = 1/rho) only when the unit is explicit.",
    },
    "PF": {
        "type": "float",
        "unit": "uW cm-1 K-2",
        "description": "Power factor S^2 * sigma.",
    },
    "doping": {
        "type": "str",
        "unit": "free text / cm-3",
        "description": "Dopant and level as written, or carrier concentration in cm-3.",
    },
}

CANONICAL_UNITS = {k: v["unit"] for k, v in TE_SCHEMA.items()}

# Core score (primary): five properties. Doping is scored separately (extended).
CORE_PROPERTIES = ["ZT", "S_uVK", "kappa", "sigma", "PF"]
EXTENDED_PROPERTIES = ["doping"]
ALL_PROPERTIES = CORE_PROPERTIES + EXTENDED_PROPERTIES
NO_RECORD = "NONE"  # gold marker: paragraph checked, no record

KAPPA_TYPES = ["total", "lattice", "electronic", "bipolar", "unspecified"]
QUALIFIERS = ["max", "min", "avg", "range"]
ORIGINS = ["reported", "cited"]
CONTEXTS = ["experimental", "computational"]

# ---------------------------------------------------------------------------
# Method input: one JSON line per paragraph. Nothing else is given to a method.
# ---------------------------------------------------------------------------
INPUT_FIELDS = ["sample_id", "paper_id", "para_id", "text"]

# ---------------------------------------------------------------------------
# Method output: one JSON line per predicted record (predictions.jsonl)
# ---------------------------------------------------------------------------
PREDICTION_FIELDS = [
    "sample_id",          # from the input line
    "material",           # str or null
    "property",           # one of ALL_PROPERTIES
    "value",              # float in canonical unit, or null (text-only doping)
    "value_max",          # upper bound of a reported range, else null
    "T_K",                # float in K, or null
    "kappa_type",         # one of KAPPA_TYPES or null (kappa only)
    "qualifier",          # one of QUALIFIERS or null
    "origin",             # one of ORIGINS or null
    "context",            # one of CONTEXTS or null
    "doping_text",        # str or null (doping only)
    "carrier_conc_cm3",   # float or null (doping only)
    "flags",              # list of str (method-specific diagnostics, not scored)
    "evidence",           # str or null (optional supporting text, not scored)
]

# Per-paragraph status written by every method (paragraph_status.jsonl).
# A failed paragraph is NOT the same as a paragraph with zero predictions.
PARAGRAPH_STATUS_FIELDS = ["sample_id", "status", "n_predictions", "error"]
PARAGRAPH_STATUSES = ["ok", "error", "timeout"]

# Run metadata (run.json). Fields a method cannot measure are null, not omitted.
RUN_META_FIELDS = [
    "method_id", "method_name", "run_id", "split",
    "code_version",        # code hash or commit
    "config",              # dict: method parameters
    "model_id",            # null for rule-based methods
    "model_params",        # dict: temperature, max_tokens, seed, ...
    "input_file", "input_sha256",
    "started_at", "finished_at", "wall_seconds",
    "n_paragraphs", "n_ok", "n_failed",
    "n_model_calls", "input_tokens", "output_tokens",
    "cost_usd", "price_table",
    "hardware",
    "capabilities",        # properties the method can emit at all
]

# ---------------------------------------------------------------------------
# Gold standard: one row per record (long format). Read only by score.py.
# ---------------------------------------------------------------------------
GOLD_RECORD_FIELDS = [
    "sample_id", "record_no", "material", "property",
    "value", "value_max", "value_as_written", "unit_as_written",
    "T_K", "T_as_written", "kappa_type", "qualifier",
    "origin", "context", "doping_text", "carrier_conc_cm3",
    "material_aliases",    # ';'-separated alternative names accepted for this record
    "notes",
]


def is_finite_number(value):
    """JSON numbers only: bool is not a measurement; NaN/Infinity are invalid."""
    import math
    return type(value) is int or (type(value) is float and math.isfinite(value))


def validate_record_values(rec):
    """Shared numeric and enum checks for parsed gold and predictions."""
    errors = []
    for field in ("value", "value_max", "T_K", "carrier_conc_cm3"):
        value = rec.get(field)
        if value is not None and not is_finite_number(value):
            errors.append(f"{field} must be a finite number or null")
    for field, allowed in (("kappa_type", KAPPA_TYPES), ("qualifier", QUALIFIERS),
                           ("origin", ORIGINS), ("context", CONTEXTS)):
        value = rec.get(field)
        if value is not None and value not in allowed:
            errors.append(f"{field} {value!r} not in {allowed}")
    return errors


def validate_prediction(rec):
    """Return a list of contract violations for one predicted record."""
    errors = []
    missing = [f for f in PREDICTION_FIELDS if f not in rec]
    if missing:
        errors.append(f"missing fields: {missing}")
    prop = rec.get("property")
    if prop not in ALL_PROPERTIES:
        errors.append(f"property {prop!r} not in {ALL_PROPERTIES}")
    errors.extend(validate_record_values(rec))
    if prop in CORE_PROPERTIES and rec.get("value") is None:
        errors.append("core property without a numeric value")
    for field in ("sample_id", "material", "doping_text", "evidence"):
        value = rec.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{field} must be a string or null")
    flags = rec.get("flags", [])
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        errors.append("flags must be a list of strings")
    return errors


# ---------------------------------------------------------------------------
# Legacy names used by regex_extractor (kept unchanged for compatibility)
# ---------------------------------------------------------------------------
TE_RECORD_FIELDS = list(TE_SCHEMA.keys())

# Numeric properties an extractor emits as individual candidates.
# 'material' and 'T_K' are attached to each candidate as context, not emitted alone.
PROPERTIES = ["ZT", "S_uVK", "kappa", "sigma", "PF", "doping"]

# regex_extractor candidate format (input to the regex adapter, not the contract)
CANDIDATE_FIELDS = [
    "paper_id", "source", "para_id", "para_kind", "property", "value", "value_max",
    "value_alt", "unit", "value_text", "qualifier", "dopant", "T_K", "T_text",
    "material", "material_link", "flags", "start", "end", "sentence",
]

# Wide annotation columns of the pre-split sample (archived; not used for scoring)
GOLD_FIELDS = TE_RECORD_FIELDS + ["notes"]

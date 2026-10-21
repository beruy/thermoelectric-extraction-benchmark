"""
ChemDataExtractor Module - Chemical and Kondo Physics Data Extraction

This module extracts chemical data (molecules, properties, spectroscopy) and
Kondo physics parameters from scientific PDFs using ChemDataExtractor library
and Gemini API integration.
"""

# Lazy imports - only load heavy dependencies when actually needed
def __getattr__(name):
    if name == 'ChemDataExtractor':
        from .extractor import ChemDataExtractor
        return ChemDataExtractor
    elif name == 'CHEMICAL_SCHEMA':
        from .schema import CHEMICAL_SCHEMA
        return CHEMICAL_SCHEMA
    elif name == 'KONDO_SCHEMA':
        from .schema import KONDO_SCHEMA
        return KONDO_SCHEMA
    elif name == 'COMBINED_SCHEMA':
        from .schema import COMBINED_SCHEMA
        return COMBINED_SCHEMA
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'ChemDataExtractor',
    'CHEMICAL_SCHEMA',
    'KONDO_SCHEMA',
    'COMBINED_SCHEMA',
]

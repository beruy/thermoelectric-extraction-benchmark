# Vendored code

Files in this folder are copied from github.com/Ramprasad-Group/polymer_information_extraction
(commit d08f2d301fb74c680d8df9b3993d496b069fc6e9, folder src/), Shetty et al., npj Comput. Mater. 9, 52 (2023),
under the Georgia Tech Research Corporation licence in LICENSE (academic, non-commercial use).

Unchanged: base_classes.py, utils.py, pre_processing.py, process_material_entities.py,
material_amount_extraction.py, record_extractor.py.

Modified (2026-10-19, marked at the top of the file): property_extraction.py — import path of
base_classes and the location of the property metadata file. No change to the extraction logic.

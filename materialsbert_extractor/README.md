# materialsbert_extractor — method M2 (PolymerNER + published linking)

M2 applies the polymer property-extraction pipeline of Shetty et al. (2023,
*npj Comput. Mater.* 9, 52) to the benchmark paragraphs, without retraining:
the token-classification model `pranav-s/PolymerNER` (MaterialsBERT encoder,
trained on polymer abstracts) and the authors' rule-based record linking
(github.com/Ramprasad-Group/polymer_information_extraction, commit d08f2d3,
vendored in `vendor/` under its academic, non-commercial licence; see
`vendor/polymer_information_extraction/NOTICE.md`). No LLM step.

| Step | Source |
|---|---|
| unit exponents to "^{-1}" notation (`normalise_text`), because the authors' number parser reads "-1" in "m-1" as a number | ours |
| PolymerNER, one pass per sentence group of at most 510 word pieces (paragraphs can exceed the 512-token limit the authors' abstracts stayed under) | model; chunking ours |
| `ner_feed` + `RelationExtraction` (`polymer_filter=False` so inorganic materials count) | authors (vendored) |
| property-name dictionary, unit conversion to canonical units, °C condition to K, range bounds | ours (`predict.py`, `units.py`, `property_metadata.json`) |

Known limits of the published linking, reported, not changed: a measurement
temperature is attached only when written as "N °C" (Kelvin conditions are not
recognised); the material is the closest material entity in the same sentence,
else every material of the text (then our mapping leaves the material empty and
flags `ambiguous_attribution`).

## Environment (Colab, separate from M1)

Python 3.8, chemdataextractor 1.3.0 (used by the linking code for abbreviations;
the version of the authors' earlier repository), torch 2.2.2 (CPU), transformers
4.30.2, spaCy 3.7.5 + en_core_web_sm 3.7.1, python-Levenshtein. The authors'
`environment.yml` covers only model training, not the linking code.

```bash
%%bash
set -euo pipefail
cd /content
export PATH=/root/.local/bin:$PATH
[ -x /root/.local/bin/uv ] || { curl -LsSf https://astral.sh/uv/install.sh -o uv_install.sh && sh uv_install.sh > /dev/null; }
uv python install 3.8 > /dev/null
[ -d m2env ] || uv venv -q -p 3.8 /content/m2env
P=/content/m2env/bin/python
uv pip install -q --python $P "chemdataextractor==1.3.0"
uv pip install -q --python $P torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
uv pip install -q --python $P "transformers==4.30.2" "spacy==3.7.5" python-Levenshtein huggingface_hub
uv pip install -q --python $P "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl"
$P -W ignore -c "from chemdataextractor.data import PACKAGES; [p.download() for p in PACKAGES]"
```

## Run

```bash
%%bash
cd /content/drive/MyDrive/arxiv
P=/content/m2env/bin/python
$P -W ignore -m materialsbert_extractor.predict --selftest
$P -W ignore -m materialsbert_extractor.predict --split dev
```

The model revision is resolved once and recorded in run.json; pass
`--revision <sha>` to reuse it (the test run must use the dev revision).

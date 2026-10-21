# chem_data_extractor — method M1 (ChemDataExtractor thermoelectric parsers)

M1 runs the published thermoelectric adaptation of ChemDataExtractor 2.0 by
Sierepeklis & Cole (2022, *Sci. Data* 9, 648; code
github.com/odysie/thermoelectricsdb, package `ChemDataExtractor-TE 2.0.0-te`)
on the benchmark paragraphs. No LLM step. `predict.py` documents which parts are
the published pipeline and which are our mapping to the contract.

## Environment (Colab)

The package needs Python 3.8 and pandas < 2. Everything is installed under
`/content`, outside the project folder.

```bash
%%bash
set -e
cd /content
curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null
export PATH=/root/.local/bin:$PATH
uv python install 3.8
[ -d cde38 ] || uv venv -q -p 3.8 /content/cde38
[ -d thermoelectricsdb ] || git clone -q --depth 1 https://github.com/odysie/thermoelectricsdb
git -C thermoelectricsdb rev-parse HEAD
mkdir -p tepkg && tar xzf thermoelectricsdb/chemdataextractor_thermoelectrics/chemdataextractor/dist/ChemDataExtractor-TE-2.0.0-te.tar.gz -C tepkg
uv pip install -q --python /content/cde38/bin/python appdirs beautifulsoup4 cssselect DAWG-Patched tabledataextractor lxml nltk pdfminer.six python-crfsuite python-dateutil PyYAML requests six selenium scipy numpy deprecation "pandas<2" click
export PYTHONPATH=/content/tepkg/ChemDataExtractor-TE-2.0.0-te
/content/cde38/bin/python -c "from chemdataextractor.data import PACKAGES; [p.download() for p in PACKAGES]"
```

## Run

```bash
%%bash
cd /content/drive/MyDrive/arxiv
export PYTHONPATH=/content/tepkg/ChemDataExtractor-TE-2.0.0-te:$PWD
/content/cde38/bin/python -W ignore -m chem_data_extractor.predict --selftest
/content/cde38/bin/python -W ignore -m chem_data_extractor.predict --split dev \
    --te-commit $(git -C /content/thermoelectricsdb rev-parse HEAD)
```

Then score in the normal environment:
`python -m evaluation.score --split dev --run results/cde/<run_id>`.

## Notes

* `te_parse` keeps only records with a compound name and a temperature (or a
  room-temperature mention); this is the published design and limits recall.
* The authors' record cleaning (data_cleaning.ipynb) is applied per record;
  every raw record and the reason it was dropped is in `raw/te_records.jsonl`.
* `legacy_README_nanosynthra.md`, `cli.py`, `extractor.py`, `schema.py` are a
  pre-benchmark NanoSynthra module (Kondo parameters via Gemini) and are not used.

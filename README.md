# 3GPP Spec Citation Graph

Code and dataset note for the [3GPP Spec Citation Graph](https://huggingface.co/datasets/joyboseroy/3gpp-citation-graph)
dataset on Hugging Face.

**Data:** hosted on Hugging Face, not in this repo (see link above).
**This repo contains:** extraction/construction scripts and the dataset note.

## Contents

- `PAPER.md` — dataset note: construction method, and importantly, the
  limitations you should read before using the data (coverage gaps,
  extraction precision, release-tagging caveats).
- `scripts/extract_crossrefs.py` — rule-based cross-reference extraction
  from 3GPP spec markdown text.
- `scripts/falkordb_loader.py` — loads extracted references into FalkorDB
  as a property graph.
- `scripts/export_3gpp_graph.py` — exports the FalkorDB graph to Parquet
  files matching the Hugging Face dataset format.

## Quick summary

130,270 clause-level nodes, 209,934 typed reference edges, covering 3GPP
Releases 11, 12, 13, 14, and 16 (Release 15 and releases outside this band
are not covered — see `PAPER.md` for full limitations).

## License

CC-BY-4.0, matching the dataset.

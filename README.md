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

## How this dataset was built

**1. Source specs — not scraped directly.** The raw 3GPP specification text
comes from [TSpec-LLM](https://huggingface.co/datasets/rasoul-nikbakht/TSpec-LLM),
an existing public dataset that already converted 3GPP's official spec
documents into clean markdown, organized by release (`Rel-11`, `Rel-12`,
etc.) and series (`23_series`, `24_series`, etc.). This project did not
scrape 3GPP's site directly — it builds on TSpec-LLM's markdown corpus, using
a partial local download covering Releases 11, 12, 13, 14, and 16.

**2. Cross-reference extraction (`scripts/extract_crossrefs.py`).** Each
markdown document is scanned for citation-like text — a clause referring to
another clause, another document, or an annex (e.g. "see clause 5.3 of
TS 23.501", "refer to Annex B"). These are matched with rule-based/regex
patterns, not an LLM, and classified into reference types: `document_level`,
`intradoc`, `clause`, `annex`, or `bare_lowconf` (a catch-all for weaker
pattern matches the extractor itself is less confident about). Output:
228,250 raw extracted references.

**3. Graph loading (`scripts/falkordb_loader.py`).** Each extracted
reference becomes an edge in a FalkorDB property graph: source clause →
`REFERENCES` → target clause, with the reference type stored as an edge
property. Each clause becomes a `Clause` node with `doc_id` (the source
spec number) and `clause_id` (the clause number within that document) as
properties. After deduplication, this produced a graph of 130,270 nodes and
209,934 edges.

**4. Validation.** A sample of extracted edges was checked against an LLM
judge (Groq llama-3.3-70b) to estimate extraction precision — this came out
to ~0.71, meaning roughly 3 in 10 extracted edges may be spurious or
mis-parsed. This is disclosed as a limitation, not filtered out — the
dataset ships as-is, with `ref_type` as a column so downstream users can
filter by confidence themselves if they want a cleaner subset.

**5. Export (`scripts/export_3gpp_graph.py`).** The graph is queried out of
FalkorDB and written to Parquet (`nodes.parquet`, `edges.parquet`), with
each node additionally tagged with its inferred 3GPP release based on which
`Rel-XX` source directory its document came from. This is the format
uploaded to the [Hugging Face dataset](https://huggingface.co/datasets/joyboseroy/3gpp-citation-graph).

**What this pipeline does *not* do:** no LLM was used to extract references
(only to spot-check a sample afterward), no manual verification of
individual edges was performed beyond that sample, and no attempt was made
to fill in the missing releases (15, and outside the 11–16 band) — this is
a partial-corpus subset, not a complete rebuild of the full TSpec-LLM
corpus.

## License

CC-BY-4.0, matching the dataset.

# 3GPP Spec Citation Graph — Dataset Note

**Dataset:** https://huggingface.co/datasets/joyboseroy/3gpp-citation-graph
**Author:** Joy Bose
**Status:** Dataset release. No accompanying topology analysis has been run yet (see Future Work).

## What this is

A clause-level cross-reference graph over a subset of 3GPP technical
specifications. Nodes are individual spec **clauses**; edges are explicit
references extracted from spec text (e.g. a clause pointing to another
clause, document, or annex), typed by reference granularity.

This is a **citation/cross-reference graph**, distinct from the several
entity-relation knowledge graphs that already exist for 3GPP content
(`otellm/3gpp_knowledgeGraph` for Rel-13, `GSMA/telecom-kg-rel19`,
`GSMA/oran_spec_knowledge_graph`). Those extract concepts, parameters, and
procedures as nodes. Here, nodes are clauses and edges are references
between them — a different graph object, suited to different questions
(reference topology, not entity QA).

## Construction

1. Source corpus: [TSpec-LLM](https://huggingface.co/datasets/rasoul-nikbakht/TSpec-LLM)
   markdown files, partial subset covering Releases 11, 12, 13, 14, and 16.
2. Cross-reference extraction (`scripts/extract_crossrefs.py`): rule-based
   parsing of clause/document/annex references from spec text.
3. Graph construction (`scripts/falkordb_loader.py`): loaded into FalkorDB
   as a property graph, `Clause` nodes connected by `REFERENCES` edges.
4. Validation: a sample was checked against an LLM judge (Groq
   llama-3.3-70b), yielding ~0.71 precision on extracted references.
5. Export (`scripts/export_3gpp_graph.py`): dumped to Parquet with release
   tags inferred from source directory structure.

Final graph: **130,270 nodes, 209,934 edges.**

## Limitations — read this before using the dataset

**Coverage is partial, not comprehensive.** This dataset covers Releases
11, 12, 13, 14, and 16 only. Release 15 is absent, and nothing outside this
band (Releases 8–10, 17 and later) is included. TSpec-LLM's full corpus
spans Release 8 through 19 across ~30,000 documents; this dataset reflects
a subset of that, built from a partial local download. Do not treat this
as "the" 3GPP citation graph, or extrapolate findings to releases not
present here.

**Extraction precision is roughly 71%, not higher.** Based on an LLM-judge
spot-check, an estimated ~29% of extracted edges may be spurious,
mis-parsed, or otherwise incorrect. A small fraction (248 edges) are
self-flagged as low-confidence (`ref_type = bare_lowconf`) by the extractor
itself, but this does not cover most of the estimated noise — the bulk of
likely errors sit inside the other `ref_type` categories, undetected at
the row level. Downstream users doing precision-sensitive work should
consider this a noisy-edge graph, not a validated ground truth.

**Release tagging is inferred, not authoritative.** 3.1% of nodes (3,979
of 130,270) could not be matched to a release directory and are marked
`unknown`. This inference is based on matching document identifiers
against source directory structure, not an authoritative 3GPP release
registry.

**Node granularity is clause-level, but incomplete at that level.** The
130,270 nodes are clauses that participate in at least one extracted
reference — not the full clause structure of every source document. Specs
with no incoming or outgoing references at the clause level are
under-represented or absent.

**Single relation type.** All edges are typed `REFERENCES` with a
`ref_type` qualifier (`document_level`, `intradoc`, `clause`, `annex`,
`bare_lowconf`). There are no semantic/entity relations — this dataset
does not tell you what a clause is *about*, only what it references.

## Intended uses

- Cross-reference/citation topology analysis within the covered releases
- Graph-RAG retrieval benchmarking (multi-hop reference traversal)
- Network-science studies of technical-standard document ecosystems, with
  the above coverage and precision caveats accounted for

## Future work (not yet done)

A topology comparison across the five covered releases — degree
distributions, hub-document stability, backward-vs-forward citation
patterns — has not been run. Scripts for this analysis exist
(`analyze_topology.py`, not yet included in this repo) but no results have
been generated or verified. Any claims about how citation structure
changes across releases would need this analysis run first; none of that
is asserted here.

## Citation

```bibtex
@misc{bose2026_3gpp_citation_graph,
  author = {Bose, Joy},
  title = {3GPP Spec Citation Graph},
  year = {2026},
  publisher = {Hugging Face},
  howpublished = {\url{https://huggingface.co/datasets/joyboseroy/3gpp-citation-graph}}
}
```

"""
Export the 3GPP citation graph from FalkorDB into HuggingFace-ready files.

Run this on your WSL machine, from the same environment where the FalkorDB
container is running (the one you started with:
  docker run -d -p 6379:6379 -v $(pwd)/falkor-data:/data falkordb/falkordb:latest
).

Usage:
    python3 export_3gpp_graph.py --host localhost --port 6379 \
        --graph tspec_citations \
        --corpus-root ~/3gpp-citation-graph-rag-data/3GPP-clean \
        --out ./3gpp-citation-graph-hf

Adjust --graph to whatever name you gave the graph in falkordb_loader.py
(check with `redis-cli GRAPH.LIST` if unsure).

Output:
    3gpp-citation-graph-hf/nodes.parquet
    3gpp-citation-graph-hf/edges.parquet
    3gpp-citation-graph-hf/release_summary.csv   (quick sanity-check stats per release)
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

try:
    from falkordb import FalkorDB
except ImportError:
    print("pip install falkordb pandas pyarrow --break-system-packages", file=sys.stderr)
    raise


REL_DIR_RE = re.compile(r"Rel-(\d+)", re.IGNORECASE)


def infer_release_from_path(doc_id: str, corpus_root: str) -> str:
    """
    Best-effort mapping from a node's document identifier back to its
    release, using the Rel-XX directory structure in 3GPP-clean.

    Falls back to scanning the corpus_root for a filename match if the
    doc_id itself doesn't carry a path. Returns 'unknown' if no match found.
    """
    m = REL_DIR_RE.search(doc_id)
    if m:
        return f"Rel-{m.group(1)}"

    # Fallback: search corpus tree for a file matching the doc_id basename.
    # Cached to avoid re-walking the tree for every node.
    if not hasattr(infer_release_from_path, "_index"):
        index = {}
        root = Path(corpus_root).expanduser()
        if root.exists():
            for rel_dir in root.iterdir():
                if rel_dir.is_dir() and REL_DIR_RE.search(rel_dir.name):
                    rel_tag = REL_DIR_RE.search(rel_dir.name).group(0)
                    for f in rel_dir.rglob("*.md"):
                        index[f.stem] = rel_tag
        infer_release_from_path._index = index

    basename = Path(doc_id).stem
    return infer_release_from_path._index.get(basename, "unknown")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=6379)
    ap.add_argument("--graph", default="tspec_citations",
                     help="Name of the graph key in FalkorDB")
    ap.add_argument("--corpus-root", default="~/3gpp-citation-graph-rag-data/3GPP-clean",
                     help="Path to the 3GPP-clean release directories, for release tagging")
    ap.add_argument("--out", default="./3gpp-citation-graph-hf")
    args = ap.parse_args()

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    db = FalkorDB(host=args.host, port=args.port)
    g = db.select_graph(args.graph)

    BATCH = 20000

    print("Querying nodes (paginated to avoid result-set truncation)...")
    nodes = []
    skip = 0
    while True:
        node_result = g.query(
            f"MATCH (n) RETURN id(n), n.doc_id, n.clause_id, labels(n) "
            f"SKIP {skip} LIMIT {BATCH}"
        )
        rows = node_result.result_set
        if not rows:
            break
        for row in rows:
            internal_id, doc_id, clause_id, labels = row
            doc_id = doc_id or ""
            release = infer_release_from_path(doc_id, args.corpus_root)
            nodes.append({
                "node_id": internal_id,
                "doc_id": doc_id,
                "clause_id": clause_id,
                "label": labels[0] if labels else None,
                "release": release,
            })
        print(f"  fetched {len(nodes)} nodes so far...")
        skip += BATCH
        if len(rows) < BATCH:
            break
    nodes_df = pd.DataFrame(nodes)
    print(f"  {len(nodes_df)} nodes total")

    print("Querying edges (paginated)...")
    # Real schema: edges are type REFERENCES with a ref_type property
    # (document_level, intradoc, clause, annex, bare_lowconf)
    edges = []
    skip = 0
    while True:
        edge_result = g.query(
            "MATCH (a)-[r]->(b) RETURN id(a), id(b), type(r), r.ref_type, "
            "a.doc_id, a.clause_id, b.doc_id, b.clause_id "
            f"SKIP {skip} LIMIT {BATCH}"
        )
        rows = edge_result.result_set
        if not rows:
            break
        for row in rows:
            src_id, dst_id, rel_type, ref_type, src_doc, src_clause, dst_doc, dst_clause = row
            edges.append({
                "source_id": src_id,
                "target_id": dst_id,
                "relation": rel_type,
                "ref_type": ref_type,
                "source_doc": src_doc,
                "source_clause": src_clause,
                "target_doc": dst_doc,
                "target_clause": dst_clause,
            })
        print(f"  fetched {len(edges)} edges so far...")
        skip += BATCH
        if len(rows) < BATCH:
            break
    edges_df = pd.DataFrame(edges)
    print(f"  {len(edges_df)} edges total")
    if not edges_df.empty:
        print("  ref_type breakdown:")
        print(edges_df["ref_type"].value_counts().to_string())

    nodes_path = out_dir / "nodes.parquet"
    edges_path = out_dir / "edges.parquet"
    nodes_df.to_parquet(nodes_path, index=False)
    edges_df.to_parquet(edges_path, index=False)
    print(f"Wrote {nodes_path}")
    print(f"Wrote {edges_path}")

    # Quick per-release summary for sanity checking.
    # IMPORTANT: multiple Clause nodes share the same doc_id, so we must
    # dedupe doc_id->release to a lookup table before merging with edges,
    # or the merge fans out and multiplies edge counts.
    if not nodes_df.empty:
        doc_release_lookup = (
            nodes_df[["doc_id", "release"]]
            .drop_duplicates(subset=["doc_id"])
            .rename(columns={"doc_id": "source_doc", "release": "source_release"})
        )
        merged = edges_df.merge(doc_release_lookup, on="source_doc", how="left")
        summary = nodes_df.groupby("release").size().rename("node_count").reset_index()
        edge_summary = merged.groupby("source_release").size().rename("outgoing_edge_count").reset_index()
        summary = summary.merge(edge_summary, left_on="release", right_on="source_release", how="left").drop(columns=["source_release"])
        summary_path = out_dir / "release_summary.csv"
        summary.to_csv(summary_path, index=False)
        print(f"Wrote {summary_path}")
        print(summary.to_string(index=False))

    unknown_count = (nodes_df["release"] == "unknown").sum() if not nodes_df.empty else 0
    if unknown_count:
        print(f"\nWARNING: {unknown_count} nodes could not be tagged with a release. "
              f"Check --corpus-root path, or inspect doc_id format for these rows.")


if __name__ == "__main__":
    main()

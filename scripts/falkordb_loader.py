"""
ingestion/falkordb_loader.py

Loads extracted RefEdges into FalkorDB as a property graph, and reports
basic graph statistics (node/edge counts, hub documents, hop-count
distribution) used to motivate Tier B's hop-count bins.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable

from falkordb import FalkorDB

from extract_crossrefs import RefEdge

def build_citation_graph(
    edges,
    db_host: str = "localhost",
    db_port: int = 6379,
    graph_name: str = "tspec_citations",
    batch_size: int = 2000,
):
    db = FalkorDB(host=db_host, port=db_port)
    graph = db.select_graph(graph_name)

    try:
        graph.query("CREATE INDEX FOR (c:Clause) ON (c.doc_id, c.clause_id)")
    except Exception:
        pass  # already exists if this is a re-run

    query = """
    UNWIND $rows AS row
    MERGE (source:Clause {doc_id: row.source_doc, clause_id: row.source_clause})
    MERGE (target:Clause {doc_id: row.target_doc, clause_id: row.target_clause})
    MERGE (source)-[r:REFERENCES {ref_type: row.ref_type}]->(target)
    """

    edges = list(edges)
    count = 0
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i + batch_size]
        rows = [
            {
                "source_doc": e.source_doc, "source_clause": e.source_clause,
                "target_doc": e.target_doc, "target_clause": e.target_clause,
                "ref_type": e.ref_type,
            }
            for e in batch
        ]
        graph.query(query, params={"rows": rows})
        count += len(batch)
        if count % 20000 == 0 or count == len(edges):
            print(f"  ingested {count}/{len(edges)} edges...")

    print(f"Graph built: {count} edges ingested into '{graph_name}'.")
    return graph


def load_edges_jsonl(path: Path) -> list[RefEdge]:
    edges = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            edges.append(RefEdge(**d))
    return edges


def graph_stats(graph) -> dict:
    n = graph.query("MATCH (c:Clause) RETURN count(c)").result_set[0][0]
    e = graph.query("MATCH ()-[r:REFERENCES]->() RETURN count(r)").result_set[0][0]

    top_hubs = graph.query("""
        MATCH (c:Clause)<-[r:REFERENCES]-()
        RETURN c.doc_id AS doc, count(r) AS in_degree
        ORDER BY in_degree DESC LIMIT 10
    """).result_set

    ref_type_counts = graph.query("""
        MATCH ()-[r:REFERENCES]->()
        RETURN r.ref_type AS t, count(r) AS c
        ORDER BY c DESC
    """).result_set

    return {
        "nodes": n,
        "edges": e,
        "top_hub_docs": top_hubs,
        "ref_type_breakdown": ref_type_counts,
    }


def sample_paths(graph, hop_count: int = 2, limit: int = 500):
    """Sample fixed-length paths via Cypher variable-length traversal."""
    query = f"""
    MATCH p = (start:Clause)-[:REFERENCES*{hop_count}]->(end:Clause)
    RETURN [node IN nodes(p) | node.doc_id + ' ' + node.clause_id] AS path
    LIMIT {limit}
    """
    result = graph.query(query)
    return [record[0] for record in result.result_set]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--edges", required=True, help="JSONL of RefEdges")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=6379)
    args = ap.parse_args()

    edges = load_edges_jsonl(Path(args.edges))
    graph = build_citation_graph(edges, db_host=args.host, db_port=args.port)
    stats = graph_stats(graph)
    print(json.dumps(stats, indent=2, default=str))

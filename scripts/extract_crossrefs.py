"""
ingestion/extract_crossrefs.py

Extracts 3GPP cross-references (clause/annex/document-level) from clause
text, to build the citation graph edges.

Handles:
  - Fully qualified: "3GPP TS 23.501 clause 5.2.1", "TS 38.331 V16.2.0"
  - Annex references: "3GPP TS 23.501 annex A", "annex A.1"
  - Bare spec numbers in "see X" form (lower confidence, tagged separately)
  - Intra-document references: "as specified in clause 6.3.2" (no spec
    number given -- resolved to the calling document)

Known limitation (not handled here): bracketed numeric references like
"[12]" that require resolving against the document's own reference list
(3GPP clause 2, "References"). This needs a second pass that parses each
document's reference list and substitutes [N] -> actual TS/TR number.
Left as future work / a documented gap, not a silent failure.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import NamedTuple, Optional


class RefEdge(NamedTuple):
    source_doc: str
    source_clause: str
    target_doc: str
    target_clause: str
    ref_type: str  # "clause" | "annex" | "document_level" | "bare_lowconf" | "intradoc"


TSPEC_PATTERN = re.compile(
    r"(?:3GPP\s+)?(TS|TR)\s+"
    r"(\d{2}\.\d{3})"
    r"(?:\s+(?:version|v)\s*\d+\.\d+\.\d+)?"
    r"(?:"
        r"[,\s]+(?:sub)?clause\s+([\d.]+)"
        r"|"
        r"[,\s]+annex\s+([A-Z](?:\.\d+)?)"
    r")?",
    re.IGNORECASE,
)

BARE_NUMBER_PATTERN = re.compile(
    r"\bsee\s+(\d{2}\.\d{3})\b(?:\s*(?:clause|§)\s*([\d.]+))?",
    re.IGNORECASE,
)

INTRADOC_PATTERN = re.compile(
    r"(?:see|refer\s+to|specified\s+in|as\s+per)\s+"
    r"(?:sub)?clause\s+([\d.]+)",
    re.IGNORECASE,
)

# Range expansion: "clauses 4.1 through 4.3" -> individual edges
RANGE_PATTERN = re.compile(
    r"clauses?\s+([\d.]+)\s+(?:through|to|-)\s+([\d.]+)",
    re.IGNORECASE,
)


def _expand_clause_range(start: str, end: str) -> list[str]:
    """
    Expand 'X.Y through X.Z' into individual subclause strings, where the
    last numeric component varies. Conservative: only expands if the prefix
    (all but the last dotted component) matches.
    """
    s_parts, e_parts = start.split("."), end.split(".")
    if s_parts[:-1] != e_parts[:-1]:
        return [start, end]  # can't safely expand, return endpoints only
    try:
        s_last, e_last = int(s_parts[-1]), int(e_parts[-1])
    except ValueError:
        return [start, end]
    prefix = ".".join(s_parts[:-1])
    return [f"{prefix}.{n}" if prefix else str(n) for n in range(s_last, e_last + 1)]


def _clean_clause(clause):
    if clause is None:
        return None
    return clause.rstrip(".")


def extract_3gpp_refs(
    text: str,
    source_doc_id: str,
    source_clause: Optional[str] = None,
) -> list[RefEdge]:
    edges: list[RefEdge] = []
    source_clause = source_clause or "full_doc"

    for m in TSPEC_PATTERN.finditer(text):
        spec_type, spec_num, clause, annex = m.group(1), m.group(2), m.group(3), m.group(4)
        clause = _clean_clause(clause)
        target_doc = f"{spec_type.upper()}{spec_num}"
        if clause:
            edges.append(RefEdge(source_doc_id, source_clause, target_doc, clause, "clause"))
        elif annex:
            edges.append(RefEdge(source_doc_id, source_clause, target_doc, annex, "annex"))
        else:
            edges.append(RefEdge(source_doc_id, source_clause, target_doc, "full_doc", "document_level"))

    for m in BARE_NUMBER_PATTERN.finditer(text):
        spec_num, clause = m.group(1), m.group(2)
        clause = _clean_clause(clause)
        target_doc = f"TS{spec_num}"
        edges.append(RefEdge(source_doc_id, source_clause, target_doc, clause or "full_doc", "bare_lowconf"))

    for m in INTRADOC_PATTERN.finditer(text):
        clause = m.group(1)
        clause = _clean_clause(clause)
        edges.append(RefEdge(source_doc_id, source_clause, source_doc_id, clause, "intradoc"))

    for m in RANGE_PATTERN.finditer(text):
        for c in _expand_clause_range(m.group(1), m.group(2)):
            edges.append(RefEdge(source_doc_id, source_clause, source_doc_id, c, "intradoc"))

    return list(set(edges))


def extract_from_corpus_jsonl(corpus_path: Path) -> list[RefEdge]:
    """corpus_path: output of ingestion/chunk_text.py (one Paragraph per line)."""
    all_edges: list[RefEdge] = []
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            all_edges.extend(
                extract_3gpp_refs(row["text"], row["doc_id"], row.get("clause_id"))
            )
    return all_edges


def write_edges_jsonl(edges: list[RefEdge], out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8") as f:
        for e in edges:
            f.write(json.dumps(e._asdict()) + "\n")


# --- validation harness ---
def validate_sample(annotated_path: Path, n: int = 200) -> dict:
    """
    annotated_path: JSONL with
      {"text": ..., "doc_id": ..., "clause": ..., "gold_refs": [[doc, clause], ...]}
    Hand-label ~30-50 clauses from a couple of hub documents (e.g. TS 23.501,
    TS 38.331) before trusting extraction at corpus scale.
    """
    tp = fp = fn = 0
    i = 0
    with annotated_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            row = json.loads(line)
            pred = {
                (e.target_doc, e.target_clause)
                for e in extract_3gpp_refs(row["text"], row["doc_id"], row.get("clause"))
            }
            gold = {tuple(g) for g in row["gold_refs"]}
            tp += len(pred & gold)
            fp += len(pred - gold)
            fn += len(gold - pred)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "n": min(n, i + 1)}

LLM_JUDGE_PROMPT = """You are checking whether a cross-reference extraction
tool correctly identified citations in 3GPP specification text.

Source text:
{text}

The tool extracted these target references: {extracted}

IMPORTANT: Citations may appear in the text with different spacing or
formatting than the extracted form (e.g. "TS 24.229" in text vs
"TS24.229" extracted -- these refer to the SAME citation and should be
judged as a match). Judge based on whether the SPECIFICATION NUMBER
matches, ignoring whitespace/formatting differences.

For each extracted reference, judge whether it is a TRUE citation actually
present in the text (correct), or a FALSE POSITIVE (the spec number
genuinely does not appear anywhere in the text).

Also check: does the text contain any OBVIOUS citations the tool MISSED?

Respond as JSON:
{{"correct": [...], "false_positives": [...], "missed_obvious": [...]}}
"""

def validate_with_llm_judge(corpus_path, n: int = 50, llm_judge=None, max_text_chars: int = 6000) -> dict:
    import json, random
    rows = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    sample = random.sample(rows, min(n, len(rows)))

    results = []
    for row in sample:
        edges = extract_3gpp_refs(row["text"], row["doc_id"], row.get("clause_id"))
        if not edges:
            continue
        extracted_str = ", ".join(f"{e.target_doc} {e.target_clause}" for e in edges)
        prompt = LLM_JUDGE_PROMPT.format(text=row["text"][:max_text_chars], extracted=extracted_str)
        raw = llm_judge(prompt)
        try:
            verdict = json.loads(raw)
        except json.JSONDecodeError:
            continue
        results.append({
            "doc_id": row["doc_id"], "clause": row.get("clause_id"),
            "verdict": verdict, "text_was_truncated": len(row["text"]) > max_text_chars,
        })

    total_extracted = sum(len(r["verdict"].get("correct", [])) + len(r["verdict"].get("false_positives", [])) for r in results)
    total_correct = sum(len(r["verdict"].get("correct", [])) for r in results)
    total_missed = sum(len(r["verdict"].get("missed_obvious", [])) for r in results)

    precision = total_correct / total_extracted if total_extracted else 0.0
    recall_proxy = total_correct / (total_correct + total_missed) if (total_correct + total_missed) else 0.0

    return {"precision": precision, "recall_proxy": recall_proxy, "n_sampled": len(sample), "details": results}

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="JSONL from chunk_text.py")
    ap.add_argument("--out", required=True, help="Output edges JSONL")
    ap.add_argument("--validate", help="Optional path to hand-annotated validation JSONL")
    args = ap.parse_args()

    edges = extract_from_corpus_jsonl(Path(args.corpus))
    write_edges_jsonl(edges, Path(args.out))
    print(f"Extracted {len(edges)} edges -> {args.out}")

    if args.validate:
        stats = validate_sample(Path(args.validate))
        print(f"Validation: precision={stats['precision']:.3f} "
              f"recall={stats['recall']:.3f} f1={stats['f1']:.3f} (n={stats['n']})")

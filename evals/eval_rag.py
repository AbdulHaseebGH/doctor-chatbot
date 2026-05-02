"""
evals/eval_rag.py
-----------------
RAG evaluation: precision@k, recall@k, faithfulness.
Tests against ground-truth query → expected document mappings.
Runs locally — imports RAG modules directly (no Docker needed).
"""

import sys
import os

# Add conversation app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conversation", "app"))

from rag.vector_store import build_index, search
from rag.retriever import retrieve


# Ground-truth: query → keywords that MUST appear in top-k results
GROUND_TRUTH = [
    {
        "query": "What are the clinic hours?",
        "expected_keywords": ["monday", "saturday", "9am", "6pm"],
        "relevant_doc_keywords": ["9am", "9 am", "6pm", "6 pm", "open"],
    },
    {
        "query": "When is Dr. Khan available?",
        "expected_keywords": ["tuesday", "thursday", "saturday", "cardiology"],
        "relevant_doc_keywords": ["khan", "cardio", "tuesday"],
    },
    {
        "query": "What does Dr. Alina specialize in?",
        "expected_keywords": ["pediatric", "children", "monday", "wednesday", "friday"],
        "relevant_doc_keywords": ["alina", "pediatric", "children"],
    },
    {
        "query": "How do I book an appointment?",
        "expected_keywords": ["book", "appointment", "555", "sara"],
        "relevant_doc_keywords": ["appointment", "book", "call"],
    },
    {
        "query": "What vaccinations are available?",
        "expected_keywords": ["vaccine", "vaccination", "mmr", "flu"],
        "relevant_doc_keywords": ["vaccin"],
    },
    {
        "query": "What should I do for an emergency?",
        "expected_keywords": ["911", "emergency room", "er"],
        "relevant_doc_keywords": ["911", "emergency"],
    },
    {
        "query": "How do I refill a prescription?",
        "expected_keywords": ["prescription", "24 hours", "doctor"],
        "relevant_doc_keywords": ["prescription", "refill"],
    },
    {
        "query": "Does the clinic accept insurance?",
        "expected_keywords": ["insurance", "card"],
        "relevant_doc_keywords": ["insurance"],
    },
]


def precision_at_k(retrieved_chunks: list[str], expected_keywords: list[str], k: int) -> float:
    """
    Precision@k: fraction of top-k results that are relevant.
    Relevance = at least one expected keyword appears in chunk.
    """
    top_k = retrieved_chunks[:k]
    if not top_k:
        return 0.0
    relevant = sum(
        1 for chunk in top_k
        if any(kw.lower() in chunk.lower() for kw in expected_keywords)
    )
    return relevant / k


def recall_at_k(retrieved_chunks: list[str], relevant_doc_keywords: list[str], k: int) -> float:
    """
    Recall@k: fraction of known-relevant docs that appear in top-k.
    (Simplified: checks if at least one relevant keyword is found in top-k)
    """
    top_k = retrieved_chunks[:k]
    if not top_k:
        return 0.0
    found = any(
        any(kw.lower() in chunk.lower() for kw in relevant_doc_keywords)
        for chunk in top_k
    )
    return 1.0 if found else 0.0


def faithfulness(query: str, retrieved_chunks: list[str], expected_keywords: list[str]) -> float:
    """
    Faithfulness: do the retrieved chunks contain the info needed to answer?
    Measured as fraction of expected keywords found in any retrieved chunk.
    """
    if not retrieved_chunks or not expected_keywords:
        return 0.0
    all_text = " ".join(retrieved_chunks).lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in all_text)
    return found / len(expected_keywords)


def run_rag_eval(k: int = 3) -> dict:
    """Run all RAG evaluation metrics."""
    print(f"\n{'='*60}")
    print(f"RAG EVALUATION — {len(GROUND_TRUTH)} queries, k={k}")
    print(f"{'='*60}")

    # Build index from local documents
    build_index()

    results = []
    for gt in GROUND_TRUTH:
        query = gt["query"]
        chunks = retrieve(query, k=k)
        expected_kw = gt["expected_keywords"]
        relevant_kw = gt["relevant_doc_keywords"]

        p_at_k = precision_at_k(chunks, expected_kw, k)
        r_at_k = recall_at_k(chunks, relevant_kw, k)
        faith = faithfulness(query, chunks, expected_kw)

        print(f"\n  Query: {query}")
        print(f"  Retrieved {len(chunks)} chunks")
        print(f"  Precision@{k}: {p_at_k:.2f} | Recall@{k}: {r_at_k:.2f} | Faithfulness: {faith:.2f}")

        results.append({
            "query": query,
            "chunks_retrieved": len(chunks),
            "precision_at_k": round(p_at_k, 3),
            "recall_at_k": round(r_at_k, 3),
            "faithfulness": round(faith, 3),
        })

    avg_precision = sum(r["precision_at_k"] for r in results) / len(results)
    avg_recall = sum(r["recall_at_k"] for r in results) / len(results)
    avg_faith = sum(r["faithfulness"] for r in results) / len(results)

    print(f"\n{'='*60}")
    print(f"AVG Precision@{k}: {avg_precision:.3f}")
    print(f"AVG Recall@{k}:    {avg_recall:.3f}")
    print(f"AVG Faithfulness: {avg_faith:.3f}")
    print(f"{'='*60}")

    return {
        "k": k,
        "queries": results,
        "averages": {
            "precision_at_k": round(avg_precision, 3),
            "recall_at_k": round(avg_recall, 3),
            "faithfulness": round(avg_faith, 3),
        }
    }


if __name__ == "__main__":
    results = run_rag_eval(k=3)

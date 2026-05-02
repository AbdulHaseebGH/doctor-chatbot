#!/usr/bin/env python3
"""
run_evals.py — Master evaluation runner
----------------------------------------
Usage:
    python run_evals.py              # Run all evaluations
    python run_evals.py --rag        # RAG only (no Docker needed)
    python run_evals.py --tools      # Tools only (no Docker needed)
    python run_evals.py --perf       # Performance (needs Docker)
    python run_evals.py --conv       # Conversations (needs Docker)

Outputs:
    evals/report.json  — Full machine-readable results
    evals/report.md    — Human-readable Markdown report
"""

import asyncio
import json
import time
import sys
import os
from datetime import datetime
from pathlib import Path


def parse_args():
    args = sys.argv[1:]
    if not args:
        return {"rag": True, "tools": True, "perf": True, "conv": True}
    return {
        "rag":   "--rag" in args or "--all" in args,
        "tools": "--tools" in args or "--all" in args,
        "perf":  "--perf" in args or "--all" in args,
        "conv":  "--conv" in args or "--all" in args,
    }


async def main():
    flags = parse_args()
    t_start = time.time()

    print("=" * 70)
    print("  🏥 Doctor Chatbot — Full Evaluation Suite")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    report = {
        "run_at": datetime.now().isoformat(),
        "results": {}
    }

    # ---- RAG Evaluation (local, no Docker) ----
    if flags["rag"]:
        print("\n📚 Running RAG Evaluation...")
        try:
            from evals.eval_rag import run_rag_eval
            rag_results = run_rag_eval(k=3)
            report["results"]["rag"] = rag_results
        except Exception as e:
            print(f"  ❌ RAG eval failed: {e}")
            report["results"]["rag"] = {"error": str(e)}

    # ---- Tool Evaluation (local, no Docker) ----
    if flags["tools"]:
        print("\n🔧 Running Tool Evaluation...")
        try:
            from evals.eval_tools import main as run_tools
            tool_results = await run_tools()
            report["results"]["tools"] = tool_results
        except Exception as e:
            print(f"  ❌ Tool eval failed: {e}")
            report["results"]["tools"] = {"error": str(e)}

    # ---- Performance Evaluation (needs Docker) ----
    if flags["perf"]:
        print("\n⚡ Running Performance Evaluation (requires Docker)...")
        try:
            from evals.eval_performance import run_performance_eval
            perf_results = await run_performance_eval()
            report["results"]["performance"] = perf_results
        except Exception as e:
            print(f"  ⚠️ Performance eval failed (is Docker running?): {e}")
            report["results"]["performance"] = {"error": str(e)}

    # ---- Conversation Evaluation (needs Docker) ----
    if flags["conv"]:
        print("\n💬 Running Conversation Evaluation (requires Docker + LM Studio)...")
        try:
            from evals.eval_conversations import run_all_conversations
            conv_results = await run_all_conversations()
            report["results"]["conversations"] = conv_results
        except Exception as e:
            print(f"  ⚠️ Conversation eval failed (is Docker running?): {e}")
            report["results"]["conversations"] = {"error": str(e)}

    # ---- Generate Reports ----
    t_total = int((time.time() - t_start) * 1000)
    report["total_time_ms"] = t_total

    output_dir = Path("evals")
    output_dir.mkdir(exist_ok=True)

    # JSON report
    json_path = output_dir / "report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n📄 JSON report saved: {json_path}")

    # Markdown report
    md_path = output_dir / "report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown_report(report))
    print(f"📝 Markdown report saved: {md_path}")

    print(f"\n⏱  Total eval time: {t_total / 1000:.1f}s")
    print("=" * 70)


def generate_markdown_report(report: dict) -> str:
    lines = [
        "# 🏥 Doctor Chatbot — Evaluation Report",
        f"\n**Run at:** {report.get('run_at', 'unknown')}",
        f"**Total time:** {report.get('total_time_ms', 0) / 1000:.1f}s",
        "\n---\n",
    ]

    results = report.get("results", {})

    # RAG
    if "rag" in results:
        rag = results["rag"]
        lines.append("## 📚 RAG Evaluation")
        if "error" in rag:
            lines.append(f"❌ Error: {rag['error']}")
        else:
            avgs = rag.get("averages", {})
            lines.extend([
                f"\n| Metric | Score |",
                f"|--------|-------|",
                f"| Precision@{rag.get('k', 3)} | {avgs.get('precision_at_k', 0):.3f} |",
                f"| Recall@{rag.get('k', 3)} | {avgs.get('recall_at_k', 0):.3f} |",
                f"| Faithfulness | {avgs.get('faithfulness', 0):.3f} |",
            ])
        lines.append("")

    # Tools
    if "tools" in results:
        tools = results["tools"]
        lines.append("## 🔧 Tool Evaluation")
        if "error" in tools:
            lines.append(f"❌ Error: {tools['error']}")
        else:
            passed = tools.get("passed", 0)
            total = tools.get("total", 0)
            failed = tools.get("failed", 0)
            lines.extend([
                f"\n| Result | Count |",
                f"|--------|-------|",
                f"| ✅ Passed | {passed} |",
                f"| ❌ Failed | {failed} |",
                f"| **Total** | **{total}** |",
            ])
        lines.append("")

    # Performance
    if "performance" in results:
        perf = results["performance"]
        lines.append("## ⚡ Performance Evaluation")
        if "error" in perf:
            lines.append(f"⚠️ Skipped (Docker required): {perf['error']}")
        else:
            bench = perf.get("latency_benchmark", {}).get("benchmark", {})
            if bench:
                ttft = bench.get("ttft_ms", {})
                total = bench.get("total_ms", {})
                target = bench.get("target_met", {}).get("preprocessing_under_2s")
                lines.extend([
                    f"\n| Metric | Min | Mean | Max |",
                    f"|--------|-----|------|-----|",
                    f"| TTFT | {ttft.get('min')}ms | {ttft.get('mean')}ms | {ttft.get('max')}ms |",
                    f"| Total | {total.get('min')}ms | {total.get('mean')}ms | {total.get('max')}ms |",
                    f"\n**Pre-processing <2s target:** {'✅ Met' if target else '❌ Not met'}",
                ])
        lines.append("")

    # Conversations
    if "conversations" in results:
        convs = results["conversations"]
        lines.append("## 💬 Conversation Evaluation")
        if isinstance(convs, dict) and "error" in convs:
            lines.append(f"⚠️ Skipped (Docker required): {convs['error']}")
        elif isinstance(convs, list) and convs:
            avg_overall = sum(c["scores"]["overall"] for c in convs) / len(convs)
            lines.extend([
                f"\n**Average Overall Score:** {avg_overall:.2f} / 1.00\n",
                "| Dialogue | Task | Coherence | Policy | Overall |",
                "|----------|------|-----------|--------|---------|",
            ])
            for c in convs:
                s = c["scores"]
                lines.append(
                    f"| {c['id']} | {s['task_completion']:.2f} | {s['coherence']:.2f} | {s['policy_adherence']:.2f} | {s['overall']:.2f} |"
                )
        lines.append("")

    lines.append("---\n*Generated by run_evals.py*")
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())

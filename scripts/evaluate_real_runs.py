#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def run_once(duration: int, realtime: int, control_channel: str, seed: int) -> Dict[str, Any]:
    ns3_cmd = (
        "./ns3 run scratch/ai5g-metrics -- "
        f"--metricsToStdout=1 --durationSeconds={duration} "
        "--enableDefaultFaults=1 --clearControlAtStart=1 "
        f"--controlChannel={control_channel} --realTime={realtime} --seed={seed}"
    )

    cmd = [
        sys.executable,
        "run.py",
        "--engine",
        "real",
        "--scenario",
        "scenarios/ns3_real_template.json",
        "--ns3-command",
        ns3_cmd,
    ]

    env = dict(**__import__("os").environ)
    env["OLLAMA_ENABLED"] = "0"

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        return {
            "ok": False,
            "return_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }

    report_path = Path("reports/final_report.json")
    if not report_path.exists():
        return {
            "ok": False,
            "return_code": 0,
            "stdout": result.stdout[-4000:],
            "stderr": "final_report.json not found",
        }

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})

    incidents = int(summary.get("incidents", 0))
    resolved = int(summary.get("resolved", 0))
    escalated = int(summary.get("escalated", 0))
    records = int(summary.get("records_processed", 0))
    ratio = (resolved / incidents) if incidents else 1.0

    return {
        "ok": True,
        "return_code": 0,
        "seed": seed,
        "records_processed": records,
        "incidents": incidents,
        "resolved": resolved,
        "escalated": escalated,
        "resolution_ratio": round(ratio, 4),
        "fault_counts": summary.get("fault_counts", {}),
    }


def classify(avg_ratio: float, runs_with_incidents: int) -> str:
    if runs_with_incidents == 0:
        return "INCONCLUSIVE"
    if avg_ratio >= 0.8:
        return "GOOD"
    if avg_ratio >= 0.5:
        return "FAIR"
    return "NEEDS_TUNING"


def build_markdown(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Real Workload Evaluation Summary")
    lines.append("")
    lines.append(f"- Timestamp: {report['timestamp']}")
    lines.append(f"- Runs: {report['config']['runs']}")
    lines.append(f"- Duration per run (seconds): {report['config']['duration']}")
    lines.append(f"- Real-time mode: {report['config']['realtime']}")
    lines.append(f"- Seed start: {report['config']['seed_start']}")
    lines.append(f"- Status: {report['aggregate']['status']}")
    lines.append("")
    lines.append("## Aggregate Metrics")
    lines.append("")
    lines.append(f"- Successful runs: {report['aggregate']['successful_runs']}/{report['config']['runs']}")
    lines.append(f"- Runs with incidents: {report['aggregate']['runs_with_incidents']}")
    lines.append(f"- Total incidents: {report['aggregate']['total_incidents']}")
    lines.append(f"- Total resolved: {report['aggregate']['total_resolved']}")
    lines.append(f"- Total escalated: {report['aggregate']['total_escalated']}")
    lines.append(f"- Average records processed: {report['aggregate']['avg_records_processed']}")
    lines.append(f"- Average resolution ratio: {report['aggregate']['avg_resolution_ratio']}")
    lines.append("")
    lines.append("## Per-Run Results")
    lines.append("")
    lines.append("| Run | Seed | OK | Records | Incidents | Resolved | Escalated | Ratio |")
    lines.append("|---:|---:|:--:|---:|---:|---:|---:|---:|")
    for item in report["runs"]:
        lines.append(
            "| {run} | {seed} | {ok} | {records} | {inc} | {res} | {esc} | {ratio} |".format(
                run=item["run_index"],
                seed=item.get("seed", "n/a"),
                ok="yes" if item.get("ok") else "no",
                records=item.get("records_processed", 0),
                inc=item.get("incidents", 0),
                res=item.get("resolved", 0),
                esc=item.get("escalated", 0),
                ratio=item.get("resolution_ratio", "n/a"),
            )
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This report is generated automatically by scripts/evaluate_real_runs.py.")
    lines.append("- Ollama is forced OFF during evaluation for deterministic and low-memory testing.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate real ns-3 workload across repeated runs.")
    parser.add_argument("--runs", type=int, default=5, help="Number of repeated runs")
    parser.add_argument("--duration", type=int, default=120, help="Duration per run in seconds")
    parser.add_argument("--realtime", type=int, default=0, choices=[0, 1], help="Use real-time mode")
    parser.add_argument("--control-channel", default="/tmp/ai5g-control.jsonl", help="Control channel path")
    parser.add_argument("--seed-start", type=int, default=7, help="Initial ns-3 seed; increments by 1 each run")
    args = parser.parse_args()

    results: List[Dict[str, Any]] = []
    for idx in range(1, args.runs + 1):
        seed = args.seed_start + (idx - 1)
        print(f"[evaluate] run {idx}/{args.runs} (seed={seed}) ...", flush=True)
        run_result = run_once(args.duration, args.realtime, args.control_channel, seed)
        run_result["run_index"] = idx
        if "seed" not in run_result:
            run_result["seed"] = seed
        results.append(run_result)

    successful = [r for r in results if r.get("ok")]
    runs_with_incidents = sum(1 for r in successful if int(r.get("incidents", 0)) > 0)

    total_incidents = sum(int(r.get("incidents", 0)) for r in successful)
    total_resolved = sum(int(r.get("resolved", 0)) for r in successful)
    total_escalated = sum(int(r.get("escalated", 0)) for r in successful)

    avg_ratio = round((total_resolved / total_incidents), 4) if total_incidents > 0 else 1.0
    avg_records = round(
        sum(int(r.get("records_processed", 0)) for r in successful) / max(len(successful), 1),
        2,
    )

    report = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "duration": args.duration,
            "realtime": args.realtime,
            "control_channel": args.control_channel,
            "seed_start": args.seed_start,
        },
        "aggregate": {
            "successful_runs": len(successful),
            "runs_with_incidents": runs_with_incidents,
            "total_incidents": total_incidents,
            "total_resolved": total_resolved,
            "total_escalated": total_escalated,
            "avg_records_processed": avg_records,
            "avg_resolution_ratio": avg_ratio,
            "status": classify(avg_ratio, runs_with_incidents),
        },
        "runs": results,
    }

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "evaluation_summary.json"
    md_path = reports_dir / "evaluation_summary.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")

    print(f"[evaluate] written {json_path}")
    print(f"[evaluate] written {md_path}")
    print(
        "[evaluate] status={status} incidents={inc} resolved={res} escalated={esc} avg_ratio={ratio}".format(
            status=report["aggregate"]["status"],
            inc=report["aggregate"]["total_incidents"],
            res=report["aggregate"]["total_resolved"],
            esc=report["aggregate"]["total_escalated"],
            ratio=report["aggregate"]["avg_resolution_ratio"],
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

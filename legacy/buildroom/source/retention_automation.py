#!/usr/bin/env python3
"""Retention automation: evaluate completed jobs and recommend keep/improve/park/prune.

Reads all jobs in ~/.hermes/buildroom-state/jobs/, scores them, and writes a
retention report. This script recommends only; it never deletes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRUST_SCORES = {"clean": 100, "watch": 60, "investigate": 20, "unknown": 0}
DELTA_SCORES = {"confirmed": 100, "drift": 50, "regression": 10, "missing_evidence": 30, "unknown": 0}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def days_since(date_str: str) -> int:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 999


def score_job(job_dir: Path) -> dict[str, Any]:
    trust = load_json(job_dir / "trust" / "trust-report.json")
    delta = load_json(job_dir / "verification" / "verification-delta.json")
    plan = load_json(job_dir / "plans" / "product-plan.json")
    retention = load_json(job_dir / "retention" / "retention-review.json")
    main_review = load_json(job_dir / "reviews" / "main-review.json")

    trust_state = trust.get("trust_state", "unknown")
    delta_state = delta.get("delta_state", "unknown")
    job_id = plan.get("job_id") or job_dir.name

    # Age scoring
    created_at = plan.get("created_at", "")
    age_days = days_since(created_at) if created_at else 999
    age_score = max(0, 100 - age_days * 2)  # Lose 2 points per day

    # Trust and delta scoring
    trust_score = TRUST_SCORES.get(trust_state, 0)
    delta_score = DELTA_SCORES.get(delta_state, 0)

    # Reusability scoring
    has_exact_changes = bool(plan.get("exact_changes"))
    has_build_plan = bool(load_json(job_dir / "plans" / "build-plan.json"))
    is_documentation = plan.get("change_classification") == "C" or "docstring" in plan.get("title", "").lower()
    reusability_score = 0
    if has_exact_changes:
        reusability_score += 30
    if has_build_plan:
        reusability_score += 30
    if is_documentation:
        reusability_score += 20  # Documentation changes are reusable patterns
    if main_review.get("risk_score", 5) <= 2:
        reusability_score += 20

    # Duplicate detection (simplified: same title pattern)
    title = plan.get("title", "")
    duplicate_penalty = 0
    if "docstring" in title.lower():
        duplicate_penalty = 10  # Small penalty if we have multiple docstring jobs

    # Weighted total
    total = (
        trust_score * 0.30 +
        delta_score * 0.25 +
        age_score * 0.20 +
        reusability_score * 0.15 +
        max(0, 100 - duplicate_penalty) * 0.10
    )

    # Recommendation
    if trust_state == "investigate":
        recommendation = "park"  # Never prune investigate jobs
    elif total >= 80:
        recommendation = "keep"
    elif total >= 60:
        recommendation = "improve"
    elif total >= 40:
        recommendation = "park"
    else:
        recommendation = "prune"

    return {
        "job_id": job_id,
        "trust_state": trust_state,
        "delta_state": delta_state,
        "age_days": age_days,
        "scores": {
            "trust": trust_score,
            "delta": delta_score,
            "age": age_score,
            "reusability": reusability_score,
            "duplicate_penalty": duplicate_penalty,
            "total": round(total, 1)
        },
        "recommendation": recommendation,
        "reason": f"trust={trust_state}, delta={delta_state}, age={age_days}d, reusability={reusability_score}"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print report without writing")
    parser.add_argument("--state-dir", default=str(Path.home() / ".hermes/buildroom-state"))
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser()
    jobs_dir = state_dir / "jobs"
    reports_dir = state_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if not jobs_dir.exists():
        print("No jobs directory found")
        return 0

    results = []
    for job_dir in sorted(jobs_dir.iterdir()):
        if not job_dir.is_dir():
            continue
        result = score_job(job_dir)
        results.append(result)

    # Sort by total score descending
    results.sort(key=lambda x: x["scores"]["total"], reverse=True)

    summary = {
        "schema_version": 1,
        "generated_at": now_utc(),
        "total_jobs": len(results),
        "recommendations": {
            "keep": sum(1 for r in results if r["recommendation"] == "keep"),
            "improve": sum(1 for r in results if r["recommendation"] == "improve"),
            "park": sum(1 for r in results if r["recommendation"] == "park"),
            "prune": sum(1 for r in results if r["recommendation"] == "prune")
        },
        "jobs": results
    }

    # Write structured report
    report_path = reports_dir / "retention-automation-report.json"
    if not args.dry_run:
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Write human-readable summary
    lines = [
        "# Retention Automation Report",
        f"Generated: {summary['generated_at']}",
        f"Total jobs: {summary['total_jobs']}",
        "",
        "## Recommendations",
        f"- keep: {summary['recommendations']['keep']}",
        f"- improve: {summary['recommendations']['improve']}",
        f"- park: {summary['recommendations']['park']}",
        f"- prune: {summary['recommendations']['prune']}",
        "",
        "## Job Details",
        ""
    ]

    for r in results:
        lines.append(f"### {r['job_id']}")
        lines.append(f"- Recommendation: **{r['recommendation']}**")
        lines.append(f"- Trust: {r['trust_state']} | Delta: {r['delta_state']} | Age: {r['age_days']}d")
        lines.append(f"- Score: {r['scores']['total']}/100")
        lines.append(f"- Reason: {r['reason']}")
        lines.append("")

    summary_text = "\n".join(lines)
    summary_path = reports_dir / "retention-automation-summary.md"
    if not args.dry_run:
        summary_path.write_text(summary_text + "\n", encoding="utf-8")

    if args.dry_run:
        print(summary_text)
    else:
        print(f"WROTE: {report_path}")
        print(f"WROTE: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

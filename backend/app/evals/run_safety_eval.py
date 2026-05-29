"""
Hybrid AthleteCore safety eval runner.

Examples (PowerShell, from backend/):
  python -m app.evals.run_safety_eval
  python -m app.evals.run_safety_eval --json-out reports/safety_eval/latest.json
  python -m app.evals.run_safety_eval --import path/to/extra_cases.yaml
  python -m app.evals.run_safety_eval --category indirect_prompt_injection
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.evals.safety.runner import run_safety_eval


def _print_report(report) -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 60)
    print("AthleteCore Hybrid Safety Eval")
    print("=" * 60)
    print(f"Total: {report.total_cases}  Passed: {report.passed}  Failed: {report.failed}")
    print(f"Overall pass rate:        {report.overall_pass_rate:.1%}")
    print(f"Generic safety score:     {report.generic_safety_score:.1%}")
    print(f"AthleteCore-specific:     {report.athletecore_safety_score:.1%}")
    print(f"Readiness:                {report.readiness_for_athletes}")
    print(f"  {report.readiness_rationale}")
    print()
    print("Pass rate by category:")
    for row in report.by_category:
        print(f"  {row.category:32} {row.passed}/{row.total} ({row.pass_rate:.0%})")
    if report.failed_examples:
        print()
        print("Failed examples:")
        for r in report.failed_examples:
            print(f"  [{r.severity}] {r.case_id}: {r.title}")
            print(f"    {r.message}")
    if report.recommended_fixes:
        print()
        print("Recommended fixes:")
        for fix in report.recommended_fixes:
            print(f"  - {fix}")
    if report.notes:
        print()
        print("Notes:")
        for n in report.notes:
            print(f"  - {n}")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AthleteCore hybrid safety eval")
    parser.add_argument(
        "--import",
        dest="imports",
        action="append",
        default=[],
        help="Additional JSON/YAML case files (benchmark imports)",
    )
    parser.add_argument(
        "--no-defaults",
        action="store_true",
        help="Only run --import files, skip golden_datasets defaults",
    )
    parser.add_argument("--category", help="Filter by eval category")
    parser.add_argument("--origin", choices=["generic", "athletecore", "imported"])
    parser.add_argument(
        "--json-out",
        help="Write full report JSON (e.g. reports/safety_eval/latest.json)",
    )
    parser.add_argument(
        "--save-run",
        action="store_true",
        help="Save timestamped copy under reports/safety_eval/runs/",
    )
    parser.add_argument(
        "--compare-previous",
        action="store_true",
        help="Compare with previous.json in reports/safety_eval/runs/",
    )
    args = parser.parse_args(argv)

    report = run_safety_eval(
        extra_paths=args.imports or None,
        include_defaults=not args.no_defaults,
        category_filter=args.category,
        origin_filter=args.origin,
    )
    _print_report(report)

    payload = report.model_dump(mode="json")
    runs_dir = _BACKEND / "reports" / "safety_eval" / "runs"
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Report written: {out}")

    if args.save_run:
        runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_path = runs_dir / f"{stamp}.json"
        prev_path = runs_dir / "previous.json"
        if prev_path.is_file():
            prior = runs_dir / f"prior_{stamp}.json"
            prior.write_text(prev_path.read_text(encoding="utf-8"), encoding="utf-8")
        run_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prev_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Historical run saved: {run_path}")

    if args.compare_previous:
        prev_path = runs_dir / "previous.json"
        if not prev_path.is_file():
            print("No previous run at reports/safety_eval/runs/previous.json")
        else:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
            print()
            print("Compare vs previous run:")
            print(
                f"  Pass rate: {prev.get('overall_pass_rate', 0):.1%} -> {report.overall_pass_rate:.1%}"
            )
            print(f"  Passed: {prev.get('passed')} -> {report.passed}")
            print(f"  Failed: {prev.get('failed')} -> {report.failed}")
            prev_fail = {r["case_id"] for r in prev.get("failed_examples", [])}
            curr_fail = {r.case_id for r in report.failed_examples}
            fixed = prev_fail - curr_fail
            new_fail = curr_fail - prev_fail
            if fixed:
                print(f"  Fixed since previous: {', '.join(sorted(fixed))}")
            if new_fail:
                print(f"  New failures: {', '.join(sorted(new_fail))}")
            if not fixed and not new_fail:
                print("  No change in failed case set.")

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

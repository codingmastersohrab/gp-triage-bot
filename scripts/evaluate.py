#!/usr/bin/env python3
"""
Query the SQLite database and print evaluation metrics for the triage sessions.

Usage:
  python scripts/evaluate.py [--db path/to/gp_triage.db]

Prints a breakdown of sessions by routing outcome, red flag rate, average turns,
completion rate, time-to-complete, symptom category distribution, and number of
clarifications per session.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

# Resolve default DB path relative to this script
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "gp_triage.db"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _safe_avg(values: list) -> str:
    vals = [v for v in values if v is not None]
    return f"{sum(vals) / len(vals):.1f}" if vals else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate triage session metrics.")
    parser.add_argument("--db", default=str(_DEFAULT_DB), help="Path to gp_triage.db")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run the server and complete at least one session first.")
        return

    import sqlalchemy as sa

    engine = sa.create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    with engine.connect() as conn:
        sessions = conn.execute(sa.text(
            "SELECT session_id, status, routing_outcome, red_flags_present, "
            "number_of_turns, symptom_category, pathway_name, "
            "created_at, completed_at, data "
            "FROM sessions"
        )).fetchall()

    total = len(sessions)
    if total == 0:
        print("No sessions found in the database.")
        return

    print(f"\n{'='*55}")
    print(f"  GP Triage Evaluation  ({total} session(s) total)")
    print(f"{'='*55}")

    # Counts by routing outcome
    from collections import Counter
    route_counts = Counter(r[2] or "not_routed" for r in sessions)
    print("\n1) Sessions by routing outcome:")
    for route, count in sorted(route_counts.items()):
        pct = 100 * count / total
        print(f"   {route:<22} {count:>4}  ({pct:.0f}%)")

    # Red flags
    with_flags = sum(1 for r in sessions if r[3] == 1)
    print(f"\n2) Sessions with any red flag:  {with_flags}/{total}  ({100*with_flags/total:.0f}%)")

    # Average turns per outcome
    turns_by_route: dict = {}
    for r in sessions:
        route  = r[2] or "not_routed"
        turns  = r[4]
        turns_by_route.setdefault(route, []).append(turns)
    print("\n3) Average turns by routing outcome:")
    for route, turns in sorted(turns_by_route.items()):
        print(f"   {route:<22} avg {_safe_avg(turns)} turns")

    # Completion rate
    status_counts = Counter(r[1] or "unknown" for r in sessions)
    completed  = status_counts.get("completed", 0)
    abandoned  = status_counts.get("abandoned", 0)
    active     = status_counts.get("active", 0)
    print(f"\n4) Session status:")
    print(f"   completed  {completed:>4}  ({100*completed/total:.0f}%)")
    print(f"   active     {active:>4}  ({100*active/total:.0f}%)")
    print(f"   abandoned  {abandoned:>4}  ({100*abandoned/total:.0f}%)")

    # Time to complete (created_at to completed_at)
    times_by_route: dict = {}
    for r in sessions:
        route      = r[2] or "not_routed"
        created    = _parse_dt(r[7])
        completed_ = _parse_dt(r[8])
        if created and completed_:
            secs = (completed_ - created).total_seconds()
            times_by_route.setdefault(route, []).append(secs)

    if times_by_route:
        print("\n5) Average time-to-complete (seconds) by outcome:")
        for route, times in sorted(times_by_route.items()):
            print(f"   {route:<22} avg {_safe_avg(times)}s")

    # Symptom category breakdown
    cat_counts = Counter(r[5] or "unknown" for r in sessions)
    print("\n6) Sessions by symptom category:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"   {cat:<22} {count:>4}  ({100*count/total:.0f}%)")

    # Number of clarifications (read from the JSON data blob)
    clarifs = []
    for r in sessions:
        try:
            data = json.loads(r[9])
            n = data.get("number_of_clarifications", 0)
            clarifs.append(n)
        except Exception:
            pass
    if clarifs:
        print(f"\n7) Average clarifications per session: {_safe_avg(clarifs)}")

    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    main()

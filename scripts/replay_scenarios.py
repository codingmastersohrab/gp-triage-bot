#!/usr/bin/env python3
"""
Replay 8 example triage scenarios through the API and print the results.

The server must be running before calling this script. Usage:
  python scripts/replay_scenarios.py [--base-url http://127.0.0.1:8000]

Each scenario drives the full conversation and prints the final routing
outcome alongside the expected one. A summary table is printed at the end.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional


# Scenario definitions
# Each scenario has a name, the expected routing outcome, and a list of user
# inputs in the order the dialogue will ask for them:
#   main_issue → duration → severity → [pathway yes/no answers] → confirm summary

@dataclass
class Scenario:
    name: str
    expected_route: str
    inputs: List[str]
    description: str = ""


# NOTE: Preamble slots (main issue / duration / severity) need no confirmation.
# Red-flag "yes" answers are held for one safety confirmation before recording.
# Each red-flag "yes" below is followed by an extra "yes" to confirm it.

SCENARIOS: List[Scenario] = [
    # Emergency scenarios
    Scenario(
        name="thunderclap_headache",
        expected_route="EMERGENCY_NOW",
        description="Headache with sudden thunderclap onset (SAH red flag)",
        inputs=[
            "I have a very sudden severe headache",  # main issue (no confirm)
            "1 hour",                                 # duration  (no confirm)
            "10",                                     # severity  (no confirm)
            "yes",                                    # sudden_onset → red-flag pending
            "yes",                                    # confirm red-flag answer
            "yes",                                    # confirm summary
        ],
    ),
    Scenario(
        name="chest_pain_radiating",
        expected_route="EMERGENCY_NOW",
        description="Chest pain radiating to left arm (ACS red flag)",
        inputs=[
            "I have chest pain going down my left arm",
            "2 hours",
            "8",
            "yes",   # radiating → red-flag pending
            "yes",   # confirm
            "yes",   # confirm summary
        ],
    ),
    Scenario(
        name="sob_at_rest",
        expected_route="EMERGENCY_NOW",
        description="Severe breathlessness at rest (respiratory/cardiac emergency)",
        inputs=[
            "I can't breathe properly, I'm struggling even sitting still",
            "1 hour",
            "9",
            "yes",   # at_rest → red-flag pending
            "yes",   # confirm
            "yes",   # confirm summary
        ],
    ),

    # Urgent same-day scenarios
    Scenario(
        name="headache_vision_changes",
        expected_route="URGENT_SAME_DAY",
        description="Headache with visual disturbance (urgent review)",
        inputs=[
            "I have a headache",
            "3 hours",
            "6",
            "no",   # sudden_onset
            "no",   # worst_ever
            "no",   # confusion_weakness
            "no",   # fever  (neck_stiffness skipped — fever=False)
            "yes",  # vision_changes → red-flag pending
            "yes",  # confirm
            "yes",  # confirm summary
        ],
    ),
    Scenario(
        name="exertional_chest_pain",
        expected_route="URGENT_SAME_DAY",
        description="Chest pain worse on exertion, no emergency signs",
        inputs=[
            "chest pain when I walk up stairs",
            "2 days",
            "5",
            "no",   # radiating
            "no",   # breathlessness
            "no",   # sweating_nausea
            "no",   # sudden_severe
            "yes",  # exertional → red-flag pending
            "yes",  # confirm
            "yes",  # confirm summary
        ],
    ),
    Scenario(
        name="post_traumatic_headache",
        expected_route="URGENT_SAME_DAY",
        description="Headache after a fall — post-traumatic (urgent review)",
        inputs=[
            "headache that started after I fell and hit my head",
            "4 hours",
            "5",
            "no",   # sudden_onset
            "no",   # worst_ever
            "no",   # confusion_weakness
            "no",   # fever
            "no",   # vision_changes
            "yes",  # head_injury → red-flag pending
            "yes",  # confirm
            "yes",  # confirm summary
        ],
    ),

    # Routine GP scenarios
    Scenario(
        name="mild_headache_routine",
        expected_route="ROUTINE_GP",
        description="Mild headache, all red flags negative",
        inputs=[
            "mild headache",
            "2 days",
            "3",
            "no",   # sudden_onset
            "no",   # worst_ever
            "no",   # confusion_weakness
            "no",   # fever  (neck_stiffness skipped)
            "no",   # vision_changes
            "no",   # head_injury
            "yes",  # confirm summary
        ],
    ),
    Scenario(
        name="stomach_ache_routine",
        expected_route="ROUTINE_GP",
        description="Stomach ache, no red flags",
        inputs=[
            "stomach ache",
            "1 day",
            "4",
            "no",   # sudden_severe
            "no",   # rigid_abdomen
            "no",   # pregnancy_possible → ectopic_risk skipped
            "no",   # blood_in_stool_vomit
            "no",   # fever
            "no",   # vomiting_diarrhoea
            "yes",  # confirm summary
        ],
    ),
]


# HTTP helpers

def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _wait_for_server(base: str, retries: int = 10) -> None:
    for i in range(retries):
        try:
            urllib.request.urlopen(f"{base}/hello", timeout=2)
            return
        except Exception:
            if i == retries - 1:
                print(f"ERROR: server not reachable at {base}")
                sys.exit(1)
            time.sleep(1)


# Replay logic

def replay(scenario: Scenario, base_url: str) -> dict:
    """Run one scenario; return final session dict."""
    session_resp = _post(f"{base_url}/session/start", {})
    session_id   = session_resp["session"]["session_id"]

    session = session_resp["session"]
    for user_input in scenario.inputs:
        resp    = _post(
            f"{base_url}/session/{session_id}/user_input",
            {"text": user_input},
        )
        session = resp["session"]

    return session


# Entry point

def main() -> None:
    parser = argparse.ArgumentParser(description="Replay triage scenarios.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--json", action="store_true", help="Print raw JSON output")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"Connecting to {base} …")
    _wait_for_server(base)
    print()

    results = []
    for scenario in SCENARIOS:
        print(f"▶  {scenario.name}")
        try:
            session = replay(scenario, base)
            got     = session.get("route_outcome", "?")
            match   = "✓" if got == scenario.expected_route else "✗"
            results.append((scenario.name, scenario.expected_route, got, match, session))
            print(f"   Expected: {scenario.expected_route}")
            print(f"   Got:      {got}  {match}")
            print(f"   Rationale: {session.get('route_rationale', '')}")
            print(f"   Category:  {session.get('symptom_category', '')}")
            print(f"   Turns:     {session.get('number_of_turns', '?')}")
            if args.json:
                print(json.dumps(session, indent=2, default=str))
        except Exception as exc:
            print(f"   ERROR: {exc}")
            results.append((scenario.name, scenario.expected_route, "ERROR", "✗", {}))
        print()

    # Summary table
    print("=" * 65)
    print(f"{'Scenario':<35} {'Expected':<18} {'Got':<18} {'OK'}")
    print("-" * 65)
    for name, exp, got, mark, _ in results:
        print(f"{name:<35} {exp:<18} {got:<18} {mark}")
    print("=" * 65)
    passed = sum(1 for *_, m, _ in results if m == "✓")
    print(f"Passed: {passed}/{len(results)}")


if __name__ == "__main__":
    main()

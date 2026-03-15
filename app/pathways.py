"""
Symptom-specific triage pathways for the GP triage prototype.

DISCLAIMER: This is a rule-based research prototype and is NOT compliant with
NHS Pathways or any clinical decision support standard. It is loosely inspired
by common red-flag screening principles for demonstration and evaluation purposes
only. It does not diagnose, prescribe, or replace clinical judgement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# Pathway step definition

@dataclass
class PathwayStep:
    key: str               # unique identifier stored in pathway_answers
    question: str          # exact question text shown to the patient
    is_red_flag: bool = False
    red_flag_route: str = "EMERGENCY_NOW"
    red_flag_rationale: str = ""
    # condition(pathway_answers) -> bool; None means always ask
    condition: Optional[Callable[[Dict[str, Any]], bool]] = field(
        default=None, repr=False
    )


# Category detection

_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "headache": [
        "headache", "head ache", "head pain", "migraine", "head hurts",
        "my head", "head is hurting", "head is pounding", "throbbing head",
    ],
    "chest_pain": [
        "chest pain", "chest tightness", "chest pressure", "chest discomfort",
        "heart pain", "pain in my chest", "chest hurts", "tight chest",
        "palpitation", "heart racing", "heart pounding", "chest ache",
    ],
    "abdominal_pain": [
        "stomach", "abdomen", "abdominal", "belly", "tummy", "gut",
        "stomach ache", "stomach pain", "stomach cramp", "bowel",
        "nausea and vomiting", "vomiting", "diarrhoea", "diarrhea",
    ],
    "shortness_of_breath": [
        "breath", "breathing", "breathless", "short of breath",
        "can't breathe", "cannot breathe", "difficulty breathing",
        "out of breath", "wheezing", "wheeze", "suffocating",
        "struggling to breathe",
    ],
}


def detect_category(text: str) -> str:
    """Return the best-matching symptom category for a complaint, or 'other'."""
    t = text.lower()
    scores: Dict[str, int] = {
        cat: sum(1 for kw in kws if kw in t)
        for cat, kws in _CATEGORY_KEYWORDS.items()
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "other"


# Pathway definitions

def _headache_steps() -> List[PathwayStep]:
    return [
        PathwayStep(
            key="sudden_onset",
            question=(
                "Did this headache come on very suddenly — reaching its worst "
                "within seconds or a minute (sometimes called a 'thunderclap headache')? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Thunderclap headache: possible subarachnoid haemorrhage — call 999",
        ),
        PathwayStep(
            key="worst_ever",
            question="Is this the worst headache you have ever had in your life? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Worst-ever headache: possible intracranial emergency — call 999",
            condition=lambda a: not a.get("sudden_onset"),
        ),
        PathwayStep(
            key="confusion_weakness",
            question=(
                "Are you feeling confused, or do you have any weakness, "
                "numbness, or difficulty speaking? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Neurological deficit with headache: possible stroke or intracranial emergency",
        ),
        PathwayStep(
            key="fever",
            question="Do you have a fever or feel unusually hot? (yes/no)",
        ),
        PathwayStep(
            key="neck_stiffness",
            question="Is your neck stiff or painful to move? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Neck stiffness with fever and headache: possible meningism — call 999",
            condition=lambda a: a.get("fever") is True,
        ),
        PathwayStep(
            key="vision_changes",
            question=(
                "Are you having any changes to your vision, such as blurring, "
                "double vision, or loss of vision? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="URGENT_SAME_DAY",
            red_flag_rationale="Visual disturbance with headache: needs same-day review",
        ),
        PathwayStep(
            key="head_injury",
            question="Did this headache start after a head injury or fall? (yes/no)",
            is_red_flag=True,
            red_flag_route="URGENT_SAME_DAY",
            red_flag_rationale="Post-traumatic headache: same-day review recommended",
        ),
    ]


def _chest_pain_steps() -> List[PathwayStep]:
    return [
        PathwayStep(
            key="radiating",
            question=(
                "Does the pain spread to your arm, shoulder, jaw, neck, or back? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Radiating chest pain: possible acute coronary syndrome — call 999",
        ),
        PathwayStep(
            key="breathlessness",
            question="Are you feeling short of breath along with the chest pain? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Chest pain with breathlessness: possible cardiac or pulmonary emergency",
        ),
        PathwayStep(
            key="sweating_nausea",
            question=(
                "Are you sweating, feeling sick, or feeling dizzy alongside the chest pain? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Chest pain with sweating or nausea: possible acute cardiac event",
        ),
        PathwayStep(
            key="sudden_severe",
            question="Did the pain come on suddenly and is it very severe? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Sudden severe chest pain: possible aortic dissection or pulmonary embolism",
        ),
        PathwayStep(
            key="exertional",
            question="Does the pain get worse with physical activity or exertion? (yes/no)",
            is_red_flag=True,
            red_flag_route="URGENT_SAME_DAY",
            red_flag_rationale="Exertional chest pain: possible cardiac cause — same-day review needed",
        ),
    ]


def _abdominal_pain_steps() -> List[PathwayStep]:
    return [
        PathwayStep(
            key="sudden_severe",
            question=(
                "Is the pain sudden in onset and very severe — for example, "
                "a pain that stops you in your tracks? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Sudden severe abdominal pain: possible surgical emergency (perforation/ischaemia)",
        ),
        PathwayStep(
            key="rigid_abdomen",
            question="Is your abdomen very hard or rigid to touch? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Rigid abdomen: possible peritonitis — call 999",
        ),
        PathwayStep(
            key="pregnancy_possible",
            question="Is there any possibility you could be pregnant? (yes/no)",
        ),
        PathwayStep(
            key="ectopic_risk",
            question=(
                "Is the pain mainly on one side — right or left lower abdomen? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="One-sided lower pain in possible pregnancy: possible ectopic pregnancy",
            condition=lambda a: a.get("pregnancy_possible") is True,
        ),
        PathwayStep(
            key="blood_in_stool_vomit",
            question="Have you noticed any blood in your stool or vomit? (yes/no)",
            is_red_flag=True,
            red_flag_route="URGENT_SAME_DAY",
            red_flag_rationale="Blood in stool or vomit: needs urgent assessment today",
        ),
        PathwayStep(
            key="fever",
            question="Do you have a fever? (yes/no)",
        ),
        PathwayStep(
            key="vomiting_diarrhoea",
            question="Are you vomiting or have you had diarrhoea? (yes/no)",
        ),
    ]


def _shortness_of_breath_steps() -> List[PathwayStep]:
    return [
        PathwayStep(
            key="at_rest",
            question=(
                "Are you breathless right now even at rest, "
                "without any physical activity? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Breathlessness at rest: possible respiratory or cardiac emergency",
        ),
        PathwayStep(
            key="blue_lips",
            question=(
                "Have you or anyone nearby noticed a blue tint to your lips "
                "or fingernails? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Cyanosis detected: critical oxygen insufficiency — call 999 immediately",
        ),
        PathwayStep(
            key="chest_pain",
            question=(
                "Are you having any chest pain or tightness alongside "
                "the breathlessness? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Breathlessness with chest pain: possible cardiac or pulmonary emergency",
        ),
        PathwayStep(
            key="wheeze",
            question=(
                "Are you wheezing — making a high-pitched noise when you breathe? (yes/no)"
            ),
        ),
        PathwayStep(
            key="asthma_copd",
            question="Do you have a diagnosed condition like asthma or COPD? (yes/no)",
            condition=lambda a: a.get("wheeze") is True,
        ),
        PathwayStep(
            key="inhaler_no_relief",
            question=(
                "Have you used your reliever inhaler and has it not helped? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="URGENT_SAME_DAY",
            red_flag_rationale="Wheeze not relieved by inhaler: same-day review needed",
            condition=lambda a: a.get("wheeze") is True and a.get("asthma_copd") is True,
        ),
        PathwayStep(
            key="fever",
            question="Do you have a fever or cough? (yes/no)",
        ),
    ]


def _other_steps() -> List[PathwayStep]:
    """Generic safety-net questions for unrecognised symptoms."""
    return [
        PathwayStep(
            key="severe_breathing_difficulty",
            question="Are you having severe difficulty breathing right now? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Severe breathing difficulty reported",
        ),
        PathwayStep(
            key="chest_pain",
            question="Are you having chest pain right now? (yes/no)",
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Chest pain reported",
        ),
        PathwayStep(
            key="stroke_signs",
            question=(
                "Do you have signs of a stroke right now, like face drooping, "
                "arm weakness, or speech problems? (yes/no)"
            ),
            is_red_flag=True,
            red_flag_route="EMERGENCY_NOW",
            red_flag_rationale="Stroke signs reported",
        ),
    ]


# Registry — maps category names to their step lists and display names

PATHWAY_VERSION = 2

_PATHWAYS: Dict[str, List[PathwayStep]] = {
    "headache":             _headache_steps(),
    "chest_pain":           _chest_pain_steps(),
    "abdominal_pain":       _abdominal_pain_steps(),
    "shortness_of_breath":  _shortness_of_breath_steps(),
    "other":                _other_steps(),
}

_PATHWAY_NAMES: Dict[str, str] = {
    "headache":             "headache_v2",
    "chest_pain":           "chest_pain_v2",
    "abdominal_pain":       "abdominal_pain_v2",
    "shortness_of_breath":  "sob_v2",
    "other":                "generic_v2",
}


def get_pathway_steps(category: str) -> List[PathwayStep]:
    return _PATHWAYS.get(category, _other_steps())


def get_pathway_name(category: str) -> str:
    return _PATHWAY_NAMES.get(category, "generic_v2")


# Navigation helpers

def next_pathway_step(
    steps: List[PathwayStep],
    pathway_answers: Dict[str, Any],
) -> Optional[PathwayStep]:
    """Return the next unanswered step whose condition is satisfied, or None."""
    for step in steps:
        if step.key in pathway_answers:
            continue                                       # already answered
        if step.condition is not None and not step.condition(pathway_answers):
            continue                                       # condition not met
        return step
    return None


def check_red_flags(
    category: str,
    pathway_answers: Dict[str, Any],
) -> Optional[tuple[str, str]]:
    """
    Scan answered pathway steps for triggered red flags.
    Returns (route, rationale) on first match, else None.
    Order follows the step definition order (highest-priority first).
    """
    for step in get_pathway_steps(category):
        if step.is_red_flag and pathway_answers.get(step.key) is True:
            return (step.red_flag_route, step.red_flag_rationale)
    return None

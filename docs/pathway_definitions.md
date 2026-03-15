# GP Triage Bot — Pathway Definitions

**DISCLAIMER:** This system is a rule-based research prototype and is **NOT**
compliant with NHS Pathways, NICE guidelines, or any other clinical decision
support standard. It is inspired by common red-flag screening principles for
demonstration and academic evaluation purposes only. It does **not** diagnose,
prescribe, or replace clinical judgement.

---

## Overview

The bot collects a structured triage checksheet via a conversation. After
confirming the main issue, duration, and severity, it detects a **symptom
category** using keyword matching and asks a pathway-specific question
sequence. Questions may be **conditional** on prior answers (branching).

### Symptom categories

| Category | Example complaint keywords |
|---|---|
| `headache` | headache, migraine, head pain |
| `chest_pain` | chest pain, chest tightness, heart pain |
| `abdominal_pain` | stomach, abdomen, belly, tummy, nausea |
| `shortness_of_breath` | breathless, can't breathe, wheeze |
| `other` | anything not matched above |

---

## Common preamble (all pathways)

1. **Main issue** — free text, then patient confirms (yes/no)
2. **Duration** — e.g. "2 days", "1 week"
3. **Severity 0–10** — numeric score, confirmed
4. → Category detected from confirmed main issue text

---

## Pathway A — Headache (`headache_v2`)

| Step | Key | Question | Red flag? | Route if yes |
|---|---|---|---|---|
| 1 | `sudden_onset` | Did this headache come on very suddenly (thunderclap)? | ✅ | EMERGENCY_NOW |
| 2 | `worst_ever` | Is this the worst headache you've ever had? *(condition: sudden_onset = false)* | ✅ | EMERGENCY_NOW |
| 3 | `confusion_weakness` | Confused, weak, numb, or difficulty speaking? | ✅ | EMERGENCY_NOW |
| 4 | `fever` | Fever or feeling unusually hot? | — | — |
| 5 | `neck_stiffness` | Neck stiff or painful to move? *(condition: fever = true)* | ✅ | EMERGENCY_NOW |
| 6 | `vision_changes` | Changes to vision (blurring, double vision)? | ✅ | URGENT_SAME_DAY |
| 7 | `head_injury` | Started after a head injury or fall? | ✅ | URGENT_SAME_DAY |

### Red-flag rules
- `sudden_onset = true` → subarachnoid haemorrhage screen → **EMERGENCY_NOW**
- `worst_ever = true` → intracranial emergency screen → **EMERGENCY_NOW**
- `confusion_weakness = true` → stroke/intracranial → **EMERGENCY_NOW**
- `fever = true` AND `neck_stiffness = true` → meningism → **EMERGENCY_NOW**
- `vision_changes = true` → same-day review → **URGENT_SAME_DAY**
- `head_injury = true` → post-traumatic → **URGENT_SAME_DAY**
- All negative → **ROUTINE_GP**

---

## Pathway B — Chest Pain (`chest_pain_v2`)

| Step | Key | Question | Red flag? | Route if yes |
|---|---|---|---|---|
| 1 | `radiating` | Pain spreading to arm, shoulder, jaw, neck, or back? | ✅ | EMERGENCY_NOW |
| 2 | `breathlessness` | Short of breath with chest pain? | ✅ | EMERGENCY_NOW |
| 3 | `sweating_nausea` | Sweating, nausea, or dizziness with chest pain? | ✅ | EMERGENCY_NOW |
| 4 | `sudden_severe` | Sudden onset and very severe? | ✅ | EMERGENCY_NOW |
| 5 | `exertional` | Worse with physical activity? | ✅ | URGENT_SAME_DAY |

### Red-flag rules
- `radiating = true` → ACS screen → **EMERGENCY_NOW**
- `breathlessness = true` → cardiac/PE screen → **EMERGENCY_NOW**
- `sweating_nausea = true` → acute cardiac event → **EMERGENCY_NOW**
- `sudden_severe = true` → aortic dissection/PE → **EMERGENCY_NOW**
- `exertional = true` → cardiac cause screen → **URGENT_SAME_DAY**
- All negative → **ROUTINE_GP**

---

## Pathway C — Abdominal Pain (`abdominal_pain_v2`)

| Step | Key | Question | Red flag? | Route if yes |
|---|---|---|---|---|
| 1 | `sudden_severe` | Sudden onset, very severe? | ✅ | EMERGENCY_NOW |
| 2 | `rigid_abdomen` | Abdomen hard or rigid to touch? | ✅ | EMERGENCY_NOW |
| 3 | `pregnancy_possible` | Could be pregnant? | — | — |
| 4 | `ectopic_risk` | One-sided lower abdominal pain? *(condition: pregnancy_possible = true)* | ✅ | EMERGENCY_NOW |
| 5 | `blood_in_stool_vomit` | Blood in stool or vomit? | ✅ | URGENT_SAME_DAY |
| 6 | `fever` | Fever? | — | — |
| 7 | `vomiting_diarrhoea` | Vomiting or diarrhoea? | — | — |

### Red-flag rules
- `sudden_severe = true` → perforation/ischaemia → **EMERGENCY_NOW**
- `rigid_abdomen = true` → peritonitis → **EMERGENCY_NOW**
- `pregnancy_possible = true` AND `ectopic_risk = true` → ectopic → **EMERGENCY_NOW**
- `blood_in_stool_vomit = true` → urgent GI assessment → **URGENT_SAME_DAY**
- All negative → **ROUTINE_GP**

---

## Pathway D — Shortness of Breath (`sob_v2`)

| Step | Key | Question | Red flag? | Route if yes |
|---|---|---|---|---|
| 1 | `at_rest` | Breathless at rest? | ✅ | EMERGENCY_NOW |
| 2 | `blue_lips` | Blue tint to lips or fingernails? | ✅ | EMERGENCY_NOW |
| 3 | `chest_pain` | Chest pain with breathlessness? | ✅ | EMERGENCY_NOW |
| 4 | `wheeze` | Wheezing? | — | — |
| 5 | `asthma_copd` | Known asthma or COPD? *(condition: wheeze = true)* | — | — |
| 6 | `inhaler_no_relief` | Inhaler used and not helped? *(condition: wheeze=true AND asthma_copd=true)* | ✅ | URGENT_SAME_DAY |
| 7 | `fever` | Fever or cough? | — | — |

### Red-flag rules
- `at_rest = true` → respiratory/cardiac emergency → **EMERGENCY_NOW**
- `blue_lips = true` → cyanosis, critical → **EMERGENCY_NOW**
- `chest_pain = true` → cardiac/PE → **EMERGENCY_NOW**
- `inhaler_no_relief = true` → uncontrolled asthma → **URGENT_SAME_DAY**
- All negative → **ROUTINE_GP**

---

## Pathway E — Other / Generic (`generic_v2`)

Fallback for unrecognised symptoms. Uses three generic safety-net questions:

| Step | Key | Red flag? | Route |
|---|---|---|---|
| 1 | `severe_breathing_difficulty` | ✅ | EMERGENCY_NOW |
| 2 | `chest_pain` | ✅ | EMERGENCY_NOW |
| 3 | `stroke_signs` | ✅ | EMERGENCY_NOW |

---

## Routing outcomes

| Route | Meaning | Patient instruction |
|---|---|---|
| `EMERGENCY_NOW` | Emergency red flag triggered | Call 999 / go to A&E immediately |
| `URGENT_SAME_DAY` | Urgent-flag triggered | Same-day GP or urgent care centre |
| `ROUTINE_GP` | No red flags | Routine appointment |
| `INCOMPLETE` | Not enough information | More questions needed |

---

## Database — stored fields (evaluation-ready)

Structured columns in the `sessions` table (in addition to the JSON blob):

| Column | Type | Purpose |
|---|---|---|
| `symptom_category` | TEXT | Detected category (headache, etc.) |
| `main_issue` | TEXT | Patient's stated complaint |
| `duration_value` | INT | Numeric duration (e.g. 2) |
| `duration_unit` | TEXT | Unit (days, weeks, etc.) |
| `severity_score` | TEXT | 0–10 score |
| `red_flags_list` | TEXT (JSON) | All pathway_answers as JSON |
| `red_flags_present` | INT (0/1) | Any positive finding? |
| `routing_outcome` | TEXT | Final route |
| `routing_rationale` | TEXT | Reason for route |
| `completed_at` | DATETIME | When patient confirmed summary |
| `pathway_name` | TEXT | e.g. "headache_v2" |
| `pathway_version` | INT | Pathway schema version |
| `number_of_turns` | INT | Conversation turns taken |
| `status` | TEXT | active / completed / abandoned |
| `created_at` | DATETIME | Session start |
| `updated_at` | DATETIME | Last update |

**Why structured columns?** The JSON blob stores the full state for perfect
fidelity, but structured columns allow direct SQL evaluation queries (e.g.
`SELECT AVG(number_of_turns) WHERE routing_outcome = 'EMERGENCY_NOW'`)
without JSON parsing.

---

## Evaluation metrics (scripts/evaluate.py)

The script queries the DB and reports:
- Session counts by routing outcome
- Percentage with red flags present
- Average turns per outcome
- Completion rate (completed / total)
- Average time to route (seconds)
- Symptom category breakdown
- Average clarifications per session

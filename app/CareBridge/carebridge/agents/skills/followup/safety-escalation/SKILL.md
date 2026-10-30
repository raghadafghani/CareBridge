---
name: safety-escalation
description: Use together with a symptom report when deciding whether the patient should keep monitoring, contact their care team, or seek emergency care. Escalation is decided by the safety specialist, not by guessing.
---

# Safety escalation

1. Call `load_care_plan` so the warning signs in the discharge report are in front of you.
2. Call `safety_review_specialist` with the patient's words unchanged.
3. Treat the tool OUTCOME as the decision.
   - emergency: emergency services (112 / 911) or the nearest emergency department, now, with no further questions
   - review: contact the clinician named in the plan today, and keep a short summary of what was reported
   - pending: ask the tool's questions before assigning review
   - monitor: no warning sign matched; that is not the same as saying they are well
4. Never override the tool toward a calmer outcome.
5. Never invent a diagnosis or a medication change to make the situation feel resolved.

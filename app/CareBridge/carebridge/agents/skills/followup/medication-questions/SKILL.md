---
name: medication-questions
description: Use when the patient asks what a medicine is for, when to take it, how long to continue it, or what to do about a dose they might have missed. Do not use it to judge new symptoms.
---

# Medication questions

1. Call `load_care_plan` with the active plan id.
2. Call `explain_medication` for the medicine they named. If they ask about the whole day, call `today_recovery_schedule` instead.
3. Answer only with what the tool returns. Do not invent a dose, a time, or a stop date.
4. If a dose was missed, say you cannot tell them to take an extra dose or to skip the next one. They should check with a pharmacist or their care team. Offer to note it.
5. If they also describe a new symptom, activate the recovery check-in skill and call `safety_review_specialist` as well.

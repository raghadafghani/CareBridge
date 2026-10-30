---
name: recovery-check-in
description: Use when the patient reports symptoms, a measurement such as temperature or blood pressure, a missed dose, or how they feel today. Also use it to start a daily recovery check-in.
---

# Recovery check-in

1. Call `load_care_plan` with the active plan id before you answer.
2. If the patient is only checking in and has not reported a symptom, remind them of today's medicines and checklist from `today_recovery_schedule`, then ask how they feel. Do not invent symptoms.
3. If they report a symptom, a measurement, a missed dose, or a change in how they feel, call `safety_review_specialist`. Pass their words unchanged, with the active plan id and session id.
4. Relay the specialist's OUTCOME and GUIDANCE.
   - `emergency`: tell them to get emergency help now. Do not ask more questions.
   - `pending`: ask the listed questions, then wait.
   - `review`: recommend contacting their care team today. Include only what they reported.
   - `monitor`: explain what the discharge instructions say and ask them to keep watching for change.
5. Do not say a symptom is normal. Do not diagnose. Do not change a dose.

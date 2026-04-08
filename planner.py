# planner.py

import json
from models import client, MODELS

PLANNER_SYSTEM_PROMPT = """You are a planner in a simple AI pipeline.

Your job:
- Understand the user's intent
- Break it into 1 to 3 simple, sequential tasks

Rules:
- Tasks must be atomic and non-overlapping
- Independent tasks must NOT depend on each other

{
  "intent": "...",
  "tasks": [
    {
      "id": "t1",
      "type": "LIST | EXPLAIN",
      "target": "...",
      "depends_on": []
    }
  ]
}
"""


class Planner:
    def create_plan(self, raw_intent: str) -> dict:
        try:
            response = client.chat.completions.create(
                model=MODELS["planner"],
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_intent}
                ],
                temperature=0.2,
                max_tokens=500
            )

            raw = response.choices[0].message.content.strip()
            plan = self._safe_parse(raw)

            # Basic validation
            if not plan.get("tasks"):
                raise ValueError("No tasks generated")

            return plan

        except Exception:
            return self._fallback_plan(raw_intent)

    # ---------------------------- #
    # Helpers
    # ---------------------------- #

    def _safe_parse(self, raw: str) -> dict:
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except:
            return {}

    def _fallback_plan(self, intent: str) -> dict:
        return {
            "intent": intent,
            "tasks": [
                {
                    "id": "t1",
                    "type": "LIST",
                    "target": intent,
                    "depends_on": []
                }
            ]
        }
import uuid


class Planner:
    def __init__(self):
        # Keywords mapped to task types
        self._task_patterns = {
            "summarize": [
                {"type": "extract", "description": "Extract key information from sources"},
                {"type": "summarize", "description": "Generate concise summary"},
            ],
            "analyze": [
                {"type": "extract", "description": "Extract relevant data points"},
                {"type": "analyze", "description": "Analyze patterns and trends"},
                {"type": "generate", "description": "Generate analysis report"},
            ],
            "compare": [
                {"type": "extract", "description": "Extract data from all sources"},
                {"type": "analyze", "description": "Compare findings across sources"},
                {"type": "validate", "description": "Cross-validate comparisons"},
                {"type": "generate", "description": "Generate comparison report"},
            ],
            "extract": [
                {"type": "extract", "description": "Extract key entities and data"},
                {"type": "validate", "description": "Validate extracted information"},
            ],
            "validate": [
                {"type": "extract", "description": "Extract claims from content"},
                {"type": "validate", "description": "Validate claims against sources"},
                {"type": "generate", "description": "Generate validation report"},
            ],
        }

    def create_plan(self, user_intent: str, num_sources: int = 0) -> dict:
        """
        Convert user intent into structured tasks with reliability signals.
        """
        tasks = self._decompose_intent(user_intent, num_sources)

        plan = {
            "intent": user_intent,
            "tasks": tasks,
            "execution_policy": {
                "parallel": len(tasks) > 4,
                "max_retries": 2,
                "confidence_threshold": 0.6
            }
        }

        return plan

    def _decompose_intent(self, intent: str, num_sources: int = 0) -> list:
        """
        Keyword-driven decomposition into typed tasks with worker assignments.
        """
        intent_lower = intent.lower()
        matched_tasks = []

        # Check for keyword matches
        for keyword, task_templates in self._task_patterns.items():
            if keyword in intent_lower:
                matched_tasks = list(task_templates)
                break

        # Default fallback
        if not matched_tasks:
            matched_tasks = [
                {"type": "extract", "description": "Extract key data from sources"},
                {"type": "analyze", "description": "Analyze content"},
                {"type": "generate", "description": "Generate response"},
            ]

        # Determine truth mode based on keywords
        uses_ssot = any(
            kw in intent_lower
            for kw in ["latest", "current", "verify", "fact", "validate", "source"]
        )

        # Build final task list with IDs, worker assignments, truth_mode
        tasks = []
        num_workers = min(len(matched_tasks), 5)

        for i, template in enumerate(matched_tasks):
            worker_id = (i % num_workers) + 1
            truth_mode = "ssot" if (uses_ssot or template["type"] == "validate") else "model"

            tasks.append({
                "id": str(uuid.uuid4())[:8],
                "type": template["type"],
                "description": template["description"],
                "worker": worker_id,
                "truth_mode": truth_mode,
                "confidence_threshold": 0.7 if truth_mode == "ssot" else 0.6,
            })

        return tasks

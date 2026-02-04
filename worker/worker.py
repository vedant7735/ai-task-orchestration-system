import random

class Worker:
    def __init__(self, name, temperature=0.5):
        self.name = name
        self.temperature = temperature

    def execute(self, task, document_text):
        """Executes a single task. Currently supports summarization as a placeholder."""
        if task["type"] == "summarize":
            return self._summarize(document_text)
        raise ValueError(f"Unsupported task type: {task['type']}")

    def _summarize(self, text):
        """Mock summarization logic. Simulates confidence degradation with higher temperature."""
        # simple fake "summary"
        summary = text[:120] + "..."
        # simulate reliability drop
        noise = random.uniform(0, self.temperature)
        confidence = round(max(0.1, 1 - noise), 2)
        return {
            "summary": summary,
            "confidence": confidence
        }
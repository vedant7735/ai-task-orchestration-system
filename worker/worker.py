import random
import re
from collections import Counter


class Worker:
    def __init__(self, name, temperature=0.5):
        self.name = name
        self.temperature = temperature

    def execute(self, task: dict, document_text: str) -> dict:
        """
        Execute a task on the given document text.
        Returns { "result": str, "confidence": float }
        """
        task_type = task.get("type", "")
        handlers = {
            "summarize": self._summarize,
            "extract": self._extract,
            "analyze": self._analyze,
            "validate": self._validate,
            "generate": self._generate,
        }

        handler = handlers.get(task_type)
        if not handler:
            return {
                "result": f"Unsupported task type: {task_type}",
                "confidence": 0.0
            }

        return handler(document_text, task)

    def _summarize(self, text: str, task: dict) -> dict:
        """Extract a summary from the text."""
        if not text or len(text.strip()) == 0:
            return {"result": "No content to summarize.", "confidence": 0.1}

        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

        if len(sentences) == 0:
            return {"result": text[:200].strip(), "confidence": 0.5}

        # Pick first + middle + last sentence for a simple summary
        picks = []
        picks.append(sentences[0])
        if len(sentences) > 2:
            picks.append(sentences[len(sentences) // 2])
        if len(sentences) > 1:
            picks.append(sentences[-1])

        summary = ". ".join(picks) + "."
        confidence = self._compute_confidence(len(text), len(summary))
        return {"result": summary, "confidence": confidence}

    def _extract(self, text: str, task: dict) -> dict:
        """Extract key sentences from the text."""
        if not text or len(text.strip()) == 0:
            return {"result": "No content to extract from.", "confidence": 0.1}

        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        # Score sentences by word count (longer = more informative, simplistic heuristic)
        scored = sorted(sentences, key=lambda s: len(s.split()), reverse=True)
        top = scored[:min(5, len(scored))]

        result = "\n".join(f"• {s}." for s in top)
        confidence = self._compute_confidence(len(text), len(result))
        return {"result": result, "confidence": confidence}

    def _analyze(self, text: str, task: dict) -> dict:
        """Basic keyword frequency analysis."""
        if not text or len(text.strip()) == 0:
            return {"result": "No content to analyze.", "confidence": 0.1}

        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        # Filter out common stop words
        stop_words = {
            "that", "this", "with", "from", "have", "been", "were", "they",
            "their", "will", "would", "could", "should", "about", "which",
            "what", "when", "where", "there", "these", "those", "than",
            "then", "also", "into", "some", "such", "each", "only"
        }
        words = [w for w in words if w not in stop_words]
        freq = Counter(words).most_common(10)

        if not freq:
            return {"result": "Could not extract meaningful terms.", "confidence": 0.3}

        lines = [f"• {word}: {count} occurrences" for word, count in freq]
        result = "Key terms found:\n" + "\n".join(lines)
        confidence = self._compute_confidence(len(text), len(freq))
        return {"result": result, "confidence": min(0.95, 0.6 + len(freq) * 0.03)}

    def _validate(self, text: str, task: dict) -> dict:
        """Basic structural validation of the text."""
        if not text or len(text.strip()) == 0:
            return {"result": "No content to validate.", "confidence": 0.1}

        checks = []
        word_count = len(text.split())
        sentence_count = len(re.split(r'[.!?]+', text))

        checks.append(f"Word count: {word_count}")
        checks.append(f"Sentence count: {sentence_count}")
        checks.append(f"Avg words/sentence: {word_count // max(1, sentence_count)}")

        if word_count < 20:
            checks.append("⚠ Content is very short — low reliability")
            confidence = 0.4
        elif word_count < 100:
            checks.append("Content length is moderate")
            confidence = 0.7
        else:
            checks.append("✓ Content has sufficient length for analysis")
            confidence = 0.85

        result = "Validation report:\n" + "\n".join(f"• {c}" for c in checks)
        noise = random.uniform(0, self.temperature * 0.2)
        return {"result": result, "confidence": round(max(0.1, confidence - noise), 2)}

    def _generate(self, text: str, task: dict) -> dict:
        """Generate a formatted output based on available data."""
        if not text or len(text.strip()) == 0:
            return {"result": "No content to generate from.", "confidence": 0.1}

        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        word_count = len(text.split())

        report = []
        report.append("=== Generated Report ===")
        report.append(f"Source length: {word_count} words")
        report.append(f"Sections identified: {min(len(sentences), 5)}")
        report.append("")

        for i, s in enumerate(sentences[:5]):
            report.append(f"[{i+1}] {s}.")

        report.append("")
        report.append("=== End of Report ===")

        confidence = self._compute_confidence(len(text), len(sentences))
        return {"result": "\n".join(report), "confidence": confidence}

    def _compute_confidence(self, input_len: int, output_metric) -> float:
        """Compute confidence based on input/output ratio with temperature noise."""
        if isinstance(output_metric, int):
            base = min(0.95, 0.5 + output_metric * 0.05)
        else:
            ratio = output_metric / max(1, input_len)
            base = min(0.95, 0.5 + ratio * 2)

        noise = random.uniform(0, self.temperature * 0.3)
        return round(max(0.1, base - noise), 2)
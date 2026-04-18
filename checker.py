# checker.py

from typing import Dict

CONFIDENCE_HIGH_THRESHOLD   = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.70

# Minimum result length to be considered non-empty
MIN_RESULT_LENGTH = 20

# Phrases that indicate the model gave up or errored
FAILURE_PHRASES = [
    "i cannot",
    "i can't",
    "i don't know",
    "i am unable",
    "i'm unable",
    "execution failed",
    "error:",
    "as an ai, i",
    "i'm sorry, i",
]


class Validator:
    def __init__(self):
        self.passed_checks = 0
        self.failed_checks = 0

    def validate(self, result_data: Dict) -> Dict:
        confidence = result_data.get("confidence", 0.5)

        if confidence >= CONFIDENCE_HIGH_THRESHOLD:
            return self._auto_accept(result_data, confidence)
        elif confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
            return self._quick_check(result_data, confidence)
        else:
            return self._full_validation(result_data, confidence)

    # ── Tier 1: High confidence ───────────────────────────
    def _auto_accept(self, data: Dict, confidence: float) -> Dict:
        self.passed_checks += 1
        return {
            "verdict":          "accept",
            "validation_type":  "skipped_high_confidence",
            "confidence":       confidence,
            "message":          "Auto-approved — high confidence.",
            "token_savings":    "~60%"
        }

    # ── Tier 2: Medium confidence — lightweight checks ────
    def _quick_check(self, data: Dict, confidence: float) -> Dict:
        result   = data.get("result", "")
        failures = []

        # Check 1: non-empty
        if len(result.strip()) < MIN_RESULT_LENGTH:
            failures.append("output too short")

        # Check 2: didn't fail silently
        result_lower = result.lower()
        for phrase in FAILURE_PHRASES:
            if phrase in result_lower:
                failures.append(f"failure phrase detected: '{phrase}'")
                break

        # Check 3: not just whitespace/punctuation
        alphanum_chars = sum(c.isalnum() for c in result)
        if alphanum_chars < 10:
            failures.append("output lacks alphanumeric content")

        passed  = len(failures) == 0
        verdict = "accept" if passed else "retry"

        if passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1

        return {
            "verdict":         verdict,
            "validation_type": "quick_sanity_check",
            "confidence":      confidence,
            "message":         (
                "Quick check passed."
                if passed
                else f"Quick check failed: {'; '.join(failures)}"
            ),
            "failures":        failures,
        }

    # ── Tier 3: Low confidence — stricter heuristics ──────
    def _full_validation(self, data: Dict, confidence: float) -> Dict:
        result   = data.get("result", "")
        failures = []

        # All quick checks apply
        if len(result.strip()) < MIN_RESULT_LENGTH:
            failures.append("output too short")

        result_lower = result.lower()
        for phrase in FAILURE_PHRASES:
            if phrase in result_lower:
                failures.append(f"failure phrase: '{phrase}'")
                break

        alphanum_chars = sum(c.isalnum() for c in result)
        if alphanum_chars < 10:
            failures.append("insufficient alphanumeric content")

        # Stricter: minimum word count for low-confidence results
        word_count = len(result.split())
        if word_count < 15:
            failures.append(f"word count too low ({word_count} < 15)")

        # Stricter: penalise extremely repetitive output
        unique_words  = len(set(result.lower().split()))
        total_words   = max(word_count, 1)
        diversity     = unique_words / total_words
        if total_words > 30 and diversity < 0.25:
            failures.append(f"low lexical diversity ({diversity:.2f})")

        passed  = len(failures) == 0
        verdict = "accept" if passed else "retry"

        if passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1

        return {
            "verdict":         verdict,
            "validation_type": "full_heuristic_validation",
            "confidence":      confidence,
            "message":         (
                "Full validation passed."
                if passed
                else f"Full validation failed: {'; '.join(failures)}"
            ),
            "failures":        failures,
        }


def create_validator() -> Validator:
    return Validator()
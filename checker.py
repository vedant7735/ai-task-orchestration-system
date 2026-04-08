# checker.py

class Checker:
    def __init__(self, confidence_threshold=0.6):
        self.threshold = confidence_threshold

    def evaluate(self, output: dict) -> dict:
        """
        Evaluate worker output.

        Returns:
        {
            "verdict": "accept" | "retry",
            "reason": str
        }
        """
        confidence = output.get("confidence", 0.0)
        result = output.get("result", "")

        # Basic rules (keep simple for V2)
        if confidence < self.threshold:
            return {
                "verdict": "retry",
                "reason": "Low confidence"
            }

        if not result or len(result.strip()) < 20:
            return {
                "verdict": "retry",
                "reason": "Weak or empty output"
            }

        return {
            "verdict": "accept",
            "reason": "Sufficient quality"
        }
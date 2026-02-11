class Assembler:
    def __init__(self, confidence_threshold=0.6):
        self.threshold = confidence_threshold

    def assemble(self, worker_outputs: dict) -> dict:
        """
        Combines worker outputs while preserving failures.
        Expects worker_outputs: { task_id: { "result": str, "confidence": float } }
        """
        assembled = {}
        failed = []

        for task_id, result in worker_outputs.items():
            confidence = result.get("confidence", 0)

            if confidence < self.threshold:
                assembled[task_id] = f"LOW CONFIDENCE ({confidence:.0%}) — {result.get('result', 'No output')}"
                failed.append(task_id)
            else:
                assembled[task_id] = result.get("result", result.get("summary", ""))

        return {
            "assembled_output": assembled,
            "failed_tasks": failed,
            "total_tasks": len(worker_outputs),
            "successful_tasks": len(worker_outputs) - len(failed),
        }
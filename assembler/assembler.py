class Assembler:
    def __init__(self, confidence_threshold=0.6):
        self.threshold = confidence_threshold

    def assemble(self, worker_outputs):
        """
        Combines fragmented outputs while preserving failures.
        """

        assembled = {}
        failed = []

        for task_id, result in worker_outputs.items():
            if result["confidence"] < self.threshold:
                assembled[task_id] = "LOW CONFIDENCE — requires retry or user input"
                failed.append(task_id)
            else:
                assembled[task_id] = result["summary"]

        return {
            "assembled_output": assembled,
            "failed_tasks": failed
        }
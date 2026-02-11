import time
from worker.worker import Worker
from assembler.assembler import Assembler


class Orchestrator:
    """
    Wires Planner output → Workers → Assembler.
    Yields progress updates for SSE streaming.
    """

    def __init__(self, confidence_threshold=0.6, max_retries=2):
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries

    def run(self, plan: dict, document_text: str):
        """
        Execute a plan against the given document text.
        Yields progress dicts for each step, then a final result dict.

        Yields:
            {"type": "worker_update", "worker_id": int, "status": str, ...}
            {"type": "result", "assembled": dict, "overall_confidence": float}
        """
        tasks = plan.get("tasks", [])
        policy = plan.get("execution_policy", {})
        threshold = policy.get("confidence_threshold", self.confidence_threshold)
        max_retries = policy.get("max_retries", self.max_retries)

        # Group tasks by worker
        worker_tasks = {}
        for task in tasks:
            wid = task.get("worker", 1)
            worker_tasks.setdefault(wid, []).append(task)

        # Create worker instances
        workers = {}
        for wid in worker_tasks:
            workers[wid] = Worker(name=f"Worker-{wid}", temperature=0.3)

        worker_outputs = {}
        all_confidences = []

        # Execute tasks per worker
        for wid, task_list in worker_tasks.items():
            worker = workers[wid]
            total = len(task_list)

            yield {
                "type": "worker_update",
                "worker_id": wid,
                "status": "running",
                "current_task": 0,
                "total_tasks": total,
                "task_description": "Starting...",
                "confidence": 0,
                "progress": 0,
            }

            for idx, task in enumerate(task_list):
                task_id = task.get("id", f"t{idx}")

                yield {
                    "type": "worker_update",
                    "worker_id": wid,
                    "status": "running",
                    "current_task": idx + 1,
                    "total_tasks": total,
                    "task_description": task.get("description", "Processing..."),
                    "confidence": 0,
                    "progress": int(((idx + 1) / total) * 100),
                }

                # Execute with retries
                result = None
                for attempt in range(max_retries + 1):
                    result = worker.execute(task, document_text)

                    if result["confidence"] >= threshold:
                        break

                    if attempt < max_retries:
                        yield {
                            "type": "worker_update",
                            "worker_id": wid,
                            "status": "running",
                            "current_task": idx + 1,
                            "total_tasks": total,
                            "task_description": f"Retrying ({attempt + 1}/{max_retries}): {task.get('description', '')}",
                            "confidence": int(result["confidence"] * 100),
                            "progress": int(((idx + 1) / total) * 100),
                        }

                worker_outputs[task_id] = result
                all_confidences.append(result["confidence"])

                yield {
                    "type": "worker_update",
                    "worker_id": wid,
                    "status": "running",
                    "current_task": idx + 1,
                    "total_tasks": total,
                    "task_description": task.get("description", "Done"),
                    "confidence": int(result["confidence"] * 100),
                    "progress": int(((idx + 1) / total) * 100),
                }

            # Worker done
            avg_conf = sum(
                worker_outputs[t["id"]]["confidence"]
                for t in task_list
                if t["id"] in worker_outputs
            ) / max(1, len(task_list))

            final_status = "complete" if avg_conf >= threshold else "failed"

            yield {
                "type": "worker_update",
                "worker_id": wid,
                "status": final_status,
                "current_task": total,
                "total_tasks": total,
                "task_description": "Complete" if final_status == "complete" else "Failed — low confidence",
                "confidence": int(avg_conf * 100),
                "progress": 100,
            }

        # Assemble results
        assembler = Assembler(confidence_threshold=threshold)
        assembled = assembler.assemble(worker_outputs)

        # Compute overall confidence
        overall = 0
        if all_confidences:
            overall = round(sum(all_confidences) / len(all_confidences), 2)

        warnings = len(assembled.get("failed_tasks", []))

        yield {
            "type": "result",
            "assembled": assembled,
            "overall_confidence": int(overall * 100),
            "total_tasks": len(tasks),
            "completed_tasks": len(tasks) - warnings,
            "warnings": warnings,
        }

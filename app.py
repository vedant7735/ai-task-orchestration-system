# app.py (CLI DEBUG MODE)

import time
from planner import Planner
from worker import Worker
from assembler import Assembler
from checker import create_validator
from models import manager, print_ram

planner = Planner()
worker = Worker()
assembler = Assembler()
validator = create_validator()

# ----------------------------
# TELEMETRY
# ----------------------------
def log_stage(stage):
    print(f"\n{'='*20} {stage} {'='*20}")
    print_ram()


def log_performance(start_time, tokens=None):
    elapsed = time.time() - start_time
    print(f"[TIME] {elapsed:.2f}s")

    if tokens:
        tps = tokens / elapsed if elapsed > 0 else 0
        print(f"[TOKENS] {tokens} | {tps:.2f} tok/s")


# ----------------------------
# TOKEN ESTIMATE (approx)
# ----------------------------
def estimate_tokens(text):
    if not text:
        return 0
    return int(len(text) / 4)  # rough heuristic

# ----------------------------
# READY TASKS
# ----------------------------

def get_ready_tasks(tasks, completed_ids):
    """
    Return tasks whose dependencies are all completed.
    """
    ready = []
    for task in tasks:
        task_id = task.get("id")
        
        # Skip if already completed
        if task_id in completed_ids:
            continue
        
        # Check if all dependencies are satisfied
        deps = task.get("depends_on", [])
        if all(dep in completed_ids for dep in deps):
            ready.append(task)
    
    return ready

# ----------------------------
# EXECUTE TASK
# ----------------------------

def execute_task(task, document, task_results):
    """
    Wrapper for worker execution with proper context.
    """
    print(f"\n[TASK START] {task['id']}")
    return worker.execute(task, document, task_results)

# ----------------------------
# PIPELINE
# ----------------------------
def run_pipeline(intent: str, document: str):

    # ----------------------------
    # ⚡ ULTRA FAST PATH (SKIP PLANNER)
    # ----------------------------
    if len(intent.split()) <= 6:
        print("\n⚡ ULTRA FAST PATH (Skipping Planner + Assembler)\n")

        task_type = "CODE" if any(k in intent.lower() for k in ["code", "function", "implement"]) else "EXPLAIN"

        task = {
            "id": "t1",
            "type": task_type,
            "target": intent,
            "depends_on": []
        }

        result = worker.execute(task, document, {})

        return {
            "status": "completed",
            "plan": {"mode": "ultra_fast"},
            "results": [result],
            "final": {
                "final_output": result["result"],
                "low_confidence_tasks": [],
                "total_tasks": 1
            }
        }

    # ----------------------------
    # 🧠 PLANNER
    # ----------------------------
    print("\n==================== PLANNER START ====================")

    plan = planner.analyze_intent(intent)

    if plan.get("status") == "needs_clarification":
        return plan

    tasks = plan.get("tasks", [])
    mode = plan.get("mode", "decompose")

    # ----------------------------
    # ⚡ DIRECT MODE (SKIP DAG + ASSEMBLER)
    # ----------------------------
    if mode == "direct" and len(tasks) == 1:
        print("\n⚡ DIRECT EXECUTION (Skipping DAG + Assembler)\n")

        result = worker.execute(tasks[0], document, {})

        print("\n[FINAL OUTPUT]")
        print(result["result"])
        print(f"\n[Confidence: {result.get('confidence', 0.0):.2f}]")

        return {
            "status": "completed",
            "plan": plan,
            "results": [result],
            "final": {
                "final_output": result["result"],
                "low_confidence_tasks": [],
                "total_tasks": 1
            }
        }

    # ----------------------------
    # 🔁 DAG EXECUTION
    # ----------------------------
    print("\n==================== WORKER START ====================")

    completed_ids = set()
    task_results = {}
    all_results = []

    while len(completed_ids) < len(tasks):

        ready_tasks = get_ready_tasks(tasks, completed_ids)

        if not ready_tasks:
            return {
                "status": "error",
                "message": "Deadlock detected in task dependencies"
            }

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []

            for task in ready_tasks:
                futures.append(
                    executor.submit(
                        execute_task,
                        task,
                        document,
                        task_results
                    )
                )

            for future in futures:
                output = future.result()

                validation = validator.validate(output)
                output["validation"] = validation

                # 🔁 RETRY LOGIC
                if validation["verdict"] == "retry":
                    original_task = next((t for t in tasks if t["id"] == output["task_id"]), None)
                    if original_task:
                        retry_output = worker.execute(original_task, document, task_results)
                        retry_output["validation"] = validator.validate(retry_output)
                        output = retry_output

                task_id = output["task_id"]

                completed_ids.add(task_id)
                task_results[task_id] = output["result"]
                all_results.append(output)

    # ----------------------------
    # CRITICAL TASK RECOVERY
    # ----------------------------

    retry_needed = [
        r for r in all_results 
        if r.get("validation", {}).get("verdict") == "retry"
    ]

    if retry_needed:
        print(f"\n⚠️ {len(retry_needed)} tasks failed validation. Retrying...")

        for item in retry_needed:
            task_id = item["task_id"]
            original_task = next((t for t in tasks if t["id"] == task_id), None)
        
            if original_task:
                old_conf = item.get("confidence", 0)
                val_type = item.get("validation", {}).get("validation_type", "unknown")
            
                print(f"   🔄 Retrying: {task_id}")
                print(f"      Reason: {val_type} (confidence: {old_conf:.2f})")
            
                retry_output = worker.execute(original_task, document, task_results)
                retry_output["validation"] = validator.validate(retry_output)
            
                # Replace old result
                for i, r in enumerate(all_results):
                    if r["task_id"] == task_id:
                        all_results[i] = retry_output
                        break
            
                task_results[task_id] = retry_output["result"]
            
                new_conf = retry_output.get("confidence", 0)
                new_verdict = retry_output.get("validation", {}).get("verdict", "unknown")
                print(f"      → New: {new_verdict} (confidence: {new_conf:.2f})")


    # ----------------------------
    # 🧩 ASSEMBLER
    # ----------------------------
    print("\n==================== ASSEMBLER START ====================")

    final = assembler.assemble(plan, all_results)

    print("\n[FINAL OUTPUT]")
    print(final["final_output"])
    print(f"\n[Total tasks: {final.get('total_tasks', 0)}]")
    print(f"[Low confidence tasks: {final.get('low_confidence_tasks', [])}]")

    return {
        "status": "completed",
        "plan": plan,
        "results": all_results,
        "final": final
    }


# ----------------------------
# CLI LOOP
# ----------------------------
if __name__ == "__main__":

    print("\n=== AI ORCHESTRATION SYSTEM (CLI DEBUG MODE) ===\n")

    while True:
        try:
            intent = input("\nEnter intent (or 'exit'): ").strip()

            if intent.lower() == "exit":
                break

            document = input("Optional document (enter to skip): ").strip()

            run_pipeline(intent, document)

        except KeyboardInterrupt:
            print("\nExiting...")
            break

        except Exception as e:
            print(f"\n[ERROR] {str(e)}")
            manager.unload_all()
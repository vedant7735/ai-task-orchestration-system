from planner import Planner
from worker import Worker
from assembler import Assembler


def run_pipeline(intent: str, document: str):
    planner = Planner()
    worker = Worker()
    assembler = Assembler()

    # 1. Plan
    print("\n[1] Planning...")
    plan = planner.create_plan(intent)
    print(f"Plan: {plan}")

    # 2. Execute tasks
    print("\n[2] Executing tasks...")
    results = []

    for task in plan.get("tasks", []):
        print(f"\n→ Running task {task['id']}: {task['description']}")

        output = worker.execute(task, document)

        print("\n--- WORKER OUTPUT ---")
        print(output["result"])
        print(f"\nConfidence: {output['confidence']:.2f}")
        print("--- END ---")

        results.append(output)

    # 3. Assemble
    print("\n[3] Assembling final response...")
    final = assembler.assemble(plan, results)

    print("\n===== FINAL OUTPUT =====\n")
    print(final["final_output"])

    print("\n===== META =====")
    print(f"Low confidence tasks: {final['low_confidence_tasks']}")
    print(f"Total tasks: {final['total_tasks']}")


if __name__ == "__main__":
    print("\nAI Pipeline V1 (Minimal)\n")

    intent = input("Enter your intent: ").strip()
    document = input("\nPaste your document (or leave empty): ").strip()

    if not intent:
        print("Intent is required.")
    else:
        run_pipeline(intent, document)
from models import client, MODELS

ASSEMBLER_SYSTEM_PROMPT = """You are an assembler in a simple AI pipeline.

You will be given:
- The user's intent
- Results from multiple tasks (each with confidence)

Your job:
- Combine them into a clear final response
- Stay grounded in the provided results
- Do NOT introduce new information

If some results are weak or incomplete:
- Mention that clearly

Be concise but complete.
"""


class Assembler:
    def assemble(self, plan: dict, worker_results: list) -> dict:
        intent = plan.get("intent", "")

        # Format worker outputs
        results_str = ""
        low_conf_tasks = []

        for res in worker_results:
            task_id = res.get("task_id")
            result = res.get("result", "")
            confidence = res.get("confidence", 0.0)

            if confidence < 0.5:
                low_conf_tasks.append(task_id)

            results_str += f"\n--- Task {task_id} (confidence: {confidence:.2f}) ---\n"
            results_str += f"{result}\n"

        user_message = f"""
USER INTENT:
{intent}

TASK RESULTS:
{results_str}

Combine these into a final response.
"""

        try:
            response = client.chat.completions.create(
                model=MODELS["assembler"],
                messages=[
                    {"role": "system", "content": ASSEMBLER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.2,
                max_tokens=1500
            )

            final_text = response.choices[0].message.content.strip()

        except Exception as e:
            final_text = f"Assembly failed: {str(e)}"

        return {
            "final_output": final_text,
            "low_confidence_tasks": low_conf_tasks,
            "total_tasks": len(worker_results)
        }
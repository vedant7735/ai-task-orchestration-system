# worker.py

from models import client, MODELS

WORKER_SYSTEM_PROMPT = """You are a task execution agent.

You will be given:
- A task description
- A document (may or may not be provided)

Your job:
- Execute the task as accurately as possible
- Use the document if it is relevant and available
- If no document is provided, rely on general knowledge

Rules:
- Do NOT refuse the task just because the document is missing
- Do NOT hallucinate specific facts you are unsure about
- If information is incomplete or uncertain, briefly state the limitation
- Still provide the best possible answer based on available knowledge

At the end, output:
CONFIDENCE: 0.XX

Where 0.XX is between 0.0 and 1.0 reflecting how reliable your answer is.
"""


class Worker:
    def execute(self, task: dict, document: str, previous_results=None) -> dict:
        task_desc = task.get("description", "")
        previous_context = ""

        if previous_results:
            previous_context += "\nRELEVANT PREVIOUS RESULTS:\n"
            for task_id, res in previous_results.items():
                previous_context += f"\nTask {task_id}:\n{res.get('result')}\n"
        
        user_message = f"""
TASK OBJECT:
{task}

{previous_context}

DOCUMENT:
{document[:4000] if document else "No document provided."}

Execute strictly based on the task type.

End with CONFIDENCE: 0.XX
"""

        try:
            response = client.chat.completions.create(
                model=MODELS["worker"],
                messages=[
                    {"role": "system", "content": WORKER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1000
            )

            raw_output = response.choices[0].message.content.strip()

            result, confidence = self._parse_output(raw_output)

            return {
                "task_id": task.get("id"),
                "result": result,
                "confidence": confidence
            }

        except Exception as e:
            return {
                "task_id": task.get("id"),
                "result": f"Execution failed: {str(e)}",
                "confidence": 0.0
            }

    # ---------------------------- #
    # Output parsing
    # ---------------------------- #

    def _parse_output(self, raw: str):
        lines = raw.strip().split("\n")

        confidence = 0.5
        result = raw

        for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1):
            line = lines[i].strip()
            if line.upper().startswith("CONFIDENCE:"):
                try:
                    conf = float(line.split(":")[1].strip())
                    confidence = max(0.0, min(1.0, conf))
                    result = "\n".join(lines[:i]).strip()
                except:
                    pass
                break

        return result, confidence
import re
import sys

_CONFIDENCE_INSTRUCTION = """

At the very end of your response, on its own line, write your confidence:
CONFIDENCE: 0.X
Where X is a number from 0.0 to 1.0.
- 0.9+ : Certain, answer is complete
- 0.7-0.9: Mostly confident
- 0.5-0.7: Partial answer
- below 0.5: Low confidence"""

_CODE_PROMPT = """You are a senior software engineer.
Write clean, executable, production-ready Python code.
Rules:
- Return ONLY raw Python code
- No markdown fences
- No explanation
- Code must be complete and runnable"""

_CODE_FIX_PROMPT = """You are a Python debugging expert.
Fix the broken code so it runs without errors.
Return ONLY the corrected Python code.
No markdown. No explanation."""

DOMAIN_PROMPTS = {
    "CODE":     _CODE_PROMPT,
    "DEBUG":    "You are a debugging expert. Identify root cause. Provide corrected code only. No explanation.",
    "REFACTOR": "You are a code optimization expert. Improve structure and readability. Return improved code only.",
    "EXPLAIN":  "You are a technical explainer. Explain clearly and concisely. Avoid fluff and repetition.",
    "CALCULATE":"You are a precise mathematical solver. Return exact results. Show steps if needed.",
    "ANALYZE":  "You are an analytical reasoning expert. Break down step by step. Be logical and structured.",
    "RESEARCH": "You are a research assistant. Provide factual structured information. Do not hallucinate.",
    "SUMMARIZE":"You are a summarization engine. Condense into key points. Preserve meaning.",
    "COMPARE":  "You are a comparison expert. Compare across key dimensions. Use bullet points.",
    "DESIGN":   "You are a system design expert. Design scalable architectures. Explain components clearly.",
    "PLAN":     "You are a task planner. Break into clear executable steps.",
    "CRITIQUE": "You are a critical evaluator. Identify weaknesses and risks. Be direct.",
    "OPTIMIZE": "You are a performance optimization expert. Improve speed and efficiency.",
    "SECURITY": "You are a security expert. Identify vulnerabilities. Suggest secure alternatives.",
    "DATA":     "You are a data processing expert. Clean and structure data logically.",
}

CODE_TASKS       = {"CODE", "DEBUG", "REFACTOR", "OPTIMIZE"}
MAX_CODE_RETRIES = 3


def _get_system_prompt(task_type: str) -> str:
    base = DOMAIN_PROMPTS.get(task_type, "You are a helpful AI assistant.")
    if task_type in CODE_TASKS:
        return base
    return base + _CONFIDENCE_INSTRUCTION


def _extract_code(raw: str) -> str:
    raw    = raw.strip()
    fenced = re.search(r'```(?:python)?\n(.*?)```', raw, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.split("\n")
        return "\n".join(lines[1:-1]).strip()
    return raw


def _parse_confidence(raw: str) -> tuple[str, float]:
    lines      = raw.strip().split("\n")
    confidence = 0.75
    result     = raw.strip()

    for i, line in enumerate(reversed(lines[-6:])):
        stripped = line.strip()
        if stripped.upper().startswith("CONFIDENCE:"):
            try:
                raw_val    = stripped.split(":", 1)[1].strip()
                confidence = max(0.0, min(1.0, float(raw_val)))
                actual_idx = len(lines) - 1 - i
                result     = "\n".join(lines[:actual_idx]).strip()
                print(f"[WORKER] Confidence: {confidence:.2f}", file=sys.__stdout__)
            except (ValueError, IndexError):
                pass
            break

    return result, confidence


def _has_error(output: str) -> bool:
    markers = [
        "Traceback (most recent call last)",
        "SyntaxError", "NameError", "TypeError",
        "ValueError", "IndentationError",
        "ImportError", "ModuleNotFoundError",
        "[ERROR"
    ]
    return any(m in output for m in markers)


class Worker:
    def execute(self, task: dict, document: str, previous_results=None) -> dict:
        from models import get_worker_backend

        task_type = task.get("type", "EXPLAIN")
        task_id   = task.get("id",   "?")
        task_desc = (task.get("target") or "").strip()

        # Build dependency context
        context = ""
        for dep in task.get("depends_on", []):
            if previous_results and dep in previous_results:
                context += f"\n--- From {dep} ---\n{previous_results[dep]}\n"

        safe_doc = document[:3000] if document else ""

        user_parts = [f"TASK:\n{task_desc}"]
        if context.strip():
            user_parts.append(f"DEPENDENCY_CONTEXT:\n{context.strip()}")
        if safe_doc.strip():
            user_parts.append(f"DOCUMENT:\n{safe_doc}")
        user_message = "\n\n".join(user_parts)

        backend = get_worker_backend()

        try:
            if task_type in CODE_TASKS:
                return self._execute_code_task(
                    backend, task_id, task_type, task_desc, user_message
                )
            else:
                return self._execute_text_task(
                    backend, task_id, task_type, user_message
                )
        finally:
            backend.unload()

    # ── CODE path ────────────────────────────────────────
    def _execute_code_task(
        self, backend, task_id, task_type, task_desc, user_message
    ) -> dict:
        from tools import run_python_code

        code        = ""
        exec_output = ""
        success     = False
        attempts    = 0

        for attempt in range(MAX_CODE_RETRIES):
            attempts = attempt + 1
            print(f"[WORKER] {task_id} | {task_type} | attempt {attempts}/{MAX_CODE_RETRIES}", file=sys.__stdout__)

            try:
                if attempt == 0:
                    raw = backend.complete(
                        system=_get_system_prompt(task_type),
                        user=user_message,
                        temperature=0.2,
                        max_tokens=1000,
                    )
                else:
                    raw = backend.complete(
                        system=_CODE_FIX_PROMPT,
                        user=(
                            f"TASK: {task_desc[:300]}\n\n"
                            f"BROKEN CODE:\n{code[:500]}\n\n"
                            f"ERROR:\n{exec_output[:300]}\n\n"
                            f"Fixed code:"
                        ),
                        temperature=0.4,
                        max_tokens=1000,
                    )

                code        = _extract_code(raw)
                exec_output = run_python_code(code)

                if not _has_error(exec_output):
                    success = True
                    print(f"[WORKER] ✅ {task_id} executed successfully (attempt {attempts})", file=sys.__stdout__)
                    break
                else:
                    print(f"[WORKER] ❌ Attempt {attempts}: {exec_output[:100]}", file=sys.__stdout__)

            except Exception as e:
                exec_output = str(e)
                print(f"[WORKER ERROR] {task_id} attempt {attempts}: {e}", file=sys.__stdout__)

        confidence = 0.95 if success else 0.30
        result = (
            f"```python\n{code}\n```\n\n"
            f"**Output**:\n```\n{exec_output}\n```"
        )

        print(f"[WORKER] {task_id} | conf={confidence} | success={success}", file=sys.__stdout__)

        return {
            "task_id":            task_id,
            "task_type":          task_type,
            "result":             result,
            "confidence":         confidence,
            "execution_success":  success,
            "attempts":           attempts,
            "execution_output":   exec_output,
            "validation_verdict": "accept" if success else "retry",
        }

    # ── TEXT path ────────────────────────────────────────
    def _execute_text_task(
        self, backend, task_id, task_type, user_message
    ) -> dict:
        print(f"[WORKER] {task_id} | {task_type} | generating...", file=sys.__stdout__)

        raw = backend.complete(
            system=_get_system_prompt(task_type),
            user=user_message,
            temperature=0.3,
            max_tokens=1000,
        )

        result, confidence = _parse_confidence(raw)

        print(f"[WORKER] {task_id} | {task_type} | conf={confidence:.2f}", file=sys.__stdout__)

        return {
            "task_id":    task_id,
            "task_type":  task_type,
            "result":     result,
            "confidence": confidence,
        }
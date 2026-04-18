import os
import sys
from models import get_assembler_backend, manager

LOW_CONF_THRESHOLD = 0.70

ASSEMBLER_SYSTEM_PROMPT = """You are a senior technical writer inside an AI orchestration pipeline.

You will receive results from multiple specialized AI workers.

Your job:
- Synthesize into ONE clear, well-structured response
- Remove redundancy - each point appears once
- Preserve all code examples exactly as written
- Preserve all specific details and technical accuracy
- If a worker had low confidence, note that briefly
- Do NOT introduce information not in the worker results
- Do NOT pad with filler phrases

Format for a technical reader. Use markdown where helpful."""


def _find_low_conf_tasks(results: list) -> list:
    return [
        r.get("task_id", "?")
        for r in results
        if r.get("confidence", 1.0) < LOW_CONF_THRESHOLD
    ]


def _build_user_message(plan: dict, results: list) -> str:
    intent = plan.get("intent", "")
    mode   = plan.get("mode",   "")

    lines = [f"USER INTENT: {intent}"]
    if mode:
        lines.append(f"EXECUTION MODE: {mode.upper()}")
    lines.append("")
    lines.append("WORKER RESULTS:")
    lines.append("=" * 60)

    for res in results:
        task_id    = res.get("task_id",    "?")
        task_type  = res.get("task_type",  "UNKNOWN")
        confidence = res.get("confidence", 0.0)
        result     = res.get("result",     "(no output)")
        verdict    = res.get("validation_verdict", "")

        conf_label = (
            "HIGH [ok]" if confidence >= 0.85 else
            "MID  [~]" if confidence >= 0.70 else
            "LOW  [!]"
        )

        header = (
            f"[{task_id}] {task_type} | "
            f"Confidence: {confidence:.2f} ({conf_label})"
        )
        if verdict:
            header += f" | Verdict: {verdict}"

        lines.append(header)
        lines.append("-" * 40)
        lines.append(result)
        lines.append("")

    lines.append("=" * 60)
    lines.append("")
    lines.append(
        "Synthesize the above into a single clear response "
        "to the user's intent."
    )

    return "\n".join(lines)


def _deterministic_merge(plan: dict, results: list) -> str:
    """Fallback — no API needed, never crashes."""
    intent = plan.get("intent", "")
    lines  = []

    if intent:
        lines.append(f"# {intent}")
        lines.append("")

    if len(results) > 1:
        lines.append("*Note: Assembled from multiple workers. Synthesis unavailable.*")
        lines.append("")

    for i, res in enumerate(results, 1):
        task_type = res.get("task_type", "")
        content   = res.get("result",    "").strip()
        conf      = res.get("confidence", 0.0)

        if len(results) > 1:
            label = f"## {task_type or f'Task {i}'}"
            if conf < LOW_CONF_THRESHOLD:
                label += " *(low confidence)*"
            lines.append(label)
            lines.append("")

        lines.append(content)
        lines.append("")

    return "\n".join(lines).strip()


class Assembler:
    def assemble(self, plan: dict, worker_results: list) -> dict:
        """
        Assemble worker results into final response.

        Paths:
          1. Single result  → direct pass-through (no API call)
          2. Multi-result   → backend synthesis (Groq or local)
          3. Backend fails  → deterministic merge (never crashes)
        """
        low_conf_tasks = _find_low_conf_tasks(worker_results)

        # ── Single result: pass through directly ──────────
        if len(worker_results) == 1:
            print("[ASSEMBLER] Single result - direct pass-through.", file=sys.__stdout__)
            return {
                "final_output":         worker_results[0].get("result", ""),
                "low_confidence_tasks": low_conf_tasks,
                "total_tasks":          1,
                "assembly_method":      "direct",
            }

        user_message = _build_user_message(plan, worker_results)
        print(
            f"[ASSEMBLER] Synthesizing {len(worker_results)} results "
            f"(~{len(user_message)//4} tokens estimated)...",
            file=sys.__stdout__
        )

        backend = get_assembler_backend()

        try:
            final_text = backend.complete(
                system=ASSEMBLER_SYSTEM_PROMPT,
                user=user_message,
                temperature=0.2,
                max_tokens=2048,
            )

            if not final_text or len(final_text) < 30:
                raise ValueError("Backend returned empty response")

            # Determine method label for frontend
            method = (
                "groq"          if backend.backend_type == "groq"
                else "llm"
            )

            print(f"[ASSEMBLER] Done ({len(final_text)} chars).", file=sys.__stdout__)

        except Exception as e:
            print(f"[ASSEMBLER] Backend failed: {e}", file=sys.__stdout__)
            print("[ASSEMBLER] Using deterministic merge.", file=sys.__stdout__)
            final_text = _deterministic_merge(plan, worker_results)
            method     = "deterministic"

        finally:
            backend.unload()

        return {
            "final_output":         final_text,
            "low_confidence_tasks": low_conf_tasks,
            "total_tasks":          len(worker_results),
            "assembly_method":      method,
        }

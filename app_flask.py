"""
app_flask.py — Flask server entry point for ORCHESTRATOR_V1
Run with: python app_flask.py
"""

import os
import time
import uuid
import sys
from datetime import datetime, timezone

from planner import Planner
from worker import Worker
from assembler import Assembler
from checker import create_validator
from models import manager, print_ram
from agent import run_lab_agent, run_analysis_agent

# ──────────────────────────────────────────────────────────
# CORE COMPONENTS
# ──────────────────────────────────────────────────────────
planner   = Planner()
worker    = Worker()
assembler = Assembler()
validator = create_validator()

# ──────────────────────────────────────────────────────────
# SESSION HISTORY STORE
# ──────────────────────────────────────────────────────────
_execution_history: list[dict] = []

def _record_execution(normalized: dict) -> None:
    _execution_history.append(normalized)


def _normalize_result(raw: dict) -> dict:
    conf    = raw.get("confidence", 0.0)
    verdict = (
        raw.get("validation", {}).get("verdict")
        or raw.get("validation_verdict")
        or ("skipped_high_confidence" if conf >= 0.85 else "accept")
    )
    return {
        "task_id":            raw.get("task_id", "t?"),
        "task_type":          raw.get("task_type") or raw.get("type", "UNKNOWN"),
        "result":             raw.get("result", ""),
        "confidence":         round(float(conf), 4),
        "validation_verdict": verdict,
    }


def _normalize_plan(raw_plan: dict, tasks: list[dict]) -> dict:
    return {
        "intent":  raw_plan.get("intent", ""),
        "mode":    raw_plan.get("mode", "direct"),
        "pattern": raw_plan.get("pattern", raw_plan.get("mode", "direct")),
        "status":  raw_plan.get("status", "ready"),
        "tasks": [
            {
                "id":         t.get("id", ""),
                "type":       t.get("type", "UNKNOWN"),
                "target":     t.get("target", ""),
                "depends_on": t.get("depends_on", []),
            }
            for t in tasks
        ],
    }


def _build_execution_record(
    execution_id: str,
    intent:       str,
    status:       str,
    plan:         dict,
    results:      list[dict],
    final:        dict | None,
    timestamp:    str,
) -> dict:
    return {
        "execution_id": execution_id,
        "id":           execution_id,
        "timestamp":    timestamp,
        "intent":       intent,
        "status":       status,
        "plan":         plan,
        "results":      results,
        "final":        final,
        "mode":         plan.get("mode", "direct"),
        "total_tasks":  len(results),
    }


# ──────────────────────────────────────────────────────────
# TELEMETRY
# ──────────────────────────────────────────────────────────
def log_stage(stage: str) -> None:
    print(f"\n{'='*20} {stage} {'='*20}")
    print_ram()


def estimate_tokens(text: str) -> int:
    return int(len(text) / 4) if text else 0


# ──────────────────────────────────────────────────────────
# DAG HELPERS
# ──────────────────────────────────────────────────────────
def get_ready_tasks(tasks: list[dict], completed_ids: set) -> list[dict]:
    ready = []
    for task in tasks:
        task_id = task.get("id")
        if task_id in completed_ids:
            continue
        deps = task.get("depends_on", [])
        if all(dep in completed_ids for dep in deps):
            ready.append(task)
    return ready


def execute_task(task: dict, document: str, task_results: dict) -> dict:
    print(f"\n[TASK START] {task['id']}")
    return worker.execute(task, document, task_results)


# ──────────────────────────────────────────────────────────
# CORE PIPELINE
# ──────────────────────────────────────────────────────────
def run_pipeline(intent: str, document: str = "") -> dict:
    execution_id = f"exec-{str(uuid.uuid4())[:8].upper()}"
    timestamp    = datetime.now(timezone.utc).isoformat()

    # -- ULTRA-FAST PATH ---------------------------------
    if len(intent.split()) <= 6:
        print("\n>> ULTRA FAST PATH\n")

        task_type = (
            "CODE"
            if any(k in intent.lower() for k in ["code", "function", "implement", "write"])
            else "EXPLAIN"
        )
        task = {"id": "t1", "type": task_type, "target": intent, "depends_on": []}

        raw_result  = worker.execute(task, document, {})
        norm_result = _normalize_result({**raw_result, "task_type": task_type})
        norm_plan   = _normalize_plan({"intent": intent, "mode": "ultra_fast"}, [task])
        final = {
            "final_output":         norm_result["result"],
            "low_confidence_tasks": [],
            "total_tasks":          1,
        }
        record = _build_execution_record(
            execution_id, intent, "completed",
            norm_plan, [norm_result], final, timestamp
        )
        _record_execution(record)
        return record

    # -- PLANNER -----------------------------------------
    print("\n==================== PLANNER ====================")
    plan  = planner.analyze_intent(intent)

    if plan.get("status") == "needs_clarification":
        return {
            "status":       "needs_clarification",
            "questions":    plan.get("questions", []),
            "execution_id": execution_id,
            "timestamp":    timestamp,
        }

    tasks = plan.get("tasks", [])
    mode  = plan.get("mode", "decompose")

    # -- DIRECT MODE -------------------------------------
    if mode == "direct" and len(tasks) == 1:
        print("\n>> DIRECT MODE\n")

        raw_result  = worker.execute(tasks[0], document, {})
        task_type   = tasks[0].get("type", "UNKNOWN")
        norm_result = _normalize_result({**raw_result, "task_type": task_type})
        norm_plan   = _normalize_plan(plan, tasks)

        final = {
            "final_output":         norm_result["result"],
            "low_confidence_tasks": [],
            "total_tasks":          1,
        }
        record = _build_execution_record(
            execution_id, intent, "completed",
            norm_plan, [norm_result], final, timestamp
        )
        _record_execution(record)
        return record

    # -- DAG EXECUTION -----------------------------------
    print("\n==================== DAG EXECUTION ====================")

    completed_ids = set()
    task_results  = {}
    all_results   = []

    while len(completed_ids) < len(tasks):
        ready_tasks = get_ready_tasks(tasks, completed_ids)

        if not ready_tasks:
            return {
                "status":       "error",
                "message":      "Deadlock detected in task dependencies",
                "execution_id": execution_id,
                "timestamp":    timestamp,
            }

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(execute_task, task, document, task_results): task
                for task in ready_tasks
            }
            for future, task in futures.items():
                output = future.result()
                output.setdefault("task_type", task.get("type", "UNKNOWN"))

                validation          = validator.validate(output)
                output["validation"] = validation

                if validation["verdict"] == "retry":
                    print(f"   [RETRY] {output.get('task_id')}")
                    retry_output               = worker.execute(task, document, task_results)
                    retry_output["task_type"]  = task.get("type", "UNKNOWN")
                    retry_output["validation"] = validator.validate(retry_output)
                    output = retry_output

                task_id = output["task_id"]
                completed_ids.add(task_id)
                task_results[task_id] = output["result"]
                all_results.append(output)

    # ── CRITICAL TASK RECOVERY ─────────────────────────────
    retry_needed = [r for r in all_results if r.get("validation", {}).get("verdict") == "retry"]

    if retry_needed:
        print(f"\n⚠️  {len(retry_needed)} tasks need recovery...")
        for item in retry_needed:
            task_id       = item["task_id"]
            original_task = next((t for t in tasks if t["id"] == task_id), None)
            if not original_task:
                continue

            retry_output               = worker.execute(original_task, document, task_results)
            retry_output["task_type"]  = original_task.get("type", "UNKNOWN")
            retry_output["validation"] = validator.validate(retry_output)

            for i, r in enumerate(all_results):
                if r["task_id"] == task_id:
                    all_results[i] = retry_output
                    break
            task_results[task_id] = retry_output["result"]

    # -- ASSEMBLER ---------------------------------------
    print("\n==================== ASSEMBLER ====================")
    final = assembler.assemble(plan, all_results)

    norm_results = [_normalize_result(r) for r in all_results]
    norm_plan    = _normalize_plan(plan, tasks)

    record = _build_execution_record(
        execution_id, intent, "completed",
        norm_plan, norm_results, final, timestamp
    )
    _record_execution(record)
    return record


# ──────────────────────────────────────────────────────────
# FLASK APP
# ──────────────────────────────────────────────────────────
def create_flask_app():
    from flask import Flask, request, jsonify, send_from_directory

    # ── Resolve absolute paths so Flask finds files regardless
    #    of the working directory you launch from ─────────────
    BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_DIR  = os.path.join(BASE_DIR, "templates")
    STATIC_DIR    = os.path.join(BASE_DIR, "static")

    app = Flask(
        __name__,
        static_folder=STATIC_DIR,
        template_folder=TEMPLATE_DIR,
    )

    # ── / → index.html ────────────────────────────────────
    @app.route("/")
    def index():
        return send_from_directory(TEMPLATE_DIR, "index.html")

    # ── /static/<file> ────────────────────────────────────
    # Flask serves static/ automatically when static_folder is set,
    # but an explicit route avoids any path ambiguity.
    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    # ── /run ──────────────────────────────────────────────
    @app.route("/run", methods=["POST"])
    def api_run():
        body     = request.get_json(silent=True) or {}
        intent   = (body.get("intent")   or "").strip()
        document = (body.get("document") or "").strip()

        if not intent:
            return jsonify({
                "status":  "error",
                "message": "Field 'intent' is required and must be non-empty.",
            }), 400

        try:
            result = run_pipeline(intent, document)
            return jsonify(result), 200

        except Exception as exc:
            print(f"[/run ERROR] {exc}", file=sys.stderr)
            try:
                manager.unload_all()
            except Exception:
                pass
            return jsonify({
                "status":  "error",
                "message": str(exc),
            }), 500

    # ── /history ──────────────────────────────────────────
    @app.route("/history", methods=["GET"])
    def api_history():
        # Newest first
        return jsonify(list(reversed(_execution_history))), 200

    # ── /health ───────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def api_health():
        return jsonify({
            "status":     "ok",
            "executions": len(_execution_history),
        }), 200

    @app.route("/agent/lab", methods=["POST"])
    def api_lab_agent():
        body       = request.get_json(silent=True) or {}
        pdf_path   = (body.get("pdf_path")    or "").strip()
        output_path = (body.get("output_path") or "").strip() or None

        if not pdf_path:
            return jsonify({"status": "error", "message": "pdf_path required"}), 400

        try:
            result = run_lab_agent(pdf_path, output_path)
            return jsonify(result), 200
        except Exception as e:
            print(f"[/agent/lab ERROR] {e}", file=sys.stderr)
            return jsonify({"status": "error", "message": str(e)}), 500


    @app.route("/agent/analysis", methods=["POST"])
    def api_analysis_agent():
        body        = request.get_json(silent=True) or {}
        excel_path  = (body.get("excel_path")  or "").strip()
        output_path = (body.get("output_path") or "").strip() or None

        if not excel_path:
            return jsonify({"status": "error", "message": "excel_path required"}), 400

        try:
            result = run_analysis_agent(excel_path, output_path)
            return jsonify(result), 200
        except Exception as e:
            print(f"[/agent/analysis ERROR] {e}", file=sys.stderr)
            return jsonify({"status": "error", "message": str(e)}), 500

    return app

# ──────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ORCHESTRATOR_V1 Flask Server")
    parser.add_argument("--host",  default="0.0.0.0")
    parser.add_argument("--port",  default=5000, type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"\n=== ORCHESTRATOR_V1 - SERVER MODE ===")
    print(f"    http://127.0.0.1:{args.port}/")
    print(f"    Base dir  : {os.path.dirname(os.path.abspath(__file__))}")
    print(f"    Templates : templates/index.html")
    print(f"    Static    : static/styles.css, static/script.js\n")

    flask_app = create_flask_app()
    flask_app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=False,   # must be False — llama.cpp handles break on fork
    )

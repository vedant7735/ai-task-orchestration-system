from flask import Flask, request, jsonify, send_from_directory
from planner import Planner
from worker import Worker
from assembler import Assembler
from checker import Checker

app = Flask(__name__)


def run_pipeline(intent: str, document: str):
    planner = Planner()
    worker = Worker()
    assembler = Assembler()
    checker = Checker()

    logs = []

    # 1. Plan
    plan = planner.create_plan(intent)

    results = {}

    # 2. Execute tasks
    for task in plan.get("tasks", []):
        relevant_results = {
            k: v for k, v in results.items()
            if k in task.get("depends_on", [])
        }

        retries = 0
        max_retries = 2

        while True:
            output = worker.execute(
                task,
                document,
                previous_results=relevant_results
            )

            evaluation = checker.evaluate(output)

            # attach verdict (UI needs this)
            output["verdict"] = evaluation["verdict"]

            if evaluation["verdict"] == "accept":
                results[task["id"]] = output
                break

            retries += 1

            if retries > max_retries:
                results[task["id"]] = output
                break

    # 3. Assemble
    final = assembler.assemble(plan, list(results.values()))

    return {
        "plan": plan,
        "results": results,
        "final": final
    }


# 🔹 Serve frontend
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/frontend/styles.css")
def styles():
    return send_from_directory("./frontend", "styles.css")

@app.route("/frontend/script.js")
def script():
    return send_from_directory("./frontend", "script.js")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)


# 🔹 API
@app.route("/run", methods=["POST"])
def run():
    data = request.json
    intent = data.get("intent", "")
    document = data.get("document", "")

    if not intent:
        return jsonify({"error": "Intent is required"}), 400

    output = run_pipeline(intent, document)
    return jsonify(output)


if __name__ == "__main__":
    app.run(debug=True)
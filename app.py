import json
import os
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

from planner.planner import Planner
from orchestrator import Orchestrator

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# In-memory storage for uploaded document text
uploaded_text = {"content": ""}

planner = Planner()
orchestrator = Orchestrator()


@app.route("/")
def serve_index():
    """Serve the main dashboard."""
    return send_from_directory(".", "index.html")


@app.route("/plan", methods=["POST"])
def create_plan():
    """
    POST /plan
    Body: { "intent": "Summarize the document" }
    Returns: { "plan": { ... } }
    """
    data = request.get_json(force=True)
    intent = data.get("intent", "").strip()

    if not intent:
        return jsonify({"error": "Intent is required"}), 400

    num_sources = 1 if uploaded_text["content"] else 0
    plan = planner.create_plan(intent, num_sources)

    return jsonify({"plan": plan})


@app.route("/upload", methods=["POST"])
def upload_files():
    """
    POST /upload
    Body: multipart/form-data with file(s), OR JSON with { "text": "..." } for pasted text
    Returns: { "sources": [ { name, type, size, status } ] }
    """
    sources = []

    # Handle JSON body (pasted text or URL)
    if request.is_json:
        data = request.get_json(force=True)
        text = data.get("text", "")
        name = data.get("name", "Pasted Text")
        source_type = data.get("type", "paste")

        if text:
            uploaded_text["content"] = text
            sources.append({
                "name": name,
                "type": source_type,
                "size": len(text),
                "status": "loaded",
            })
        return jsonify({"sources": sources})

    # Handle file uploads
    files = request.files.getlist("files")
    combined_text = []

    for f in files:
        try:
            content = f.read().decode("utf-8", errors="ignore")
            combined_text.append(content)
            sources.append({
                "name": f.filename,
                "type": f.filename.rsplit(".", 1)[-1] if "." in f.filename else "txt",
                "size": len(content),
                "status": "loaded",
            })
        except Exception as e:
            sources.append({
                "name": f.filename,
                "type": "unknown",
                "size": 0,
                "status": "error",
                "error": str(e),
            })

    if combined_text:
        uploaded_text["content"] = "\n\n---\n\n".join(combined_text)

    return jsonify({"sources": sources})


@app.route("/run", methods=["POST"])
def run_orchestration():
    """
    POST /run
    Body: { "plan": { ... } }
    Returns: Server-Sent Events stream of worker updates + final result
    """
    data = request.get_json(force=True)
    plan = data.get("plan", {})

    if not plan.get("tasks"):
        return jsonify({"error": "No tasks in plan"}), 400

    document_text = uploaded_text.get("content", "")

    if not document_text:
        document_text = (
            "This is sample content for demonstration purposes. "
            "The AI Task Orchestration System separates planning from execution. "
            "Workers process tasks independently with confidence scoring. "
            "The assembler combines results and surfaces uncertainty explicitly. "
            "Failures are isolated and visible. Retries are bounded. "
            "Source-of-Truth data is preferred when available. "
            "Model knowledge is used as a fallback for reasoning tasks."
        )

    def generate():
        for update in orchestrator.run(plan, document_text):
            yield f"data: {json.dumps(update)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    print("\n  AI Task Orchestration System")
    print("  ============================")
    print("  Server running at: http://localhost:5000")
    print("  Press Ctrl+C to stop\n")
    app.run(debug=True, port=5000)

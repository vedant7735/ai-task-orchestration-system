"""
agent.py — Tool-using agent for demo scenarios

Demo 1: PDF lab manual -> Word lab file
Demo 2: Excel data    -> PDF analysis report
"""

import os
import sys
from datetime import datetime

from tools import (
    read_pdf, extract_experiments,
    read_excel, excel_to_text,
    write_lab_word, write_analysis_pdf
)
from worker import Worker
from models import manager

worker = Worker()


# ──────────────────────────────────────────────────────────
# DEMO 1 - PDF -> Word Lab File
# ──────────────────────────────────────────────────────────

def run_lab_agent(pdf_path: str, output_path: str = None) -> dict:
    """
    Read a lab PDF, process each experiment with a worker,
    write a structured Word document.
    """
    if not output_path:
        output_path = os.path.join(
            os.path.dirname(pdf_path),
            f"lab_file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        )

    print(f"\n{'='*50}")
    print(f"LAB AGENT - {os.path.basename(pdf_path)}")
    print(f"{'='*50}")

    # ── Step 1: Read PDF ──────────────────────────────────
    print("\n[AGENT] Step 1: Reading PDF...")
    pdf_text    = read_pdf(pdf_path)
    experiments = extract_experiments(pdf_text)

    print(f"[AGENT] Found {len(experiments)} experiments")

    # ── Step 2: Process each experiment with a worker ─────
    print("\n[AGENT] Step 2: Processing experiments...")
    processed = []

    for exp in experiments:
        print(f"\n[AGENT] Processing Experiment {exp['number']}...")

        task = {
            "id":         f"exp_{exp['number']}",
            "type":       "ANALYZE",
            "target":     _build_lab_prompt(exp),
            "depends_on": []
        }

        result = worker.execute(task, "", {})
        parsed = _parse_lab_output(result["result"])

        processed.append({
            "number":     exp["number"],
            "title":      exp["title"],
            "aim":        parsed.get("aim",        exp["title"]),
            "theory":     parsed.get("theory",     ""),
            "code":       parsed.get("code",       ""),
            "output":     parsed.get("output",     ""),
            "conclusion": parsed.get("conclusion", ""),
        })

        print(f"[AGENT] Experiment {exp['number']} done - conf={result.get('confidence', 0):.2f}")

    manager.unload_all()

    # ── Step 3: Write Word document ───────────────────────
    print(f"\n[AGENT] Step 3: Writing Word document...")
    write_lab_word(output_path, processed)

    print(f"\n[AGENT] [DONE] Lab file saved: {output_path}")

    return {
        "status":       "completed",
        "output_path":  output_path,
        "experiments":  len(processed),
        "mode":         "lab_agent"
    }


def _build_lab_prompt(exp: dict) -> str:
    return f"""
You are processing a lab experiment for a student lab file.

Here is the raw experiment content:
---
{exp['raw_text'][:2000]}
---

Extract and structure the following sections.
Use EXACTLY these headers:

AIM:
Write the aim of the experiment in 1-2 sentences.

THEORY:
Write a concise theory explanation (3-5 sentences).

CODE:
Extract or write the complete code for this experiment.

OUTPUT:
Write what the expected output of the code would be.

CONCLUSION:
Write a 2-3 sentence conclusion.

CONFIDENCE: 0.X
"""


def _parse_lab_output(raw: str) -> dict:
    """
    Parse the structured worker output into sections.
    Looks for AIM:, THEORY:, CODE:, OUTPUT:, CONCLUSION: headers.
    """
    import re

    sections = {}
    pattern  = re.compile(
        r'^(AIM|THEORY|CODE|OUTPUT|CONCLUSION)\s*:\s*$',
        re.IGNORECASE | re.MULTILINE
    )

    # Also try inline: "AIM: text"
    inline_pattern = re.compile(
        r'^(AIM|THEORY|CODE|OUTPUT|CONCLUSION)\s*:\s*(.+)',
        re.IGNORECASE | re.MULTILINE
    )

    matches = list(pattern.finditer(raw))

    if matches:
        for i, match in enumerate(matches):
            key   = match.group(1).lower()
            start = match.end()
            end   = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            sections[key] = raw[start:end].strip()
    else:
        # Try inline format
        for match in inline_pattern.finditer(raw):
            key = match.group(1).lower()
            if key not in sections:
                sections[key] = match.group(2).strip()

    # Strip CONFIDENCE line from any section
    for key in sections:
        lines = sections[key].split("\n")
        sections[key] = "\n".join(
            l for l in lines
            if not l.strip().upper().startswith("CONFIDENCE:")
        ).strip()

    return sections


# DEMO 2 - Excel -> PDF Analysis Report
# ----------------------------------------------------------

def run_analysis_agent(excel_path: str, output_path: str = None) -> dict:
    """
    Read an Excel file, analyze it with workers,
    write a structured PDF report.
    """
    if not output_path:
        output_path = os.path.join(
            os.path.dirname(excel_path),
            f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )

    print(f"\n{'='*50}")
    print(f"ANALYSIS AGENT - {os.path.basename(excel_path)}")
    print(f"{'='*50}")

    # ── Step 1: Read Excel ────────────────────────────────
    print("\n[AGENT] Step 1: Reading Excel...")
    excel_data  = read_excel(excel_path)
    excel_text  = excel_to_text(excel_data)

    print(f"[AGENT] {excel_data['total_sheets']} sheets, {excel_data['total_rows']} rows")

    # ── Step 2: Run analysis workers ─────────────────────
    print("\n[AGENT] Step 2: Running analysis tasks...")

    tasks = [
        {
            "id":     "summary",
            "type":   "ANALYZE",
            "label":  "Executive Summary",
            "target": f"Write an executive summary of this dataset:\n\n{excel_text}"
        },
        {
            "id":     "trends",
            "type":   "ANALYZE",
            "label":  "Trend Analysis",
            "target": f"Identify key trends and patterns in this dataset:\n\n{excel_text}"
        },
        {
            "id":     "insights",
            "type":   "ANALYZE",
            "label":  "Key Insights & Recommendations",
            "target": f"List key insights and actionable recommendations from this data:\n\n{excel_text}"
        },
    ]

    sections = []
    summary  = ""

    for task_def in tasks:
        print(f"\n[AGENT] Running: {task_def['label']}...")

        task = {
            "id":         task_def["id"],
            "type":       task_def["type"],
            "target":     task_def["target"],
            "depends_on": []
        }

        result = worker.execute(task, "", {})
        output = result.get("result", "").strip()
        conf   = result.get("confidence", 0.0)

        print(f"[AGENT] {task_def['label']} done — conf={conf:.2f}")

        if task_def["id"] == "summary":
            summary = output
        else:
            sections.append({
                "heading": task_def["label"],
                "content": output
            })

    manager.unload_all()

    # ── Step 3: Write PDF ─────────────────────────────────
    print(f"\n[AGENT] Step 3: Writing PDF report...")

    analysis = {
        "title":     f"Data Analysis Report - {os.path.basename(excel_path)}",
        "summary":   summary,
        "sections":  sections,
        "generated": datetime.now().strftime("%d %B %Y %H:%M"),
    }

    write_analysis_pdf(output_path, analysis)

    print(f"\n[AGENT] [DONE] Report saved: {output_path}")

    return {
        "status":      "completed",
        "output_path": output_path,
        "sheets":      excel_data["total_sheets"],
        "rows":        excel_data["total_rows"],
        "mode":        "analysis_agent"
    }


# ──────────────────────────────────────────────────────────
# CLI TEST
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",   choices=["lab", "analysis"], required=True)
    parser.add_argument("--input",  required=True, help="Path to PDF or Excel file")
    parser.add_argument("--output", help="Output file path (optional)")
    args = parser.parse_args()

    if args.mode == "lab":
        run_lab_agent(args.input, args.output)
    elif args.mode == "analysis":
        run_analysis_agent(args.input, args.output)
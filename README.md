# AI Task Orchestration System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: In Development](https://img.shields.io/badge/status-in%20development-orange.svg)]()

> A reliability-first AI orchestration framework built in layers — correct flow first, state second, reliability third, optimization last.

---

## Philosophy

Build systems in layers. Avoid introducing multiple architectural variables at once.

```
Control flow first
State second
Reliability third
Optimization last
```

---

## Version Roadmap

```
v1   → Minimal pipeline
v1.1 → Context propagation
v2   → Checker + retry loop
v3   → DAG execution (parallelism)
v4   → Advanced state management
```

---

## Current Version — v1 (Complete)

### Architecture

```
Planner → Worker → Assembler
```

### Objective

A clean, deterministic pipeline with no hidden state, no shared memory, and no implicit dependencies. Every component has one job. Data flow is explicit and visible.

### How It Works

The **Planner** receives a natural language intent and decomposes it into 1–3 structured tasks. Each task has a type, description, and explicit rationale.

The **Worker** executes each task independently against the provided document. It returns a result and a confidence score. Workers are stateless — they share nothing.

The **Assembler** combines worker outputs into a final response. It restructures output without correcting logic. If information is missing, it surfaces that gap explicitly rather than filling it with fabricated content.

### Design Constraints (v1)

These are intentional — not limitations, but boundaries that keep v1 clean:

- No DAG or task dependencies
- No parallelism
- No shared context window
- No retries
- No checker
- Stateless workers only

### What v1 Proves

- Pipeline executes in correct order
- Components are cleanly separated
- Worker outputs are independent and visible
- Assembler restructures without hallucinating
- System does not fabricate missing information

### Problems Identified in v1

**1. No task dependency**
Tasks execute independently. A worker executing `t2` has no awareness of what `t1` produced. This is by design in v1, and the problem to be solved in v1.1.

**2. Worker drift**
With no alignment mechanism, workers can misinterpret vague instructions. Identified, deferred to v2.

**3. Assembler acting as implicit filter**
The assembler currently removes incorrect outputs, which introduces unintended responsibility. The assembler should only restructure — not correct logic. Identified, deferred to v2.

### Key Insight

v1 behaves as:
```
Independent task execution + post-processing
```
Not yet:
```
Sequential reasoning pipeline
```
This distinction drives every subsequent version.

---

## Tech Stack

- **Python 3.11+**
- **Flask** — API layer
- **Groq API** — LLM inference
  - Planner + Assembler: `openai/gpt-oss-120b`
  - Workers: `mistral-saba-24b`

---

## Getting Started

### Prerequisites

- Python 3.11+
- Groq API key — [console.groq.com](https://console.groq.com)

### Installation

```bash
git clone https://github.com/vedant7735/ai-task-orchestration-system.git
cd ai-task-orchestration-system

pip install -r requirements.txt

cp .env.example .env
# add your Groq API key to .env
```

### Running

```bash
py src/app.py
# open http://localhost:5000
```

---

## Project Structure

```
ai-task-orchestration-system/
├── src/
│   ├── planner/
│   │   └── planner.py       # intent decomposition
│   ├── worker/
│   │   └── worker.py        # stateless task execution
│   ├── assembler/
│   │   └── assembler.py     # output combination
│   ├── orchestrator.py      # pipeline wiring
│   └── app.py               # Flask API
├── index.html               # dashboard UI
├── requirements.txt
├── .env.example
└── README.md
```

---

## Related Work

This project was developed independently alongside recent academic work on agentic hyperautomation architectures (Tomasino et al., 2025). Key difference: this project prioritizes **reliability and failure visibility** over capability, with uncertainty treated as a first-class system signal rather than an afterthought.

---

## Contact

**Maintainer:** Vedant | [@vedant7735](https://github.com/vedant7735)
**Repository:** [github.com/vedant7735/ai-task-orchestration-system](https://github.com/vedant7735/ai-task-orchestration-system)

---

*Built incrementally. One variable per version.*
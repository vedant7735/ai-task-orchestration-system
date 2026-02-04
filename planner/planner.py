import json
import os

# INPUTS (hardcoded for v1)

user_instruction = "Summarize the three documents and provide a combined overview."

documents = {
    "doc1": "Text of document one goes here.",
    "doc2": "Text of document two goes here.",
    "doc3": "Text of document three goes here."
}

# PLANNER SYSTEM PROMPT

PLANNER_PROMPT = """
You are an AI Planner Agent.

Your job is NOT to solve the task.
Your job is to understand the user's intent and decompose the task into
clear, structured steps that can be executed by worker agents.

Rules:
- Do NOT perform the task yourself.
- Do NOT summarize the documents.
- ONLY output valid JSON.
- The output represents instructions for worker agents.

Output JSON schema:
{
  "intent": string,
  "tasks": [
    {
      "id": number,
      "type": string,
      "input": string or list
    }
  ],
  "execution_policy": {
    "parallelizable_tasks": list of task ids,
    "requires_assembly": boolean
  }
}
"""

# MOCK LLM CALL

def call_planner_llm(prompt, instruction, docs):
    """
    This is a placeholder for the LLM call.
    We simulate what a planner LLM would return.
    """

    planner_output = {
        "intent": "Summarize multiple documents and produce a combined overview",
        "tasks": [
            {"id": 1, "type": "summarize", "input": "doc1"},
            {"id": 2, "type": "summarize", "input": "doc2"},
            {"id": 3, "type": "summarize", "input": "doc3"},
            {"id": 4, "type": "aggregate", "input": [1, 2, 3]}
        ],
        "execution_policy": {
            "parallelizable_tasks": [1, 2, 3],
            "requires_assembly": True
        }
    }

    return planner_output

# MAIN EXECUTION

if __name__ == "__main__":
    print("Running Planner Agent...\n")

    planner_result = call_planner_llm(
        PLANNER_PROMPT,
        user_instruction,
        documents
    )

    print("Planner Output (Worker Instructions):\n")
    print(json.dumps(planner_result, indent=2))

    print("\nNOTE:")
    print("This output represents the instruction set that will be sent to worker agents.")
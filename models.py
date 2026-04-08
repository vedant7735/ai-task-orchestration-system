# models.py

import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env
load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODELS = {
    "planner": "openai/gpt-oss-120b",
    "worker": "llama-3.1-8b-instant",
    "assembler": "openai/gpt-oss-120b",
}
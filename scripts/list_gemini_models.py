"""List available Gemini models via the OpenAI-compatible endpoint."""
import os
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent / "analysis" / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not set in analysis/.env")

client = OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

models = client.models.list()
for m in sorted(models, key=lambda m: m.id):
    print(m.id)

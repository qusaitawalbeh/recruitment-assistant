import os
from dotenv import load_dotenv

load_dotenv()

print("Python works")
print("Model from .env:", os.getenv("OLLAMA_MODEL"))


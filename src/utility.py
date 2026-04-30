from pathlib import Path

import os
from dotenv import load_dotenv
from langfuse import Langfuse

load_dotenv()  # Load .env first

langfuse = Langfuse(
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL"),
)

if langfuse.auth_check():
    print("✅ Langfuse Authenticated Successfully!")
else:
    print("❌ Auth check failed.")

from pathlib import Path
import os
from dotenv import load_dotenv
from google import genai

# Locate the main project folder
project_root = Path(__file__).resolve().parent.parent

# Load the API key
load_dotenv(project_root / ".env")
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: API key not found. Check your .env file.")
else:
    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents="In one sentence, explain what a customer support AI assistant does."
        )

        print("\nGemini is working!")
        print(response.text)

    except Exception as error:
        print("\nGemini test failed.")
        print("Error:", error)

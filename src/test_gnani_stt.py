import os
from pathlib import Path
import requests
from dotenv import load_dotenv
# Load API credentials from the project's .env file
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")
api_key = os.getenv("GNANI_API_KEY")
audio_file = project_root / "data" / "audio" / "input" / "Recording.m4a"
if not api_key:
    raise SystemExit("GNANI_API_KEY is missing from .env")
if not audio_file.exists():
    raise SystemExit(f"Audio file not found: {audio_file}")

url = "https://api.vachana.ai/stt/v3"

headers = {
    "X-API-Key-ID": api_key
}

with audio_file.open("rb") as audio:
    response = requests.post(
        url,
        headers=headers,
        files={
            "audio_file": (
                audio_file.name,
                audio,
                "audio/mp4"
            )
        },
        data={"language_code": "en-IN"},
        timeout=60,
    )

if response.ok:
    result = response.json()
    print("\nGnani STT test successful!")
    print("Response:", result)
else:
    print("Gnani request failed.")
    print("HTTP status:", response.status_code)
    print("Response:", response.text[:1000])

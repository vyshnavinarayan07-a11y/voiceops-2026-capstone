
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Find the project folder and load the API key
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

api_key = os.getenv("GNANI_API_KEY")

if not api_key:
    raise SystemExit("GNANI_API_KEY is missing from .env")

# Text that Gnani will speak
text = (
    "Hello! Welcome to ZentroMart support. "
    "Electronics can generally be returned within "
    "seven days of delivery, subject to the return policy."
)

url = "https://api.vachana.ai/api/v1/tts/inference"

headers = {
    "X-API-Key-ID": api_key,
    "Content-Type": "application/json",
}

payload = {
    "text": text,
    "voice": "Nalini",
    "model": "timbre-v2.5",
    "language": "en-IN",
    "speed": 1.0,
    "audio_config": {
        "sample_rate": 48000,
        "num_channels": 1,
        "sample_width": 2,
        "encoding": "linear_pcm",
        "container": "wav",
    },
}

response = requests.post(
    url,
    headers=headers,
    json=payload,
    timeout=90,
)

if response.ok:
    output_folder = project_root / "data" / "audio" / "output"
    output_folder.mkdir(parents=True, exist_ok=True)

    output_file = output_folder / "gnani_tts_test.wav"
    output_file.write_bytes(response.content)

    print("Gnani TTS test successful!")
    print(f"Audio saved to: {output_file}")
    print("Play the WAV file to hear the generated speech.")
else:
    print("Gnani TTS request failed.")
    print("HTTP status:", response.status_code)
    print("Response:", response.text[:1000])

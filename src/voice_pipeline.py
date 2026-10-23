
import os
import sys
import asyncio
import io
import wave
from pathlib import Path

from dotenv import load_dotenv
from gnani.stt import GnaniSTTStreamClient
from gnani.tts import GnaniTTSStreamClient, AudioConfig

# Project paths and environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

from answer_question import answer_question

API_KEY = os.getenv("GNANI_API_KEY")

INPUT_AUDIO = (
    PROJECT_ROOT / "data" / "audio" / "input"
    / "Recording_16k_mono.wav"
)
OUTPUT_DIR = PROJECT_ROOT / "data" / "audio" / "output"
OUTPUT_AUDIO = OUTPUT_DIR / "voice_pipeline_reply.wav"


async def transcribe_audio(audio_path):
    """Transcribe 16 kHz mono PCM audio using Gnani WebSocket STT."""

    # Read the WAV and extract raw PCM frames (without the WAV header).
    with wave.open(str(audio_path), "rb") as wav_file:
        if wav_file.getframerate() != 16000:
            raise ValueError("Input audio must be 16000 Hz.")
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError("Input audio must be mono, 16-bit PCM.")

        pcm_audio = wav_file.readframes(wav_file.getnframes())

    if not pcm_audio:
        raise ValueError("The input audio contains no audio frames.")

    client = GnaniSTTStreamClient(
        api_key=API_KEY,
        language_code="en-IN",
        sample_rate=16000,
    )

    print("Connecting to Gnani STT WebSocket...")
    await client.connect()

    print("Streaming audio to Gnani...")
    events = await client.stream_audio(
        io.BytesIO(pcm_audio),
        chunk_size=1024,
        realtime_pace=True,
    )

    # The SDK returns transcript events.
    transcript_parts = []
    for event in events:
        text = getattr(event, "text", "")
        if text and text.strip():
            transcript_parts.append(text.strip())

    transcript = " ".join(transcript_parts).strip()

    if not transcript:
        raise RuntimeError(
            "Gnani WebSocket STT returned no transcript. "
            "Check the SDK output and API access."
        )

    return transcript


def generate_speech(text):
    """Generate speech using Gnani's streamed TTS SDK."""

    client = GnaniTTSStreamClient(api_key=API_KEY)

    audio_config = AudioConfig(
        sample_rate=48000,
        encoding="linear_pcm",
        num_channels=1,
        sample_width=2,
        container="wav",
    )

    print("Requesting streamed speech from Gnani...")
    chunks = client.synthesize_stream(
        text,
        voice="Nalini",
        model="timbre-v2.5",
        language="en-IN",
        speed=1.0,
        audio_config=audio_config,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # SDK yields raw PCM chunks, so add a WAV header when saving.
    total_bytes = 0
    with wave.open(str(OUTPUT_AUDIO), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)

        for chunk in chunks:
            if chunk:
                wav_file.writeframesraw(chunk)
                total_bytes += len(chunk)

    if total_bytes == 0:
        raise RuntimeError("Gnani TTS returned no audio data.")

    return OUTPUT_AUDIO


async def main():
    if not API_KEY:
        raise RuntimeError(
            "GNANI_API_KEY is missing from your .env file."
        )

    if not INPUT_AUDIO.exists():
        raise FileNotFoundError(
            f"Converted audio file not found: {INPUT_AUDIO}"
        )

    print("\n1. Transcribing existing audio with Gnani WebSocket STT...")
    question = await transcribe_audio(INPUT_AUDIO)
    print("Recognized question:", question)

    print("\n2. Getting an answer from Gemini + RAG...")
    answer = answer_question(question)

    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError(
            "Gemini + RAG returned an empty or invalid answer."
        )

    print("\nAssistant answer:")
    print(answer)

    print("\n3. Generating speech with Gnani streamed TTS...")
    audio_path = generate_speech(answer)

    print("\nSUCCESS! Full voice pipeline finished.")
    print("Input audio:", INPUT_AUDIO)
    print("Recognized question:", question)
    print("Spoken answer saved to:", audio_path)


if __name__ == "__main__":
    asyncio.run(main())


import os
import csv
import json
import sys
import io
import asyncio
import subprocess
import tempfile
import wave

from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from gnani.stt import GnaniSTTStreamClient
from gnani.tts import GnaniTTSStreamClient, AudioConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

load_dotenv(PROJECT_ROOT / ".env")

from answer_question import answer_question
from search_knowledge import search_knowledge

GNANI_API_KEY = os.getenv("GNANI_API_KEY")

INPUT_DIR = PROJECT_ROOT / "data" / "audio" / "input"
OUTPUT_DIR = PROJECT_ROOT / "data" / "audio" / "output"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}


async def transcribe_audio(audio_path):
    """Convert input to PCM WAV and transcribe using Gnani WebSocket STT."""

    # FFmpeg normalizes different audio formats for the STT SDK.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        temp_path = Path(temp.name)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(audio_path),
                "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le",
                str(temp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # A WAV header must not be sent as part of the raw PCM stream.
        with wave.open(str(temp_path), "rb") as wav_file:
            if (
                wav_file.getframerate() != 16000
                or wav_file.getnchannels() != 1
                or wav_file.getsampwidth() != 2
            ):
                raise ValueError("FFmpeg did not produce 16 kHz mono 16-bit PCM.")

            pcm_audio = wav_file.readframes(wav_file.getnframes())

        if not pcm_audio:
            raise RuntimeError("The input audio contains no audio frames.")

    except subprocess.CalledProcessError as error:
        details = error.stderr or str(error)
        raise RuntimeError(f"FFmpeg could not convert {audio_path.name}: {details}") from error
    finally:
        temp_path.unlink(missing_ok=True)

    client = GnaniSTTStreamClient(
        api_key=GNANI_API_KEY,
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

    transcript_parts = []
    for event in events:
        text = getattr(event, "text", "")
        if text and text.strip():
            transcript_parts.append(text.strip())

    transcript = " ".join(transcript_parts).strip()

    if not transcript:
        raise RuntimeError("Gnani WebSocket STT returned an empty transcript.")

    return transcript


def generate_speech(text, output_path):
    """Generate and save speech from Gnani's streamed TTS response."""

    client = GnaniTTSStreamClient(api_key=GNANI_API_KEY)

    audio_config = AudioConfig(
        sample_rate=48000,
        encoding="linear_pcm",
        num_channels=1,
        sample_width=2,
        container="wav",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Generating speech with Gnani streamed TTS...")
    chunks = client.synthesize_stream(
        text,
        voice="Nalini",
        model="timbre-v2.5",
        language="en-IN",
        speed=1.0,
        audio_config=audio_config,
    )

    total_bytes = 0

    # The SDK yields raw PCM chunks, so write a WAV header around them.
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)

        for chunk in chunks:
            if chunk:
                wav_file.writeframesraw(chunk)
                total_bytes += len(chunk)

    if total_bytes == 0:
        raise RuntimeError("Gnani streamed TTS returned no audio data.")

    return output_path


async def process_audio(audio_path):
    print(f"\nProcessing: {audio_path.name}")

    record = {
        "audio_file": audio_path.name,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "status": "success",
        "transcript": "",
        "answer": "",
        "reply_audio": "",
        "retrieved_chunks": [],
        "error": "",
    }

    try:
        # 1. Gnani WebSocket speech-to-text
        transcript = await transcribe_audio(audio_path)
        record["transcript"] = transcript
        print("Transcript:", transcript)

        # 2. Retrieve knowledge evidence
        chunks = search_knowledge(transcript)
        record["retrieved_chunks"] = [
            {
                "filename": chunk.get("filename", ""),
                "title": chunk.get("title", ""),
                "text": chunk.get("text", ""),
            }
            for chunk in chunks
        ]

        # 3. Gemini + RAG answer
        answer = answer_question(transcript)

        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Gemini + RAG returned an empty answer.")

        record["answer"] = answer
        print("Answer:", answer)

        # 4. Gnani streamed text-to-speech
        reply_path = OUTPUT_DIR / f"{audio_path.stem}_reply.wav"
        generate_speech(answer, reply_path)

        record["reply_audio"] = str(reply_path.relative_to(PROJECT_ROOT))
        print("Reply audio:", record["reply_audio"])

    except Exception as error:
        record["status"] = "failed"
        record["error"] = str(error)
        print("ERROR:", error)

    return record


async def main():
    if not GNANI_API_KEY:
        raise RuntimeError("GNANI_API_KEY is missing from .env")

    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Input folder not found: {INPUT_DIR}")

    audio_files = sorted(
        path for path in INPUT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO
    )

    if not audio_files:
        print(f"No supported audio files found in {INPUT_DIR}")
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    jsonl_path = RESULTS_DIR / "batch_results.jsonl"
    csv_path = RESULTS_DIR / "batch_results.csv"

    records = []

    print(f"Found {len(audio_files)} audio file(s).")

    for audio_path in audio_files:
        records.append(await process_audio(audio_path))

    # Save detailed results and retrieval evidence.
    with jsonl_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Save a simpler CSV summary.
    fields = [
        "audio_file", "status", "transcript",
        "answer", "reply_audio", "error",
    ]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for record in records:
            writer.writerow({field: record[field] for field in fields})

    succeeded = sum(record["status"] == "success" for record in records)
    failed = len(records) - succeeded

    print("\n========== BATCH SUMMARY ==========")
    print(f"Total files: {len(records)}")
    print(f"Successful: {succeeded}")
    print(f"Failed: {failed}")
    print(f"JSONL evidence: {jsonl_path}")
    print(f"CSV summary: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())

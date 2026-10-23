# VoiceOps 2026 Capstone — Project Guide

## 1. Project overview

This project implements a voice-based customer-support assistant for the
synthetic ZentroMart dataset.

The pipeline combines:
- Gnani speech-to-text (STT)
- Knowledge-base retrieval (RAG)
- Gemini answer generation
- Gnani text-to-speech (TTS)

The project also includes dataset validation, practice-question evaluation,
and batch audio processing.

## 2. Requirements

- Python 3.14.7 was used for the current working setup.
- FFmpeg must be installed and available on PATH for audio conversion in
  the batch runner.
- A Gemini API key is required for answer generation.
- A Gnani API key is required for speech-to-text and text-to-speech.

## 3. Installation

Open PowerShell in the project root.

Create and activate a virtual environment if you do not already have one:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

Install Python dependencies:

    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

If PowerShell blocks environment activation, you can run Python directly
using .\.venv\Scripts\python.exe instead.

Install FFmpeg separately if it is not already installed, and confirm
that the `ffmpeg` command is available in a new terminal.

## 4. API configuration

Create a local `.env` file by copying `.env.example`:

    Copy-Item .env.example .env

Open `.env` and replace the placeholder values with your own valid API keys:

    GEMINI_API_KEY=your_gemini_api_key
    GNANI_API_KEY=your_gnani_api_key

Do not commit or submit `.env`. Never share API keys in screenshots,
reports, or source control.

## 5. Validate the dataset

Run:

    python validate_dataset.py

The dataset validation script should report PASS when the dataset checks
succeed.

## 6. Run the main voice pipeline

The standard voice pipeline expects this input file:

    data/audio/input/Recording_16k_mono.wav

Run:

    python src/voice_pipeline.py

The script transcribes the input audio, generates an answer using Gemini
and the knowledge base, and saves the spoken response to:

    data/audio/output/voice_pipeline_reply.wav

The input WAV must be 16 kHz, mono, 16-bit PCM.

## 7. Run batch audio processing

Place supported audio files in:

    data/audio/input/

Run:

    python src/batch_runner.py

The batch runner processes supported audio files and writes generated
audio and result reports to the project's output and results directories.

## 8. Evaluate practice questions

Run the full practice evaluation:

    python src/evaluate_practice.py

To evaluate a single question by ID, for example PQ0032:

    python src/evaluate_practice.py --id PQ0032

The evaluation produces CSV and JSONL reports in `data/results/`.
Review the reports to understand the checks and outcomes. API or generation
errors should be distinguished from evaluation passes and failures.

## 9. Useful inspection scripts

Inspect dataset information:

    python src/inspect_dataset.py

Test Gemini connectivity:

    python src/test_llm.py

Test Gnani STT:

    python src/test_gnani_stt.py

Test Gnani TTS:

    python src/test_gnani_tts.py

The API test scripts may make live API requests and may incur usage or cost.

## 10. Important project files

- `src/answer_question.py` — answer generation and question handling
- `src/search_knowledge.py` — knowledge-base retrieval
- `src/voice_pipeline.py` — end-to-end voice pipeline
- `src/batch_runner.py` — batch audio processing
- `src/evaluate_practice.py` — practice-question evaluation
- `validate_dataset.py` — dataset validation
- `kb/` — knowledge-base documents
- `data/` — dataset, audio, and result files
- `practice/` — practice questions and conversations
- `tools/` — supporting tool functions
- `requirements.txt` — Python dependencies

## 11. Submission and security checklist

- Keep the original dataset README and supplied data documentation.
- Include the source code, required dataset files, and relevant evaluation
  reports and audio artifacts, subject to the official submission rules.
- Do not include `.env`, `.venv/`, `__pycache__/`, or `.pyc` files.
- Do not include API keys in documentation or screenshots.
- Run dataset validation and evaluation before final packaging.
- Verify the final ZIP contents before submitting.

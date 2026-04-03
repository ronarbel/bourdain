from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import openai


def transcribe_voice(ogg_path: str | Path, api_key: str) -> str:
    """Convert an .ogg voice note to text using OpenAI Whisper API."""
    ogg_path = Path(ogg_path)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = Path(tmp.name)

    try:
        subprocess.run(
            ["ffmpeg", "-i", str(ogg_path), "-y", str(mp3_path)],
            capture_output=True,
            check=True,
        )

        client = openai.OpenAI(api_key=api_key)
        with open(mp3_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return transcript.text
    finally:
        mp3_path.unlink(missing_ok=True)

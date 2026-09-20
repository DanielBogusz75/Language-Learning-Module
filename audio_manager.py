"""Module for downloading, caching, and playing pronunciations using edge-tts."""

import asyncio
from pathlib import Path
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import edge_tts


class PronunciationEngine:
    """Manages downloading, storing, and playing TTS audio files per language."""

    DEFAULT_VOICES = {
        "pl": "pl-PL-MarekNeural",
        "nl": "nl-NL-ColetteNeural",
        "de": "de-DE-KillianNeural",
        "en": "en-US-ChristopherNeural",
        "es": "es-ES-AlvaroNeural",
    }

    def __init__(self, base_audio_dir: str | Path = "audio_cache"):
        self.base_dir = Path(base_audio_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.mixer_ready = False
        try:
            pygame.mixer.init()
            self.mixer_ready = True
        except Exception:
            self.mixer_ready = False

    def _get_file_path(self, text: str, lang_code: str) -> Path:
        lang_folder = self.base_dir / lang_code.lower()
        lang_folder.mkdir(exist_ok=True)

        safe_filename = (
            "".join(c for c in text.lower() if c.isalnum() or c in (" ", "_"))
            .strip()
            .replace(" ", "_")
        )
        return lang_folder / f"{safe_filename}.mp3"

    async def _download_tts(
        self, text: str, output_path: Path, voice: str
    ) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    def get_or_download_audio(
        self, text: str, lang_code: str = "pl", voice: str | None = None
    ) -> Path:
        file_path = self._get_file_path(text, lang_code)

        if not file_path.exists():
            selected_voice = (
                voice
                or self.DEFAULT_VOICES.get(lang_code.lower())
                or "en-US-ChristopherNeural"
            )
            print(
                f"Audio not found locally. Downloading '{text}' ({lang_code})..."
            )
            asyncio.run(self._download_tts(text, file_path, selected_voice))
        else:
            print(f"Loaded '{text}' from local cache.")

        return file_path

    def speak(
        self, text: str, lang_code: str = "pl", voice: str | None = None
    ) -> Path:
        mp3_path = self.get_or_download_audio(
            text, lang_code=lang_code, voice=voice
        )

        if not self.mixer_ready:
            print(f"Audio playback is unavailable in this environment; saved to {mp3_path}")
            return mp3_path

        pygame.mixer.music.load(str(mp3_path))
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        return mp3_path


if __name__ == "__main__":
    engine = PronunciationEngine(base_audio_dir="media/pronunciations")
    engine.speak(text="pić", lang_code="pl")
    engine.speak(text="drinken", lang_code="nl")
    engine.speak(text="dziękuję", lang_code="pl", voice="pl-PL-ZofiaNeural")
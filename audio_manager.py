"""Module for downloading, caching, and playing pronunciations using edge-tts."""

import asyncio
from pathlib import Path
import pygame
import edge_tts


class PronunciationEngine:
    """Manages downloading, storing, and playing TTS audio files per language."""

    # Default neural voices for common target languages
    DEFAULT_VOICES = {
        "pl": "pl-PL-MarekNeural",  # Polish (Male) or "pl-PL-ZofiaNeural" (Female)
        "nl": "nl-NL-ColetteNeural",  # Dutch
        "de": "de-DE-KillianNeural",  # German
        "en": "en-US-ChristopherNeural",  # English
        "es": "es-ES-AlvaroNeural",  # Spanish
    }

    def __init__(self, base_audio_dir: str | Path = "audio_cache"):
        self.base_dir = Path(base_audio_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        pygame.mixer.init()

    def _get_file_path(self, text: str, lang_code: str) -> Path:
        """Generate a safe, subfolder-isolated path for the MP3 file."""
        lang_folder = self.base_dir / lang_code.lower()
        lang_folder.mkdir(exist_ok=True)

        # Sanitize text to create a clean filename
        safe_filename = (
            "".join(c for c in text.lower() if c.isalnum() or c in (" ", "_"))
            .strip()
            .replace(" ", "_")
        )
        return lang_folder / f"{safe_filename}.mp3"

    async def _download_tts(
        self, text: str, output_path: Path, voice: str
    ) -> None:
        """Asynchronously stream TTS audio from Edge API to disk."""
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    def get_or_download_audio(
        self, text: str, lang_code: str = "pl", voice: str | None = None
    ) -> Path:
        """Retrieve local MP3 path, downloading it via TTS if it doesn't exist."""
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
        """Fetch/download the MP3 and play it out loud."""
        mp3_path = self.get_or_download_audio(
            text, lang_code=lang_code, voice=voice
        )

        # Load and play audio via Pygame
        pygame.mixer.music.load(str(mp3_path))
        pygame.mixer.music.play()

        # Wait until playback finishes before continuing
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        return mp3_path


# --- Example Usage ---
if __name__ == "__main__":
    engine = PronunciationEngine(base_audio_dir="media/pronunciations")

    # Speak Polish word (downloads to media/pronunciations/pl/pic.mp3 on first run)
    engine.speak(text="pić", lang_code="pl")

    # Speak Dutch word (downloads to media/pronunciations/nl/drinken.mp3)
    engine.speak(text="drinken", lang_code="nl")

    # Custom female Polish voice option
    engine.speak(text="dziękuję", lang_code="pl", voice="pl-PL-ZofiaNeural")
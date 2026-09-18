"""Polyglot Vocabulary Manager CLI with persistent INI configuration."""

import argparse
import configparser
from pathlib import Path
import sys

from audio_manager import PronunciationEngine
from polyglot_db import UniversalDictionary


class ConfigManager:
    """Manages reading and writing application settings to config.ini."""

    DEFAULT_SETTINGS = {
        "source_lang": "nl",
        "target_lang": "pl",
        "audio_dir": "audio_cache",
        "db_path": "polyglot_learning.db",
    }

    def __init__(self, config_file: str | Path = "config.ini"):
        self.config_file = Path(config_file)
        self.config = configparser.ConfigParser()
        self.load_or_create()

    def load_or_create(self) -> None:
        """Load configuration from disk or create default config.ini if missing."""
        if not self.config_file.exists():
            self.config["DEFAULTS"] = self.DEFAULT_SETTINGS
            self.save()
        else:
            self.config.read(self.config_file)

    def save(self) -> None:
        """Write current configuration back to disk."""
        with open(self.config_file, "w") as f:
            self.config.write(f)

    def get(self, key: str) -> str:
        """Fetch setting value with fallback to global default."""
        return self.config.get(
            "DEFAULTS", key, fallback=self.DEFAULT_SETTINGS.get(key, "")
        )

    def set(self, key: str, value: str) -> None:
        """Update and persist a single configuration value."""
        if "DEFAULTS" not in self.config:
            self.config["DEFAULTS"] = {}
        self.config["DEFAULTS"][key] = value.lower()
        self.save()


class CommandRunner:
    """Encapsulates execution handlers for CLI commands."""

    def __init__(self):
        self.config_mgr = ConfigManager()

        # Initialize core services using values from config.ini
        self.dict_app = UniversalDictionary(
            db_path=self.config_mgr.get("db_path")
        )
        self.audio_engine = PronunciationEngine(
            base_audio_dir=self.config_mgr.get("audio_dir")
        )

    def handle_config(self, args: argparse.Namespace) -> None:
        """Handler for 'config' command to view or set configuration."""
        if args.set:
            key, val = args.set
            self.config_mgr.set(key, val)
            print(f"Setting updated: {key} = {val.lower()}")
        else:
            print("\n--- Current Configuration (config.ini) ---")
            for key, value in self.config_mgr.config["DEFAULTS"].items():
                print(f"• {key}: {value}")

    def handle_speak(self, args: argparse.Namespace) -> None:
        """Handler for 'speak' command, using configured target language as default."""
        lang = args.lang or self.config_mgr.get("target_lang")
        print(f"Pronouncing '{args.word}' in [{lang}]...")
        self.audio_engine.speak(text=args.word, lang_code=lang)

    def handle_list(self, args: argparse.Namespace) -> None:
        """Handler for 'list' command using defaults from config.ini."""
        target = args.target or self.config_mgr.get("target_lang")
        source = args.source or self.config_mgr.get("source_lang")

        words = self.dict_app.get_vocabulary(
            target_lang=target, source_lang=source
        )
        print(f"\n--- Vocabulary ({target.upper()} -> {source.upper()}) ---")
        if not words:
            print("No words found for this language pair.")
            return

        for w in words:
            cats = (
                f" [{', '.join(w['categories'])}]" if w["categories"] else ""
            )
            print(
                f"• {w['lemma']} ({w['part_of_speech']}): {w['translation']}{cats}"
            )

    def handle_add(self, args: argparse.Namespace) -> None:
        """Handler for 'add' command using default target/source settings."""
        target = args.target or self.config_mgr.get("target_lang")
        source = args.source or self.config_mgr.get("source_lang")
        categories = args.categories.split(",") if args.categories else None

        word = self.dict_app.add_word(
            target_lang=target,
            source_lang=source,
            lemma=args.lemma,
            primary_translation=args.translation,
            part_of_speech=args.pos,
            categories=categories,
        )
        print(
            f"Successfully added '{word.lemma}' ({word.primary_translation})!"
        )

        if args.speak:
            self.audio_engine.speak(text=word.lemma, lang_code=target)


def build_parser() -> argparse.ArgumentParser:
    """Constructs the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="llm",
        description="Language Learning Manager; CLI utility for managing multi-language vocabulary & audio pronunciations.",
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Available subcommands"
    )

    # --- Subcommand: config ---
    config_parser = subparsers.add_parser(
        "config", help="View or modify application settings"
    )
    config_parser.add_argument(
        "--set",
        nargs=2,
        metavar=("KEY", "VALUE"),
        help="Set a configuration parameter (e.g. --set target_lang de)",
    )

    # --- Subcommand: speak ---
    speak_parser = subparsers.add_parser(
        "speak", help="Pronounce a word (downloads MP3 if missing)"
    )
    speak_parser.add_argument("word", type=str, help="Word or phrase to speak")
    speak_parser.add_argument(
        "-l",
        "--lang",
        type=str,
        help="Target language code (defaults to config target_lang)",
    )

    # --- Subcommand: list ---
    list_parser = subparsers.add_parser(
        "list", help="List stored vocabulary for a language pair"
    )
    list_parser.add_argument(
        "-t",
        "--target",
        type=str,
        help="Target language (defaults to config target_lang)",
    )
    list_parser.add_argument(
        "-s",
        "--source",
        type=str,
        help="Source language (defaults to config source_lang)",
    )

    # --- Subcommand: add ---
    add_parser = subparsers.add_parser("add", help="Add a new word entry")
    add_parser.add_argument(
        "lemma", type=str, help="Base form of word in target language"
    )
    add_parser.add_argument(
        "translation", type=str, help="Translation in source language"
    )
    add_parser.add_argument(
        "-p", "--pos", type=str, default="werkwoord", help="Part of speech"
    )
    add_parser.add_argument("-t", "--target", type=str, help="Target language")
    add_parser.add_argument("-s", "--source", type=str, help="Source language")
    add_parser.add_argument(
        "-c", "--categories", type=str, help="Comma-separated categories"
    )
    add_parser.add_argument(
        "--speak", action="store_true", help="Pronounce word after adding"
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    runner = CommandRunner()

    handler_name = f"handle_{args.command}"
    if hasattr(runner, handler_name):
        handler = getattr(runner, handler_name)
        handler(args)


if __name__ == "__main__":
    main()
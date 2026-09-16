"""Language Learning Manager CLI.

Integrates relational dictionary management, audio caching, and command-line execution.
"""

import argparse
from pathlib import Path
import sys

# Import components (or include classes directly in your project module)
from audio_manager import PronunciationEngine
from polyglot_db import UniversalDictionary


class CommandRunner:
    """Encapsulates execution handlers for CLI commands to keep expansion clean."""

    def __init__(self, db_path: str = "polyglot_learning.db"):
        self.dict_app = UniversalDictionary(db_path=db_path)
        self.audio_engine = PronunciationEngine(base_audio_dir="audio_cache")

    def handle_speak(self, args: argparse.Namespace) -> None:
        """Handler for 'speak' command."""
        print(f"Pronouncing '{args.word}' in [{args.lang}]...")
        self.audio_engine.speak(text=args.word, lang_code=args.lang)

    def handle_list(self, args: argparse.Namespace) -> None:
        """Handler for 'list' command."""
        words = self.dict_app.get_vocabulary(
            target_lang=args.target, source_lang=args.source
        )
        print(
            f"\n--- Vocabulary ({args.target.upper()} -> {args.source.upper()}) ---"
        )
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
        """Handler for 'add' command."""
        categories = args.categories.split(",") if args.categories else None
        word = self.dict_app.add_word(
            target_lang=args.target,
            source_lang=args.source,
            lemma=args.lemma,
            primary_translation=args.translation,
            part_of_speech=args.pos,
            categories=categories,
        )
        print(
            f"Successfully added '{word.lemma}' ({word.primary_translation})!"
        )

        if args.speak:
            self.audio_engine.speak(text=word.lemma, lang_code=args.target)


def build_parser() -> argparse.ArgumentParser:
    """Constructs the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="polyglot",
        description="CLI utility for managing multi-language vocabulary & audio pronunciations.",
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Available subcommands"
    )

    # --- Subcommand: speak ---
    speak_parser = subparsers.add_parser(
        "speak", help="Pronounce a word (downloads MP3 if not cached)"
    )
    speak_parser.add_argument("word", type=str, help="Word or phrase to speak")
    speak_parser.add_argument(
        "-l",
        "--lang",
        type=str,
        default="pl",
        help="Target language code (default: pl)",
    )

    # --- Subcommand: list ---
    list_parser = subparsers.add_parser(
        "list", help="List stored vocabulary for a language pair"
    )
    list_parser.add_argument(
        "-t",
        "--target",
        type=str,
        default="pl",
        help="Target language (default: pl)",
    )
    list_parser.add_argument(
        "-s",
        "--source",
        type=str,
        default="nl",
        help="Source language (default: nl)",
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
        "-p",
        "--pos",
        type=str,
        default="werkwoord",
        help="Part of speech (e.g. werkwoord, zelfstandig naamwoord)",
    )
    add_parser.add_argument(
        "-t",
        "--target",
        type=str,
        default="pl",
        help="Target language (default: pl)",
    )
    add_parser.add_argument(
        "-s",
        "--source",
        type=str,
        default="nl",
        help="Source language (default: nl)",
    )
    add_parser.add_argument(
        "-c",
        "--categories",
        type=str,
        help="Comma-separated category names (e.g. 'Eten,A1')",
    )
    add_parser.add_argument(
        "--speak",
        action="store_true",
        help="Immediately pronounce word after adding",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    runner = CommandRunner()

    # Dynamic handler dispatching
    handler_name = f"handle_{args.command}"
    if hasattr(runner, handler_name):
        handler = getattr(runner, handler_name)
        handler(args)
    else:
        print(f"Error: Command '{args.command}' has no registered handler.")


if __name__ == "__main__":
    main()
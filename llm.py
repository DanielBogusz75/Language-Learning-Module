# llm.py
"""Language Learning Manager; CLI utility for managing multi-language vocabulary & audio pronunciations."""
import argparse
import sys
import llm_tui

def main():
    parser = argparse.ArgumentParser(
        prog="llm",
        description="Language Learning Manager; CLI utility for managing multi-language vocabulary & audio pronunciations.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
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

    args = parser.parse_args()

    runner = llm_tui.CommandRunner()  # Define runner regardless of command

    if not args.command:
        llm_tui.main()
    else:
        handler_name = f"handle_{args.command}"
        if hasattr(runner, handler_name):
            handler = getattr(runner, handler_name)
            handler(args)

if __name__ == "__main__":
    main()
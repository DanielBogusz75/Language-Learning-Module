from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from functools import partial
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
import questionary
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static, TextArea

from audio_manager import PronunciationEngine
from polyglot_db import UniversalDictionary

console = Console()

class CommandRunner:
    """Command-driven access to the dictionary and pronunciation features."""

    def __init__(
        self,
        db_path: str | Path = "polyglot_learning.db",
        config_path: str | Path = "llm_config.json",
    ):
        self.db_path = Path(db_path)
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.dict_app = UniversalDictionary(db_path=self.db_path)

    def _load_config(self) -> dict[str, object]:
        default = {
            "source_lang": "nl",
            "target_lang": "pl",
            "ui_lang": "en",
            "available_ui_languages": [],
            "translations": {},
        }
        source_path = self.config_path
        if not source_path.exists():
            bundled_config = Path(__file__).with_name("llm_config.json")
            if bundled_config.exists():
                source_path = bundled_config
            else:
                return default.copy()

        try:
            with source_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                merged = default.copy()
                merged.update({k: v for k, v in data.items() if v is not None})
                if isinstance(merged.get("available_ui_languages"), str):
                    try:
                        parsed_languages = json.loads(merged["available_ui_languages"])
                    except json.JSONDecodeError:
                        parsed_languages = []
                    merged["available_ui_languages"] = parsed_languages if isinstance(parsed_languages, list) else []
                if isinstance(merged.get("translations"), str):
                    try:
                        parsed_translations = json.loads(merged["translations"])
                    except json.JSONDecodeError:
                        parsed_translations = {}
                    merged["translations"] = parsed_translations if isinstance(parsed_translations, dict) else {}
                return merged
        except (json.JSONDecodeError, OSError):
            pass

        return default.copy()

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as fh:
            json.dump(self.config, fh, indent=2)

    def _strings(self) -> dict[str, str]:
        language = str(self.config.get("ui_lang", "en")).lower()
        configured = self.config.get("translations", {})
        if not isinstance(configured, dict):
            return {}
        language_strings = configured.get(language, {})
        return {
            str(key): str(value)
            for key, value in language_strings.items()
        } if isinstance(language_strings, dict) else {}

    def available_ui_languages(self) -> list[str]:
        """Return only the interface languages enabled in llm_config.json."""
        configured = self.config.get("available_ui_languages", [])
        if not isinstance(configured, list):
            return []
        languages = sorted({str(code).strip().lower() for code in configured if str(code).strip()})
        return languages

    def _current_target_lang(self) -> str:
        return str(self.config.get("target_lang", "pl"))

    def _current_source_lang(self) -> str:
        return str(self.config.get("source_lang", "nl"))

    def _show_config_table(self) -> None:
        strings = self._strings()
        table = Table(title=strings["config_title"], box=box.SIMPLE_HEAVY)
        table.add_column("Key")
        table.add_column("Value")
        for key in ["source_lang", "target_lang", "ui_lang"]:
            table.add_row(key, str(self.config.get(key, "")))
        console.print(table)

    def handle_config(self, args) -> dict[str, str]:
        strings = self._strings()
        if getattr(args, "set", None):
            key, value = args.set
            self.config[key] = value
            self._save_config()
            console.print(Panel.fit(f"{strings['config_updated']}: {key}={value}", style="green"))
        else:
            self._show_config_table()
        return self.config

    def handle_speak(self, args) -> str:
        lang = getattr(args, "lang", None) or self._current_target_lang()
        engine = PronunciationEngine()
        file_path = engine.speak(args.word, lang_code=lang)
        translation = None
        if getattr(args, "translation", None):
            translation = args.translation
        elif lang != self._current_source_lang():
            word = self.dict_app.get_word(lang, self._current_source_lang(), args.word)
            if word is not None:
                translation = word.primary_translation
        console.print(
            Panel.fit(
                f"'{args.word}' in {lang} | translation: {translation or 'n/a'} | file: {file_path}",
                style="cyan",
            )
        )
        return str(file_path)

    def _table_width(self) -> int:
        width = getattr(console, "size", None)
        if width is not None and getattr(width, "width", None):
            return max(50, min(120, width.width - 4))
        return 100

    def _render_vocabulary_table(self, entries: list[dict], title: str) -> None:
        if not entries:
            console.print(Panel.fit("No vocabulary found.", style="yellow"))
            return

        table = Table(
            title=title,
            box=box.ROUNDED,
            header_style="bold cyan",
            width=self._table_width(),
            show_lines=False,
        )
        table.add_column("Lemma", style="bold")
        table.add_column("Translation")
        table.add_column("Part of speech")
        table.add_column("Categories")
        table.add_column("Sentences")

        for entry in entries:
            categories = ", ".join(entry.get("categories", [])) or "-"
            table.add_row(
                str(entry.get("lemma", "")),
                str(entry.get("translation", "")),
                str(entry.get("part_of_speech", "")),
                categories,
                str(entry.get("sentence_count", 0)),
            )
        console.print(table)

    def handle_list(self, args):
        target = getattr(args, "target", None) or self._current_target_lang()
        source = getattr(args, "source", None) or self._current_source_lang()
        entries = self.dict_app.get_vocabulary(target_lang=target, source_lang=source)
        title = f"{self._strings()['table_list_title']} ({target} → {source})"
        self._render_vocabulary_table(entries, title)
        return entries

    def handle_sentences(self, args):
        target = getattr(args, "target", None) or self._current_target_lang()
        source = getattr(args, "source", None) or self._current_source_lang()
        sentences = self.dict_app.get_sentences(target_lang=target, source_lang=source)
        if not sentences:
            console.print(Panel.fit("No sentences found for the current language pair.", style="yellow"))
            return []

        table = Table(
            title=f"Sentences ({target} → {source})",
            box=box.ROUNDED,
            header_style="bold cyan",
            width=self._table_width(),
            show_lines=False,
        )
        table.add_column("Lemma")
        table.add_column("Translation")
        table.add_column("Target sentence")
        table.add_column("Natural translation")
        table.add_column("Notes")

        for sentence in sentences:
            table.add_row(
                str(sentence.get("lemma", "")),
                str(sentence.get("translation", "")),
                str(sentence.get("target_text", "")),
                str(sentence.get("source_fluent", "")),
                str(sentence.get("notes") or "-"),
            )

        console.print(table)
        return sentences

    def _pick_word_for_speaking(self, target: str, source: str) -> str | None:
        entries = self.dict_app.get_vocabulary(target_lang=target, source_lang=source)
        if not entries:
            return None

        choices = [f"{entry['lemma']} — {entry['translation']}" for entry in entries]
        choices.append("Type manually")
        selected = questionary.select("Choose a word", choices=choices).ask()
        if selected == "Type manually":
            return Prompt.ask("Enter a word to speak")
        return next((item.split(" — ")[0] for item in choices if item == selected), selected)

    def _pick_sentence_for_speaking(self, target: str, source: str) -> str | None:
        sentences = self.dict_app.get_sentences(target_lang=target, source_lang=source)
        if not sentences:
            return None

        choices = [f"{sentence['lemma']}: {sentence['target_text']}" for sentence in sentences]
        choices.append("Type manually")
        selected = questionary.select("Choose a sentence", choices=choices).ask()
        if selected == "Type manually":
            return Prompt.ask("Enter a sentence to speak")
        return next((item.split(": ", 1)[1] for item in choices if item == selected), selected)

    def handle_update_word(self, args):
        target = getattr(args, "target", None) or self._current_target_lang()
        source = getattr(args, "source", None) or self._current_source_lang()
        entries = self.dict_app.get_vocabulary(target_lang=target, source_lang=source)
        if not entries:
            console.print(Panel.fit(self._strings().get("alert_no_words", "No words found."), style="yellow"))
            return None

        choices = [f"{entry['lemma']} — {entry['translation']}" for entry in entries]
        selection = questionary.select("Select a word to update", choices=choices).ask()
        selected_lemma = selection.split(" — ")[0]
        word = self.dict_app.get_word(target_lang=target, source_lang=source, lemma=selected_lemma)
        if word is None:
            return None

        new_lemma = Prompt.ask("New lemma", default=word.lemma)
        new_translation = Prompt.ask("New translation", default=word.primary_translation)
        new_pos = Prompt.ask("New part of speech", default=word.part_of_speech)
        categories = questionary.checkbox(
            "Select categories",
            choices=["voeding", "familie", "werk", "reizen", "dagelijks"],
        ).ask() or []

        self.dict_app.update_word(
            word,
            target_lang=target,
            source_lang=source,
            lemma=new_lemma,
            primary_translation=new_translation,
            part_of_speech=new_pos,
            categories=categories,
        )
        console.print(Panel.fit(f"Updated '{new_lemma}'", style="green"))
        return word

    def handle_update_sentence(self, args):
        target = getattr(args, "target", None) or self._current_target_lang()
        source = getattr(args, "source", None) or self._current_source_lang()
        sentences = self.dict_app.get_sentences(target_lang=target, source_lang=source)
        if not sentences:
            console.print(Panel.fit("No sentences found.", style="yellow"))
            return None

        choices = [f"{sentence['lemma']}: {sentence['target_text']}" for sentence in sentences]
        selection = questionary.select("Select a sentence to update", choices=choices).ask()
        selected_sentence = next(
            (item for item in sentences if f"{item['lemma']}: {item['target_text']}" == selection),
            None,
        )
        if selected_sentence is None:
            return None

        word = self.dict_app.get_word(target_lang=target, source_lang=source, lemma=selected_sentence["lemma"])
        if word is None:
            return None

        sentence = next(
            (s for s in word.sentences if s.target_text == selected_sentence["target_text"]),
            None,
        )
        if sentence is None:
            return None

        target_text = Prompt.ask("New target sentence", default=sentence.target_text)
        source_literal = Prompt.ask("New literal translation", default=sentence.source_literal)
        source_fluent = Prompt.ask("New fluent translation", default=sentence.source_fluent)
        notes = Prompt.ask("Notes", default=sentence.notes or "")

        self.dict_app.update_sentence(
            sentence,
            target_text=target_text,
            source_literal=source_literal,
            source_fluent=source_fluent,
        )
        sentence.notes = notes or None
        sentence.save()
        console.print(Panel.fit(f"Updated sentence: {target_text}", style="green"))
        return sentence

    def handle_add(self, args):
        target = getattr(args, "target", None) or self._current_target_lang()
        source = getattr(args, "source", None) or self._current_source_lang()
        pos = getattr(args, "pos", None) or "werkwoord"
        categories = getattr(args, "categories", None)
        if categories is None:
            cats = []
        elif isinstance(categories, str):
            cats = [cat.strip() for cat in categories.split(",") if cat.strip()]
        else:
            cats = list(categories)

        word = self.dict_app.add_word(
            target_lang=target,
            source_lang=source,
            lemma=args.lemma,
            primary_translation=args.translation,
            part_of_speech=pos,
            categories=cats,
        )

        if getattr(args, "speak", False):
            self.handle_speak(type("SpeakArgs", (), {"word": args.lemma, "lang": target})())

        console.print(
            Panel.fit(
                f"{word.lemma} — {word.primary_translation}",
                title=self._strings()["word_added"],
                style="green",
            )
        )
        return word

    def handle_sentence(self, args):
        target = getattr(args, "target", None) or self._current_target_lang()
        source = getattr(args, "source", None) or self._current_source_lang()
        entries = self.dict_app.get_vocabulary(target_lang=target, source_lang=source)
        if not entries:
            console.print(Panel.fit(self._strings()["alert_no_words"], style="yellow"))
            return None

        choices = [f"{entry['lemma']} — {entry['translation']}" for entry in entries]
        selection = questionary.select(self._strings()["select_word"], choices=choices).ask()
        selected_entry = next(
            (e for e in entries if f"{e['lemma']} — {e['translation']}" == selection),
            None,
        )
        if selected_entry is None:
            console.print(Panel.fit(self._strings()["alert_no_match"], style="red"))
            return None

        word = self.dict_app.get_word(
            target_lang=target,
            source_lang=source,
            lemma=selected_entry["lemma"],
        )
        if word is None:
            console.print(Panel.fit(self._strings()["alert_no_match"], style="red"))
            return None

        target_text = Prompt.ask(self._strings()["prompt_target_sentence"])
        source_literal = Prompt.ask(self._strings()["prompt_literal_translation"])
        source_fluent = Prompt.ask(self._strings()["prompt_fluent_translation"])
        notes = Prompt.ask(self._strings()["prompt_sentence_notes"], default="")

        sentence = self.dict_app.add_sentence(
            word=word,
            target_text=target_text,
            source_literal=source_literal,
            source_fluent=source_fluent,
            token_mapping=None,
        )
        sentence.notes = notes or None
        sentence.save()

        console.print(
            Panel.fit(
                f"{target_text}",
                title=self._strings()["sentence_title"],
                style="cyan",
            )
        )
        return sentence

    def _configure_settings(self) -> None:
        strings = self._strings()
        self.config["ui_lang"] = questionary.select(
            strings["choose_ui_language"],
            choices=["en", "nl"],
        ).ask()

        self.config["source_lang"] = Prompt.ask(
            strings["prompt_source_lang"],
            default=self.config.get("source_lang", "nl"),
        )
        self.config["target_lang"] = Prompt.ask(
            strings["prompt_target_lang"],
            default=self.config.get("target_lang", "pl"),
        )

        self._save_config()
        console.print(Panel.fit(strings["change_done"], style="green"))

    def legacy_main(self):
        """Prompt-based fallback kept for terminals without Textual support."""
        console.print(
            Panel.fit(
                self._strings()["welcome"],
                title="language-learning-module",
                border_style="bright_blue",
            )
        )

        while True:
            strings = self._strings()
            choices = [
                strings["add_word"],
                strings["add_sentence"],
                strings["show_sentences"],
                strings["update_word"],
                strings["update_sentence"],
                strings["list_words"],
                strings["speak_word"],
                strings["speak_sentence"],
                strings["config"],
                strings["exit"],
            ]
            choice = questionary.select(strings["menu_title"], choices=choices).ask()

            if choice == strings["exit"]:
                break
            if choice == strings["config"]:
                self._configure_settings()
                continue
            if choice == strings["add_word"]:
                lemma = Prompt.ask(strings["prompt_lemma"])
                translation = Prompt.ask(strings["prompt_translation"])
                pos = questionary.select(
                    strings["prompt_pos"],
                    choices=["werkwoord", "zelfstandig naamwoord", "bijvoeglijk naamwoord", "nieuw"],
                ).ask()
                categories = questionary.checkbox(
                    strings["prompt_categories"],
                    choices=["voeding", "familie", "werk", "reizen", "dagelijks"],
                ).ask() or []
                self.handle_add(
                    type(
                        "Args",
                        (),
                        {
                            "lemma": lemma,
                            "translation": translation,
                            "pos": pos,
                            "target": self._current_target_lang(),
                            "source": self._current_source_lang(),
                            "categories": ",".join(categories),
                            "speak": False,
                        },
                    )()
                )
                continue
            if choice == strings["add_sentence"]:
                self.handle_sentence(
                    type(
                        "Args",
                        (),
                        {
                            "target": self._current_target_lang(),
                            "source": self._current_source_lang(),
                        },
                    )()
                )
                continue
            if choice == strings["show_sentences"]:
                self.handle_sentences(
                    type(
                        "Args",
                        (),
                        {
                            "target": self._current_target_lang(),
                            "source": self._current_source_lang(),
                        },
                    )()
                )
                continue
            if choice == strings["update_word"]:
                self.handle_update_word(
                    type(
                        "Args",
                        (),
                        {
                            "target": self._current_target_lang(),
                            "source": self._current_source_lang(),
                        },
                    )()
                )
                continue
            if choice == strings["update_sentence"]:
                self.handle_update_sentence(
                    type(
                        "Args",
                        (),
                        {
                            "target": self._current_target_lang(),
                            "source": self._current_source_lang(),
                        },
                    )()
                )
                continue
            if choice == strings["list_words"]:
                self.handle_list(
                    type(
                        "Args",
                        (),
                        {
                            "target": self._current_target_lang(),
                            "source": self._current_source_lang(),
                        },
                    )()
                )
                continue
            if choice == strings["speak_word"]:
                selected_word = self._pick_word_for_speaking(
                    self._current_target_lang(),
                    self._current_source_lang(),
                )
                if selected_word is None:
                    continue
                if questionary.confirm(f"Speak '{selected_word}'?").ask():
                    translation = None
                    word = self.dict_app.get_word(self._current_target_lang(), self._current_source_lang(), selected_word)
                    if word is not None:
                        translation = word.primary_translation
                    self.handle_speak(
                        type(
                            "Args",
                            (),
                            {"word": selected_word, "lang": self._current_target_lang(), "translation": translation},
                        )()
                    )
                continue
            if choice == strings["speak_sentence"]:
                selected_sentence = self._pick_sentence_for_speaking(
                    self._current_target_lang(),
                    self._current_source_lang(),
                )
                if selected_sentence is None:
                    continue
                if questionary.confirm(f"Speak '{selected_sentence}'?").ask():
                    sentence = next(
                        (
                            item
                            for item in self.dict_app.get_sentences(
                                target_lang=self._current_target_lang(),
                                source_lang=self._current_source_lang(),
                            )
                            if item.get("target_text") == selected_sentence
                        ),
                        None,
                    )
                    translation_text = sentence.get("source_fluent") if sentence else None
                    self.handle_speak(
                        type(
                            "Args",
                            (),
                            {"word": selected_sentence, "lang": self._current_target_lang(), "translation": translation_text},
                        )()
                    )
                continue


def add_word(dict_app, existing_pos, existing_categories):
    """Compatibility wrapper for older interactive code."""
    runner = CommandRunner()
    lemma = Prompt.ask(runner._strings()["prompt_lemma"])
    translation = Prompt.ask(runner._strings()["prompt_translation"])

    pos = questionary.select(runner._strings()["prompt_pos"], choices=existing_pos).ask()
    if pos == "New" or pos == "Nieuw":
        pos = Prompt.ask("Enter the new part of speech")
        if pos and pos not in existing_pos:
            existing_pos.insert(-1, pos)

    selected_categories = questionary.checkbox(
        runner._strings()["prompt_categories"],
        choices=existing_categories,
    ).ask() or []

    categories_list = []
    for cat in selected_categories:
        if cat != "New" and cat != "Nieuw":
            categories_list.append(cat)

    if "New" in selected_categories or "Nieuw" in selected_categories:
        while True:
            new_cat = Prompt.ask("Enter a new category (or leave blank to finish)").strip()
            if not new_cat:
                break
            if new_cat not in categories_list:
                categories_list.append(new_cat)
            if new_cat not in existing_categories:
                existing_categories.insert(-1, new_cat)

    console.print(f"[dim]Saving categories: {categories_list}[/dim]")
    runner.dict_app.add_word(
        target_lang=runner._current_target_lang(),
        source_lang=runner._current_source_lang(),
        lemma=lemma,
        primary_translation=translation,
        part_of_speech=pos,
        categories=categories_list,
    )
    console.print(
        f"[bold green]Successfully added '{lemma}' with translation '{translation}'.[/bold green]"
    )


class LearningApp(App):
    """Full-screen, responsive terminal interface for the language database."""

    CSS = """
    Screen { background: $surface; layers: base popup menu; }
    #app-frame { height: 1fr; }
    #menu-bar { layer: menu; height: 3; background: $panel; border-bottom: solid $primary; padding: 0 1; }
    #menu-bar Button { height: 3; min-width: 12; border: none; background: $panel; color: $text; }
    #menu-bar Button:hover, #menu-bar Button:focus { background: $primary; color: $text; }
    #menu-popup { layer: popup; width: 34; height: auto; min-height: 3; display: none; background: $panel; border: solid $primary; padding: 1; offset: 1 3; }
    #menu-popup Button { width: 100%; height: 3; border: none; content-align: left middle; }
    #context-bar { height: 3; padding: 0 1; background: $surface-darken-1; }
    #context-bar Label { padding: 1 1; color: $text-muted; }
    #context-bar Input { width: 10; margin: 0 1; }
    #context-bar Select { width: 12; margin: 0 1; }
    #content { height: 1fr; padding: 0 1; }
    #title { height: 3; padding: 1 1; text-style: bold; color: $accent; }
    #status { height: 2; padding: 0 1; color: $text-muted; }
    #view { height: 1fr; border: solid $primary-darken-1; padding: 1; }
    #settings-catalog { height: 1fr; min-height: 12; }
    .form-row { height: auto; margin: 0 0 1 0; }
    .form-label { width: 24; padding: 1 0; }
    .form-control { width: 1fr; }
    .actions { height: 3; margin-top: 1; }
    .actions Button { margin-right: 1; }
    DataTable { height: auto; min-height: 8; }
    .form-label { width: 20%; min-width: 14; max-width: 24; }
    """

    BINDINGS = [
        ("1", "show_words", "Words"),
        ("2", "show_sentences", "Sentences"),
        ("a", "add_word", "Add word"),
        ("s", "speak_word", "Speak word"),
        ("c", "show_settings", "Settings"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, runner: CommandRunner):
        super().__init__()
        self.runner = runner
        self.strings = runner._strings()
        self._menu_item_number = 0
        self._menu_actions: dict[str, str] = {}
        self._open_menu: str | None = None
        self._settings_form_number = 0
        self._settings_ids: dict[str, str] = {}
        self._edit_form_number = 0
        self._edit_ids: dict[str, str] = {}
        self._last_table_selection: tuple[str | None, int, float] = (None, -1, 0.0)
        self._word_rows: list[dict] = []
        self._sentence_rows: list[dict] = []
        self._table_number = 0
        self._clipboard_value: str | None = None
        self._clipboard_process: subprocess.Popen[str] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="app-frame"):
            with Horizontal(id="menu-bar"):
                yield Button(self.strings["menu_file"], id="menu-file")
                yield Button(self.strings["menu_words"], id="menu-words")
                yield Button(self.strings["menu_sentences"], id="menu-sentences")
                yield Button(self.strings["menu_audio"], id="menu-audio")
                yield Button(self.strings["menu_settings"], id="menu-settings")
            with Vertical(id="menu-popup"):
                pass
            with Horizontal(id="context-bar"):
                yield Label(self.strings["prompt_ui_lang"])
                yield Select(
                    [(code, code) for code in self.runner.available_ui_languages()],
                    value=self.runner.config.get("ui_lang", "en"),
                    id="ui-language",
                )
                yield Label(self.strings["prompt_target_lang"])
                yield Input(value=self.runner._current_target_lang(), id="target-language")
                yield Label(self.strings["prompt_source_lang"])
                yield Input(value=self.runner._current_source_lang(), id="source-language")
            with Vertical(id="content"):
                yield Static(self.strings["menu_title"], id="title")
                yield Static("", id="status")
                yield ScrollableContainer(id="view")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_dashboard()

    def _save_context(self) -> None:
        self.runner.config["target_lang"] = self.query_one("#target-language", Input).value.strip().lower() or "pl"
        self.runner.config["source_lang"] = self.query_one("#source-language", Input).value.strip().lower() or "nl"
        self.runner._save_config()

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def refresh_shell_labels(self) -> None:
        labels = {
            "#menu-file": "menu_file",
            "#menu-words": "menu_words",
            "#menu-sentences": "menu_sentences",
            "#menu-audio": "menu_audio",
            "#menu-settings": "menu_settings",
        }
        for selector, key in labels.items():
            self.query_one(selector, Button).label = self.strings[key]
        self.query_one("#title", Static).update(self.strings["menu_title"])

    def show_menu(self, menu: str) -> None:
        popup = self.query_one("#menu-popup", Vertical)
        if self._open_menu == menu and popup.display:
            self.close_menu()
            return
        popup.remove_children()
        menu_items = {
            "file": [(self.strings["menu_exit"], "menu-exit")],
            "words": [(self.strings["list_words"], "nav-words"), (self.strings["add_word"], "nav-add-word")],
            "sentences": [(self.strings["show_sentences"], "nav-sentences"), (self.strings["add_sentence"], "nav-add-sentence")],
            "audio": [
                (self.strings["speak_word"], "nav-speak-word"),
                (self.strings["speak_sentence"], "nav-speak-sentence"),
            ],
            "settings": [(self.strings["config"], "nav-settings")],
        }
        for label, item_id in menu_items[menu]:
            self._menu_item_number += 1
            widget_id = f"menu-item-{self._menu_item_number}"
            self._menu_actions[widget_id] = item_id
            popup.mount(Button(label, id=widget_id))
        popup.display = True
        self._open_menu = menu

    def close_menu(self) -> None:
        self.query_one("#menu-popup", Vertical).display = False
        self._open_menu = None

    @staticmethod
    def _select_is_empty(value) -> bool:
        return value is None or value is Select.BLANK or value is Select.NULL

    def _speak_in_background(self, word: str) -> None:
        self.runner.handle_speak(type("Args", (), {"word": word, "lang": self.runner._current_target_lang()})())

    def _copy_to_clipboard(self, text: str) -> None:
        self._clipboard_value = text
        # Use an external clipboard owner so pasted applications never depend
        # on this Textual event loop servicing clipboard requests.
        for command in ("wl-copy", "xclip", "xsel"):
            executable = shutil.which(command)
            if not executable:
                continue
            try:
                if command == "wl-copy":
                    subprocess.run([executable], input=text, text=True, check=True)
                elif command == "xclip":
                    subprocess.run([executable, "-selection", "clipboard"], input=text, text=True, check=True)
                else:
                    subprocess.run([executable, "--clipboard", "--input"], input=text, text=True, check=True)
                self.notify(self.strings["copied"])
                return
            except (OSError, subprocess.SubprocessError):
                continue
        if self._copy_with_clipboard_helper(text):
            self.notify(self.strings["copied"])
            return
        self.notify(self.strings["clipboard_unavailable"], severity="error")

    def _copy_with_clipboard_helper(self, text: str) -> bool:
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False
        helper = """
import queue
import json
import sys
import threading
import tkinter as tk

pending = queue.Queue()
root = tk.Tk()
root.withdraw()

def read_input():
    for line in sys.stdin:
        pending.put(json.loads(line))

def update_clipboard():
    try:
        while True:
            value = pending.get_nowait()
            root.clipboard_clear()
            root.clipboard_append(value)
            root.update()
    except queue.Empty:
        pass
    root.after(50, update_clipboard)

threading.Thread(target=read_input, daemon=True).start()
root.after(0, update_clipboard)
root.mainloop()
"""
        try:
            if self._clipboard_process is None or self._clipboard_process.poll() is not None:
                self._clipboard_process = subprocess.Popen(
                    [sys.executable, "-u", "-c", helper],
                    stdin=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
            if self._clipboard_process.stdin is None:
                return False
            self._clipboard_process.stdin.write(json.dumps(text, ensure_ascii=False) + "\n")
            self._clipboard_process.stdin.flush()
            return True
        except (OSError, subprocess.SubprocessError):
            self._clipboard_process = None
            return False

    def on_unmount(self) -> None:
        if self._clipboard_process is not None:
            self._clipboard_process.terminate()
            self._clipboard_process = None

    def _table(self, columns: list[str], rows: list[list[str]], table_id: str) -> DataTable:
        table = DataTable(id=table_id, zebra_stripes=True, cursor_type="row")
        table.add_columns(*columns)
        for row in rows:
            table.add_row(*row)
        return table

    def refresh_dashboard(self) -> None:
        self._save_context()
        entries = self.runner.dict_app.get_vocabulary(
            self.runner._current_target_lang(), self.runner._current_source_lang()
        )
        self._word_rows = entries
        self._table_number += 1
        table_id = f"words-table-{self._table_number}"
        self._set_status(
            f"{self.runner._current_target_lang()} -> {self.runner._current_source_lang()} | {len(entries)} words"
        )
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        view.mount(self._table(
            [self.strings["table_lemma"], self.strings["table_translation"], self.strings["table_pos"], self.strings["table_count"]],
            [[str(item["lemma"]), str(item["translation"]), str(item["part_of_speech"]), str(item["sentence_count"])] for item in entries],
            table_id,
        ))

    def action_show_words(self) -> None:
        self.show_words()

    def action_show_sentences(self) -> None:
        self.show_sentences()

    def action_add_word(self) -> None:
        self.show_add_word()

    def action_speak_word(self) -> None:
        self.show_speak_word()

    def action_show_settings(self) -> None:
        self.show_settings()

    def show_words(self) -> None:
        self.refresh_dashboard()

    def show_sentences(self) -> None:
        self._save_context()
        sentences = self.runner.dict_app.get_sentences(self.runner._current_target_lang(), self.runner._current_source_lang())
        self._sentence_rows = sentences
        self._table_number += 1
        table_id = f"sentences-table-{self._table_number}"
        self._set_status(f"{len(sentences)} sentences")
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        view.mount(self._table(
            ["Lemma", "Target", "Literal", "Translation"],
            [[str(item["lemma"]), str(item["target_text"]), str(item["source_literal"]), str(item["source_fluent"])] for item in sentences],
            table_id,
        ))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id or ""
        now = time.monotonic()
        previous_table, previous_row, previous_time = self._last_table_selection
        self._last_table_selection = (table_id, event.cursor_row, now)
        if table_id != previous_table or event.cursor_row != previous_row or now - previous_time > 0.6:
            return
        if table_id.startswith("words-table-") and event.cursor_row < len(self._word_rows):
            self.show_edit_word(self._word_rows[event.cursor_row])
        elif table_id.startswith("sentences-table-") and event.cursor_row < len(self._sentence_rows):
            self.show_edit_sentence(self._sentence_rows[event.cursor_row])

    def _new_edit_id(self, name: str) -> str:
        return f"edit-{name}-{self._edit_form_number}"

    def show_edit_word(self, entry: dict) -> None:
        self._edit_form_number += 1
        suffix = str(self._edit_form_number)
        self._edit_ids = {name: f"edit-{name}-{suffix}" for name in ("lemma", "translation", "pos", "save", "copy")}
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        view.mount(Label(self.strings["update_word"]))
        view.mount(self._form_row(self.strings["prompt_lemma"], Input(value=str(entry["lemma"]), id=self._edit_ids["lemma"], classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_translation"], Input(value=str(entry["translation"]), id=self._edit_ids["translation"], classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_pos"], Input(value=str(entry["part_of_speech"]), id=self._edit_ids["pos"], classes="form-control")))
        view.mount(Horizontal(
            Button(self.strings["save"], id=self._edit_ids["save"], variant="success"),
            Button(self.strings["copy_word"], id=self._edit_ids["copy"]),
            Button(self.strings["back"], id="cancel-form"),
            classes="actions",
        ))
        self._edit_entry = entry

    def show_edit_sentence(self, entry: dict) -> None:
        self._edit_form_number += 1
        suffix = str(self._edit_form_number)
        self._edit_ids = {name: f"edit-{name}-{suffix}" for name in ("target", "literal", "fluent", "notes", "save", "copy")}
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        view.mount(Label(self.strings["update_sentence"]))
        view.mount(self._form_row(self.strings["prompt_target_sentence"], Input(value=str(entry["target_text"]), id=self._edit_ids["target"], classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_literal_translation"], Input(value=str(entry["source_literal"]), id=self._edit_ids["literal"], classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_fluent_translation"], Input(value=str(entry["source_fluent"]), id=self._edit_ids["fluent"], classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_sentence_notes"], Input(value=str(entry.get("notes") or ""), id=self._edit_ids["notes"], classes="form-control")))
        view.mount(Horizontal(
            Button(self.strings["save"], id=self._edit_ids["save"], variant="success"),
            Button(self.strings["copy_sentence"], id=self._edit_ids["copy"]),
            Button(self.strings["back"], id="cancel-form"),
            classes="actions",
        ))
        self._edit_entry = entry

    def _form_row(self, label: str, control) -> Horizontal:
        return Horizontal(Label(label, classes="form-label"), control, classes="form-row")

    def show_add_word(self) -> None:
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        view.mount(Label(self.strings["add_word"]))
        view.mount(self._form_row(self.strings["prompt_lemma"], Input(id="word-lemma", classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_translation"], Input(id="word-translation", classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_pos"], Input(value="word", id="word-pos", classes="form-control")))
        view.mount(Horizontal(Button(self.strings["save"], id="save-word", variant="success"), Button(self.strings["back"], id="cancel-form"), classes="actions"))

    def show_add_sentence(self) -> None:
        entries = self.runner.dict_app.get_vocabulary(self.runner._current_target_lang(), self.runner._current_source_lang())
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        options = [(f"{item['lemma']} - {item['translation']}", item["lemma"]) for item in entries]
        view.mount(Label(self.strings["add_sentence"]))
        view.mount(self._form_row(self.strings["select_word"], Select(options, id="sentence-word", classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_target_sentence"], Input(id="sentence-target", classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_literal_translation"], Input(id="sentence-literal", classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_fluent_translation"], Input(id="sentence-fluent", classes="form-control")))
        view.mount(self._form_row(self.strings["prompt_sentence_notes"], Input(id="sentence-notes", classes="form-control")))
        view.mount(Horizontal(Button(self.strings["save"], id="save-sentence", variant="success"), Button(self.strings["back"], id="cancel-form"), classes="actions"))

    def show_speak_word(self) -> None:
        entries = self.runner.dict_app.get_vocabulary(self.runner._current_target_lang(), self.runner._current_source_lang())
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        options = [(f"{item['lemma']} - {item['translation']}", item["lemma"]) for item in entries]
        view.mount(Label(self.strings["speak_word"]))
        view.mount(Select(options, id="speak-selection"))
        view.mount(Horizontal(Button(self.strings["speak_word"], id="speak-selected", variant="primary"), Button(self.strings["back"], id="cancel-form"), classes="actions"))

    def show_speak_sentence(self) -> None:
        sentences = self.runner.dict_app.get_sentences(self.runner._current_target_lang(), self.runner._current_source_lang())
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        options = [(f"{item['lemma']} - {item['target_text']}", item["target_text"]) for item in sentences]
        view.mount(Label(self.strings["speak_sentence"]))
        view.mount(Select(options, id="speak-sentence-selection"))
        view.mount(Horizontal(Button(self.strings["speak_sentence"], id="speak-sentence-selected", variant="primary"), Button(self.strings["back"], id="cancel-form"), classes="actions"))

    def show_copy(self, kind: str) -> None:
        if kind == "word":
            entries = self.runner.dict_app.get_vocabulary(self.runner._current_target_lang(), self.runner._current_source_lang())
            options = [(f"{item['lemma']} - {item['translation']}", item["lemma"]) for item in entries]
            title = self.strings["copy_word"]
            select_id = "copy-word-selection"
            button_id = "copy-word-selected"
        else:
            entries = self.runner.dict_app.get_sentences(self.runner._current_target_lang(), self.runner._current_source_lang())
            options = [(f"{item['lemma']} - {item['target_text']}", item["target_text"]) for item in entries]
            title = self.strings["copy_sentence"]
            select_id = "copy-sentence-selection"
            button_id = "copy-sentence-selected"
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        view.mount(Label(title))
        view.mount(Select(options, id=select_id))
        view.mount(Horizontal(Button(title, id=button_id, variant="primary"), Button(self.strings["back"], id="cancel-form"), classes="actions"))

    def show_settings(self) -> None:
        view = self.query_one("#view", ScrollableContainer)
        view.remove_children()
        self._settings_form_number += 1
        suffix = str(self._settings_form_number)
        self._settings_ids = {
            key: f"settings-{key}-{suffix}"
            for key in ("ui-language", "languages", "catalog", "save")
        }
        configured_languages = self.runner.config.get("available_ui_languages", ["en", "nl"])
        if not isinstance(configured_languages, list):
            configured_languages = self.runner.available_ui_languages()
        configured_languages = [str(code).lower() for code in configured_languages]
        current_language = str(self.runner.config.get("ui_lang", "en")).lower()
        if current_language not in configured_languages:
            configured_languages.append(current_language)
        catalog = self.runner.config.get("translations", {})
        catalog_text = json.dumps(catalog if isinstance(catalog, dict) else {}, indent=2, ensure_ascii=False)
        view.mount(Label(self.strings["settings_title"]))
        view.mount(Label(self.strings["settings_hint"]))
        view.mount(self._form_row(
            self.strings["prompt_ui_lang"],
            Select(
                [(code, code) for code in configured_languages],
                value=self.runner.config.get("ui_lang", "en"),
                id=self._settings_ids["ui-language"],
                classes="form-control",
            ),
        ))
        view.mount(self._form_row(
            self.strings["settings_languages"],
            Input(value=", ".join(str(code) for code in configured_languages), id=self._settings_ids["languages"], classes="form-control"),
        ))
        view.mount(Label(self.strings["settings_catalog"]))
        view.mount(TextArea(catalog_text, id=self._settings_ids["catalog"], language="json"))
        view.mount(Horizontal(
            Button(self.strings["save"], id=self._settings_ids["save"], variant="success"),
            Button(self.strings["back"], id="cancel-form"),
            classes="actions",
        ))
        self._set_status(str(self.runner.config_path))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "ui-language" and event.value is not Select.BLANK:
            self.runner.config["ui_lang"] = str(event.value)
            self.runner._save_config()
            self.strings = self.runner._strings()
            self.refresh_shell_labels()
            self.notify("Language saved. Restart the app to refresh every label.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id
        if action in self._menu_actions:
            action = self._menu_actions[action]
        if action in {"menu-file", "menu-words", "menu-sentences", "menu-audio", "menu-settings"}:
            self.show_menu(action.removeprefix("menu-"))
            return
        if action == "menu-exit":
            self.exit()
            return
        self.close_menu()
        self._save_context()
        if action == "nav-words":
            self.show_words()
        elif action == "nav-sentences":
            self.show_sentences()
        elif action == "nav-add-word":
            self.show_add_word()
        elif action == "nav-add-sentence":
            self.show_add_sentence()
        elif action == "nav-speak-word":
            self.show_speak_word()
        elif action == "nav-speak-sentence":
            self.show_speak_sentence()
        elif action == "nav-settings":
            self.show_settings()
        elif action == "cancel-form":
            self.show_words()
        elif action == self._edit_ids.get("copy"):
            if "lemma" in self._edit_ids:
                self._copy_to_clipboard(str(self._edit_entry["lemma"]))
            else:
                self._copy_to_clipboard(str(self._edit_entry["target_text"]))
        elif action == self._edit_ids.get("save"):
            entry = self._edit_entry
            if "lemma" in self._edit_ids:
                word = self.runner.dict_app.get_word(
                    self.runner._current_target_lang(), self.runner._current_source_lang(), str(entry["lemma"])
                )
                if word is not None:
                    self.runner.dict_app.update_word(
                        word,
                        lemma=self.query_one(f"#{self._edit_ids['lemma']}", Input).value,
                        primary_translation=self.query_one(f"#{self._edit_ids['translation']}", Input).value,
                        part_of_speech=self.query_one(f"#{self._edit_ids['pos']}", Input).value,
                    )
                self.show_words()
            else:
                word = self.runner.dict_app.get_word(
                    self.runner._current_target_lang(), self.runner._current_source_lang(), str(entry["lemma"])
                )
                sentence = next((item for item in (word.sentences if word else []) if item.id == entry["sentence_id"]), None)
                if sentence is not None:
                    self.runner.dict_app.update_sentence(
                        sentence,
                        target_text=self.query_one(f"#{self._edit_ids['target']}", Input).value,
                        source_literal=self.query_one(f"#{self._edit_ids['literal']}", Input).value,
                        source_fluent=self.query_one(f"#{self._edit_ids['fluent']}", Input).value,
                    )
                    sentence.notes = self.query_one(f"#{self._edit_ids['notes']}", Input).value or None
                    sentence.save()
                self.show_sentences()
        elif action == "save-word":
            self.runner.handle_add(type("Args", (), {
                "lemma": self.query_one("#word-lemma", Input).value,
                "translation": self.query_one("#word-translation", Input).value,
                "pos": self.query_one("#word-pos", Input).value or "word",
                "target": self.runner._current_target_lang(), "source": self.runner._current_source_lang(),
                "categories": "", "speak": False,
            })())
            self.notify(self.strings["word_added"])
            self.show_words()
        elif action == "speak-sentence-selected":
            value = self.query_one("#speak-sentence-selection", Select).value
            if self._select_is_empty(value):
                self.notify(self.strings["alert_no_match"], severity="warning")
                return
            self.run_worker(partial(self._speak_in_background, str(value)), thread=True)
        elif action == "copy-word-selected":
            value = self.query_one("#copy-word-selection", Select).value
            if self._select_is_empty(value):
                self.notify(self.strings["alert_no_match"], severity="warning")
                return
            self._copy_to_clipboard(str(value))
        elif action == "copy-sentence-selected":
            value = self.query_one("#copy-sentence-selection", Select).value
            if self._select_is_empty(value):
                self.notify(self.strings["alert_no_match"], severity="warning")
                return
            self._copy_to_clipboard(str(value))
        elif action.startswith("settings-save-"):
            selected_language = self.query_one(f"#{self._settings_ids['ui-language']}", Select).value
            language_text = self.query_one(f"#{self._settings_ids['languages']}", Input).value
            languages = [code.strip().lower() for code in language_text.split(",") if code.strip()]
            if not languages:
                self.notify(self.strings["alert_no_match"], severity="error")
                return
            if self._select_is_empty(selected_language) or str(selected_language) not in languages:
                self.notify(self.strings["alert_no_match"], severity="error")
                return
            try:
                catalog = json.loads(self.query_one(f"#{self._settings_ids['catalog']}", TextArea).text)
            except json.JSONDecodeError as error:
                self.notify(f"Invalid JSON: {error.msg}", severity="error")
                return
            if not isinstance(catalog, dict) or any(not isinstance(value, dict) for value in catalog.values()):
                self.notify(self.strings["alert_no_match"], severity="error")
                return
            self.runner.config["ui_lang"] = str(selected_language)
            self.runner.config["available_ui_languages"] = languages
            self.runner.config["translations"] = catalog
            self.runner._save_config()
            self.strings = self.runner._strings()
            self.notify(self.strings["settings_saved"])
            self.refresh_shell_labels()
            self.show_settings()
        elif action == "save-sentence":
            selected = self.query_one("#sentence-word", Select).value
            if self._select_is_empty(selected):
                self.notify(self.strings["alert_no_match"], severity="error")
                return
            word = self.runner.dict_app.get_word(
                self.runner._current_target_lang(), self.runner._current_source_lang(), str(selected)
            )
            if word is None:
                self.notify(self.strings["alert_no_match"], severity="error")
                return
            sentence = self.runner.dict_app.add_sentence(
                word=word,
                target_text=self.query_one("#sentence-target", Input).value,
                source_literal=self.query_one("#sentence-literal", Input).value,
                source_fluent=self.query_one("#sentence-fluent", Input).value,
            )
            sentence.notes = self.query_one("#sentence-notes", Input).value or None
            sentence.save()
            self.notify(self.strings["sentence_title"])
            self.show_sentences()
        elif action == "speak-selected":
            value = self.query_one("#speak-selection", Select).value
            if self._select_is_empty(value):
                self.notify(self.strings["alert_no_match"], severity="warning")
                return
            self.run_worker(partial(self._speak_in_background, str(value)), thread=True)


def main() -> None:
    """Launch the dedicated full-screen terminal UI."""
    LearningApp(CommandRunner()).run()


if __name__ == "__main__":
    main()
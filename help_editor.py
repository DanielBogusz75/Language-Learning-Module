from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Label, Markdown, Select, Static, TextArea


class HelpEditor(App):
    """Standalone Markdown editor for help_content.json."""

    CSS = """
    Screen { background: $surface; }
    #menu-bar { height: 3; background: $panel; border-bottom: solid $primary; padding: 0 1; }
    #menu-bar Button { height: 3; min-width: 12; border: none; background: $panel; }
    #menu-bar Button:hover, #menu-bar Button:focus { background: $primary; }
    #menu-popup { layer: popup; width: 30; height: auto; display: none; background: $panel; border: solid $primary; padding: 1; offset: 1 3; }
    #menu-popup Button { width: 100%; height: 3; border: none; content-align: left middle; }
    #toolbar { height: 4; padding: 1 1; background: $surface-darken-1; }
    #toolbar Label { width: 14; padding: 1 0; }
    #section-select { width: 1fr; }
    #workspace { height: 1fr; padding: 0 1; }
    .pane { width: 1fr; height: 1fr; border: solid $primary-darken-1; padding: 1; }
    .pane-title { height: 2; text-style: bold; color: $accent; }
    #editor { height: 1fr; }
    #preview { height: 1fr; overflow: auto; }
    #status { height: 2; padding: 0 1; color: $text-muted; }
    #actions { height: 3; padding: 0 1; }
    #actions Button { margin-right: 1; }
    """

    BINDINGS = [
        ("ctrl+s", "save_file", "Save"),
        ("ctrl+r", "reload_file", "Reload"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, content_path: str | Path | None = None):
        super().__init__()
        self.content_path = Path(content_path) if content_path else Path(__file__).with_name("help_content.json")
        self.content: dict = {}
        self.sections: list[tuple[str, str, str]] = []
        self._open_menu: str | None = None
        self._menu_actions: dict[str, str] = {}
        self._menu_item_number = 0
        self._current_section: tuple[str, str, str] | None = None
        self._dirty = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="menu-bar"):
            yield Button("File", id="menu-file")
            yield Button("Edit", id="menu-edit")
        with Vertical(id="menu-popup"):
            pass
        with Horizontal(id="toolbar"):
            yield Label("Help section")
            yield Select([], id="section-select", allow_blank=True)
        with Horizontal(id="workspace"):
            with Vertical(classes="pane"):
                yield Label("Markdown source", classes="pane-title")
                yield TextArea(language="markdown", id="editor", show_line_numbers=True, tab_behavior="indent")
            with Vertical(classes="pane"):
                yield Label("Preview", classes="pane-title")
                yield Markdown("", id="preview")
        yield Static("", id="status")
        with Horizontal(id="actions"):
            yield Button("Save", id="save", variant="success")
            yield Button("Reload", id="reload")
            yield Button("Exit", id="exit")
        yield Footer()

    def on_mount(self) -> None:
        self._load_content()

    def _load_content(self) -> None:
        try:
            with self.content_path.open("r", encoding="utf-8") as file_handle:
                loaded = json.load(file_handle)
        except (OSError, json.JSONDecodeError) as error:
            self._set_status(f"Could not load {self.content_path}: {error}")
            return
        if not isinstance(loaded, dict):
            self._set_status("Help content must be a JSON object.")
            return
        self.content = loaded
        self.sections = []
        for section_name, section_values in loaded.items():
            if not isinstance(section_values, dict):
                continue
            for language_code, language_value in section_values.items():
                if not isinstance(language_value, dict):
                    continue
                if "markdown" in language_value:
                    field = "markdown"
                elif "text" in language_value:
                    field = "text"
                else:
                    for field_name, field_value in language_value.items():
                        if isinstance(field_value, str):
                            field = field_name
                            break
                    else:
                        continue
                self.sections.append((section_name, str(language_code), field))
        options = [
            (f"{section} / {language} ({field})", f"{section}|{language}|{field}")
            for section, language, field in self.sections
        ]
        select = self.query_one("#section-select", Select)
        select.set_options(options)
        if options:
            select.value = options[0][1]
            self._select_section(options[0][1])
        self._dirty = False
        self._set_status(f"Loaded {self.content_path}")

    def _section_value(self, section: tuple[str, str, str]) -> str:
        section_name, language_code, field = section
        return str(self.content[section_name][language_code].get(field, ""))

    def _select_section(self, value: str) -> None:
        try:
            section = next(item for item in self.sections if "|".join(item) == value)
        except StopIteration:
            return
        self._current_section = section
        editor = self.query_one("#editor", TextArea)
        editor.load_text(self._section_value(section))
        self._dirty = False
        self._update_preview(editor.text)
        self._set_status(f"Editing {section[0]} / {section[1]}")

    def _update_preview(self, markdown: str) -> None:
        self.query_one("#preview", Markdown).update(markdown)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "editor":
            return
        self._dirty = True
        self._update_preview(event.text_area.text)
        self._set_status("Unsaved changes")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "section-select" or event.value is Select.BLANK:
            return
        if self._dirty:
            self._save_current()
        self._select_section(str(event.value))

    def _save_current(self) -> bool:
        if self._current_section is None:
            return False
        section_name, language_code, field = self._current_section
        self.content[section_name][language_code][field] = self.query_one("#editor", TextArea).text
        return self._write_content()

    def _write_content(self) -> bool:
        try:
            self.content_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.content_path.parent,
                prefix=f".{self.content_path.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                json.dump(self.content, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            temporary_path.replace(self.content_path)
        except OSError as error:
            self._set_status(f"Could not save: {error}")
            return False
        self._dirty = False
        self._set_status(f"Saved {self.content_path}")
        return True

    def action_save_file(self) -> None:
        self._save_current()

    def action_reload_file(self) -> None:
        self._load_content()

    def show_menu(self, menu: str) -> None:
        popup = self.query_one("#menu-popup", Vertical)
        if self._open_menu == menu and popup.display:
            self.close_menu()
            return
        popup.remove_children()
        items = {
            "file": [("Save", "save"), ("Reload", "reload"), ("Exit", "exit")],
            "edit": [("Save", "save"), ("Reload", "reload")],
        }
        for label, action in items[menu]:
            self._menu_item_number += 1
            widget_id = f"menu-item-{self._menu_item_number}"
            self._menu_actions[widget_id] = action
            popup.mount(Button(label, id=widget_id))
        popup.display = True
        self._open_menu = menu

    def close_menu(self) -> None:
        self.query_one("#menu-popup", Vertical).display = False
        self._open_menu = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.id or ""
        if action in ("menu-file", "menu-edit"):
            self.show_menu(action.removeprefix("menu-"))
            return
        action = self._menu_actions.get(action, action)
        self.close_menu()
        if action == "save":
            self._save_current()
        elif action == "reload":
            self._load_content()
        elif action == "exit":
            self.exit()

    def action_quit(self) -> None:
        if self._dirty:
            self._save_current()
        self.exit()


def main() -> None:
    content_path = sys.argv[1] if len(sys.argv) > 1 else None
    HelpEditor(content_path).run()


if __name__ == "__main__":
    main()

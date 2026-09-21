# Language Learning Module

Terminal-based vocabulary and sentence manager for studying a target language through a source language. The application stores words, categories, example sentences, translations, pronunciation audio, and word-level metadata in SQLite.

## Requirements

- Python 3.12 or newer
- `uv` recommended for environment and dependency management
- A terminal with mouse support for the full interface
- An audio player supported by the local pronunciation setup when using speech features

## Installation

From the project directory:

```bash
uv sync
```

Alternatively, activate an existing virtual environment and install the dependencies from `pyproject.toml`.

## Start the application

Launch the full-screen Textual interface with:

```bash
uv run llm.py
```

With an activated virtual environment:

```bash
python llm.py
```

The application creates or opens `polyglot_learning.db` in the project directory. The database contains words, categories, word-category relationships, sentences, sentence tokens, and language metadata.

## Main interface

The top menu contains:

### Application

- **Help**: open formatted Markdown help for the active interface, source, and target languages.
- **Manage categories**: add and edit categories for the current source language.
- **Settings**: edit interface languages, the active UI language, and the translation catalog.
- **Exit**: close the application.

### Words

- **View words by category**: choose a category and show only its words.
- **List words**: show all words for the active language pair.
- **Add word**: create a word with lemma, translation, part of speech, categories, and optional metadata.

### Sentences

- **Show all sentences**: view saved example sentences for the active language pair.
- **Add sentence**: attach a target sentence, literal translation, fluent translation, and optional notes to a word.

### Audio

- Speak a selected word.
- Speak a selected sentence.

The source and target language fields are visible in the context bar. Changing them affects the current views and category list.

## Words and categories

A word can belong to any number of categories. Enter category names separated by commas, for example:

```text
food and drink, daily life, verbs
```

Categories are stored through the `WordCategory` junction table, so one word can be assigned to many categories and one category can contain many words. Category names are scoped to the source language.

Words support these optional fields:

- Gender
- Grammatical aspect
- Governed case
- Description
- Inflections
- Synonyms

Use **Application > Manage categories** to add or edit category names and descriptions. Double-click a category row to edit it.

## Tables and mouse actions

Word and sentence tables support sorting by clicking a column header:

- The first click sorts ascending and shows `↑` in the header.
- Clicking the same header again sorts descending and shows `↓`.
- Sentence count is sorted numerically.

### Word context menu

Right-click a word row, or double-click it, to open its context menu:

- **Speak word**: pronounce the word in the active target language.
- **Show connected sentences**: open the sentence list filtered to that word.
- **Edit word**: open the complete word editor.

Right-clicking a lemma in the sentence table can also open the word record when it exists.

## Keyboard shortcuts

In the main application:

| Shortcut | Action |
| --- | --- |
| `1` | Show words |
| `2` | Show sentences |
| `a` | Add a word |
| `s` | Speak a word |
| `c` | Open settings |
| `q` | Quit |

Mouse interaction is supported for menus, buttons, table sorting, row actions, and context menus.

## Help and Markdown editor

Help content is stored in [help_content.json](help_content.json). It is organized by:

- Application help by interface language
- Source-language help by source language
- Target-language help by target language

Open the editor from **Application > Help > Edit help**. The editor opens in a separate terminal window and provides:

- A section and language selector
- Editable Markdown source
- Live Markdown preview
- File and Edit menus
- Save, Reload, and Exit actions
- `Ctrl+S` to save
- `Ctrl+R` to reload
- `Ctrl+Q` to quit

The editor saves the JSON file atomically. It can also be started independently:

```bash
uv run help-editor
```

Or, with an activated environment:

```bash
python help_editor.py
```

## Polish special characters

The built-in Polish target-language help documents:

`ą ć ę ł ń ó ś ź ż`

On an international QWERTY layout, use `Right Alt` (`AltGr`) with the corresponding letter:

```text
AltGr+a = ą
AltGr+c = ć
AltGr+e = ę
AltGr+l = ł
AltGr+n = ń
AltGr+o = ó
AltGr+s = ś
AltGr+x = ź
AltGr+z = ż
```

On Linux systems that support Unicode input:

1. Hold `Ctrl+Shift` and press `U`.
2. Release the keys.
3. Type the hexadecimal code point.
4. Press `Enter` or `Space`.

For example, `Ctrl+Shift+U`, `0105`, `Enter` produces `ą`. The code points for all Polish letters are included in the in-app Help view.

On Windows applications that support `Alt+X`, type the code point and press `Alt+X`, for example `0105` followed by `Alt+X` for `ą`. If these methods are unavailable, enable a Polish keyboard layout or use the operating system character picker.

## Command-line interface

The command-line utility is available through `llm.py`:

```bash
uv run llm.py --help
```

Available commands include:

### Configuration

```bash
uv run llm.py config
uv run llm.py config --set target_lang pl
uv run llm.py config --set source_lang nl
```

### Add a word

```bash
uv run llm.py add pić drinken \
  --pos verb \
  --target pl \
  --source nl \
  --categories "food and drink,daily life"
```

### List words

```bash
uv run llm.py list --target pl --source nl
```

### Speak a word

```bash
uv run llm.py speak pić --lang pl
```

Use `--speak` with the `add` command to pronounce a word after adding it.

## Configuration and project files

- `llm_config.json`: active source language, target language, UI language, available UI languages, and translated interface labels.
- `help_content.json`: Markdown help content by application, source language, and target language.
- `polyglot_learning.db`: SQLite database created by the application.
- `llm_tui.py`: main Textual interface and command runner.
- `help_editor.py`: standalone Markdown help editor.
- `polyglot_db.py`: Peewee models and dictionary/category database operations.
- `audio_manager.py`: pronunciation and audio-cache support.

To add an interface language, add its code to `available_ui_languages` and add a translation object under `translations` in `llm_config.json`. Missing labels can be added incrementally, but every label used by the interface should eventually be translated.

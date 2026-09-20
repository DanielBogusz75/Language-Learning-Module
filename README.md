## Language Learning Module

Launch the full-screen terminal UI with:

```bash
uv run llm.py
```

The interface is resizable and supports mouse interaction, dropdowns, buttons, and keyboard shortcuts. The saved interface language and language pair live in `llm_config.json`.

To add another interface language, add its code to `available_ui_languages` and add translated labels under `translations`. Missing labels fall back to English, so a new language can be introduced incrementally:

```json
{
	"ui_lang": "de",
	"available_ui_languages": ["en", "nl", "de"],
	"translations": {
		"de": {
			"welcome": "Sprachlernmodul",
			"add_word": "Wort hinzufügen",
			"list_words": "Wörter anzeigen"
		}
	}
}
```

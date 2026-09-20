from argparse import Namespace

from llm_tui import CommandRunner


def test_add_and_list_word(tmp_path):
    db_path = tmp_path / "polyglot.db"
    runner = CommandRunner(db_path=db_path)

    add_args = Namespace(
        lemma="pić",
        translation="drinken",
        pos="werkwoord",
        target="pl",
        source="nl",
        categories="voeding,dagelijks",
        speak=False,
    )

    runner.handle_add(add_args)
    entries = runner.handle_list(Namespace(target="pl", source="nl"))

    assert entries
    assert entries[0]["lemma"] == "pić"
    assert entries[0]["translation"] == "drinken"

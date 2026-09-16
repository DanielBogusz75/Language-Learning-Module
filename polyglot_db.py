"""Universal Multilingual Dictionary and Sentence Database using Peewee ORM."""

from pathlib import Path
from peewee import (
    CharField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

db = SqliteDatabase("polyglot_learning.db", pragmas={"foreign_keys": 1})


class BaseModel(Model):
    """Base model setting the shared database connection."""

    class Meta:
        database = db


class Category(BaseModel):
    """Categories and topics (e.g., 'Eten & Drinken', 'Grammatica: A1')."""

    name = CharField(index=True)
    language_code = CharField(
        default="nl"
    )  # Language of category label itself
    description = TextField(null=True)

    class Meta:
        indexes = ((("name", "language_code"), True),)


class Word(BaseModel):
    """Target language vocabulary entries."""

    target_lang = CharField(index=True)  # e.g., 'pl', 'de', 'es'
    source_lang = CharField(index=True)  # e.g., 'nl'
    lemma = CharField(index=True)  # Word in target language (e.g., 'pić')
    primary_translation = CharField()  # Main meaning in source language (e.g., 'drinken')
    part_of_speech = CharField()  # Verb, Noun, Adjective, etc.
    gender = CharField(null=True)  # Grammatical gender if applicable
    grammatical_aspect = CharField(null=True)  # e.g., Perfective / Imperfective
    governed_case = CharField(null=True)  # Required case / preposition rule
    description = TextField(null=True)  # Additional notes in source language

    # JSON strings for language-specific properties
    inflections = TextField(null=True)  # Conjugation / declension tables
    synonyms = TextField(null=True)  # Synonyms in target language


class WordCategory(BaseModel):
    """Junction table connecting Words to Categories."""

    word = ForeignKeyField(Word, backref="categories", on_delete="CASCADE")
    category = ForeignKeyField(
        Category, backref="words", on_delete="CASCADE"
    )

    class Meta:
        indexes = ((("word", "category"), True),)


class Sentence(BaseModel):
    """Example sentences with dual-layer translation."""

    word = ForeignKeyField(Word, backref="sentences", on_delete="CASCADE")
    target_text = TextField()  # Complete target sentence
    source_literal = TextField()  # Word-for-word translation in source language
    source_fluent = TextField()  # Natural translation in source language
    notes = TextField(null=True)


class SentenceToken(BaseModel):
    """Token-level translation breakdown."""

    sentence = ForeignKeyField(
        Sentence, backref="tokens", on_delete="CASCADE"
    )
    position = IntegerField()  # Word order index
    target_token = CharField()  # Exact word in target sentence
    source_token = CharField()  # Direct meaning in source language
    grammatical_note = CharField(null=True)  # e.g., "Accusatief vrouwelijk"


class UniversalDictionary:
    """Neutral controller for managing multi-language learning databases."""

    def __init__(self, db_path: str | Path = "polyglot_learning.db"):
        self.db = db
        self.db.init(db_path)
        self.db.connect(reuse_if_open=True)
        self.db.create_tables(
            [Category, Word, WordCategory, Sentence, SentenceToken]
        )

    def add_word(
        self,
        target_lang: str,
        source_lang: str,
        lemma: str,
        primary_translation: str,
        part_of_speech: str,
        categories: list[str] | None = None,
        **kwargs,
    ) -> Word:
        """Add a vocabulary entry for any target/source language pair."""
        with self.db.atomic():
            word = Word.create(
                target_lang=target_lang.lower(),
                source_lang=source_lang.lower(),
                lemma=lemma,
                primary_translation=primary_translation,
                part_of_speech=part_of_speech,
                **kwargs,
            )

            if categories:
                for cat_name in categories:
                    category, _ = Category.get_or_create(
                        name=cat_name, language_code=source_lang.lower()
                    )
                    WordCategory.create(word=word, category=category)
            return word

    def add_sentence(
        self,
        word: Word,
        target_text: str,
        source_literal: str,
        source_fluent: str,
        token_mapping: list[tuple[str, str, str | None]] | None = None,
    ) -> Sentence:
        """Attach an example sentence with token-by-token alignment."""
        with self.db.atomic():
            sentence = Sentence.create(
                word=word,
                target_text=target_text,
                source_literal=source_literal,
                source_fluent=source_fluent,
            )

            if token_mapping:
                for pos, (t_tok, s_tok, note) in enumerate(token_mapping):
                    SentenceToken.create(
                        sentence=sentence,
                        position=pos,
                        target_token=t_tok,
                        source_token=s_tok,
                        grammatical_note=note,
                    )
            return sentence

    def get_vocabulary(
        self, target_lang: str, source_lang: str = "nl"
    ) -> list[dict]:
        """Fetch all vocabulary entries matching a specific language pair."""
        query = Word.select().where(
            (Word.target_lang == target_lang.lower())
            & (Word.source_lang == source_lang.lower())
        )

        entries = []
        for word in query:
            entries.append(
                {
                    "lemma": word.lemma,
                    "translation": word.primary_translation,
                    "part_of_speech": word.part_of_speech,
                    "categories": [wc.category.name for wc in word.categories],
                    "sentence_count": word.sentences.count(),
                }
            )
        return entries
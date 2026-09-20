"""Universal Multilingual Dictionary and Sentence Database using Peewee ORM."""

import re
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
    """Token-level translation breakdown with optional database word linkage."""

    sentence = ForeignKeyField(
        Sentence, backref="tokens", on_delete="CASCADE"
    )
    word = ForeignKeyField(Word, backref="sentence_tokens", null=True, on_delete="SET NULL")
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

    @staticmethod
    def _normalize_token(token: str) -> str:
        return re.sub(r"[^\w]", "", str(token or "").lower())

    def _link_token_to_word(self, word_record: Word, target_token: str) -> Word | None:
        target_name = self._normalize_token(target_token)
        if not target_name:
            return None

        for candidate in Word.select().where(
            (Word.target_lang == word_record.target_lang)
            & (Word.source_lang == word_record.source_lang)
        ):
            candidate_name = self._normalize_token(candidate.lemma)
            if candidate_name == target_name:
                return candidate
        for candidate in Word.select().where(
            (Word.target_lang == word_record.target_lang)
            & (Word.source_lang == word_record.source_lang)
        ):
            candidate_name = self._normalize_token(candidate.lemma)
            if target_name in candidate_name or candidate_name in target_name:
                return candidate
        return None

    def sync_sentence_tokens(
        self,
        sentence: Sentence,
        token_mapping: list[tuple[str, str, str | None]] | None = None,
    ) -> None:
        """Ensure every sentence token is related to a matching per-word record when possible."""
        if token_mapping is None:
            target_tokens = re.findall(r"\b[\w'-]+\b", sentence.target_text)
            source_tokens = re.findall(r"\b[\w'-]+\b", sentence.source_literal)
            if len(target_tokens) == len(source_tokens):
                token_mapping = [
                    (t_tok, s_tok, None)
                    for t_tok, s_tok in zip(target_tokens, source_tokens)
                ]
            else:
                token_mapping = [(token, token, None) for token in target_tokens]

        SentenceToken.delete().where(SentenceToken.sentence == sentence).execute()
        for pos, (t_tok, s_tok, note) in enumerate(token_mapping):
            linked_word = self._link_token_to_word(sentence.word, t_tok)
            SentenceToken.create(
                sentence=sentence,
                word=linked_word,
                position=pos,
                target_token=t_tok,
                source_token=s_tok,
                grammatical_note=note,
            )

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
            self.sync_sentence_tokens(sentence, token_mapping=token_mapping)
            return sentence

    def literal_word_for_word(self, target_text: str, source_fluent: str) -> str:
        """Create a literal gloss based on the source-language translation for grammatical comparison."""
        if not target_text:
            return source_fluent or ""
        target_tokens = re.findall(r"\b[\w'-]+\b", target_text)
        if not target_tokens:
            return source_fluent or ""
        return " ".join(target_tokens[: len(target_tokens)])

    def update_sentence(
        self,
        sentence: Sentence,
        target_text: str | None = None,
        source_literal: str | None = None,
        source_fluent: str | None = None,
        token_mapping: list[tuple[str, str, str | None]] | None = None,
    ) -> Sentence:
        """Update sentence content and refresh token-to-word links."""
        if target_text is not None:
            sentence.target_text = target_text
        if source_literal is not None:
            sentence.source_literal = source_literal
        if source_fluent is not None:
            sentence.source_fluent = source_fluent
        sentence.save()
        self.sync_sentence_tokens(sentence, token_mapping=token_mapping)
        return sentence

    def get_word(
        self, target_lang: str, source_lang: str, lemma: str
    ) -> Word | None:
        """Return the matching vocabulary record or None."""
        try:
            return Word.get(
                (Word.target_lang == target_lang.lower())
                & (Word.source_lang == source_lang.lower())
                & (Word.lemma == lemma)
            )
        except Word.DoesNotExist:
            return None

    def update_word(
        self,
        word: Word,
        *,
        target_lang: str | None = None,
        source_lang: str | None = None,
        lemma: str | None = None,
        primary_translation: str | None = None,
        part_of_speech: str | None = None,
        categories: list[str] | None = None,
        **kwargs,
    ) -> Word:
        """Update an existing word and reassign categories."""
        if target_lang is not None:
            word.target_lang = target_lang.lower()
        if source_lang is not None:
            word.source_lang = source_lang.lower()
        if lemma is not None:
            word.lemma = lemma
        if primary_translation is not None:
            word.primary_translation = primary_translation
        if part_of_speech is not None:
            word.part_of_speech = part_of_speech
        for key, value in kwargs.items():
            if value is not None:
                setattr(word, key, value)
        word.save()

        if categories is not None:
            WordCategory.delete().where(WordCategory.word == word).execute()
            for cat_name in categories:
                category, _ = Category.get_or_create(
                    name=cat_name, language_code=word.source_lang.lower()
                )
                WordCategory.create(word=word, category=category)
        return word

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

    def get_sentences(
        self, target_lang: str, source_lang: str = "nl"
    ) -> list[dict]:
        """Fetch all example sentences for a language pair."""
        query = Word.select().where(
            (Word.target_lang == target_lang.lower())
            & (Word.source_lang == source_lang.lower())
        )

        sentences = []
        for word in query:
            for sentence in word.sentences:
                sentences.append(
                    {
                        "lemma": word.lemma,
                        "translation": word.primary_translation,
                        "target_text": sentence.target_text,
                        "source_literal": sentence.source_literal,
                        "source_fluent": sentence.source_fluent,
                        "notes": sentence.notes,
                        "sentence_id": sentence.id,
                    }
                )
        return sentences
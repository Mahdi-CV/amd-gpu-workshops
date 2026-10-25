"""
tests/test_words.py
-------------------
Unit tests for words.py — word list generation and utilities.
"""

import pytest
from words import generate, generate_from_pool, words_in, EASY_WORDS, MEDIUM_WORDS, HARD_WORDS, ALL_WORDS


class TestGenerate:
    def test_returns_correct_word_count(self):
        text = generate(10, "easy")
        assert len(text.split()) == 10

    def test_returns_string(self):
        assert isinstance(generate(5), str)

    def test_all_difficulties(self):
        for diff in ("easy", "medium", "hard", "mixed"):
            result = generate(5, diff)
            assert len(result.split()) == 5

    def test_words_come_from_correct_pool_easy(self):
        text = generate(100, "easy")
        for word in text.split():
            assert word in EASY_WORDS

    def test_words_come_from_correct_pool_hard(self):
        text = generate(50, "hard")
        for word in text.split():
            assert word in HARD_WORDS

    def test_large_count(self):
        # generate() uses random.choices so count can exceed pool size
        text = generate(500, "easy")
        assert len(text.split()) == 500

    def test_single_word(self):
        text = generate(1)
        assert len(text.split()) == 1
        assert " " not in text


class TestGenerateFromPool:
    def test_uses_provided_pool(self):
        pool = ["alpha", "beta", "gamma"]
        text = generate_from_pool(pool, 10)
        for word in text.split():
            assert word in pool

    def test_falls_back_on_empty_pool(self):
        # Empty pool → falls back to generate()
        text = generate_from_pool([], 5)
        assert len(text.split()) == 5

    def test_count_respected(self):
        pool = ["word"]
        text = generate_from_pool(pool, 7)
        assert len(text.split()) == 7


class TestWordsIn:
    def test_splits_correctly(self):
        assert words_in("the quick fox") == ["the", "quick", "fox"]

    def test_single_word(self):
        assert words_in("hello") == ["hello"]

    def test_empty_string(self):
        assert words_in("") == []

    def test_round_trip(self):
        original = generate(20)
        assert words_in(original) == original.split()


class TestWordLists:
    def test_no_duplicates_in_easy(self):
        assert len(EASY_WORDS) == len(set(EASY_WORDS))

    def test_no_duplicates_in_medium(self):
        assert len(MEDIUM_WORDS) == len(set(MEDIUM_WORDS))

    def test_no_duplicates_in_hard(self):
        assert len(HARD_WORDS) == len(set(HARD_WORDS))

    def test_all_lowercase(self):
        for word in ALL_WORDS:
            assert word == word.lower(), f"'{word}' is not lowercase"

    def test_no_spaces_in_words(self):
        for word in ALL_WORDS:
            assert " " not in word, f"'{word}' contains a space"

    def test_all_non_empty(self):
        for word in ALL_WORDS:
            assert len(word) > 0

    def test_pools_have_reasonable_size(self):
        assert len(EASY_WORDS) >= 50
        assert len(MEDIUM_WORDS) >= 50
        assert len(HARD_WORDS) >= 50

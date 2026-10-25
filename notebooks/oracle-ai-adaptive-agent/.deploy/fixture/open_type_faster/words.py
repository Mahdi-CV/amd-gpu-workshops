"""
words.py
--------
Word lists and text generation for typing tests.

Three difficulty tiers are provided so tests can be tailored to skill level.
The generate() function is the single public interface used by the rest of
the app; everything else is implementation detail.
"""

import random
from typing import Literal

# ── Word lists ─────────────────────────────────────────────────────────────────

# High-frequency short words — great for building raw speed.
EASY_WORDS: list[str] = [
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "it",
    "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
    "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
    "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "no", "just", "him", "know",
    "take", "into", "your", "good", "some", "could", "them", "see", "than",
    "now", "look", "only", "come", "over", "think", "also", "back", "after",
    "use", "two", "how", "our", "work", "well", "way", "even", "new", "want",
    "any", "give", "day", "most", "us", "long", "own", "right", "old", "last",
    "still", "never", "move", "every", "must", "here", "turn", "help", "same",
    "should", "under", "while", "being", "set", "put", "end", "why", "ask",
    "big", "such", "next", "home", "read", "need", "hold", "act", "add",
    "real", "air", "land", "let", "men", "too", "does", "off", "few", "got",
]

# Mid-length everyday words — tests rhythm and finger transitions.
MEDIUM_WORDS: list[str] = [
    "people", "because", "these", "great", "little", "world", "large",
    "often", "second", "again", "another", "thought", "through", "always",
    "number", "house", "point", "small", "order", "place", "story", "found",
    "those", "every", "might", "since", "tell", "three", "change", "light",
    "animal", "mother", "father", "picture", "build", "earth", "where",
    "during", "school", "family", "follow", "example", "letter", "along",
    "below", "paper", "music", "group", "river", "north", "south", "plant",
    "state", "cover", "color", "front", "above", "other", "after",
    "before", "early", "ready", "clear", "close", "class", "power",
    "drive", "stand", "break", "bring", "start", "carry", "watch", "write",
    "table", "chair", "floor", "store", "money", "thank", "today", "until",
    "voice", "heart", "blood", "night", "short", "horse", "model",
    "large", "heavy", "white", "black", "young", "brown", "field", "piece",
    "plain", "price", "quite", "reach", "round", "sense", "serve", "seven",
    "shall", "share", "shape", "shown", "since", "sleep", "small", "sound",
    "speak", "speed", "spend", "stone", "study", "style", "sugar",
    "sweet", "taken", "taste", "teach", "teeth", "thick", "thing",
    "think", "those", "throw", "tired", "touch", "trade", "treat", "trial",
    "tried", "truth", "twice", "under", "upper", "usual", "visit",
    "waste", "water", "which", "while", "whose",
    "woman", "women", "world", "worry", "worse", "worst", "worth", "would",
    "wrong", "years",
]

# Long or tricky words — tests accuracy over raw speed.
HARD_WORDS: list[str] = [
    "phenomenon", "necessary", "accommodate", "occurrence", "separate",
    "definitely", "beginning", "receive", "believe", "achieve", "argument",
    "conscience", "conscious", "category", "beautiful", "immediately",
    "independent", "embarrass", "environment", "experience", "government",
    "interesting", "knowledge", "language", "particularly", "probably",
    "throughout", "themselves", "understanding", "whatever", "although",
    "business", "community", "consider", "continue", "describe", "different",
    "following", "including", "industry", "information", "international",
    "national", "particular", "personal", "possible", "problem", "program",
    "question", "remember", "several", "something", "sometimes", "together",
    "whether", "already", "between", "children", "country", "develop",
    "general", "however", "important", "instead", "looking", "million",
    "morning", "nothing", "outside", "perhaps", "quickly", "results",
    "service", "society", "special", "started", "student", "support",
    "system", "usually", "without", "working", "yourself", "approach",
    "available", "complete", "decision", "directly", "discover", "distance",
    "economic", "employee", "everyone", "exercise", "expected", "football",
    "function", "happened", "hospital", "increase", "industry", "language",
    "material", "mountain", "movement", "multiple", "negative", "neighbor",
    "ordinary", "organize", "overcome", "position", "possible", "practice",
    "pressure", "previous", "probably", "producer", "property", "purchase",
    "quantity", "question", "recently", "relation", "religion", "research",
    "resource", "response", "sentence", "shortage", "shoulder", "singular",
    "situated", "solution", "somebody", "strength", "suddenly", "supplied",
    "surprise", "teaching", "thousand", "together", "tomorrow", "transfer",
    "treasure", "treatment", "triangle", "ultimate", "universe", "valuable",
    "variable", "velocity", "whatever", "whenever", "wherever", "yourself",
]

# Deduplicate each list while preserving insertion order.
# dict.fromkeys() is the idiomatic, order-preserving deduplication idiom.
EASY_WORDS   = list(dict.fromkeys(EASY_WORDS))
MEDIUM_WORDS = list(dict.fromkeys(MEDIUM_WORDS))
HARD_WORDS   = list(dict.fromkeys(HARD_WORDS))

# All tiers combined — used when mode is "mixed"
ALL_WORDS: list[str] = list(dict.fromkeys(EASY_WORDS + MEDIUM_WORDS + HARD_WORDS))

Difficulty = Literal["easy", "medium", "hard", "mixed"]

# ── Public interface ───────────────────────────────────────────────────────────

def generate(count: int, difficulty: Difficulty = "mixed") -> str:
    """
    Return a space-separated string of *count* random words at the requested
    difficulty level.  This is the text the user will be asked to type.
    """
    pool = _pool_for(difficulty)
    # sample with replacement so we can always fill large counts
    chosen = random.choices(pool, k=count)
    return " ".join(chosen)


def generate_from_pool(pool: list[str], count: int) -> str:
    """
    Build a test string from a caller-supplied word pool.
    Used by practice mode to weight towards the user's weak words.
    """
    if not pool:
        return generate(count)
    chosen = random.choices(pool, k=count)
    return " ".join(chosen)


def words_in(text: str) -> list[str]:
    """Split a test string back into individual words."""
    return text.split()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pool_for(difficulty: Difficulty) -> list[str]:
    mapping = {
        "easy":   EASY_WORDS,
        "medium": MEDIUM_WORDS,
        "hard":   HARD_WORDS,
        "mixed":  ALL_WORDS,
    }
    return mapping[difficulty]

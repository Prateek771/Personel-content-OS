"""Local semantic similarity computation using token stemming and cosine vectorization."""

import math
import re
from collections import Counter


def _stem(word: str) -> str:
    """Lightweight rule-based suffix normalizer for common English inflections."""
    w = word.lower()
    for suffix in ["ing", "tion", "ed", "es", "s"]:
        if w.endswith(suffix) and len(w) > len(suffix) + 3:
            return w[:-len(suffix)]
    return w


def _tokenize(text: str) -> list[str]:
    """Tokenize text into normalized stemmed words and adjacent word pairs."""
    words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
    stopwords = {"the", "a", "an", "in", "on", "for", "and", "or", "to", "with", "at", "by", "from", "is", "are", "of"}
    stemmed_words = [_stem(w) for w in words if w not in stopwords]

    # Include stemmed bigrams for compound terms (e.g. "context_protocol", "ai_agent")
    bigrams = [f"{stemmed_words[i]}_{stemmed_words[i+1]}" for i in range(len(stemmed_words)-1)]
    return stemmed_words + bigrams


def compute_cosine_similarity(text_a: str, text_b: str) -> float:
    """Calculate cosine similarity between two text strings based on term frequencies."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)

    if not tokens_a or not tokens_b:
        return 0.0

    vec_a = Counter(tokens_a)
    vec_b = Counter(tokens_b)

    intersection = set(vec_a.keys()) & set(vec_b.keys())
    numerator = sum(vec_a[x] * vec_b[x] for x in intersection)

    sum_a = sum(val ** 2 for val in vec_a.values())
    sum_b = sum(val ** 2 for val in vec_b.values())
    denominator = math.sqrt(sum_a) * math.sqrt(sum_b)

    if not denominator:
        return 0.0
    return float(numerator / denominator)

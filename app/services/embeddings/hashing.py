"""Local hashing-vectorizer embeddings: deterministic, offline, no API key.

A classic feature-hashing bag-of-words encoder: stopwords removed, unigrams
plus bigrams, sub-linear term frequency, signed hashing, L2-normalised.

Cosine similarity over these vectors measures *lexical* overlap, not semantic
similarity, so a question phrased with different vocabulary than the source
text scores poorly. It also has no corpus-wide IDF, so a short question against
a long chunk is penalised by length normalisation. It exists so the whole
pipeline runs, is testable and is measurable with no network access - use
`EMBEDDING_PROVIDER=openai` for semantic retrieval, and see the eval numbers in
the README for what the difference costs.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

from app.services.embeddings.base import Embedder

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# There is no corpus-wide IDF to down-weight common words here, so the most
# frequent ones are removed outright. Without this, a question and a document
# title match on "the"/"is"/"of" and the title chunk outranks the chunk that
# actually answers the question.
_STOPWORD_TEXT = (
    "a an and are as at be been being but by can could did do does doing done for from had "
    "has have having he her hers him his how i if in into is it its itself me my of on or "
    "our ours out over own she should so some such than that the their theirs them then "
    "there these they this those to too under up us was we were what when where which while "
    "who whom why will with would you your yours "
)
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def _tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


def _features(tokens: Sequence[str]) -> Counter[str]:
    counts: Counter[str] = Counter(tokens)
    counts.update(f"{first}_{second}" for first, second in pairwise(tokens))
    return counts


class HashingEmbedder(Embedder):
    name = "hashing"

    def __init__(self, dimensions: int = 1536, model: str = "local-hashing-v1") -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be >= 8")
        self.dimensions = dimensions
        self.model = model

    def encode(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, frequency in _features(_tokenize(text)).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            bucket = raw % self.dimensions
            sign = 1.0 if (raw >> 63) & 1 else -1.0
            vector[bucket] += sign * (1.0 + math.log(frequency))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return self._sentinel()
        return [value / norm for value in vector]

    def _sentinel(self) -> list[float]:
        """Unit vector for text with no features (empty or punctuation only).

        The weight is spread over every dimension with alternating signs rather
        than parked on one basis vector, so it does not coincide with any real
        feature bucket and its similarity to ordinary text stays near zero.
        """
        magnitude = 1.0 / math.sqrt(self.dimensions)
        return [magnitude if index % 2 == 0 else -magnitude for index in range(self.dimensions)]

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.encode(text) for text in texts]

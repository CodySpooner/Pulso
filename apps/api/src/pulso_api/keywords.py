"""Keyword candidates from a product's titles (KW-1, DEC-281): pure functions, no I/O.

A candidate is a run of 1–4 words inside a title, between stop words, punctuation and dropped
tokens. Its relevance is half the share of the product's distinct titles that hold the phrase and
half the mean share that hold each of its words (titles often reorder the same words), times a
length weight: one word is a broad search, so it counts half. Only the owner's confirmation makes a
candidate a product keyword (DEC-245 d: a title match alone is a guessed link)."""

import re
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable
from typing import NamedTuple

from pulso_core.taxonomy import fold

Key = tuple[str, ...]

# ponytail: guesses; tune them once the owner's confirmations show which candidates get picked.
WEIGHT = {1: 0.5, 2: 0.85, 3: 1.0, 4: 1.0}
LIMIT = 12
STOP = frozenset(
    """a about above after all an and any are as at be by can for from has have in into is it
    its of off on onto or our out over per so than that the their them then these this those to
    up us via vs we what when which while who will with within without you your
    new hot sale free shipping fast best top quality pcs pc pack piece pieces x""".split()
)
TOKEN = re.compile(r"[^\W_]+(?:['-][^\W_]+)*")
# Punctuation, or a dash between spaces, ends a phrase; a hyphen inside a word doesn't.
BREAK = re.compile(r"[^\w\s'-]|_|\s[-']+\s|\s[-']+$|^[-']+\s")
QUANTITY = re.compile(r"\d+(?:\.\d+)?(?:pcs?|pack|ft|in|inch|cm|mm|m|ml|l|oz|lbs?|kg|g|mah|w|v|x)?")


class Gram(NamedTuple):
    keyword: str  # the spelling most titles use
    relevance: float  # 0–1
    titles: int  # how many distinct titles hold it


def normalize(text: str) -> str:
    """Casefolded, a curly apostrophe made straight, spacing collapsed."""
    return " ".join(text.replace("’", "'").casefold().split())


def tokens(text: str) -> list[str]:
    return TOKEN.findall(normalize(text))


def key(keyword: str) -> Key:
    """A keyword's identity: its words with a trailing plural folded, so "lamps" is "lamp"."""
    return tuple(fold(word) for word in tokens(keyword))


def phrases(title: str) -> list[list[str]]:
    """The runs of kept words in a title."""
    runs: list[list[str]] = []
    for part in BREAK.split(normalize(title)):
        run: list[str] = []
        for word in tokens(part):
            if word in STOP or len(word) < 2 or QUANTITY.fullmatch(word):
                if run:
                    runs.append(run)
                run = []
            else:
                run.append(word)
        if run:
            runs.append(run)
    return runs


def grams(titles: Iterable[str]) -> dict[Key, Gram]:
    """Every candidate in the titles, scored. Titles that differ only in case or spacing count once."""
    distinct = list(dict.fromkeys(normalize(title) for title in titles if title.strip()))
    held: Counter[Key] = Counter()
    word_held: Counter[str] = Counter()
    spellings: defaultdict[Key, Counter[str]] = defaultdict(Counter)
    for title in distinct:
        seen: dict[Key, str] = {}
        for run in phrases(title):
            for n in WEIGHT:
                for i in range(len(run) - n + 1):
                    words = run[i : i + n]
                    seen.setdefault(tuple(fold(word) for word in words), " ".join(words))
        for gram, spelling in seen.items():
            held[gram] += 1
            spellings[gram][spelling] += 1
            if len(gram) == 1:
                word_held[gram[0]] += 1
    n = len(distinct)

    def relevance(gram: Key, count: int) -> float:
        words = sum(word_held[word] for word in gram) / len(gram)
        return round((count + words) / 2 / n * WEIGHT[len(gram)], 3)

    return {
        gram: Gram(spellings[gram].most_common(1)[0][0], relevance(gram, count), count)
        for gram, count in held.items()
    }


def suggest(
    scored: dict[Key, Gram], skip: Collection[Key] = (), limit: int = LIMIT
) -> list[tuple[str, float]]:
    """The best candidates not in `skip`. A phrase that only ever appears inside one longer
    phrase is left out: the longer one says the same, with no less evidence."""
    inside = {
        part
        for gram, found in scored.items()
        for part in (gram[1:], gram[:-1])
        if len(gram) > 1 and scored[part].titles <= found.titles
    }
    keep = [found for gram, found in scored.items() if gram not in inside and gram not in skip]
    keep.sort(key=lambda found: (-found.relevance, -len(found.keyword.split()), found.keyword))
    return [(found.keyword, found.relevance) for found in keep[:limit]]

import pytest

from pulso_api.keywords import grams, key, normalize, suggest

# KW-1 candidates (DEC-281): phrases from a product's titles, scored by the share of titles that
# hold them, weighted by length. Pure functions, no database.

LAMP = [
    "Sunset projection lamp with 16 colour modes and remote",
    "Sunset Projection Lamp, 16 Colors, USB",
    "LED Sunset Lamp Projector for Bedroom",
    "Sunset Projection Lamp – Rainbow Night Light",
]


def words(candidates: list[tuple[str, float]]) -> list[str]:
    return [keyword for keyword, _ in candidates]


def test_the_shared_phrase_leads_and_its_inner_pieces_fold_into_it() -> None:
    scored = grams(LAMP)
    top = suggest(scored)
    # The phrase is in 3 of 4 titles and its words in 4, 3 and 4: (0.75 + 11/12) / 2, full weight.
    assert top[0] == ("sunset projection lamp", 0.833)
    # Only ever inside the 3-word phrase, so they add nothing: suppressed from the list.
    assert "projection lamp" not in words(top)
    assert "sunset projection" not in words(top)
    # In every title, but one word is a broad search: half weight.
    assert ("sunset", 0.5) in top
    # Still scored, so a decided keyword reads its relevance.
    assert scored[key("projection lamp")].relevance == pytest.approx(
        (0.75 + 0.875) / 2 * 0.85, abs=1e-3
    )


def test_titles_that_reorder_the_words_still_rank_the_full_phrase_above_single_words() -> None:
    scored = grams(
        [
            "Magnetic Car Phone Mount, 360° Rotation, Strong Magnet for iPhone",
            "Car Phone Holder Magnetic Dashboard Mount",
            "Magnetic Phone Car Mount Vent Clip",
        ]
    )
    top = words(suggest(scored, limit=50))
    assert top.index("magnetic car phone mount") < top.index("car") < top.index("strong magnet")
    assert scored[key("magnetic car phone mount")].titles == 1  # the exact phrase, once


def test_stop_words_numbers_and_listing_noise_never_make_a_keyword() -> None:
    top = words(suggest(grams(["New Hot Sale 2pcs Free Shipping Pet Hair Remover Roller 2024"])))
    assert top == ["pet hair remover roller"]
    lamp = words(suggest(grams(LAMP), limit=50))
    for word in ("with", "and", "for", "16"):
        assert not any(
            k == word or k.startswith(f"{word} ") or k.endswith(f" {word}") for k in lamp
        )
    assert grams(["2024 New Hot", "   "]) == {}
    assert grams([]) == {}


def test_a_trailing_plural_is_one_keyword_spelled_the_most_common_way() -> None:
    scored = grams(["LED Strip Lights 50ft", "Smart LED strip lights", "LED strip light for room"])
    top = suggest(scored)
    assert top[0] == ("led strip lights", 1.0)  # all three titles; "lights" twice, "light" once
    assert "led strip light" not in words(top)


def test_punctuation_and_a_spaced_dash_split_phrases_but_inner_hyphens_stay() -> None:
    assert words(suggest(grams(["Anti-Slip Yoga Mat - Extra Thick"]))) == [
        "anti-slip yoga mat",
        "extra thick",
    ]
    assert words(suggest(grams(["Women’s Heated Eye Mask"]))) == ["women's heated eye mask"]


def test_a_title_repeated_in_another_case_counts_once() -> None:
    assert suggest(grams(["Heated Eye Mask", "heated eye MASK"])) == [("heated eye mask", 1.0)]


def test_suggest_skips_decided_keywords_by_key_and_stops_at_the_limit() -> None:
    scored = grams(LAMP)
    rest = words(suggest(scored, skip={key("Sunset Projection Lamps")}))
    assert "sunset projection lamp" not in rest
    assert rest[:2] == ["lamp", "sunset"]  # a tie at 0.5, A to Z
    assert len(suggest(scored, limit=3)) == 3
    # Best first, then the longer phrase, then A to Z.
    ordered = suggest(scored, limit=50)
    assert ordered == sorted(ordered, key=lambda c: (-c[1], -len(c[0].split()), c[0]))


def test_normalize_and_key() -> None:
    assert normalize("  Sunset   LAMP\n") == "sunset lamp"
    assert normalize("Women’s mask") == "women's mask"
    assert key("Sunset Lamps") == key("sunset lamp") == ("sunset", "lamp")

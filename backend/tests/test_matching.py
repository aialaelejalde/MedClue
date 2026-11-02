"""Test medication name, strength, and form comparisons with CIMA presentations."""

import pytest

from medclue_api.matching import (
    compare_forms,
    compare_strengths,
    find_presentation_matches,
    normalize_name
)
from medclue_api.schemas import CimaPresentation, MedicationCandidate


NAME_VARIANTS = (
    "Example-Plus", "Example+Plus", "Example/Plus", "Example.Plus",
    "Example_Plus", "ExamplePlus", "Example Plus",
)


@pytest.fixture
def candidate():
    return MedicationCandidate(name="Example", strength="500 mg", form="tablet")


@pytest.fixture
def presentation():
    return CimaPresentation(
        name="EXAMPLE 500 mg COMPRIMIDOS EFG",
        strength="500 mg",
        form="comprimidos",
        registration_number="000001",
        national_code="000002",
    )


def test_name_normalization_keeps_distinctive_words_and_punctuation():
    assert normalize_name("  MÉDICINE   FORTE ") == "medicine forte"
    assert normalize_name("Example Plus") != normalize_name("Example")
    assert normalize_name("Example-Plus") != normalize_name("Example Plus")


@pytest.mark.parametrize(
    "first, second, expected",
    [
        ("tablet", "comprimidos", True),
        ("film-coated tablet", "comprimidos recubiertos con película", True),
        ("prolonged-release tablet", "comprimidos de liberación prolongada", True),
        ("gastro-resistant tablet", "comprimidos gastrorresistentes", True),
        ("hard capsule", "cápsulas duras", True),
        ("oral solution", "solución oral", True),
        ("tablet", "capsule", False),
        ("oral solution", "oral suspension", False),
        ("oral solution", "solution for injection", False),
        ("cream", "ointment", False),
        ("gel", "cream", False),
        ("tablet", "film-coated tablet", None),
        ("comprimidos", "comprimidos recubiertos con película", None),
        ("tablet", "prolonged-release tablet", None),
        ("tablet", "gastro-resistant tablet", None),
        ("film-coated tablet", "prolonged-release tablet", None),
        ("prolonged-release tablet", "gastro-resistant tablet", None),
        ("capsule", "hard capsule", None),
        ("unlisted form", "tablet", None),
        ("unlisted form", "another unlisted form", None),
        (None, "tablet", None),
        (" ", "tablet", None),
    ],
)
def test_form_comparison_handles_uncertainty_and_order(first, second, expected):
    """Check that uncertain form comparisons return None and that changing the order does not affect the result."""
    assert compare_forms(first, second) is expected
    assert compare_forms(second, first) is expected


@pytest.mark.parametrize(
    "first, second, expected",
    [
        ("1 g", "1000 mg", True),
        ("0,5 g", "500 mg", True),
        ("500 µg", "0.5 mg", True),
        ("500 microgramos", "500 mcg", True),
        ("875 mg + 125 mg", "875 mg/125 mg", True),
        ("875 mg + 125 mg", "0.875 g/0.125 g", True),
        ("1 g + 125 mg", "1000 mg/125 mg", True),
        ("1 g/125 mg", "1000 mg + 125 mg", True),
        ("875 MG / 125 MG", "875 mg + 125 mg", True),
        ("1 mg + 2 mg + 3 mg", "1 mg/2 mg/3 mg", True),
        ("1 mg/2 mg + 3 mg", "1 mg + 2 mg + 3 mg", True),
        ("875 mg/125 mg", "875 mg + 250 mg", False),
        ("875 mg/125 mg", "125 mg + 875 mg", False),
        ("875 mg/125 mg", "875 mg", False),
        ("100 mg/5 ml", "20 mg/ml", True),
        ("100 mg/5 ml", "0.1 g/5 ml", True),
        ("1 g/l", "1 mg/ml", True),
        ("1 mg/3 ml", "2 mg/6 ml", True),
        ("100 mg/5 ml", "100 mg/ml", False),
        ("100 mg/5 ml", "100 mg + 5 mg", False),
        ("100 mg/5 ml + 25 mg/5 ml", "20 mg/ml + 5 mg/ml", True),
        ("1 mg/3 ml", "0.3333333333333333333333333333 mg/ml", False),
        ("875/125 mg", "875 mg + 125 mg", None),
        ("875 mg/125", "875 mg + 125 mg", None),
        ("875 mg/125 mg/5 ml", "175 mg/ml + 25 mg/ml", None),
        ("875 mg + 125 mg/5 ml", "175 mg/ml + 25 mg/ml", None),
        ("100 mg/5 ml/25 mg/5 ml", "20 mg/ml + 5 mg/ml", None),
        ("875 mg/", "875 mg", None),
        ("875 mg +", "875 mg", None),
        ("100 mg/ml + 25 mg", "100 mg/ml + 25 mg", None),
        ("1.000 mg/125 mg", "1000 mg + 125 mg", None),
        ("5%", "50 mg/ml", None),
        ("10 mg/g", "10 mg + 1 g", None),
        ("12 mcg/h", "12 mcg/h", None),
        ("1 mg/0 ml", "1 mg/ml", None),
        ("0 mg/125 mg", "0 mg + 125 mg", None),
        ("-1 mg/125 mg", "1 mg + 125 mg", None),
        ("unknown", "unknown", None),
        (None, "500 mg", None),
        ("", "500 mg", None),
    ],
)
def test_strength_comparison_preserves_units_order_and_uncertainty(first, second, expected):
    assert compare_strengths(first, second) is expected
    assert compare_strengths(second, first) is expected


def test_one_fully_matching_presentation_can_be_verified(candidate, presentation):
    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified == presentation


def test_different_medication_names_do_not_match(candidate, presentation):
    other = presentation.model_copy(update={"name": "Another medicine"})
    result = find_presentation_matches(candidate, [other])

    assert result.presentations == []
    assert result.verified is None


def test_different_strengths_do_not_match(candidate, presentation):
    other = presentation.model_copy(update={"name": "Example", "strength": "250 mg"})
    result = find_presentation_matches(candidate, [other])

    assert result.presentations == []
    assert result.verified is None


def test_missing_candidate_form_prevents_verification(candidate, presentation):
    incomplete = candidate.model_copy(update={"form": None})
    result = find_presentation_matches(incomplete, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None


@pytest.mark.parametrize("candidate_name", NAME_VARIANTS)
@pytest.mark.parametrize("presentation_name", NAME_VARIANTS)
def test_name_variants_keep_possible_matches_and_require_strict_verification(candidate, presentation, candidate_name, presentation_name):
    suggestion = candidate.model_copy(update={"name": candidate_name})
    possible = presentation.model_copy(update={"name": presentation_name})
    result = find_presentation_matches(suggestion, [possible])

    assert result.presentations == [possible]
    if candidate_name == presentation_name:
        assert result.verified == possible
    else:
        assert result.verified is None


@pytest.mark.parametrize(
    "candidate_name, presentation_name",
    [
        ("Example - Plus", "ExamplePlus"),
        ("Example+Plus 500 mg tablets", "ExamplePlus 500 mg COMPRIMIDOS EFG"),
        ("ExamplePlus 500 mg tablets", "Example/Plus 500 mg COMPRIMIDOS EFG"),
    ],
)
def test_flexible_names_also_work_with_extra_spaces_and_full_cima_names(candidate, presentation, candidate_name, presentation_name):
    suggestion = candidate.model_copy(update={"name": candidate_name})
    possible = presentation.model_copy(update={"name": presentation_name})
    result = find_presentation_matches(suggestion, [possible])

    assert result.presentations == [possible]
    assert result.verified is None


def test_a_flexible_name_alternative_prevents_automatic_selection(candidate, presentation):
    suggestion = candidate.model_copy(update={"name": "Example-Plus"})
    exact = presentation.model_copy(update={"name": "Example-Plus 500 mg COMPRIMIDOS EFG"})
    flexible = presentation.model_copy(update={"name": "Example Plus", "national_code": "000003"})
    result = find_presentation_matches(suggestion, [exact, flexible])

    assert result.presentations == [exact, flexible]
    assert result.verified is None


@pytest.mark.parametrize(
    "strength, form", [("250 mg", "comprimidos"), ("500 mg", "capsule")]
)
@pytest.mark.parametrize("name", NAME_VARIANTS)
def test_flexible_names_do_not_override_incompatible_strengths_or_forms(candidate, presentation, strength, form, name):
    suggestion = candidate.model_copy(update={"name": name})
    incompatible = presentation.model_copy(update={"name": "Example Plus", "strength": strength, "form": form})
    result = find_presentation_matches(suggestion, [incompatible])

    assert result.presentations == []
    assert result.verified is None


@pytest.mark.parametrize(
    "form",
    [
        "film-coated tablet", "prolonged-release tablet",
        "gastro-resistant tablet", "unlisted form",
    ],
)
def test_uncertain_form_stays_possible_but_is_never_verified(candidate, form):
    specific = CimaPresentation(
        name=f"Example 500 mg {form}", strength="500 mg", form=form,
        registration_number="000001", national_code="000002",
    )
    result = find_presentation_matches(candidate, [specific])

    assert result.presentations == [specific]
    assert result.verified is None


def test_an_uncertain_alternative_prevents_automatic_selection(candidate, presentation):
    specific = CimaPresentation(
        name="Example", strength="500 mg", form="film-coated tablet",
        registration_number="000001", national_code="000003",
    )
    result = find_presentation_matches(candidate, [presentation, specific])

    assert result.presentations == [presentation, specific]
    assert result.verified is None


def test_two_exact_presentations_require_user_selection(candidate, presentation):
    another_pack = presentation.model_copy(update={"national_code": "000003"})
    result = find_presentation_matches(candidate, [presentation, another_pack])

    assert result.presentations == [presentation, another_pack]
    assert result.verified is None


def test_incompatible_form_is_excluded(candidate):
    incompatible = CimaPresentation(
        name="Example", strength="500 mg", form="capsule",
        registration_number="000001", national_code="000002",
    )
    result = find_presentation_matches(candidate, [incompatible])

    assert result.presentations == []
    assert result.verified is None


def test_equivalent_combination_can_match_a_full_cima_name():
    candidate = MedicationCandidate(
        name="Example", strength="875 mg + 125 mg", form="tablet"
    )
    presentation = CimaPresentation(
        name="EXAMPLE 875 mg/125 mg COMPRIMIDOS EFG",
        strength="875 mg/125 mg", form="comprimidos",
        registration_number="000001", national_code="000002",
    )
    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified == presentation


@pytest.mark.parametrize("strength", ["125 mg/875 mg", "875 mg/250 mg"])
def test_different_combination_cannot_be_verified(strength):
    candidate = MedicationCandidate(
        name="Example", strength="875 mg + 125 mg", form="tablet"
    )
    presentation = CimaPresentation(
        name="Example", strength=strength, form="comprimidos",
        registration_number="000001", national_code="000002",
    )
    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == []
    assert result.verified is None


@pytest.mark.parametrize("strength", [None, "875/125 mg", "5%"])
def test_unclear_strength_prevents_verification_even_with_one_result(strength):
    candidate = MedicationCandidate(name="Example", strength=strength, form="tablet")
    presentation = CimaPresentation(
        name="Example", strength="875 mg + 125 mg", form="comprimidos",
        registration_number="000001", national_code="000002",
    )
    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None

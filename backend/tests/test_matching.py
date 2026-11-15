"""Test medication name, strength, and form comparisons with CIMA presentations."""

import pytest

from medclue_api.matching import (
    compare_forms,
    compare_names,
    compare_strengths,
    find_presentation_matches,
    group_presentations,
    matches_search_name,
    normalize_name,
)
from medclue_api.schemas import CimaPresentation, MedicationCandidate


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


@pytest.mark.parametrize(
    "name, expected",
    [
        ("  MÉDICINE   FORTE ", "medicine forte"),
        ("Example-Plus", "example-plus"),
    ],
)
def test_name_normalization_keeps_distinctive_words_and_punctuation(name, expected):
    assert normalize_name(name) == expected


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


def test_medication_without_strength_remains_possible():
    candidate = MedicationCandidate(name="Vaporub", strength=None, form="ointment")
    presentation = CimaPresentation(
        name="VAPORUB POMADA",
        strength=None,
        form="pomada",
        registration_number="000001",
        national_code="000002",
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None


@pytest.mark.parametrize(
    "candidate_name, presentation_name, verified",
    [
        ("Example-Plus", "Example-Plus", True),
        ("  ÉXAMPLE PLUS ", "Example Plus", True),
        ("Example-Plus", "Example Plus", False),
        ("Example+Plus", "ExamplePlus", False),
        ("Example/Plus", "Example Plus", False),
        ("Example.Plus", "ExamplePlus", False),
        ("Example_Plus", "Example Plus", False),
    ],
)
def test_name_variants_keep_possible_matches_and_require_strict_verification(
    candidate, presentation, candidate_name, presentation_name, verified,
):
    suggestion = candidate.model_copy(update={"name": candidate_name})
    possible = presentation.model_copy(update={"name": presentation_name})
    result = find_presentation_matches(suggestion, [possible])

    assert result.presentations == [possible]
    if verified:
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


def test_flexible_names_prevent_automatic_verification(candidate, presentation):
    suggestion = candidate.model_copy(update={"name": "Example-Plus"})
    exact = presentation.model_copy(update={"name": "Example-Plus 500 mg COMPRIMIDOS EFG"})
    flexible = presentation.model_copy(update={"name": "Example Plus", "national_code": "000003"})
    result = find_presentation_matches(suggestion, [exact, flexible])

    assert result.presentations == [exact, flexible]
    assert result.verified is None


@pytest.mark.parametrize(
    "strength, form", [("250 mg", "comprimidos"), ("500 mg", "capsule")]
)
def test_flexible_names_do_not_override_incompatible_strengths_or_forms(candidate, presentation, strength, form):
    suggestion = candidate.model_copy(update={"name": "Example+Plus"})
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


def test_different_package_sizes_are_grouped_and_verified(candidate, presentation):
    another_pack = presentation.model_copy(update={"national_code": "000003"})
    result = find_presentation_matches(candidate, [presentation, another_pack])

    assert result.presentations == [presentation]
    assert result.verified == presentation


def test_identical_medications_with_different_registrations_require_selection(candidate, presentation):
    another = presentation.model_copy(update={"registration_number": "000004", "national_code": "000003"})
    result = find_presentation_matches(candidate, [presentation, another])

    assert result.presentations == [presentation, another]
    assert result.verified is None


@pytest.mark.parametrize("other", ["Example Plus", "Examples", "Another", "", " - "])
def test_name_comparison_keeps_distinctive_words(other):
    assert not compare_names("Example", other)


@pytest.mark.parametrize(
    "query, name, strength, form, expected",
    [
        ("Example-Plus", "EXAMPLE PLUS 500 mg COMPRIMIDOS EFG", "500 mg", "comprimidos", True),
        ("  Médicine   Plus ", "MEDICINE+PLUS 500 mg COMPRIMIDOS", "500 mg", "comprimidos", True),
        ("Example", "Example Forte 500 mg COMPRIMIDOS", "500 mg", "comprimidos", False),
        ("Example", "Another 500 mg COMPRIMIDOS", "500 mg", "comprimidos", False),
        ("Example", "Example 5% CREMA", "5%", "crema", True),
        ("Example", "Example 500 mg COMPRIMIDOS", None, None, True),
        ("Example", "Example CREMA", None, "crema", True),
        ("Example 500 mg tablets", "Example 500 mg COMPRIMIDOS EFG", "500 mg", "comprimidos", True),
        ("Example 2", "Example 2 500 mg COMPRIMIDOS", "500 mg", "comprimidos", True),
        ("Example+Plus", "ExamplePlus 875 mg/125 mg COMPRIMIDOS", "875 mg + 125 mg", "comprimidos", True),
    ],
)
def test_search_name_matches_cima_medication_names(query, name, strength, form, expected):
    medication = MedicationCandidate(name=name, strength=strength, form=form)

    assert matches_search_name(query, medication) is expected


@pytest.mark.parametrize(
    "changes",
    [
        {"registration_number": "000004"},
        {"name": "Another"},
        {"strength": "250 mg"},
        {"form": "capsule"},
        {"strength": None},
        {"form": None},
        {"active_ingredients": ["Different ingredient"]},
    ],
)
def test_grouping_keeps_different_medications_separate(presentation, changes):
    other = presentation.model_copy(update={**changes, "national_code": "000003"})

    assert group_presentations([presentation, other]) == [presentation, other]


def test_grouping_ignores_case_and_outer_spacing_but_keeps_first_code(presentation):
    other = presentation.model_copy(update={
        "name": presentation.name.lower(), "strength": " 500 MG ",
        "form": "COMPRIMIDOS", "national_code": "000003",
    })

    assert group_presentations([presentation, other, presentation]) == [presentation]


def test_grouping_packages_does_not_verify_uncertain_data(candidate, presentation):
    incomplete = candidate.model_copy(update={"strength": None})
    another_pack = presentation.model_copy(update={"national_code": "000003"})
    result = find_presentation_matches(incomplete, [presentation, another_pack])

    assert result.presentations == [presentation]
    assert result.verified is None


def test_different_strengths_remain_options_when_candidate_strength_is_unknown(candidate, presentation):
    incomplete = candidate.model_copy(update={"strength": None})
    other = presentation.model_copy(update={"name": "Example", "strength": "250 mg", "national_code": "000003"})
    result = find_presentation_matches(incomplete, [presentation, other])

    assert result.presentations == [presentation, other]
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


@pytest.mark.parametrize(
    "name, strength, form, official_name",
    [
        ("Aspirina C", "400 mg + 240 mg", "COMPRIMIDO EFERVESCENTE",
         "ASPIRINA C 400 mg/240 mg COMPRIMIDOS EFERVESCENTES"),
        ("Example", "20 mg/ml", "SOLUCION PARA PULVERIZACION NASAL",
         "EXAMPLE 100 mg/5 ml SOLUCION PARA PULVERIZACION NASAL"),
        ("Example 2", "500 mg", "tablet", "EXAMPLE 2 500 mg TABLETS"),
        ("Example", "500 mg", "film-coated tablet", "EXAMPLE 500 mg COMPRIMIDOS EFG"),
    ],
)
def test_matching_strength_and_form_in_cima_name_allow_verification(name, strength, form, official_name):
    candidate = MedicationCandidate(name=name, strength=strength, form=form)
    presentation = CimaPresentation(
        name=official_name, strength=strength, form=form,
        registration_number="000001", national_code="000002",
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified == presentation


@pytest.mark.parametrize(
    "candidate_strength, official_strength, candidate_form, official_form, official_name",
    [
        ("5%", "5%", "cream", "CREMA", "EXAMPLE 5% CREMA"),
        ("500 mg", None, "tablet", None, "EXAMPLE 500 mg COMPRIMIDOS"),
        ("400 mg + 240 mg", "400 mg + 240 mg", "effervescent tablet",
         "COMPRIMIDO EFERVESCENTE", "EXAMPLE 400 mg/240 mg COMPRIMIDOS EFERVESCENTES"),
    ],
)
def test_unrecognized_or_missing_fields_do_not_discard_full_official_names(candidate_strength, official_strength, candidate_form, official_form, official_name):
    candidate = MedicationCandidate(name="Example", strength=candidate_strength, form=candidate_form)
    presentation = CimaPresentation(
        name=official_name, strength=official_strength, form=official_form,
        registration_number="000001", national_code="000002",
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None


@pytest.mark.parametrize("official_name", ["Example Forte 500 mg TABLETS", "Example C 500 mg TABLETS"])
def test_distinctive_name_words_are_not_ignored(candidate, official_name):
    presentation = CimaPresentation(
        name=official_name, strength="500 mg", form="tablet",
        registration_number="000001", national_code="000002",
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == []
    assert result.verified is None


@pytest.mark.parametrize(
    "strength, official_name",
    [
        ("100 mg", "EXAMPLE 100 mg / 5 ml SOLUCION"),
        ("400 mg", "EXAMPLE 400 mg + 240 mg TABLETS"),
    ],
)
def test_partial_strength_in_a_full_name_does_not_allow_verification(strength, official_name):
    candidate = MedicationCandidate(name="Example", strength=strength, form="tablet")
    presentation = CimaPresentation(
        name=official_name, strength=strength, form="tablet",
        registration_number="000001", national_code="000002",
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None


@pytest.mark.parametrize("structured_form", ["GRAGEAS", "film-coated tablet"])
def test_full_name_corroborates_a_generic_coating_without_equating_forms(structured_form):
    candidate = MedicationCandidate(name="Example", strength="100 mg", form="comprimidos recubiertos")
    presentation = CimaPresentation(
        name="EXAMPLE 0,1 g COMPRIMIDOS RECUBIERTOS EFG", strength="100 mg", form=structured_form,
        registration_number="000001", national_code="000002",
    )

    assert compare_forms(candidate.form, presentation.form) is None
    assert find_presentation_matches(candidate, [presentation]).verified == presentation
    without_suffix = presentation.model_copy(update={"name": "EXAMPLE"})
    assert find_presentation_matches(candidate, [without_suffix]).verified is None


@pytest.mark.parametrize(
    "official_name, structured_strength, structured_form",
    [
        ("EXAMPLE 500 mg CAPSULAS", "500 mg", "tablet"),
        ("EXAMPLE 250 mg TABLETS", "500 mg", "tablet"),
        ("EXAMPLE 500 mg TABLETS", "250 mg", "tablet"),
        ("EXAMPLE 500 mg COMPRIMIDOS DE LIBERACION PROLONGADA", "500 mg", "tablet"),
        ("EXAMPLE 500 mg COMPRIMIDOS GASTRORRESISTENTES", "500 mg", "tablet"),
        ("EXAMPLE 500 mg TABLETS", "500 mg", "unlisted form"),
        ("EXAMPLE 500 mg TABLETS", "500 mg", "film-coated tablet"),
        ("EXAMPLE 500 mg TABLETS", "500 mg", "prolonged-release tablet"),
        ("EXAMPLE 500 mg TABLETS", None, "tablet"),
        ("EXAMPLE 500 mg TABLETS", "500 mg", None),
        ("EXAMPLE 500 mg TABLETS FOR ORAL USE", "500 mg", "tablet"),
    ],
)
def test_name_evidence_never_overrides_contradictory_or_insufficient_fields(
    candidate, official_name, structured_strength, structured_form,
):
    presentation = CimaPresentation(
        name=official_name, strength=structured_strength, form=structured_form,
        registration_number="000001", national_code="000002",
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None


@pytest.mark.parametrize(
    "candidate_form, named_form, structured_form",
    [
        ("oral solution", "SOLUCION INYECTABLE", "SOLUCION ORAL"),
        ("film-coated tablet", "COMPRIMIDOS RECUBIERTOS CON PELICULA", "GRAGEAS"),
        ("comprimidos recubiertos", "COMPRIMIDOS RECUBIERTOS", "prolonged-release tablet"),
        ("comprimidos recubiertos", "COMPRIMIDOS RECUBIERTOS", "capsule"),
    ],
)
def test_conflicting_pharmaceutical_forms_prevent_verification(candidate_form, named_form, structured_form):
    candidate = MedicationCandidate(name="Example", strength="100 mg", form=candidate_form)
    presentation = CimaPresentation(
        name=f"EXAMPLE 100 mg {named_form}", strength="100 mg", form=structured_form,
        registration_number="000001", national_code="000002",
    )

    assert find_presentation_matches(candidate, [presentation]).verified is None


def test_candidate_name_must_also_agree_with_its_extracted_fields(candidate, presentation):
    inconsistent = candidate.model_copy(update={"name": "Example 500 mg capsules"})

    result = find_presentation_matches(inconsistent, [presentation])

    assert result.presentations == [presentation]
    assert result.verified is None


@pytest.mark.parametrize("inconsistent", [False, True])
def test_name_based_verification_does_not_hide_an_alternative(inconsistent):
    candidate = MedicationCandidate(name="Example", strength="100 mg", form="comprimidos recubiertos")
    first = CimaPresentation(
        name="EXAMPLE 100 mg COMPRIMIDOS RECUBIERTOS", strength="100 mg", form="GRAGEAS",
        registration_number="000001", national_code="000002",
    )
    second = first.model_copy(update={
        "registration_number": "000003", "national_code": "000004",
        "form": "capsule" if inconsistent else "GRAGEAS",
    })

    result = find_presentation_matches(candidate, [first, second])

    assert result.presentations == [first, second]
    assert result.verified is None


@pytest.mark.parametrize(
    "first, second, ingredients, expected",
    [
        ("550 mg", "0,55 g naproxeno sodico", ["Naproxeno sódico"], True),
        ("500 mg", "550 mg naproxeno sodico", ["Naproxeno sódico"], False),
        ("550 mg", "550 mg naproxeno sodico", [], None),
        ("550 mg", "550 mg naproxeno sodico", ["Naproxeno"], None),
        ("550 mg naproxeno", "550 mg naproxeno sodico", ["Naproxeno sódico"], None),
        ("550 mg", "550 mg naproxeno potasico", ["Naproxeno sódico"], None),
        ("550 mg", "550 mg ibuprofeno", ["Naproxeno sódico"], None),
        ("100 mg + 20 mg", "100 mg first + 20 mg second", ["first", "second"], None),
        ("550 mg", "550 mg/ml naproxeno sodico", ["Naproxeno sódico"], False),
    ],
)
def test_strength_comparison_with_active_ingredient_names(first, second, ingredients, expected):
    assert compare_strengths(first, second, active_ingredients=ingredients) is expected
    assert compare_strengths(second, first, active_ingredients=ingredients) is expected


@pytest.mark.parametrize("ingredients, verified", [([], False), (["Naproxeno"], False), (["Naproxeno sódico"], True)])
def test_verification_with_ingredient_name_in_strength(ingredients, verified):
    candidate = MedicationCandidate(
        name="Naproxeno sódico cinfa", strength="550 mg", form="comprimidos recubiertos con película",
    )
    presentation = CimaPresentation(
        name="NAPROXENO SODICO CINFA 550 mg COMPRIMIDOS EFG", strength="550 mg naproxeno sodico",
        form="COMPRIMIDO RECUBIERTO CON PELÍCULA", registration_number="65730", national_code="000001",
        active_ingredients=ingredients,
    )

    result = find_presentation_matches(candidate, [presentation])

    assert result.presentations == [presentation]
    assert (result.verified == presentation) is verified

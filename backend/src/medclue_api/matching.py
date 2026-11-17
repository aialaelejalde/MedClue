"""Match AI medication candidates with CIMA presentations by comparing names, strengths, forms, and equivalent units."""

import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

from medclue_api.schemas import CimaPresentation, MedicationCandidate


MASS_UNITS = {
    "g": Fraction(1000),
    "mg": Fraction(1),
    "microgram": Fraction(1, 1000),
    "micrograms": Fraction(1, 1000),
    "microgramo": Fraction(1, 1000),
    "microgramos": Fraction(1, 1000),
    "mcg": Fraction(1, 1000),
    "ug": Fraction(1, 1000),
    "μg": Fraction(1, 1000),
}
VOLUME_UNITS = {"ml": Fraction(1), "l": Fraction(1000)}
FORM_NAMES = {
    "tablet": ("tablet", "tablets", "comprimido", "comprimidos"),
    "coated_tablet": ("coated tablet", "coated tablets", "comprimido recubierto", "comprimidos recubiertos"),
    "sugar_coated_tablet": ("sugar-coated tablet", "sugar-coated tablets", "gragea", "grageas"),
    "film_coated_tablet": (
        "film-coated tablet", "film-coated tablets",
        "film coated tablet", "film coated tablets",
        "comprimido recubierto con pelicula", "comprimidos recubiertos con pelicula"
    ),
    "prolonged_release_tablet": (
        "prolonged-release tablet", "prolonged-release tablets",
        "comprimido de liberacion prolongada", "comprimidos de liberacion prolongada"
    ),
    "gastro_resistant_tablet": (
        "gastro-resistant tablet", "gastro-resistant tablets",
        "comprimido gastrorresistente", "comprimidos gastrorresistentes"
    ),
    "capsule": ("capsule", "capsules", "capsula", "capsulas"),
    "hard_capsule": ("hard capsule", "hard capsules", "capsula dura", "capsulas duras"),
    "oral_solution": ("oral solution", "solucion oral"),
    "oral_suspension": ("oral suspension", "suspension oral"),
    "solution_for_injection": ("solution for injection", "solucion inyectable"),
    "cream": ("cream", "crema"),
    "ointment": ("ointment", "pomada"),
    "gel": ("gel",),
}
QUANTITY_PATTERN = r"([0-9]+(?:[.,][0-9]+)?)\s*([a-zμ]+)"
VOLUME_PATTERN = r"(?:([0-9]+(?:[.,][0-9]+)?)\s*)?([a-z]+)"
FORM_FAMILIES = {
    "coated_tablet": "tablet",
    "sugar_coated_tablet": "tablet",
    "film_coated_tablet": "tablet",
    "prolonged_release_tablet": "tablet",
    "gastro_resistant_tablet": "tablet",
    "hard_capsule": "capsule",
}
FORM_DESCRIPTIONS = {
    "coated_tablet": "tablet",
    "sugar_coated_tablet": "coated_tablet",
    "film_coated_tablet": "coated_tablet",
    "hard_capsule": "capsule",
}


@dataclass
class PresentationMatches:
    """Keep possible matches separate from a single fully checked match."""

    presentations: list[CimaPresentation]
    verified: CimaPresentation | None = None


@dataclass(frozen=True)
class _NameParts:
    """Keep the complete strength and form found in an official medication name."""

    name: str
    strength: str | None
    form: str


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.split())


def compare_names(first: str, second: str) -> bool:
    first, second = normalize_name(first), normalize_name(second)
    if not first or not second:
        return False
    flexible_first = _flexible_name_key(first)
    return first == second or bool(flexible_first and flexible_first == _flexible_name_key(second))


def matches_search_name(name: str, medication: MedicationCandidate) -> bool:
    """Filter by name while allowing strength and form suffixes in CIMA results."""
    search = medication.model_copy(update={"name": name})
    search_name = _name_key(search) or normalize_name(name)
    medication_name = _name_key(medication) or normalize_name(medication.name)
    if compare_names(search_name, medication_name):
        return True

    # CIMA names may contain strength or form details. Compare the name before each number to keep these as possible matches.
    return any(
        compare_names(search_name, medication_name[:number.start()])
        for number in re.finditer(r"(?<!\S)[0-9]", medication_name)
    )


def group_presentations(presentations: list[CimaPresentation]) -> list[CimaPresentation]:
    """Group identical CIMA presentations, keeping only one when they differ by package size."""
    grouped = {}
    for presentation in presentations:
        key = (
            presentation.registration_number,
            normalize_name(presentation.name),
            normalize_name(presentation.strength) if presentation.strength else None,
            normalize_name(presentation.form) if presentation.form else None,
            tuple(normalize_name(ingredient) for ingredient in presentation.active_ingredients),
        )
        grouped.setdefault(key, presentation)
    return list(grouped.values())


def compare_strengths(first: str | None, second: str | None, *, active_ingredients: list[str] | None = None) -> bool | None:
    """Return True for equivalent strengths, False for different strengths, or None if uncertain."""
    if not first or not second:
        return None
    first_values = _parse_strength_with_ingredient_name(first, active_ingredients)
    second_values = _parse_strength_with_ingredient_name(second, active_ingredients)
    if first_values is None or second_values is None:
        return None
    return first_values == second_values


def compare_forms(first: str | None, second: str | None) -> bool | None:
    """Return True for equivalent forms, False for incompatible forms, or None if uncertain."""
    if not first or not second:
        return None
    first_form = _form_key(first)
    second_form = _form_key(second)
    if not first_form or not second_form:
        return None
    if first_form == second_form:
        return True
    # Allow singular and plural forms, but keep differences in formulation and administration route.
    first_words, second_words = first_form.split(), second_form.split()
    if len(first_words) == len(second_words) and all(
        first == second or first + "s" == second or second + "s" == first
        for first, second in zip(first_words, second_words)
    ):
        return True
    if first_form not in FORM_NAMES or second_form not in FORM_NAMES:
        return None

    first_family = FORM_FAMILIES.get(first_form, first_form)
    second_family = FORM_FAMILIES.get(second_form, second_form)
    return None if first_family == second_family else False


def find_presentation_matches(candidate: MedicationCandidate, presentations: list[CimaPresentation]) -> PresentationMatches:
    candidate_name = _name_key(candidate)
    matches = []
    for presentation in presentations:
        presentation_name = _name_key(presentation)
        if (
            not compare_names(candidate_name, presentation_name)
            and not matches_search_name(candidate.name, presentation)
        ):
            continue
        if _compare_presentation_details(candidate, presentation) is False:
            continue
        matches.append(presentation)

    matches = group_presentations(matches)
    result = PresentationMatches(presentations=matches)
    if len(matches) == 1:
        presentation = matches[0]
        if compare_presentation(candidate, presentation) is True:
            result.verified = presentation
    return result


def compare_presentation(candidate: MedicationCandidate, presentation: CimaPresentation, *, require_complete_details: bool = True) -> bool | None:
    """Compare the name, strength, and form of an AI candidate and a CIMA presentation."""
    candidate_name = _name_key(candidate, allow_missing_details=not require_complete_details)
    official_name = _name_key(presentation, allow_missing_details=not require_complete_details)
    names_match = (
        candidate_name == official_name if require_complete_details
        else compare_names(candidate_name, official_name)
    )
    if not names_match:
        return False
    details_match = _compare_presentation_details(candidate, presentation)
    if require_complete_details or details_match is not None:
        return details_match
    return _compare_presentation_details(candidate, presentation, require_complete_details=False)


def _form_field_matches_name(structured: str | None, named: str | None) -> bool:
    """Check that the form in the medication name does not contradict the separate form field."""
    if compare_forms(structured, named) is True:
        return True
    if not structured or not named:
        return False
    structured_form, named_form = _form_key(structured), _form_key(named)
    while structured_form in FORM_DESCRIPTIONS:
        structured_form = FORM_DESCRIPTIONS[structured_form]
        if structured_form == named_form:
            return True
    return False


def _name_conflicts_with_fields(medication: MedicationCandidate, parts: _NameParts | None) -> bool:
    """Check if the strength or form in the medication name conflicts with its separate fields. Keep inconsistent records as uncertain."""
    if parts is None:
        return False
    ingredients = medication.active_ingredients if isinstance(medication, CimaPresentation) else None
    if compare_strengths(parts.strength, medication.strength, active_ingredients=ingredients) is False:
        return True
    if not medication.form:
        return False
    named_form, structured_form = _form_key(parts.form), _form_key(medication.form)
    if named_form in FORM_NAMES and structured_form in FORM_NAMES:
        return not _form_field_matches_name(medication.form, parts.form)
    return False


def _compare_presentation_details(candidate: MedicationCandidate, presentation: CimaPresentation, *, require_complete_details: bool = True) -> bool | None:
    """Compare strength and form between an AI candidate and a CIMA presentation. Return True if they match, False if they differ, or None if uncertain."""
    candidate_parts = _split_medication_name(candidate.name, allow_missing_strength=not require_complete_details)
    official_parts = _split_medication_name(presentation.name, allow_missing_strength=not require_complete_details)
    if _name_conflicts_with_fields(candidate, candidate_parts) or _name_conflicts_with_fields(presentation, official_parts):
        return None

    if not require_complete_details:
        comparisons = []
        for field, compare in (
            ("strength", lambda first, second: compare_strengths(
                first, second, active_ingredients=presentation.active_ingredients,
            )),
            ("form", compare_forms),
        ):
            candidate_values = {getattr(candidate, field)}
            official_values = {getattr(presentation, field)}
            if candidate_parts is not None:
                candidate_values.add(getattr(candidate_parts, field))
            if official_parts is not None:
                official_values.add(getattr(official_parts, field))
            for first in candidate_values - {None}:
                for second in official_values - {None}:
                    comparisons.append(
                        True if normalize_name(first) == normalize_name(second)
                        else compare(first, second)
                    )
        if False in comparisons:
            return False
        return None if None in comparisons else True

    strength_match = compare_strengths(
        candidate.strength, presentation.strength, active_ingredients=presentation.active_ingredients,
    )
    form_match = compare_forms(candidate.form, presentation.form)
    if strength_match is False or form_match is False:
        return False
    if strength_match is not True or not candidate.form or not presentation.form:
        return None

    if candidate_parts is not None and (
        compare_strengths(candidate_parts.strength, candidate.strength) is not True
        or not _form_field_matches_name(candidate.form, candidate_parts.form)
    ):
        return None

    if official_parts is None:
        return True if form_match is True else None

    if form_match is not True and _form_key(official_parts.form) in FORM_FAMILIES.values():
        return None
    if (
        compare_strengths(candidate.strength, official_parts.strength) is not True
        or not (
            compare_forms(candidate.form, official_parts.form) is True
            or (form_match is True and _form_field_matches_name(candidate.form, official_parts.form))
        )
        or not _form_field_matches_name(presentation.form, official_parts.form)
    ):
        return None
    return True


def _flexible_name_key(name: str) -> str:
    """Ignore common separators for possible matches, not verification."""
    return re.sub(r"[-+/._\s]+", "", name)


def _form_key(form: str) -> str:
    """Return a common name for equivalent pharmaceutical forms."""
    normalized = normalize_name(form)
    for key, aliases in FORM_NAMES.items():
        if normalized in aliases:
            return key
    return normalized


def _name_key(medication: MedicationCandidate, *, allow_missing_details: bool = False) -> str:
    """Get the medication name without its strength and form, when possible."""
    name = normalize_name(medication.name)

    parts = _split_medication_name(name, allow_missing_strength=allow_missing_details)
    ingredients = medication.active_ingredients if isinstance(medication, CimaPresentation) else None
    if parts is not None and (
        allow_missing_details
        or compare_strengths(parts.strength, medication.strength, active_ingredients=ingredients) is True
    ):
        name = parts.name
        if not allow_missing_details:
            return name

    elif medication.form:
        aliases = FORM_NAMES.get(_form_key(medication.form), (normalize_name(medication.form),))
        form_pattern = "|".join(re.escape(alias) for alias in aliases)
        name = re.sub(r"\s+(?:" + form_pattern + r")(?:\s+efg)?$", "", name)

    if allow_missing_details and medication.strength:
        name = re.sub(r"\s+" + re.escape(normalize_name(medication.strength)) + r"$", "", name)

    return name


def _split_medication_name(name: str, *, allow_missing_strength: bool = False) -> _NameParts | None:
    """Separate the medication name into its name, strength, and form when possible."""
    name = normalize_name(name)
    for number in re.finditer(r"(?<!\S)[0-9]", name):
        if number.start() == 0:
            continue
        suffix = name[number.start():]
        parts = []
        for boundary in re.finditer(r"\s+|$", suffix):
            strength = suffix[:boundary.start()]
            form = suffix[boundary.end():].strip()
            if not form or not form[0].isalpha():
                continue
            if _parse_strength(strength) is not None:
                form = re.sub(r"\s+efg$", "", form)
                parts.append(_NameParts(name[:number.start()].strip(), strength, form))
        if parts:
            return parts[0] if len(parts) == 1 else None
    if allow_missing_strength:
        aliases = sorted((alias for aliases in FORM_NAMES.values() for alias in aliases), key=len, reverse=True)
        for alias in aliases:
            match = re.fullmatch(r"(.+)\s+" + re.escape(alias) + r"(?:\s+efg)?", name)
            if match is not None:
                return _NameParts(match.group(1), None, alias)
    return None


def _parse_strength_with_ingredient_name(strength: str, active_ingredients: list[str] | None) -> list[tuple[str, Fraction]] | None:
    """Parse a strength that may include the name of an active ingredient."""
    parsed = _parse_strength(strength)
    if parsed is not None or not active_ingredients or len(active_ingredients) != 1:
        return parsed
    strength = normalize_name(strength)
    ingredient = normalize_name(active_ingredients[0])
    suffix = " " + ingredient
    if not strength.endswith(suffix):
        return None
    parsed = _parse_strength(strength[:-len(suffix)])
    return parsed if parsed is not None and len(parsed) == 1 else None


def _parse_strength(strength: str) -> list[tuple[str, Fraction]] | None:
    """Split a complete medication strength into comparable components."""
    components = []
    for component in normalize_name(strength).split("+"):
        parsed = _parse_component(component.strip())
        if parsed is not None:
            components.append(parsed)
            continue

        mass_parts = component.split("/")
        if len(mass_parts) < 2:
            return None
        for mass_part in mass_parts:
            mass = _parse_component(mass_part.strip())
            if mass is None or mass[0] != "mass":
                return None
            components.append(mass)

    if len({kind for kind, value in components}) != 1:
        return None
    return components


def _parse_component(component: str) -> tuple[str, Fraction] | None:
    """Convert one strength component into a comparable mass or concentration."""
    parts = component.split("/")
    if len(parts) > 2:
        return None
    quantity = re.fullmatch(QUANTITY_PATTERN, parts[0].strip())
    if quantity is None:
        return None

    value = _positive_fraction(quantity.group(1))
    mass_factor = MASS_UNITS.get(quantity.group(2))
    if value is None or mass_factor is None:
        return None
    mass = value * mass_factor
    if len(parts) == 1:
        return "mass", mass

    volume = re.fullmatch(VOLUME_PATTERN, parts[1].strip())
    if volume is None:
        return None
    volume_value = _positive_fraction(volume.group(1) or "1")
    volume_factor = VOLUME_UNITS.get(volume.group(2))
    if volume_value is None or volume_factor is None:
        return None
    return "mass_per_volume", mass / (volume_value * volume_factor)


def _positive_fraction(number: str) -> Fraction | None:
    """Convert positive numbers to fractions, rejecting ambiguous thousands separators."""
    parts = re.split(r"[.,]", number)
    if len(parts) == 2 and int(parts[0]) != 0 and len(parts[1]) == 3:
        return None
    value = Fraction(number.replace(",", "."))
    return value if value > 0 else None

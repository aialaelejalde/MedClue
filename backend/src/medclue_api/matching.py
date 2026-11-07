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
    "film_coated_tablet": "tablet",
    "prolonged_release_tablet": "tablet",
    "gastro_resistant_tablet": "tablet",
    "hard_capsule": "capsule",
}


@dataclass
class PresentationMatches:
    """Keep possible matches separate from a single fully checked match."""

    presentations: list[CimaPresentation]
    verified: CimaPresentation | None = None


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

    # Keep possible matches when missing or unsupported details leave a numeric suffix.
    return any(
        compare_names(search_name, medication_name[:number.start()])
        for number in re.finditer(r"(?<!\S)[0-9]", medication_name)
    )


def group_presentations(presentations: list[CimaPresentation]) -> list[CimaPresentation]:
    """Keep one national code per medication, ignoring package size."""
    grouped = {}
    for presentation in presentations:
        key = (
            presentation.registration_number,
            normalize_name(presentation.name),
            normalize_name(presentation.strength) if presentation.strength else None,
            normalize_name(presentation.form) if presentation.form else None,
        )
        grouped.setdefault(key, presentation)
    return list(grouped.values())


def compare_strengths(first: str | None, second: str | None) -> bool | None:
    """Return True for equivalent strengths, False for different strengths, or None if uncertain."""
    if not first or not second:
        return None
    first_values = _parse_strength(first)
    second_values = _parse_strength(second)
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
        if compare_strengths(candidate.strength, presentation.strength) is False:
            continue
        if compare_forms(candidate.form, presentation.form) is False:
            continue
        matches.append(presentation)

    matches = group_presentations(matches)
    result = PresentationMatches(presentations=matches)
    if len(matches) == 1:
        presentation = matches[0]
        if (
            candidate_name == _name_key(presentation)
            and compare_strengths(candidate.strength, presentation.strength) is True
            and compare_forms(candidate.form, presentation.form) is True
        ):
            result.verified = presentation
    return result


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


def _name_key(medication: MedicationCandidate) -> str:
    """Use a matching structured strength to locate the end of the medication name."""
    name = normalize_name(medication.name)

    if medication.strength:
        for number in re.finditer(r"(?<!\S)[0-9]", name):
            if number.start() == 0:
                continue
            suffix = name[number.start():]
            for boundary in re.finditer(r"\s+|$", suffix):
                strength = suffix[:boundary.start()]
                remaining = suffix[boundary.end():].lstrip()
                if remaining.startswith(("/", "+")) or re.match(r"[0-9]", remaining):
                    continue
                if compare_strengths(strength, medication.strength) is True:
                    return name[:number.start()].strip()

    if medication.form:
        aliases = FORM_NAMES.get(_form_key(medication.form), (normalize_name(medication.form),))
        form_pattern = "|".join(re.escape(alias) for alias in aliases)
        name = re.sub(r"\s+(?:" + form_pattern + r")(?:\s+efg)?$", "", name)

    return name


def _parse_strength(strength: str) -> list[tuple[str, Fraction]] | None:
    """Convert medication strengths into comparable values, including combinations and concentrations."""
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
    """Convert a medication strength into a mass or mass-per-volume value using equivalent units."""
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

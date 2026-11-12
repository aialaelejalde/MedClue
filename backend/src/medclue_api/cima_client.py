"""Read official medications, presentations, and section 4.1 from CIMA."""

import re

import httpx

from medclue_api.config import CIMA_BASE_URL, IDENTIFICATION_TIMEOUT_SECONDS
from medclue_api.matching import MASS_UNITS, group_presentations, matches_search_name, normalize_name
from medclue_api.schemas import CimaPresentation, MedicationCandidate


class CimaClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=CIMA_BASE_URL,
            timeout=IDENTIFICATION_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )

    async def search_presentations(self, name: str) -> list[CimaPresentation]:
        name = normalize_name(_required_text(name, "Medication name"))
        medications = await self._search_medications(name)
        presentations = {}
        for medication in medications:
            if not matches_search_name(name, _medication_candidate(medication)):
                continue
            registration_number = _required_text(medication.get("nregistro"), "Registration number")
            details = await self._get_json("medicamento", {"nregistro": registration_number})
            if details is None or details.get("nregistro") != registration_number:
                raise ValueError("CIMA did not return the requested medication.")

            for presentation in _medication_presentations(details):
                previous = presentations.get(presentation.national_code)
                if previous is not None and previous != presentation:
                    raise ValueError("CIMA returned conflicting presentation data.")
                presentations[presentation.national_code] = presentation

        return group_presentations(list(presentations.values()))

    async def get_presentation(self, national_code: str) -> CimaPresentation | None:
        national_code = _required_text(national_code, "National code")
        medication = await self._get_json("medicamento", {"cn": national_code})
        if medication is None:
            return None

        presentations = _medication_presentations(medication)
        for presentation in presentations:
            if presentation.national_code == national_code:
                return presentation
        raise ValueError("CIMA did not return the requested presentation.")

    async def get_official_indications(self, registration_number: str) -> str:
        registration_number = _required_text(registration_number, "Registration number")
        response = await self._client.get(
            "docSegmentado/contenido/1",
            params={"nregistro": registration_number, "seccion": "4.1"},
            headers={"Accept": "text/plain"},
        )
        response.raise_for_status()
        if response.status_code == 204:
            return ""
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "text/plain":
            raise ValueError("CIMA did not return plain-text therapeutic indications.")
        return response.text.strip()

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: dict) -> dict | None:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("CIMA did not return a JSON object.")
        return data

    async def _search_medications(self, name: str) -> list[dict]:
        """Read every page so omitted results cannot cause a false unique match."""
        medications = []
        page = 1
        total = None
        page_size = None
        while True:
            data = await self._get_json("medicamentos", {"nombre": name, "pagina": page})
            if data is None:
                if page == 1:
                    return []
                raise ValueError("CIMA returned an incomplete medication search.")

            results = data.get("resultados")
            current_total = data.get("totalFilas")
            current_size = data.get("tamanioPagina")
            current_page = data.get("pagina")
            if (
                not isinstance(results, list)
                or not all(isinstance(item, dict) for item in results)
                or type(current_total) is not int or current_total < 0
                or type(current_size) is not int or current_size <= 0
                or type(current_page) is not int or current_page != page
            ):
                raise ValueError("CIMA returned invalid search pagination.")
            if total is None:
                total, page_size = current_total, current_size
            if current_total != total or current_size != page_size:
                raise ValueError("CIMA search results changed during pagination.")
            expected_count = min(page_size, total - len(medications))
            if len(results) != expected_count:
                raise ValueError("CIMA returned an incomplete medication search.")

            medications.extend(results)
            if len(medications) == total:
                return medications
            page += 1


def _medication_candidate(medication: dict) -> MedicationCandidate:
    name = _required_text(medication.get("nombre"), "Medication name")
    strength = _optional_text(medication.get("dosis"))
    if strength is not None:
        strength = _normalize_strength(strength)

    form = medication.get("formaFarmaceutica")
    if form is not None and not isinstance(form, dict):
        raise ValueError("CIMA returned an invalid pharmaceutical form.")
    form_name = _optional_text(form.get("nombre")) if form is not None else None
    return MedicationCandidate(name=name, strength=strength, form=form_name)


def _medication_presentations(medication: dict) -> list[CimaPresentation]:
    candidate = _medication_candidate(medication)
    registration_number = _required_text(medication.get("nregistro"), "Registration number")
    ingredients = medication.get("principiosActivos", [])
    if not isinstance(ingredients, list) or not all(isinstance(item, dict) for item in ingredients):
        raise ValueError("CIMA returned invalid active ingredients.")
    active_ingredients = [_required_text(item.get("nombre"), "Active ingredient") for item in ingredients]

    packages = medication.get("presentaciones")
    if not isinstance(packages, list) or not all(isinstance(item, dict) for item in packages):
        raise ValueError("CIMA returned an invalid presentation list.")
    return [
        CimaPresentation(
            name=candidate.name,
            strength=candidate.strength,
            form=candidate.form,
            registration_number=registration_number,
            national_code=package.get("cn"),
            active_ingredients=active_ingredients,
        )
        for package in packages
    ]


def _normalize_strength(strength: str) -> str:
    """Expand CIMA mass combinations such as '400/240 mg/mg' without guessing units."""
    match = re.fullmatch(
        r"([0-9]+(?:[.,][0-9]+)?(?:/[0-9]+(?:[.,][0-9]+)?)+)\s+([a-zμ]+(?:/[a-zμ]+)+)",
        normalize_name(strength),
    )
    if match is None:
        return strength
    amounts = match.group(1).split("/")
    units = match.group(2).split("/")
    if len(amounts) != len(units) or any(unit not in MASS_UNITS for unit in units):
        return strength
    return " + ".join(f"{amount} {unit}" for amount, unit in zip(amounts, units))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("CIMA text fields must contain strings.")
    return value.strip() or None


def _required_text(value: object, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field_name} must contain text.")
    return text

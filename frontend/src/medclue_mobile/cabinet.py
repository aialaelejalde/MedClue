"""Manage saved medications, search, sorting, and duplicate names."""

from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.sqlite_repository import MedicationRepository


SORT_ORDERS = ("recently_added", "name_az")


class DuplicateMedicationError(ValueError):
    """Indicate that saving a duplicate medication requires confirmation."""


class MedicationCabinet:
    def __init__(self, repository: MedicationRepository):
        self._repository = repository

    def list_medications(self, query: str = "", sort_order: str = "recently_added") -> list[Medication]:
        if not isinstance(query, str):
            raise ValueError("The search query must be text.")
        if sort_order not in SORT_ORDERS:
            raise ValueError("Select a valid medication sort order.")

        medications = self._repository.list_all()
        search_text = _normalize_text(query)
        if search_text:
            medications = [
                medication
                for medication in medications
                if search_text in _normalize_text(medication.name or "")
                or any(
                    search_text in _normalize_text(reason)
                    for reason in medication.uses
                )
            ]

        if sort_order == "name_az":
            medications.sort(
                key=lambda medication: (
                    not bool(_normalize_text(medication.name or "")),
                    _normalize_text(medication.name or ""),
                )
            )

        return medications

    def get_medication(self, medication_id: int) -> Medication:
        medication = self._repository.get(medication_id)
        if medication is None:
            raise LookupError("The medication record was not found.")
        return medication

    def find_duplicates(self, name: str | None, exclude_id: int | None = None) -> list[Medication]:
        """Find medications with the same name, ignoring case and extra spaces, and excluding the current record."""
        if name is None:
            return []
        if not isinstance(name, str):
            raise ValueError("The medication name must be text.")

        normalized_name = _normalize_text(name)
        if not normalized_name:
            return []

        return [
            medication
            for medication in self._repository.list_all()
            if medication.id != exclude_id
            and _normalize_text(medication.name or "") == normalized_name
        ]

    def save_medication(self, medication: Medication, allow_duplicate: bool = False) -> Medication:
        """Save only after validation and any required duplicate confirmation."""
        validate_medication(medication)
        if not isinstance(allow_duplicate, bool):
            raise ValueError("Duplicate confirmation must be true or false.")

        check_duplicates = medication.id is None
        if medication.id is not None:
            saved_medication = self.get_medication(medication.id)
            check_duplicates = (
                _normalize_text(medication.name or "")
                != _normalize_text(saved_medication.name or "")
            )

        if check_duplicates:
            duplicates = self.find_duplicates(medication.name, medication.id)
            if duplicates and not allow_duplicate:
                raise DuplicateMedicationError("A medication with this name already exists in the cabinet.")

        if medication.id is None:
            return self._repository.add(medication)
        return self._repository.update(medication)

    def delete_medication(self, medication_id: int) -> None:
        self._repository.delete(medication_id)


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).casefold()

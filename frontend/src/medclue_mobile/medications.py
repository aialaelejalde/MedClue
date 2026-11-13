"""Define medication data, allowed values, and validation rules."""

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite


AMOUNT_UNITS = (
    "tablets", "capsules", "mL", "drops", "puffs", "sprays",
    "sachets", "patches", "mg", "g",
)
FREQUENCY_UNITS = ("minutes", "hours", "days", "weeks", "months", "years")
FREQUENCY_TYPES = (
    "once_daily", "twice_daily", "three_times_daily", "interval",
    "as_needed", "custom", "not_specified",
)
FOOD_TYPES = (
    "before_meals", "with_food", "after_meals", "empty_stomach",
    "with_or_without_food", "not_applicable", "custom",
)
TREATMENT_END_TYPES = ("date", "no_end_date", "not_taking", "unknown")


@dataclass
class Amount:
    type: str
    value: float | None = None
    unit: str | None = None
    text: str | None = None


@dataclass
class Frequency:
    type: str
    value: float | None = None
    unit: str | None = None
    text: str | None = None


@dataclass
class FoodInstructions:
    type: str
    text: str | None = None


@dataclass
class TreatmentEnd:
    type: str
    end_date: date | None = None


@dataclass
class Medication:
    name: str | None = None
    photo: bytes | None = field(default=None, repr=False)
    uses: list[str] = field(default_factory=list)
    amount: Amount | None = None
    frequency: Frequency | None = None
    food: FoodInstructions | None = None
    prescription_date: date | None = None
    treatment_end: TreatmentEnd | None = None
    notes: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    strength: str | None = None
    form: str | None = None


def validate_medication(medication: Medication) -> None:
    """Raise ValueError if any field is invalid or the record is empty."""
    if not isinstance(medication, Medication):
        raise ValueError("A medication record is required.")

    _validate_optional_text(medication.name, "Medication name")
    _validate_optional_text(medication.notes, "Additional notes")
    _validate_optional_text(medication.strength, "Strength")
    _validate_optional_text(medication.form, "Pharmaceutical form")

    if medication.photo is not None:
        if not isinstance(medication.photo, bytes) or not medication.photo:
            raise ValueError("The photo must contain image bytes.")

    if not isinstance(medication.uses, list):
        raise ValueError("Saved uses and reasons must be a list.")
    for reason in medication.uses:
        _validate_required_text(reason, "Each saved use or reason")

    if medication.amount is not None:
        _validate_amount(medication.amount)
    if medication.frequency is not None:
        _validate_frequency(medication.frequency)
    if medication.food is not None:
        _validate_food(medication.food)
    if medication.treatment_end is not None:
        _validate_treatment_end(medication.treatment_end)

    if medication.prescription_date is not None:
        if type(medication.prescription_date) is not date:
            raise ValueError("The prescription date must be a calendar date.")

    if medication.id is not None:
        if type(medication.id) is not int or medication.id <= 0:
            raise ValueError("The record ID must be a positive integer.")
    if medication.created_at is not None:
        if not isinstance(medication.created_at, datetime):
            raise ValueError("The creation time must be a date and time.")

    if not has_medication_information(medication):
        raise ValueError("Please add at least one piece of information before saving.")


def has_medication_information(medication: Medication) -> bool:
    """Check if any user field has information."""
    return any((
        medication.name is not None and bool(medication.name.strip()),
        bool(medication.photo),
        bool(medication.uses),
        medication.amount is not None,
        medication.frequency is not None,
        medication.food is not None,
        medication.prescription_date is not None,
        medication.treatment_end is not None,
        medication.notes is not None and bool(medication.notes.strip()),
    ))


def _validate_amount(amount: Amount) -> None:
    if not isinstance(amount, Amount):
        raise ValueError("The amount must be an Amount value.")
    if amount.type == "quantity":
        _validate_positive_number(amount.value, "Quantity")
        if amount.unit not in AMOUNT_UNITS:
            raise ValueError("Select a valid amount unit.")
        if amount.text is not None:
            raise ValueError("A quantity cannot also contain custom instructions.")
    elif amount.type == "custom":
        _validate_required_text(amount.text, "Custom amount instructions")
        if amount.value is not None or amount.unit is not None:
            raise ValueError("A custom amount cannot also contain a quantity or unit.")
    else:
        raise ValueError("Select a valid amount type.")


def _validate_frequency(frequency: Frequency) -> None:
    if not isinstance(frequency, Frequency):
        raise ValueError("The frequency must be a Frequency value.")
    if frequency.type not in FREQUENCY_TYPES:
        raise ValueError("Select a valid frequency type.")

    if frequency.type == "interval":
        _validate_positive_number(frequency.value, "Frequency interval")
        if frequency.unit not in FREQUENCY_UNITS:
            raise ValueError("Select a valid frequency unit.")
    elif frequency.value is not None or frequency.unit is not None:
        raise ValueError("Only an interval can contain a frequency value and unit.")

    if frequency.type == "custom":
        _validate_required_text(frequency.text, "Custom frequency instructions")
    elif frequency.text is not None:
        raise ValueError("Only a custom frequency can contain instructions.")


def _validate_food(food: FoodInstructions) -> None:
    if not isinstance(food, FoodInstructions):
        raise ValueError("Food instructions must be a FoodInstructions value.")
    if food.type not in FOOD_TYPES:
        raise ValueError("Select a valid food instruction type.")
    if food.type == "custom":
        _validate_required_text(food.text, "Custom food instructions")
    elif food.text is not None:
        raise ValueError("Only custom food instructions can contain text.")


def _validate_treatment_end(treatment_end: TreatmentEnd) -> None:
    if not isinstance(treatment_end, TreatmentEnd):
        raise ValueError("The treatment end must be a TreatmentEnd value.")
    if treatment_end.type not in TREATMENT_END_TYPES:
        raise ValueError("Select a valid treatment end type.")
    if treatment_end.type == "date":
        if type(treatment_end.end_date) is not date:
            raise ValueError("Select a calendar date for the treatment end.")
    elif treatment_end.end_date is not None:
        raise ValueError("Only the date option can contain a treatment end date.")


def _validate_optional_text(text: str | None, field_name: str) -> None:
    if text is not None and not isinstance(text, str):
        raise ValueError(f"{field_name} must be text.")


def _validate_required_text(text: str | None, field_name: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{field_name} must contain text.")


def _validate_positive_number(value: float | None, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a positive number.")
    if value <= 0 or (isinstance(value, float) and not isfinite(value)):
        raise ValueError(f"{field_name} must be a positive number.")

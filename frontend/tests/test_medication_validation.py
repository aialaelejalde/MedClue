"""Test medication data validation and detection of empty records."""

from copy import deepcopy
from datetime import date, datetime

import pytest

from medclue_mobile.medications import (
    Amount,
    FoodInstructions,
    Frequency,
    Medication,
    TreatmentEnd,
    has_medication_information,
    validate_medication,
)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(name="Paracetamol"),
        Medication(photo=b"stored photo bytes"),
        Medication(uses=["Pain"]),
        Medication(uses=["I don't know / I don't remember"]),
        Medication(amount=Amount("quantity", 0.5, "tablets")),
        Medication(amount=Amount("custom", text="Use as instructed")),
        Medication(frequency=Frequency("interval", 8, "hours")),
        Medication(frequency=Frequency("custom", text="On Mondays")),
        Medication(food=FoodInstructions("custom", "With a snack")),
        Medication(prescription_date=date(2026, 11, 1)),
        Medication(treatment_end=TreatmentEnd("date", date(2026, 12, 1))),
        Medication(notes="Keep the package"),
    ],
)
def test_one_filled_field_is_enough_to_save(medication):
    validate_medication(medication)

    assert has_medication_information(medication)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(),
        Medication(name="", notes=""),
        Medication(name=" \t", notes="\n "),
        Medication(id=1),
        Medication(created_at=datetime(2026, 11, 1, 12)),
        Medication(id=1, created_at=datetime(2026, 11, 1, 12)),
    ],
)
def test_empty_medication_cannot_be_saved(medication):
    assert not has_medication_information(medication)

    with pytest.raises(ValueError, match="at least one piece of information"):
        validate_medication(medication)


def test_blank_optional_text_is_allowed_with_another_valid_field():
    validate_medication(Medication(name="  ", notes="Keep the package"))


@pytest.mark.parametrize(
    "unit",
    [
        "tablets", "capsules", "mL", "drops", "puffs", "sprays",
        "sachets", "patches", "mg", "g",
    ],
)
def test_amount_accepts_each_approved_unit(unit):
    validate_medication(Medication(amount=Amount("quantity", 1.5, unit)))


@pytest.mark.parametrize(
    "value", [0, -1, True, False, float("inf"), float("nan"), "1", None]
)
def test_amount_and_interval_require_positive_finite_numbers(value):
    with pytest.raises(ValueError, match="positive number"):
        validate_medication(Medication(amount=Amount("quantity", value, "mg")))

    with pytest.raises(ValueError, match="positive number"):
        validate_medication(Medication(frequency=Frequency("interval", value, "hours")))


@pytest.mark.parametrize(
    "frequency_type",
    ["once_daily", "twice_daily", "three_times_daily", "as_needed", "not_specified"],
)
def test_fixed_frequency_choices_count_as_information(frequency_type):
    medication = Medication(frequency=Frequency(frequency_type))

    validate_medication(medication)

    assert has_medication_information(medication)


@pytest.mark.parametrize(
    "unit", ["minutes", "hours", "days", "weeks", "months", "years"]
)
def test_frequency_accepts_each_approved_interval_unit(unit):
    validate_medication(Medication(frequency=Frequency("interval", 1.5, unit)))


@pytest.mark.parametrize(
    "food_type",
    [
        "before_meals", "with_food", "after_meals", "empty_stomach",
        "with_or_without_food", "not_applicable",
    ],
)
def test_fixed_food_choices_count_as_information(food_type):
    medication = Medication(food=FoodInstructions(food_type))

    validate_medication(medication)

    assert has_medication_information(medication)


@pytest.mark.parametrize("end_type", ["no_end_date", "not_taking", "unknown"])
def test_treatment_end_choices_do_not_require_a_date(end_type):
    medication = Medication(treatment_end=TreatmentEnd(end_type))

    validate_medication(medication)

    assert has_medication_information(medication)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(amount=Amount("custom")),
        Medication(amount=Amount("custom", text=" \n")),
        Medication(amount=Amount("custom", text=123)),
        Medication(frequency=Frequency("custom")),
        Medication(frequency=Frequency("custom", text=" \t")),
        Medication(food=FoodInstructions("custom")),
        Medication(food=FoodInstructions("custom", " ")),
    ],
)
def test_custom_options_require_written_instructions(medication):
    with pytest.raises(ValueError, match="must contain text"):
        validate_medication(medication)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(amount=Amount("unknown")),
        Medication(amount=Amount("quantity", 1, "litres")),
        Medication(amount=Amount("quantity", 1)),
        Medication(frequency=Frequency("unknown")),
        Medication(frequency=Frequency("interval", 8, "seconds")),
        Medication(frequency=Frequency("interval", 8)),
        Medication(food=FoodInstructions("unknown")),
        Medication(treatment_end=TreatmentEnd("unknown_option")),
    ],
)
def test_unknown_options_and_missing_units_are_rejected(medication):
    with pytest.raises(ValueError):
        validate_medication(medication)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(amount=Amount("quantity", 1, "mg", "Extra text")),
        Medication(amount=Amount("custom", value=1, text="Use as instructed")),
        Medication(amount=Amount("custom", unit="mg", text="Use as instructed")),
        Medication(frequency=Frequency("once_daily", value=1)),
        Medication(frequency=Frequency("as_needed", unit="hours")),
        Medication(frequency=Frequency("not_specified", text="Extra text")),
        Medication(frequency=Frequency("interval", 8, "hours", "Extra text")),
        Medication(food=FoodInstructions("with_food", "Extra text")),
        Medication(treatment_end=TreatmentEnd("no_end_date", date(2026, 12, 1))),
    ],
)
def test_options_cannot_keep_fields_from_another_option(medication):
    with pytest.raises(ValueError):
        validate_medication(medication)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(prescription_date="2026-11-01"),
        Medication(prescription_date=datetime(2026, 11, 1, 12)),
        Medication(treatment_end=TreatmentEnd("date")),
        Medication(treatment_end=TreatmentEnd("date", "2026-12-01")),
        Medication(treatment_end=TreatmentEnd("date", datetime(2026, 12, 1, 12))),
    ],
)
def test_selected_dates_must_be_calendar_dates(medication):
    with pytest.raises(ValueError, match="date"):
        validate_medication(medication)


@pytest.mark.parametrize(
    "medication",
    [
        Medication(name=123),
        Medication(notes=123),
        Medication(photo=b""),
        Medication(photo="photo path"),
        Medication(uses="Pain"),
        Medication(uses=[""]),
        Medication(uses=["  "]),
        Medication(uses=[None]),
        Medication(amount={}),
        Medication(frequency={}),
        Medication(food={}),
        Medication(treatment_end={}),
        Medication(name="Medicine", id=0),
        Medication(name="Medicine", id=True),
        Medication(name="Medicine", created_at="2026-11-01"),
    ],
)
def test_invalid_field_values_are_rejected(medication):
    with pytest.raises(ValueError):
        validate_medication(medication)


def test_validation_keeps_the_original_field_values():
    medication = Medication(
        name="  Paracetamol  ",
        photo=b"stored photo bytes",
        uses=["Pain", "My own reason"],
        amount=Amount("quantity", 0.5, "tablets"),
        frequency=Frequency("interval", 8, "hours"),
        food=FoodInstructions("with_food"),
        prescription_date=date(2026, 11, 1),
        treatment_end=TreatmentEnd("unknown"),
        notes=" Keep the package ",
        id=1,
        created_at=datetime(2026, 11, 1, 12),
    )
    original = deepcopy(medication)

    validate_medication(medication)

    assert medication == original


def test_failed_validation_keeps_the_entered_values():
    medication = Medication(
        name="Paracetamol",
        amount=Amount("quantity", -1, "tablets"),
        notes="Keep this note",
    )
    original = deepcopy(medication)

    with pytest.raises(ValueError):
        validate_medication(medication)

    assert medication == original

"""Test medication storage, editing, deletion, search, sorting, and duplicate handling."""

import json
import sqlite3
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from medclue_mobile.cabinet import DuplicateMedicationError, MedicationCabinet
from medclue_mobile.medications import (Amount, FoodInstructions, Frequency, Medication, TreatmentEnd)
from medclue_mobile.sqlite_repository import MedicationRepository


@pytest.fixture
def repository(tmp_path):
    medication_repository = MedicationRepository(tmp_path / "medclue.db")
    medication_repository.initialize()
    return medication_repository


@pytest.fixture
def cabinet(repository):
    return MedicationCabinet(repository)


def test_new_cabinet_is_empty(cabinet):
    assert cabinet.list_medications() == []


def test_count_tracks_saved_and_deleted_medications_without_loading_records(cabinet, repository, monkeypatch):
    assert cabinet.count_medications() == 0
    first = cabinet.save_medication(Medication(name="First", photo=b"photo"))
    cabinet.save_medication(Medication(name="Second"))
    def fail_if_loaded():
        raise AssertionError("Counting must not load medication records")
    monkeypatch.setattr(repository, "list_all", fail_if_loaded)
    assert cabinet.count_medications() == 2
    cabinet.delete_medication(first.id)
    assert cabinet.count_medications() == 1


def test_save_keeps_all_fields_and_does_not_change_the_draft(cabinet):
    draft = Medication(
        name="Paracetamol",
        strength="500 mg",
        form="tablet",
        photo=b"compressed photo bytes",
        uses=["Pain", "My own reason"],
        amount=Amount("quantity", 0.5, "tablets"),
        frequency=Frequency("interval", 8, "hours"),
        food=FoodInstructions("with_food"),
        prescription_date=date(2026, 11, 1),
        treatment_end=TreatmentEnd("date", date(2026, 12, 1)),
        notes="Keep the package",
    )
    original = deepcopy(draft)
    saved = cabinet.save_medication(draft)

    assert saved.id > 0
    assert isinstance(saved.created_at, datetime)
    assert replace(saved, id=None, created_at=None) == original
    assert cabinet.get_medication(saved.id) == saved
    assert draft == original


@pytest.mark.parametrize(
    "draft",
    [
        Medication(name="Name only"),
        Medication(photo=b"photo only"),
        Medication(uses=["My own reason"]),
        Medication(amount=Amount("custom", text="Use as instructed")),
        Medication(frequency=Frequency("custom", text="On Mondays")),
        Medication(frequency=Frequency("not_specified")),
        Medication(food=FoodInstructions("custom", "With a snack")),
        Medication(prescription_date=date(2026, 11, 1)),
        Medication(treatment_end=TreatmentEnd("unknown")),
        Medication(notes="Notes only"),
    ],
)
def test_optional_and_custom_fields_are_preserved(cabinet, draft):
    saved = cabinet.save_medication(draft)
    restored = cabinet.get_medication(saved.id)

    assert restored == saved
    assert replace(restored, id=None, created_at=None) == draft


@pytest.mark.parametrize(
    "column, stored_value",
    [
        pytest.param("amount", "{invalid json", id="malformed-json"),
        pytest.param(
            "amount", json.dumps({"type": "quantity", "value": -1, "unit": "mg"}),
            id="negative-quantity",
        ),
        pytest.param("prescription_date", "not-a-date", id="invalid-date"),
    ],
)
def test_invalid_stored_values_are_rejected_on_read(repository, tmp_path, column, stored_value):
    saved = repository.add(Medication(name="Paracetamol"))
    with closing(sqlite3.connect(tmp_path / "medclue.db")) as connection:
        with connection:
            connection.execute(
                f"UPDATE medications SET {column} = ? WHERE id = ?",
                (stored_value, saved.id),
            )

    with pytest.raises(ValueError, match="^The saved medication contains invalid values\\.$"):
        repository.get(saved.id)


def test_records_remain_after_reopening_and_initializing(cabinet, tmp_path):
    saved = cabinet.save_medication(Medication(name="Paracetamol", photo=b"photo"))
    with closing(sqlite3.connect(tmp_path / "medclue.db")) as connection:
        with connection:
            connection.execute("ALTER TABLE medications DROP COLUMN strength")
            connection.execute("ALTER TABLE medications DROP COLUMN form")
    reopened_repository = MedicationRepository(tmp_path / "medclue.db")

    reopened_repository.initialize()
    reopened_cabinet = MedicationCabinet(reopened_repository)

    assert reopened_cabinet.get_medication(saved.id) == saved
    assert reopened_cabinet.list_medications() == [saved]
    updated = reopened_cabinet.save_medication(replace(saved, strength="500 mg", form="tablet"))
    reopened_repository.initialize()
    assert reopened_cabinet.get_medication(saved.id) == updated
    assert updated.created_at == saved.created_at


def test_sqlite_stores_photos_as_blobs_and_options_as_json(cabinet, tmp_path):
    saved = cabinet.save_medication(
        Medication(
            photo=b"compressed photo bytes",
            uses=["Personal reason"],
            frequency=Frequency("interval", 8, "hours"),
        )
    )

    with closing(sqlite3.connect(tmp_path / "medclue.db")) as connection:
        row = connection.execute(
            "SELECT typeof(photo), photo, uses, frequency FROM medications "
            "WHERE id = ?",
            (saved.id,),
        ).fetchone()

    assert row[0] == "blob"
    assert row[1] == saved.photo
    assert json.loads(row[2]) == ["Personal reason"]
    assert json.loads(row[3])["type"] == "interval"
    assert json.loads(row[3])["value"] == 8
    assert json.loads(row[3])["unit"] == "hours"


def test_edit_keeps_id_creation_time_and_recent_order(cabinet):
    first = cabinet.save_medication(Medication(name="Paracetamol", photo=b"old"))
    second = cabinet.save_medication(Medication(name="Amoxicillin"))
    draft = replace(
        first,
        notes="Updated notes",
        photo=b"new",
        created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )

    updated = cabinet.save_medication(draft)

    assert updated.id == first.id
    assert updated.created_at == first.created_at
    assert updated.notes == "Updated notes"
    assert updated.photo == b"new"
    assert cabinet.list_medications() == [second, updated]
    assert draft.created_at.year == 2000


def test_edit_can_clear_optional_fields_and_remove_the_photo(cabinet):
    saved = cabinet.save_medication(
        Medication(
            name="Paracetamol", photo=b"photo", uses=["Pain"],
            prescription_date=date(2026, 11, 1),
            treatment_end=TreatmentEnd("unknown"),
        )
    )

    updated = cabinet.save_medication(
        replace(
            saved, photo=None, uses=[], prescription_date=None,
            treatment_end=None,
        )
    )

    assert updated.photo is None
    assert updated.uses == []
    assert updated.prescription_date is None
    assert updated.treatment_end is None
    assert updated.name == saved.name
    assert cabinet.get_medication(saved.id) == updated


@pytest.mark.parametrize(
    "query, expected_names",
    [
        ("PARA", ["Paracetamol"]),
        ("  pain   RELIEF ", ["Paracetamol"]),
        ("infection", ["Amoxicillin"]),
        ("Personal reason", [None]),
        ("private note", []),
        ("Unknown medication", []),
        ("No match", []),
        ("", [None, "Amoxicillin", "Paracetamol"]),
        ("   ", [None, "Amoxicillin", "Paracetamol"]),
    ],
)
def test_search_uses_only_saved_names_and_reasons(cabinet, query, expected_names):
    cabinet.save_medication(Medication(name="Paracetamol", uses=["Pain relief"], notes="private note"))
    cabinet.save_medication(Medication(name="Amoxicillin", uses=["Infection"]))
    cabinet.save_medication(Medication(uses=["Personal reason"]))

    matches = cabinet.list_medications(query)

    assert [medication.name for medication in matches] == expected_names


@pytest.mark.parametrize(
    "query, expected_names",
    [
        ("", ["amoxicillin", "Paracetamol", None]),
        ("a", ["amoxicillin", "Paracetamol"]),
    ],
)
def test_name_sort_ignores_case_and_places_unnamed_records_last(cabinet, query, expected_names):
    cabinet.save_medication(Medication(name="Paracetamol"))
    cabinet.save_medication(Medication(name="amoxicillin"))
    cabinet.save_medication(Medication(notes="No name"))

    medications = cabinet.list_medications(query, sort_order="name_az")

    assert [medication.name for medication in medications] == expected_names


def test_duplicate_name_requires_confirmation_without_changing_the_draft(cabinet):
    saved = cabinet.save_medication(Medication(name="Paracetamol"))
    draft = Medication(name=" PARACETAMOL ", notes="Keep this note")
    original = deepcopy(draft)

    with pytest.raises(DuplicateMedicationError):
        cabinet.save_medication(draft)

    assert cabinet.list_medications() == [saved]
    assert draft == original


def test_confirmed_duplicate_creates_a_separate_record(cabinet):
    first = cabinet.save_medication(Medication(name="Paracetamol", notes="First"))
    second = cabinet.save_medication(Medication(name="Paracetamol", notes="Second"), allow_duplicate=True)

    assert second.id != first.id
    assert cabinet.get_medication(first.id) == first
    assert cabinet.list_medications() == [second, first]


@pytest.mark.parametrize("edited_name", ["Paracetamol", " PARACETAMOL "])
def test_editing_an_existing_duplicate_does_not_repeat_the_warning(cabinet, edited_name):
    first = cabinet.save_medication(Medication(name="Paracetamol"))
    second = cabinet.save_medication(Medication(name="Paracetamol"), allow_duplicate=True)
    updated = cabinet.save_medication(replace(first, name=edited_name, notes="Updated notes"))

    assert updated.notes == "Updated notes"
    assert updated.name == edited_name
    assert updated.created_at == first.created_at
    assert cabinet.get_medication(second.id) == second
    assert len(cabinet.list_medications()) == 2


def test_renaming_to_an_existing_name_requires_confirmation(cabinet):
    first = cabinet.save_medication(Medication(name="Paracetamol"))
    second = cabinet.save_medication(Medication(name="Amoxicillin"))
    draft = replace(second, name="Paracetamol")

    with pytest.raises(DuplicateMedicationError):
        cabinet.save_medication(draft)

    assert cabinet.get_medication(second.id) == second

    confirmed = cabinet.save_medication(draft, allow_duplicate=True)

    assert confirmed.id == second.id
    assert confirmed.created_at == second.created_at
    assert cabinet.get_medication(first.id) == first
    assert len(cabinet.list_medications()) == 2


@pytest.mark.parametrize("new_name", ["Amoxicillin", None])
def test_changing_to_a_unique_or_empty_name_needs_no_confirmation(cabinet, new_name):
    saved = cabinet.save_medication(Medication(name="Paracetamol", notes="Keep"))

    updated = cabinet.save_medication(replace(saved, name=new_name))

    assert updated.name == new_name
    assert updated.id == saved.id
    assert cabinet.get_medication(saved.id) == updated


def test_multiple_unnamed_records_need_no_confirmation(cabinet):
    first = cabinet.save_medication(Medication(notes="First record"))
    second = cabinet.save_medication(Medication(notes="Second record"))

    assert first.name is None
    assert second.name is None
    assert second.id != first.id
    assert cabinet.get_medication(first.id) == first
    assert cabinet.get_medication(second.id) == second


def test_duplicate_search_matches_full_names_and_excludes_the_current_record(cabinet):
    saved = cabinet.save_medication(Medication(name="Vitamin C"))

    assert cabinet.find_duplicates(" VITAMIN   C ") == [saved]
    assert cabinet.find_duplicates("Vitamin") == []
    assert cabinet.find_duplicates(saved.name, exclude_id=saved.id) == []
    assert cabinet.find_duplicates(None) == []
    assert cabinet.find_duplicates("  ") == []


def test_delete_removes_the_record_and_its_photo(cabinet, tmp_path):
    saved = cabinet.save_medication(Medication(name="Paracetamol", photo=b"photo"))

    cabinet.delete_medication(saved.id)

    assert cabinet.list_medications() == []
    with closing(sqlite3.connect(tmp_path / "medclue.db")) as connection:
        row = connection.execute(
            "SELECT id, photo FROM medications WHERE id = ?", (saved.id,)
        ).fetchone()
    assert row is None
    with pytest.raises(LookupError):
        cabinet.get_medication(saved.id)


def test_empty_records_are_not_written(cabinet):
    with pytest.raises(ValueError, match="at least one piece of information"):
        cabinet.save_medication(Medication())

    assert cabinet.list_medications() == []


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE", "DELETE"])
def test_failed_writes_keep_stored_records_and_entered_values(cabinet, tmp_path, operation):
    saved = cabinet.save_medication(Medication(name="Paracetamol", photo=b"old"))
    if operation != "DELETE":
        if operation == "INSERT":
            draft = Medication(name="Amoxicillin", notes="Keep this draft")
        else:
            draft = replace(saved, notes="Changed notes", photo=b"new")
        original = deepcopy(draft)

    with closing(sqlite3.connect(tmp_path / "medclue.db")) as connection:
        with connection:
            connection.execute(
                f"""
                CREATE TRIGGER fail_write AFTER {operation} ON medications
                BEGIN SELECT RAISE(FAIL, 'Forced storage failure'); END
                """
            )

    with pytest.raises(sqlite3.IntegrityError, match="Forced storage failure"):
        if operation == "DELETE":
            cabinet.delete_medication(saved.id)
        else:
            cabinet.save_medication(draft)

    assert cabinet.list_medications() == [saved]
    if operation != "DELETE":
        assert draft == original

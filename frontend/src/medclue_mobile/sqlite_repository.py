"""Read and write medication records in the local SQLite database."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from medclue_mobile.medications import (
    Amount,
    FoodInstructions,
    Frequency,
    Medication,
    TreatmentEnd,
    validate_medication,
)


class MedicationRepository:
    """Manage medication records in a local SQLite database."""

    def __init__(self, database_path: str | Path):
        self._database_path = Path(database_path)

    def initialize(self) -> None:
        """Create the medications table if it does not exist."""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS medications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        strength TEXT,
                        form TEXT,
                        photo BLOB,
                        uses TEXT,
                        amount TEXT,
                        frequency TEXT,
                        food TEXT,
                        prescription_date TEXT,
                        treatment_end TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # Older installations keep their records when the app is updated.
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(medications)")}
                for column in ("strength", "form"):
                    if column not in columns:
                        connection.execute(f"ALTER TABLE medications ADD COLUMN {column} TEXT")

    def add(self, medication: Medication) -> Medication:
        validate_medication(medication)
        if medication.id is not None or medication.created_at is not None:
            raise ValueError("A new medication cannot have saved record metadata.")

        values = _medication_values(medication)
        values["created_at"] = datetime.now(timezone.utc).isoformat()

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO medications (
                        name, strength, form, photo, uses, amount, frequency, food,
                        prescription_date, treatment_end, notes, created_at
                    ) VALUES (
                        :name, :strength, :form, :photo, :uses, :amount, :frequency, :food,
                        :prescription_date, :treatment_end, :notes, :created_at
                    )
                    """,
                    values,
                )
                row = connection.execute("SELECT * FROM medications WHERE id = ?", (cursor.lastrowid,)).fetchone()
                saved_medication = _medication_from_row(row)

        return saved_medication

    def get(self, medication_id: int) -> Medication | None:
        _validate_record_id(medication_id)
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM medications WHERE id = ?", (medication_id,)).fetchone()

        return _medication_from_row(row) if row is not None else None

    def count(self) -> int:
        """Count saved records without reading their photos or other fields."""
        with closing(self._connect()) as connection:
            return connection.execute("SELECT COUNT(*) FROM medications").fetchone()[0]

    def list_all(self) -> list[Medication]:
        """Return all medications ordered by creation date, newest first."""
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM medications ORDER BY created_at DESC, id DESC").fetchall()

        return [_medication_from_row(row) for row in rows]

    def update(self, medication: Medication) -> Medication:
        """Update user fields while keeping the stored ID and creation time."""
        validate_medication(medication)
        _validate_record_id(medication.id)
        values = _medication_values(medication)
        values["id"] = medication.id

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE medications SET
                        name = :name,
                        strength = :strength,
                        form = :form,
                        photo = :photo,
                        uses = :uses,
                        amount = :amount,
                        frequency = :frequency,
                        food = :food,
                        prescription_date = :prescription_date,
                        treatment_end = :treatment_end,
                        notes = :notes
                    WHERE id = :id
                    """,
                    values,
                )
                if cursor.rowcount == 0:
                    raise LookupError("The medication record was not found.")
                row = connection.execute("SELECT * FROM medications WHERE id = ?", (medication.id,)).fetchone()
                saved_medication = _medication_from_row(row)

        return saved_medication

    def delete(self, medication_id: int) -> None:
        _validate_record_id(medication_id)
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute("DELETE FROM medications WHERE id = ?", (medication_id,))
                if cursor.rowcount == 0:
                    raise LookupError("The medication record was not found.")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _validate_record_id(medication_id: int | None) -> None:
    if type(medication_id) is not int or medication_id <= 0:
        raise ValueError("The record ID must be a positive integer.")


def _medication_values(medication: Medication) -> dict:
    return {
        "name": medication.name,
        "strength": medication.strength,
        "form": medication.form,
        "photo": medication.photo,
        "uses": json.dumps(medication.uses, ensure_ascii=False),
        "amount": _option_json(medication.amount),
        "frequency": _option_json(medication.frequency),
        "food": _option_json(medication.food),
        "prescription_date": medication.prescription_date.isoformat()
        if medication.prescription_date is not None else None,
        "treatment_end": _option_json(medication.treatment_end),
        "notes": medication.notes,
    }


def _option_json(option: Amount | Frequency | FoodInstructions | TreatmentEnd | None) -> str | None:
    if option is None:
        return None

    fields = asdict(option)
    if isinstance(option, TreatmentEnd) and option.end_date is not None:
        fields["end_date"] = option.end_date.isoformat()
    return json.dumps(fields, ensure_ascii=False, allow_nan=False)


def _medication_from_row(row: sqlite3.Row) -> Medication:
    """Convert a database row into a validated Medication object."""
    try:
        amount = (
            Amount(**json.loads(row["amount"]))
            if row["amount"] is not None else None
        )
        frequency = (
            Frequency(**json.loads(row["frequency"]))
            if row["frequency"] is not None else None
        )
        food = (
            FoodInstructions(**json.loads(row["food"]))
            if row["food"] is not None else None
        )
        treatment_end = None
        if row["treatment_end"] is not None:
            end_fields = json.loads(row["treatment_end"])
            if not isinstance(end_fields, dict):
                raise ValueError("The saved treatment end must be a JSON object.")
            if end_fields.get("end_date") is not None:
                end_fields["end_date"] = date.fromisoformat(end_fields["end_date"])
            treatment_end = TreatmentEnd(**end_fields)

        medication = Medication(
            id=row["id"],
            name=row["name"],
            strength=row["strength"],
            form=row["form"],
            photo=row["photo"],
            uses=json.loads(row["uses"]) if row["uses"] is not None else [],
            amount=amount,
            frequency=frequency,
            food=food,
            prescription_date=date.fromisoformat(row["prescription_date"])
            if row["prescription_date"] is not None else None,
            treatment_end=treatment_end,
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        validate_medication(medication)
    except (TypeError, ValueError) as error:
        raise ValueError("The saved medication contains invalid values.") from error

    return medication

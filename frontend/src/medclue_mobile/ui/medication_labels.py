"""Define display labels for medication options."""

FREQUENCY_LABELS = {
    "once_daily": "Once a day",
    "twice_daily": "Twice a day",
    "three_times_daily": "Three times a day",
    "interval": "Every X",
    "as_needed": "As needed",
    "custom": "Other / Custom instructions",
    "not_specified": "Not specified",
}
FOOD_LABELS = {
    "before_meals": "Before meals",
    "with_food": "With food",
    "after_meals": "After meals",
    "empty_stomach": "On an empty stomach",
    "with_or_without_food": "With or without food",
    "not_applicable": "Not applicable",
    "custom": "Other / Custom instructions",
}
TREATMENT_END_LABELS = {
    "date": "I have an end date",
    "no_end_date": "No end date was given",
    "not_taking": "I'm not currently taking it",
    "unknown": "I don't know",
}
AMOUNT_UNIT_LABELS = {
    "tablets": "Tablet(s)", "capsules": "Capsule(s)", "mL": "mL",
    "drops": "Drop(s)", "puffs": "Puff(s)", "sprays": "Spray(s)",
    "sachets": "Sachet(s)", "patches": "Patch(es)", "mg": "mg", "g": "g",
}
UNKNOWN_REASON = "I don't know / I don't remember"

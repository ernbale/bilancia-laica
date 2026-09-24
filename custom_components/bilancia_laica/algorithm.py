"""Formule di composizione corporea (algoritmo YoHealth ricostruito).

Le formule sono quelle ricostruite da piggei dall'implementazione nativa
YoHealth: github.com/piggei/home-assistant-laica-ble (licenza MIT).
Servono a riprodurre i numeri dell'app LAICA, non sono valori medici.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .const import SEX_MALE


@dataclass(frozen=True, slots=True)
class BodyMetrics:
    """Valori calcolati da peso + impedenza + profilo."""

    bmi: float
    body_fat_pct: float
    water_pct: float
    muscle_pct: float
    bone_mass_kg: float
    visceral_fat_pct: float
    bmr_kcal_per_day: int
    body_age: int


def age_on(birth_date: date, today: date) -> int:
    """Età in anni compiuti."""
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def bmi_only(weight_kg: float, height_cm: float) -> float:
    """BMI da solo peso e altezza (funziona anche senza impedenza)."""
    height_m = height_cm / 100.0
    return weight_kg / (height_m * height_m)


def calculate(
    *, weight_kg: float, impedance: int, height_cm: float, age: int, sex: str
) -> BodyMetrics:
    """Composizione corporea completa."""
    male = sex == SEX_MALE
    sex_native = 0.0 if male else 1.0

    bmi = bmi_only(weight_kg, height_cm)

    lean_mass_kg = (
        0.00067 * height_cm * height_cm
        + 2.0
        + 0.53 * weight_kg
        - 0.00095 * impedance
        - 3.0 * sex_native
        - 0.05 * age
    )

    fat = (weight_kg - lean_mass_kg) / weight_kg
    if fat < 0.10:
        fat = fat + 0.7 * (0.10 - fat)

    water = 0.73 * lean_mass_kg / weight_kg

    if male:
        muscle_pct = (7.78 * height_cm + 334.0 - 9.8 * age) / weight_kg + 24.4
        bmr = 13.7 * weight_kg + 5.0 * height_cm - 6.8 * age + 66.0
    else:
        muscle_pct = (7.74 * height_cm - 318.0 - 9.8 * age) / weight_kg + 24.4
        bmr = 9.6 * weight_kg + 1.8 * height_cm - 4.7 * age + 655.0

    bone = (
        0.0077200001 * weight_kg
        + 0.0045 * height_cm
        + 1.95
        - 0.00636 * age
        - 0.000232 * impedance
    )
    if not male:
        bone *= 0.75

    visceral = fat * (0.45 if male else 0.20) * 100.0

    if age < 20:
        body_age = age
    elif bmi > 28.0:
        body_age = age + 15
    elif bmi > 26.0:
        body_age = age + 12
    elif bmi > 25.0:
        body_age = age + 7
    elif bmi > 23.0:
        body_age = age + 4
    elif age < 30:
        body_age = 18
    elif age <= 44:
        body_age = age - 12
    else:
        body_age = age - 16

    return BodyMetrics(
        bmi=bmi,
        body_fat_pct=fat * 100.0,
        water_pct=water * 100.0,
        muscle_pct=muscle_pct,
        bone_mass_kg=bone,
        visceral_fat_pct=visceral,
        bmr_kcal_per_day=math.floor(bmr + 0.5),
        body_age=body_age,
    )

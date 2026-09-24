"""Costanti dell'integrazione Bilancia Laica."""

from typing import Final

DOMAIN: Final = "bilancia_laica"
MANUFACTURER: Final = "LAICA"
DEFAULT_MODEL: Final = "PS7002L"

CONF_SEX: Final = "sex"
CONF_BIRTH_DATE: Final = "birth_date"
CONF_HEIGHT_CM: Final = "height_cm"
CONF_MODEL: Final = "model"

SEX_MALE: Final = "male"
SEX_FEMALE: Final = "female"

# Manufacturer ID del modulo YoHealth (bytes 02 A1 sull'aria → 0xA102).
YOHEALTH_COMPANY_ID: Final = 0xA102

# Stati del frame.
STATUS_REALTIME: Final = 0x80  # peso in corso, non stabile
STATUS_STABLE: Final = 0x82  # peso stabile, senza impedenza
STATUS_FINAL: Final = 0x86  # peso + impedenza (composizione corporea)

# Chiavi dei sensori.
KEY_WEIGHT: Final = "weight"
KEY_LAST_WEIGHING: Final = "last_weighing"
KEY_IMPEDANCE: Final = "impedance"
KEY_BMI: Final = "bmi"
KEY_BODY_FAT: Final = "body_fat"
KEY_WATER: Final = "body_water"
KEY_MUSCLE: Final = "muscle"
KEY_BONE: Final = "bone_mass"
KEY_VISCERAL_FAT: Final = "visceral_fat"
KEY_BMR: Final = "bmr"
KEY_BODY_AGE: Final = "body_age"

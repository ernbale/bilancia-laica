"""Protocollo e formule, senza Home Assistant."""

from datetime import date

from custom_components.bilancia_laica.algorithm import age_on, bmi_only, calculate
from custom_components.bilancia_laica.const import STATUS_FINAL, STATUS_STABLE
from custom_components.bilancia_laica.protocol import (
    checksum,
    parse_manufacturer_data,
    parse_payload,
)

# Campioni veri della PS7002L di casa (21 settembre 2026).
SOCKS = bytes.fromhex("09ff0486ffff82000021d6aa")  # 115,8 kg, calzini
FULL = bytes.fromhex("09ff048401fc86000021d7aa")  # 115,6 kg + 508 ohm
REALTIME = bytes.fromhex("09ff0486ffff80000021d4aa")  # in corso


def test_socks_frame_is_weight_only() -> None:
    frame = parse_payload(SOCKS)
    assert frame is not None
    assert frame.weight_kg == 115.8
    assert frame.impedance is None
    assert frame.status == STATUS_STABLE
    assert frame.is_weighing and not frame.has_composition


def test_full_frame_has_composition() -> None:
    frame = parse_payload(FULL)
    assert frame is not None
    assert frame.weight_kg == 115.6
    assert frame.impedance == 508
    assert frame.status == STATUS_FINAL
    assert frame.is_weighing and frame.has_composition


def test_realtime_frame_is_not_a_weighing() -> None:
    frame = parse_payload(REALTIME)
    assert frame is not None
    assert not frame.is_weighing


def test_bad_checksum_rejected() -> None:
    bad = bytearray(SOCKS)
    bad[10] ^= 0x01
    assert parse_payload(bytes(bad)) is None


def test_wrong_length_or_header_rejected() -> None:
    assert parse_payload(SOCKS[:-1]) is None
    assert parse_payload(b"\x00" + SOCKS[1:]) is None
    assert parse_payload(SOCKS[:-1] + b"\x00") is None


def test_checksum_matches_samples() -> None:
    assert checksum(SOCKS) == SOCKS[10]
    assert checksum(FULL) == FULL[10]


def test_manufacturer_data_lookup() -> None:
    assert parse_manufacturer_data({0xA102: SOCKS}) is not None
    assert parse_manufacturer_data({0x004C: SOCKS}) is None
    assert parse_manufacturer_data({}) is None


def test_age() -> None:
    assert age_on(date(1974, 7, 17), date(2026, 9, 21)) == 52
    assert age_on(date(1974, 7, 17), date(2026, 7, 16)) == 51


def test_metrics_match_first_measurement_of_21_september() -> None:
    """115,6 kg · 508 Ω · uomo · 1974 · 174 cm → i numeri visti in HA."""
    m = calculate(weight_kg=115.6, impedance=508, height_cm=174, age=52, sex="male")
    assert round(m.bmi, 1) == 38.2
    assert round(m.body_fat_pct, 1) == 30.4
    assert round(m.water_pct, 1) == 50.8
    assert round(m.muscle_pct, 1) == 34.6
    assert round(m.bone_mass_kg, 2) == 3.18
    assert round(m.visceral_fat_pct, 1) == 13.7
    assert m.bmr_kcal_per_day == 2166
    assert m.body_age == 67


def test_bmi_without_impedance() -> None:
    assert round(bmi_only(113.9, 174), 1) == 37.6

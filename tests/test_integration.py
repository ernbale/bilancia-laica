"""L'integrazione intera dentro un Home Assistant di test, con advertising finti."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.api import _get_manager
from homeassistant.components.logbook import EVENT_LOGBOOK_ENTRY
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)
from .conftest import (
    generate_advertisement_data,
    generate_ble_device,
    inject_bluetooth_service_info,
)

from custom_components.bilancia_laica.const import (
    CONF_BIRTH_DATE,
    CONF_HEIGHT_CM,
    CONF_MODEL,
    CONF_SEX,
    DOMAIN,
)

ADDRESS = "FF:FF:FF:FF:FF:D0"
SOCKS = bytes.fromhex("09ff0486ffff82000021d6aa")  # 115,8 kg
SOCKS_2 = bytes.fromhex("09ff0473ffff82000021c3aa")  # 113,9 kg
FULL = bytes.fromhex("09ff048401fc86000021d7aa")  # 115,6 kg + 508 ohm
REALTIME = bytes.fromhex("09ff0486ffff80000021d4aa")

PESO = "sensor.bilancia_laica_ps7002l_body_weight"
ULTIMA = "sensor.bilancia_laica_ps7002l_last_weighing"
GRASSO = "sensor.bilancia_laica_ps7002l_body_fat"
ACQUA = "sensor.bilancia_laica_ps7002l_body_water"
IMPEDENZA = "sensor.bilancia_laica_ps7002l_impedance"
BMI = "sensor.bilancia_laica_ps7002l_bmi"


def info(payload: bytes, rssi: int = -85) -> BluetoothServiceInfoBleak:
    return BluetoothServiceInfoBleak(
        name="YoHealth",
        address=ADDRESS,
        rssi=rssi,
        manufacturer_data={0xA102: payload},
        service_data={},
        service_uuids=[],
        source="proxy",
        device=generate_ble_device(ADDRESS, "YoHealth"),
        advertisement=generate_advertisement_data(
            local_name="YoHealth", manufacturer_data={0xA102: payload}
        ),
        time=0,
        connectable=False,
        tx_power=None,
    )


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bilancia Laica PS7002L",
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS},
        options={
            CONF_SEX: "male",
            CONF_BIRTH_DATE: "1974-07-17",
            CONF_HEIGHT_CM: 174.0,
            CONF_MODEL: "PS7002L",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def state(hass: HomeAssistant, entity_id: str) -> Any:
    s = hass.states.get(entity_id)
    assert s is not None, entity_id
    return s.state


async def test_entities_exist_but_unavailable_before_first_weighing(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    for e in (PESO, ULTIMA, GRASSO, IMPEDENZA):
        assert state(hass, e) == "unavailable"


async def test_socks_weighing_updates_weight_and_time_only(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    events = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    inject_bluetooth_service_info(hass, info(REALTIME))
    inject_bluetooth_service_info(hass, info(SOCKS))
    await hass.async_block_till_done()

    assert state(hass, PESO) == "115.8"
    assert state(hass, ULTIMA) != "unavailable"
    assert state(hass, BMI) != "unavailable"  # BMI si calcola dal solo peso
    assert state(hass, GRASSO) == "unavailable"  # senza impedenza niente composizione
    assert len(events) == 1
    assert "115.8" in events[0].data["message"]
    assert events[0].data["entity_id"] == PESO


async def test_full_weighing_computes_composition(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    inject_bluetooth_service_info(hass, info(FULL))
    await hass.async_block_till_done()

    assert state(hass, PESO) == "115.6"
    assert state(hass, IMPEDENZA) == "508"
    assert round(float(state(hass, GRASSO)), 1) == 30.4
    assert round(float(state(hass, ACQUA)), 1) == 50.8


async def test_socks_after_full_keeps_last_composition(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    inject_bluetooth_service_info(hass, info(FULL))
    await hass.async_block_till_done()
    inject_bluetooth_service_info(hass, info(SOCKS_2))
    await hass.async_block_till_done()

    assert state(hass, PESO) == "113.9"
    assert state(hass, IMPEDENZA) == "508"
    assert round(float(state(hass, GRASSO)), 1) == 30.4


async def test_repeated_frame_is_one_weighing_but_later_same_weight_is_another(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    events = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    scale = entry.runtime_data

    inject_bluetooth_service_info(hass, info(SOCKS))
    await hass.async_block_till_done()
    first_time = state(hass, ULTIMA)
    assert len(events) == 1

    # Lo stesso frame ripetuto (solo RSSI diverso) entro 60 s: stessa pesata.
    inject_bluetooth_service_info(hass, info(SOCKS, rssi=-80))
    await hass.async_block_till_done()
    assert len(events) == 1

    # Scendo e risalgo (frame 0x80 in mezzo), stesso identico peso: è una
    # pesata nuova. Successo davvero il 24 set: calzini, poi scalzo, 113,9 kg
    # tutte e due le volte, e la seconda era stata scartata.
    inject_bluetooth_service_info(hass, info(REALTIME))
    inject_bluetooth_service_info(hass, info(SOCKS, rssi=-70))
    await hass.async_block_till_done()
    assert len(events) == 2

    # Domani mattina, stesso identico peso. Quando la bilancia tace, HA toglie
    # l'indirizzo dalla sua storia (habluetooth _async_check_unavailable →
    # history.pop), quindi il frame identico viene ripassato: è una pesata nuova.
    _get_manager(hass)._all_history.pop(ADDRESS, None)
    with (
        patch(
            "custom_components.bilancia_laica.time.monotonic",
            return_value=scale._last_payload_at + 24 * 3600,
        ),
        patch(
            "custom_components.bilancia_laica.dt_util.now",
            return_value=dt_util.now() + timedelta(days=1),
        ),
    ):
        inject_bluetooth_service_info(hass, info(SOCKS, rssi=-90))
        await hass.async_block_till_done()
    assert len(events) == 3
    assert state(hass, ULTIMA) != first_time
    assert state(hass, PESO) == "115.8"


async def test_two_weighings_same_session_both_count(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Prima coi calzini, poi scalzo un minuto dopo: sono due pesate."""
    events = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    inject_bluetooth_service_info(hass, info(SOCKS))
    await hass.async_block_till_done()
    inject_bluetooth_service_info(hass, info(FULL))
    await hass.async_block_till_done()
    assert len(events) == 2
    assert state(hass, PESO) == "115.6"


async def test_values_survive_restart(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    inject_bluetooth_service_info(hass, info(FULL))
    await hass.async_block_till_done()
    ultima = state(hass, ULTIMA)

    # Riavvio: scarico e ricarico l'entry senza nessun advertising in giro.
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # RestoreSensor legge dallo storage degli stati: lo forziamo a scrivere.
    from homeassistant.helpers.restore_state import async_get

    await async_get(hass).async_dump_states()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert state(hass, PESO) == "115.6"
    assert state(hass, IMPEDENZA) == "508"
    assert round(float(state(hass, GRASSO)), 1) == 30.4
    assert state(hass, ULTIMA) == ultima


async def test_options_change_recalculates_without_new_weighing(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    inject_bluetooth_service_info(hass, info(FULL))
    await hass.async_block_till_done()
    before = float(state(hass, GRASSO))

    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_HEIGHT_CM: 180.0}
    )
    await hass.async_block_till_done()

    after = float(state(hass, GRASSO))
    assert after != before
    assert round(float(state(hass, BMI)), 1) == round(115.6 / 1.8**2, 1)


async def test_realtime_frames_do_nothing(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    events = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    inject_bluetooth_service_info(hass, info(REALTIME))
    await hass.async_block_till_done()
    assert state(hass, PESO) == "unavailable"
    assert not events


async def test_unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(PESO).state == "unavailable"

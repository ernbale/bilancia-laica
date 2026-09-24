"""Fixture e helper Bluetooth (copiati da quelli dei test di Home Assistant core)."""

from __future__ import annotations

import time

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.api import _get_manager
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Carica custom_components."""


@pytest.fixture(autouse=True)
async def bluetooth_ready(hass: HomeAssistant, mock_bluetooth: None) -> None:
    """Il componente bluetooth deve esistere (finto, senza adattatori veri)."""
    assert await async_setup_component(hass, "bluetooth", {})
    await hass.async_block_till_done()


def generate_ble_device(address: str, name: str) -> BLEDevice:
    return BLEDevice(address, name, {})


def generate_advertisement_data(**kwargs) -> AdvertisementData:
    base = {
        "local_name": None,
        "manufacturer_data": {},
        "service_data": {},
        "service_uuids": [],
        "rssi": -127,
        "platform_data": (),
        "tx_power": -127,
    }
    base.update(kwargs)
    return AdvertisementData(**base)


def inject_bluetooth_service_info(hass: HomeAssistant, info: BluetoothServiceInfoBleak) -> None:
    """Fa arrivare un advertising al manager Bluetooth di HA."""
    info.time = time.monotonic()
    _get_manager(hass).scanner_adv_received(info)

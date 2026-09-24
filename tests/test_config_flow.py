"""Flusso di configurazione e opzioni."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bilancia_laica.const import (
    CONF_BIRTH_DATE,
    CONF_HEIGHT_CM,
    CONF_MODEL,
    CONF_SEX,
    DOMAIN,
)

from .conftest import inject_bluetooth_service_info
from .test_integration import ADDRESS, SOCKS, info

PROFILE = {CONF_SEX: "male", CONF_BIRTH_DATE: "1974-07-17", CONF_HEIGHT_CM: 174, CONF_MODEL: "PS7002L"}


async def test_manual_address_then_profile(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "non-un-mac"}
    )
    assert result["errors"] == {CONF_ADDRESS: "invalid_address"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "ff:ff:ff:ff:ff:d0"}
    )
    assert result["step_id"] == "profile"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], PROFILE)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bilancia Laica PS7002L"
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["options"][CONF_HEIGHT_CM] == 174.0
    assert result["options"][CONF_BIRTH_DATE] == "1974-07-17"


async def test_discovered_scale_offered_in_list(hass: HomeAssistant) -> None:
    inject_bluetooth_service_info(hass, info(SOCKS))
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_ADDRESS)
    assert ADDRESS in schema[key].container


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info(SOCKS)
    )
    assert result["step_id"] == "profile"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PROFILE)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_future_birth_date_rejected(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info(SOCKS)
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**PROFILE, CONF_BIRTH_DATE: "2999-01-01"}
    )
    assert result["errors"] == {CONF_BIRTH_DATE: "birth_date_in_future"}


async def test_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}, options=PROFILE).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info(SOCKS)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}, options=PROFILE)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**PROFILE, CONF_HEIGHT_CM: 180}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_HEIGHT_CM] == 180.0

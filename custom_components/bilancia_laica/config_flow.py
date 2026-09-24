"""Configurazione della Bilancia Laica: bilancia + profilo di chi si pesa."""

from __future__ import annotations

from datetime import date
import re
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BIRTH_DATE,
    CONF_HEIGHT_CM,
    CONF_MODEL,
    CONF_SEX,
    DEFAULT_MODEL,
    DOMAIN,
    SEX_FEMALE,
    SEX_MALE,
)
from .protocol import looks_like_scale

MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def _profile_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_SEX, default=d.get(CONF_SEX, SEX_MALE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SEX_MALE, SEX_FEMALE],
                    translation_key="sex",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_BIRTH_DATE, default=d.get(CONF_BIRTH_DATE, "1974-01-01")
            ): selector.DateSelector(),
            vol.Required(
                CONF_HEIGHT_CM, default=d.get(CONF_HEIGHT_CM, 175)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=80,
                    max=250,
                    step=0.5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="cm",
                )
            ),
            vol.Required(
                CONF_MODEL, default=d.get(CONF_MODEL, DEFAULT_MODEL)
            ): selector.TextSelector(),
        }
    )


def _validate(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Controlla il profilo e lo normalizza."""
    errors: dict[str, str] = {}
    try:
        birth = date.fromisoformat(str(user_input[CONF_BIRTH_DATE]))
    except ValueError:
        errors[CONF_BIRTH_DATE] = "invalid_birth_date"
        return {}, errors
    today = dt_util.now().date()
    if birth > today:
        errors[CONF_BIRTH_DATE] = "birth_date_in_future"
    elif today.year - birth.year > 130:
        errors[CONF_BIRTH_DATE] = "invalid_birth_date"
    model = str(user_input[CONF_MODEL]).strip() or DEFAULT_MODEL
    options = {
        CONF_SEX: user_input[CONF_SEX],
        CONF_BIRTH_DATE: birth.isoformat(),
        CONF_HEIGHT_CM: float(user_input[CONF_HEIGHT_CM]),
        CONF_MODEL: model,
    }
    return options, errors


def _title(model: str) -> str:
    model = model.strip()
    return model if model.lower().startswith("laica") else f"Bilancia Laica {model}"


class BilanciaLaicaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Scoperta Bluetooth o scelta manuale, poi il profilo."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._discovered: dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BilanciaLaicaOptionsFlow:
        """Opzioni: il profilo si può cambiare dopo."""
        return BilanciaLaicaOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """La bilancia è stata vista in giro."""
        if not looks_like_scale(discovery_info.manufacturer_data):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self.context["title_placeholders"] = {"name": _label(discovery_info)}
        return await self.async_step_profile()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Scelta fra le bilance che trasmettono, o indirizzo scritto a mano."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = str(user_input[CONF_ADDRESS]).strip().upper()
            if not MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._address = address
                return await self.async_step_profile()

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, False):
            if info.address in configured or info.address in self._discovered:
                continue
            if looks_like_scale(info.manufacturer_data):
                self._discovered[info.address] = _label(info)

        if self._discovered:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)})
        else:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): selector.TextSelector()})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sesso, data di nascita, altezza, modello."""
        assert self._address is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=_title(options[CONF_MODEL]),
                    data={CONF_ADDRESS: self._address},
                    options=options,
                )
        return self.async_show_form(
            step_id="profile",
            data_schema=_profile_schema(user_input),
            errors=errors,
            description_placeholders={"address": self._address},
        )


class BilanciaLaicaOptionsFlow(OptionsFlow):
    """Cambia il profilo: i valori si ricalcolano subito."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Unico passo."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options, errors = _validate(user_input)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=_title(options[CONF_MODEL])
                )
                return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=_profile_schema(user_input or dict(self.config_entry.options)),
            errors=errors,
        )


def _label(info: BluetoothServiceInfoBleak) -> str:
    return f"{info.name or 'YoHealth'} ({info.address})"

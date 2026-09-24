"""Sensori della Bilancia Laica."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_ADDRESS, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ICON_URL, BilanciaConfigEntry, BilanciaLaica
from .const import (
    CONF_MODEL,
    DEFAULT_MODEL,
    DOMAIN,
    KEY_BMI,
    KEY_BMR,
    KEY_BODY_AGE,
    KEY_BODY_FAT,
    KEY_BONE,
    KEY_IMPEDANCE,
    KEY_LAST_WEIGHING,
    KEY_MUSCLE,
    KEY_VISCERAL_FAT,
    KEY_WATER,
    KEY_WEIGHT,
    MANUFACTURER,
)

PERCENT = "%"

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=KEY_WEIGHT,
        translation_key=KEY_WEIGHT,
        icon="mdi:scale-bathroom",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_LAST_WEIGHING,
        translation_key=KEY_LAST_WEIGHING,
        icon="mdi:clock-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=KEY_BMI,
        translation_key=KEY_BMI,
        icon="mdi:human",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_BODY_FAT,
        translation_key=KEY_BODY_FAT,
        icon="mdi:percent",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_WATER,
        translation_key=KEY_WATER,
        icon="mdi:water-percent",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_MUSCLE,
        translation_key=KEY_MUSCLE,
        icon="mdi:arm-flex",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_BONE,
        translation_key=KEY_BONE,
        icon="mdi:bone",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key=KEY_VISCERAL_FAT,
        translation_key=KEY_VISCERAL_FAT,
        icon="mdi:percent-circle-outline",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key=KEY_BMR,
        translation_key=KEY_BMR,
        icon="mdi:fire",
        native_unit_of_measurement="kcal/d",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_BODY_AGE,
        translation_key=KEY_BODY_AGE,
        icon="mdi:calendar-account",
        native_unit_of_measurement=UnitOfTime.YEARS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key=KEY_IMPEDANCE,
        translation_key=KEY_IMPEDANCE,
        icon="mdi:omega",
        native_unit_of_measurement="Ω",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BilanciaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea gli 11 sensori."""
    scale = entry.runtime_data
    async_add_entities(BilanciaSensor(scale, entry, d) for d in SENSORS)


class BilanciaSensor(RestoreSensor):
    """Un valore della bilancia. Resta disponibile fra una pesata e l'altra."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        scale: BilanciaLaica,
        entry: BilanciaConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        self.entity_description = description
        self._scale = scale
        address: str = entry.data[CONF_ADDRESS]
        model = entry.options.get(CONF_MODEL, DEFAULT_MODEL)
        self._attr_unique_id = f"{address}_{description.key}"
        if description.key == KEY_WEIGHT:
            self._attr_entity_picture = ICON_URL
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=model,
        )

    async def async_added_to_hass(self) -> None:
        """Ritrova il valore dopo un riavvio e si iscrive agli aggiornamenti."""
        await super().async_added_to_hass()
        if self.entity_description.key not in self._scale.data:
            last = await self.async_get_last_sensor_data()
            if last is not None and last.native_value is not None:
                self._scale.restore(self.entity_description.key, last.native_value)
        self.async_on_remove(self._scale.add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | float | int | None:
        """Ultimo valore noto."""
        value: Any = self._scale.data.get(self.entity_description.key)
        return value

    @property
    def available(self) -> bool:
        """Disponibile appena c'è un valore: la bilancia dorme fra le pesate."""
        return self.entity_description.key in self._scale.data

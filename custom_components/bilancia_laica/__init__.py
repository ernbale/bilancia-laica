"""Bilancia Laica: peso e composizione corporea dall'advertising BLE.

Nessun cancello, nessuna connessione: ogni frame «peso stabile» (0x82, anche
coi calzini) aggiorna peso e ora della pesata; ogni frame completo (0x86, con
impedenza) aggiorna anche la composizione corporea. Ogni pesata scrive una voce
nel registro (Attività) di Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from pathlib import Path
import time
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.logbook import async_log_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .algorithm import BodyMetrics, age_on, bmi_only, calculate
from .const import (
    CONF_BIRTH_DATE,
    CONF_HEIGHT_CM,
    CONF_SEX,
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
)
from .protocol import Frame, parse_manufacturer_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
ICON_URL = f"/{DOMAIN}/icon.png"
REPEAT_WINDOW_S = 60.0

type BilanciaConfigEntry = ConfigEntry[BilanciaLaica]


@dataclass
class Profile:
    """Chi si pesa: serve solo per le formule."""

    sex: str
    birth_date: date
    height_cm: float

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> Profile:
        """Legge il profilo dalle opzioni della config entry."""
        return cls(
            sex=entry.options[CONF_SEX],
            birth_date=date.fromisoformat(entry.options[CONF_BIRTH_DATE]),
            height_cm=float(entry.options[CONF_HEIGHT_CM]),
        )


@dataclass
class BilanciaLaica:
    """Ascolta la bilancia e tiene l'ultima misura."""

    hass: HomeAssistant
    entry: ConfigEntry
    address: str
    profile: Profile
    data: dict[str, Any] = field(default_factory=dict)
    last_frame: Frame | None = None
    _listeners: list[CALLBACK_TYPE] = field(default_factory=list)
    _unregister: CALLBACK_TYPE | None = None
    _last_payload: tuple[float, int | None, int] | None = None
    _last_payload_at: float = 0.0

    @callback
    def start(self) -> None:
        """Registra l'ascolto passivo sull'indirizzo della bilancia."""
        self._unregister = bluetooth.async_register_callback(
            self.hass,
            self._on_advertisement,
            BluetoothCallbackMatcher(address=self.address, connectable=False),
            BluetoothScanningMode.PASSIVE,
        )

    @callback
    def stop(self) -> None:
        """Ferma l'ascolto."""
        if self._unregister is not None:
            self._unregister()
            self._unregister = None

    @callback
    def add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Un sensore si iscrive agli aggiornamenti."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def _on_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        frame = parse_manufacturer_data(service_info.manufacturer_data)
        if frame is None:
            return
        _LOGGER.debug(
            "Frame da %s (%s, %d dBm): %.1f kg stato=0x%02X impedenza=%s",
            self.address,
            service_info.source,
            service_info.rssi,
            frame.weight_kg,
            frame.status,
            frame.impedance,
        )
        if not frame.is_weighing:
            # Frame «in corso» (0x80): qualcuno è appena salito. Da qui in poi
            # il prossimo peso stabile è una pesata nuova, anche se identico.
            self._last_payload = None
            return
        # La bilancia ripete lo stesso frame finché resta accesa: una pesata
        # sola non deve produrre dieci voci nel registro. Ma due pesate uguali
        # a distanza di tempo sono due pesate: la finestra è di 60 secondi.
        payload = (frame.weight_kg, frame.impedance, frame.status)
        now_mono = time.monotonic()
        if payload == self._last_payload and now_mono - self._last_payload_at < REPEAT_WINDOW_S:
            return
        self._last_payload = payload
        self._last_payload_at = now_mono
        self.accept(frame, dt_util.now())

    @callback
    def accept(self, frame: Frame, when: datetime) -> None:
        """Registra una pesata: peso sempre, composizione se c'è l'impedenza."""
        self.last_frame = frame
        self.data[KEY_WEIGHT] = frame.weight_kg
        self.data[KEY_LAST_WEIGHING] = when
        self.data[KEY_BMI] = bmi_only(frame.weight_kg, self.profile.height_cm)

        metrics: BodyMetrics | None = None
        if frame.has_composition:
            assert frame.impedance is not None
            metrics = self._compute(frame, when.date())
            self._store_metrics(frame.impedance, metrics)

        if metrics is None:
            message = f"Pesata: {frame.weight_kg:.1f} kg (solo peso)"
            _LOGGER.info("Pesata: %.1f kg, solo peso", frame.weight_kg)
        else:
            message = (
                f"Pesata: {frame.weight_kg:.1f} kg, grasso {metrics.body_fat_pct:.1f} %, "
                f"acqua {metrics.water_pct:.1f} %, muscoli {metrics.muscle_pct:.1f} %"
            )
            _LOGGER.info(
                "Pesata: %.1f kg, impedenza %s ohm, grasso %.1f %%",
                frame.weight_kg,
                frame.impedance,
                metrics.body_fat_pct,
            )
        self._log_activity(message)
        self._notify()

    def _compute(self, frame: Frame, today: date) -> BodyMetrics:
        assert frame.impedance is not None
        return calculate(
            weight_kg=frame.weight_kg,
            impedance=frame.impedance,
            height_cm=self.profile.height_cm,
            age=age_on(self.profile.birth_date, today),
            sex=self.profile.sex,
        )

    def _store_metrics(self, impedance: int, metrics: BodyMetrics) -> None:
        self.data[KEY_IMPEDANCE] = impedance
        self.data[KEY_BMI] = metrics.bmi
        self.data[KEY_BODY_FAT] = metrics.body_fat_pct
        self.data[KEY_WATER] = metrics.water_pct
        self.data[KEY_MUSCLE] = metrics.muscle_pct
        self.data[KEY_BONE] = metrics.bone_mass_kg
        self.data[KEY_VISCERAL_FAT] = metrics.visceral_fat_pct
        self.data[KEY_BMR] = metrics.bmr_kcal_per_day
        self.data[KEY_BODY_AGE] = metrics.body_age

    @callback
    def recalculate(self, profile: Profile) -> None:
        """Profilo cambiato: ricalcola sull'ultima pesata, senza ripesarsi."""
        self.profile = profile
        frame = self.last_frame
        if frame is None:
            return
        self.data[KEY_BMI] = bmi_only(frame.weight_kg, profile.height_cm)
        if frame.has_composition:
            assert frame.impedance is not None
            self._store_metrics(frame.impedance, self._compute(frame, dt_util.now().date()))
        self._notify()

    @callback
    def restore(self, key: str, value: Any) -> None:
        """Un sensore ha ritrovato il suo valore dopo un riavvio."""
        self.data.setdefault(key, value)

    def _log_activity(self, message: str) -> None:
        """Voce nel registro di HA, agganciata al sensore del peso."""
        async_log_entry(
            self.hass,
            name=self.entry.title,
            message=message,
            domain=DOMAIN,
            entity_id=self._weight_entity_id(),
        )

    def _weight_entity_id(self) -> str | None:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        return registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, f"{self.address}_{KEY_WEIGHT}"
        )


async def async_setup_entry(hass: HomeAssistant, entry: BilanciaConfigEntry) -> bool:
    """Avvia l'integrazione per una bilancia."""
    address: str = entry.data[CONF_ADDRESS]
    await _async_serve_icon(hass)
    scale = BilanciaLaica(hass, entry, address, Profile.from_entry(entry))
    entry.runtime_data = scale

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    scale.start()
    entry.async_on_unload(scale.stop)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_serve_icon(hass: HomeAssistant) -> None:
    """La foto della bilancia, servita dalla cartella dell'integrazione."""
    if hass.data.get(f"{DOMAIN}_icon_served"):
        return
    hass.data[f"{DOMAIN}_icon_served"] = True
    icon = Path(__file__).parent / "icon.png"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(ICON_URL, str(icon), cache_headers=True)]
    )


async def _async_options_updated(hass: HomeAssistant, entry: BilanciaConfigEntry) -> None:
    """Sesso, data di nascita o altezza cambiati dalle opzioni."""
    entry.runtime_data.recalculate(Profile.from_entry(entry))


async def async_unload_entry(hass: HomeAssistant, entry: BilanciaConfigEntry) -> bool:
    """Scarica l'integrazione."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rimossa: la bilancia torna scopribile subito."""
    bluetooth.async_rediscover_address(hass, entry.data[CONF_ADDRESS])


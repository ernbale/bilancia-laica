"""Decodifica dell'advertising BLE YoHealth (bilance LAICA).

Payload dopo il manufacturer ID (12 byte):

    09 FF | WW WW | ZZ ZZ | SS | FF FF | MM | CC | AA
    header  peso    imped.  stato riserv. modo chk fine

- peso: big-endian, in ettogrammi (÷10 = kg) per il modo 0x21
- impedenza: ohm; 0xFFFF o 0x0000 = non misurata (calzini, piastre sporche)
- stato: 0x80 in corso, 0x82 peso stabile, 0x86 peso + impedenza
- checksum: somma dei 2 byte del manufacturer ID + i primi 10 byte del payload, & 0xFF

Ricerca sul protocollo: github.com/piggei/laica-ps7002-ble-research (MIT).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .const import STATUS_FINAL, STATUS_STABLE, YOHEALTH_COMPANY_ID

PAYLOAD_LEN = 12
HEADER = bytes((0x09, 0xFF))
TERMINATOR = 0xAA
COMPANY_ID_BYTES = bytes((0x02, 0xA1))
INVALID_IMPEDANCE = {0x0000, 0xFFFF}


@dataclass(frozen=True, slots=True)
class Frame:
    """Un frame YoHealth valido."""

    weight_kg: float
    impedance: int | None
    status: int
    mode: int

    @property
    def is_weighing(self) -> bool:
        """True se il peso è stabile (con o senza impedenza)."""
        return self.status in (STATUS_STABLE, STATUS_FINAL)

    @property
    def has_composition(self) -> bool:
        """True se c'è un'impedenza utilizzabile."""
        return self.status == STATUS_FINAL and self.impedance is not None


def checksum(payload: bytes) -> int:
    """Checksum YoHealth del payload."""
    return (sum(COMPANY_ID_BYTES) + sum(payload[:10])) & 0xFF


def parse_payload(payload: bytes) -> Frame | None:
    """Valida e decodifica il payload; None se non è un frame YoHealth."""
    if len(payload) != PAYLOAD_LEN:
        return None
    if payload[:2] != HEADER or payload[-1] != TERMINATOR:
        return None
    if checksum(payload) != payload[10]:
        return None

    mode = payload[9]
    weight_raw = (payload[2] << 8) | payload[3]
    impedance_raw = (payload[4] << 8) | payload[5]
    # Cifra delle unità del modo = numero di decimali del peso (PS7002L: 0x21 → 1).
    divisor = 100.0 if (mode & 0x0F) == 2 else 10.0

    return Frame(
        weight_kg=weight_raw / divisor,
        impedance=None if impedance_raw in INVALID_IMPEDANCE else impedance_raw,
        status=payload[6],
        mode=mode,
    )


def parse_manufacturer_data(manufacturer_data: Mapping[int, bytes]) -> Frame | None:
    """Estrae il frame dai manufacturer data di un advertising."""
    payload = manufacturer_data.get(YOHEALTH_COMPANY_ID)
    if payload is None:
        return None
    return parse_payload(bytes(payload))


def looks_like_scale(manufacturer_data: Mapping[int, bytes]) -> bool:
    """True se l'advertising ha l'header YoHealth (per la scoperta)."""
    payload = manufacturer_data.get(YOHEALTH_COMPANY_ID)
    return payload is not None and bytes(payload).startswith(HEADER)

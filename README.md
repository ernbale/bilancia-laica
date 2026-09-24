# Bilancia Laica per Home Assistant

Integrazione per le bilance **LAICA** con modulo Bluetooth **YoHealth** (PS7002, PS7002L e
simili). Legge peso e impedenza **dall'advertising BLE**: nessun accoppiamento, nessuna
connessione, nessuna app. Funziona con i proxy Bluetooth ESPHome e con l'adattatore locale.

## Cosa fa
- **Peso** a ogni pesata, anche coi calzini.
- **Composizione corporea** quando la bilancia misura l'impedenza (piedi nudi, piastre pulite):
  BMI, grasso, acqua, massa muscolare, massa ossea, grasso viscerale, metabolismo basale, età corporea.
- **Ultima pesata**: data e ora, anche se il peso è uguale alla volta prima.
- **Registro (Attività)**: ogni pesata scrive una riga «Pesata: 113,9 kg…» sul dispositivo.
- I valori restano dopo un riavvio.
- **Profilo modificabile** (sesso, data di nascita, altezza) dalle opzioni: i valori si
  ricalcolano subito sull'ultima pesata, senza ripesarsi.

Niente «cancelli» o filtri: ogni frame di peso stabile viene registrato. Due pesate uguali a
distanza di tempo sono due pesate. Lo stesso frame ripetuto entro 60 secondi è una sola.

## Installazione
1. Copia `custom_components/bilancia_laica` in `/config/custom_components/` (oppure aggiungi
   questo repository a HACS come repository personalizzato, tipo *Integrazione*).
2. Riavvia Home Assistant.
3. Sali sulla bilancia: viene scoperta da sola. Oppure *Impostazioni → Integrazioni → Aggiungi →
   Bilancia Laica* e inserisci l'indirizzo Bluetooth.
4. Inserisci sesso, data di nascita e altezza.

## Protocollo
Manufacturer ID `0xA102`, payload `09 FF | peso (hg) | impedenza (Ω) | stato | FF FF | modo | chk | AA`.
Stato `0x80` in corso, `0x82` peso stabile, `0x86` peso + impedenza. Impedenza `FFFF` = non misurata.

## Crediti
Le formule di composizione corporea e la ricerca sul protocollo sono di
[piggei](https://github.com/piggei/home-assistant-laica-ble) (MIT). Questa integrazione è una
riscrittura senza filtri, pensata per non perdere mai una pesata.

## Test
```
uv venv -p 3.14 .venv && uv pip install -p .venv/bin/python pytest-homeassistant-custom-component
.venv/bin/python -m pytest
```
Licenza MIT.

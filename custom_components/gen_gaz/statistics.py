from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
DOMAIN = "gen_gaz"


def _parse_date(value: Any) -> datetime | None:
    """Parse and normalize date string to UTC top of the hour."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    # HA recorder statistics require timestamps at the top of the hour
    return dt.replace(minute=0, second=0, microsecond=0)


def import_reading_statistics(
    hass: HomeAssistant, readings: list[dict[str, Any]], kwh_per_m3: float
) -> None:
    """Import G.EN. meter history into HA long-term statistics."""
    if not readings:
        return

    readings_by_meter: dict[str, list[dict[str, Any]]] = {}
    for item in readings:
        meter_no = str(item.get("deviceNumber") or item.get("meterNumber") or "meter")
        readings_by_meter.setdefault(meter_no, []).append(item)

    for meter_no, meter_readings in readings_by_meter.items():
        ordered: list[tuple[datetime, float]] = []
        for item in meter_readings:
            dt = _parse_date(item.get("readingDate"))
            value = item.get("readingValue")
            if dt is None or not isinstance(value, (int, float)):
                continue
            ordered.append((dt, float(value)))

        if not ordered:
            continue

        # Sort chronologically
        ordered.sort(key=lambda x: x[0])

        # De-duplicate entries sharing the same rounded hour (keep the latest)
        deduped: dict[datetime, float] = {}
        for dt, reading in ordered:
            deduped[dt] = reading

        safe_meter = "".join(c if c.isalnum() else "_" for c in meter_no).lower()

        volume_id = f"{DOMAIN}:gas_meter_{safe_meter}"
        energy_id = f"{DOMAIN}:gas_meter_{safe_meter}_kwh"

        volume_meta = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"G.EN. Gaz – licznik gazu {meter_no}",
            source=DOMAIN,
            statistic_id=volume_id,
            unit_of_measurement="m³",
        )
        energy_meta = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"G.EN. Gaz – szacowane zużycie energii {meter_no}",
            source=DOMAIN,
            statistic_id=energy_id,
            unit_of_measurement="kWh",
        )

        volume_stats = []
        energy_stats = []
        for dt, reading in deduped.items():
            volume_stats.append(StatisticData(start=dt, state=reading, sum=reading))
            energy_stats.append(
                StatisticData(
                    start=dt,
                    state=round(reading * kwh_per_m3, 2),
                    sum=round(reading * kwh_per_m3, 2),
                )
            )

        try:
            async_add_external_statistics(hass, volume_meta, volume_stats)
            async_add_external_statistics(hass, energy_meta, energy_stats)
            _LOGGER.debug(
                "Imported %d G.EN. readings into long-term statistics for meter %s",
                len(volume_stats),
                meter_no,
            )
        except Exception:
            _LOGGER.exception("Unable to import G.EN. statistics for meter %s", meter_no)

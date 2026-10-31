from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import VolumeConverter, EnergyConverter

_LOGGER = logging.getLogger(__name__)
DOMAIN = "gen_gaz"


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def import_reading_statistics(hass: HomeAssistant, readings: list[dict[str, Any]], kwh_per_m3: float) -> None:
    """Import G.EN. meter history into HA long-term statistics."""
    if not readings:
        return

    ordered = []
    for item in readings:
        dt = _parse_date(item.get("readingDate"))
        value = item.get("readingValue")
        if dt is None or not isinstance(value, (int, float)):
            continue
        ordered.append((dt, float(value)))

    if not ordered:
        return

    ordered.sort(key=lambda x: x[0])
    meter_no = str(readings[0].get("deviceNumber") or "meter")
    safe_meter = "".join(c if c.isalnum() else "_" for c in meter_no).lower()

    volume_id = f"{DOMAIN}:gas_meter_{safe_meter}"
    energy_id = f"{DOMAIN}:gas_meter_{safe_meter}_kwh"

    volume_meta = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=f"G.EN. Gaz – licznik gazu {meter_no}",
        source=DOMAIN,
        statistic_id=volume_id,
        unit_class=VolumeConverter.UNIT_CLASS,
        unit_of_measurement="m³",
    )
    energy_meta = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=f"G.EN. Gaz – szacowane zużycie energii {meter_no}",
        source=DOMAIN,
        statistic_id=energy_id,
        unit_class=EnergyConverter.UNIT_CLASS,
        unit_of_measurement="kWh",
    )

    volume_stats = []
    energy_stats = []
    for dt, reading in ordered:
        volume_stats.append(StatisticData(start=dt, state=reading, sum=reading))
        energy_stats.append(
            StatisticData(start=dt, state=reading * kwh_per_m3, sum=reading * kwh_per_m3)
        )

    try:
        async_add_external_statistics(hass, volume_meta, volume_stats)
        async_add_external_statistics(hass, energy_meta, energy_stats)
        _LOGGER.debug("Imported %d G.EN. readings into long-term statistics", len(volume_stats))
    except Exception:
        _LOGGER.exception("Unable to import G.EN. statistics")

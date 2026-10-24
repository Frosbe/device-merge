"""Base entity: follows its source entities and combines them by strategy."""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from . import DeviceMergeConfigEntry, MergedSpec
from .const import (
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    DOMAIN,
    STRATEGY_ALL,
    STRATEGY_ANY,
    STRATEGY_MAX,
    STRATEGY_MEAN,
    STRATEGY_MEDIAN,
    STRATEGY_MIN,
)

AGGREGATES = {STRATEGY_MIN: min, STRATEGY_MAX: max, STRATEGY_MEAN: mean, STRATEGY_MEDIAN: median}


def specs_for(entry: DeviceMergeConfigEntry, domain: str) -> list[MergedSpec]:
    return [spec for spec in entry.runtime_data if spec.domain == domain]


def is_on_state(state: State) -> bool | None:
    """Normalise on/off-like states of any domain (lock: on = unlocked, cover: on = open)."""
    if state.domain == "lock":
        return state.state == "unlocked"
    if state.domain == "cover":
        return state.state != "closed"
    if state.state in ("on", "off"):
        return state.state == "on"
    return None


class MergedEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: DeviceMergeConfigEntry, spec: MergedSpec) -> None:
        self._spec = spec
        self._strategy = spec.strategy
        self._source_ids = [s.entity_id for s in spec.sources]
        self._platforms = {s.entity_id: s.platform for s in spec.sources}
        self._primary_id = spec.primary.entity_id
        self._source: State | None = None
        self._value: Any = None
        self.entity_id = spec.entity_id
        self._attr_unique_id = spec.unique_id
        self._attr_name = spec.name
        primary = spec.primary
        self._attr_device_class = primary.device_class or primary.original_device_class
        self._attr_entity_category = primary.entity_category
        options = entry.options
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=options.get(CONF_NAME) or entry.title,
            manufacturer=options.get(CONF_MANUFACTURER) or None,
            model=options.get(CONF_MODEL) or None,
        )

    def _read(self, state: State) -> Any:
        """One source state as this entity's value (None = not usable)."""
        return state.state

    @property
    def primary_state(self) -> State | None:
        return self.hass.states.get(self._primary_id)

    def _attr(self, name: str, default: Any = None) -> Any:
        state = self.primary_state
        return state.attributes.get(name, default) if state else default

    def _refresh(self) -> None:
        usable: list[tuple[State, Any]] = []
        for entity_id in self._source_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                continue
            value = self._read(state)
            if value is not None:
                usable.append((state, value))
        self._source, self._value = None, None
        if not usable:
            return
        if self._strategy in AGGREGATES:
            numbers = [v for _, v in usable if isinstance(v, (int, float))]
            if numbers:
                self._source, self._value = usable[0][0], AGGREGATES[self._strategy](numbers)
            return
        if self._strategy == STRATEGY_ANY:
            self._source, self._value = usable[0][0], any(bool(v) for _, v in usable)
            return
        if self._strategy == STRATEGY_ALL:
            self._source, self._value = usable[0][0], all(bool(v) for _, v in usable)
            return
        if self._strategy == "freshest":
            self._source, self._value = max(usable, key=lambda sv: sv[0].last_reported)
            return
        self._source, self._value = usable[0]  # prefer_first / single

    @property
    def available(self) -> bool:
        return self._source is not None

    @property
    def icon(self) -> str | None:
        return self._attr("icon")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if len(self._source_ids) < 2:
            return {}
        aggregated = self._strategy in AGGREGATES or self._strategy in (STRATEGY_ANY, STRATEGY_ALL)
        return {
            "source": None if aggregated or not self._source else self._source.entity_id,
            "source_integration": None if aggregated or not self._source else self._platforms.get(self._source.entity_id),
            "sources": self._source_ids,
            "strategy": self._strategy,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_track_state_change_event(self.hass, self._source_ids, self._on_source))
        self._refresh()

    @callback
    def _on_source(self, event: Event[EventStateChangedData]) -> None:
        self._refresh()
        self.async_write_ha_state()

    async def _call(self, domain: str, service: str, **data: Any) -> None:
        await self.hass.services.async_call(domain, service, {"entity_id": self._primary_id, **data}, blocking=True)

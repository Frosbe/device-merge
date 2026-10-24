"""Merged numbers (charge limit merged with TeslaMate, charging amps)."""

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedNumber(entry, spec) for spec in specs_for(entry, "number"))


class MergedNumber(MergedEntity, NumberEntity):
    def _read(self, state: State):
        try:
            return float(state.state)
        except ValueError:
            return None

    @property
    def native_value(self):
        return self._value

    @property
    def native_min_value(self):
        return self._attr("min", 0)

    @property
    def native_max_value(self):
        return self._attr("max", 100)

    @property
    def native_step(self):
        return self._attr("step", 1)

    @property
    def native_unit_of_measurement(self):
        return self._attr("unit_of_measurement")

    @property
    def mode(self):
        return self._attr("mode", "auto")

    async def async_set_native_value(self, value: float) -> None:
        await self._call("number", "set_value", value=value)

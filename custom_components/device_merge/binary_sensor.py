"""Merged binary sensors."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, is_on_state, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedBinarySensor(entry, spec) for spec in specs_for(entry, "binary_sensor"))


class MergedBinarySensor(MergedEntity, BinarySensorEntity):
    def _read(self, state: State):
        return is_on_state(state)

    @property
    def is_on(self):
        return self._value

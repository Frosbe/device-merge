"""Merged text entities."""

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedText(entry, spec) for spec in specs_for(entry, "text"))


class MergedText(MergedEntity, TextEntity):
    @property
    def native_value(self):
        return self._value

    @property
    def native_min(self):
        return self._attr("min", 0)

    @property
    def native_max(self):
        return self._attr("max", 255)

    @property
    def pattern(self):
        return self._attr("pattern")

    @property
    def mode(self):
        return self._attr("mode", "text")

    async def async_set_value(self, value: str) -> None:
        await self._call("text", "set_value", value=value)

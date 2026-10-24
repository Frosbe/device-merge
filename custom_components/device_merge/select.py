"""Merged selects (seat heaters, cabin overheat protection)."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedSelect(entry, spec) for spec in specs_for(entry, "select"))


class MergedSelect(MergedEntity, SelectEntity):
    @property
    def options(self) -> list[str]:
        return list(self._attr("options", []))

    @property
    def current_option(self):
        return self._value

    async def async_select_option(self, option: str) -> None:
        await self._call("select", "select_option", option=option)

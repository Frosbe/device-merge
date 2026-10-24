"""Merged buttons."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedButton(entry, spec) for spec in specs_for(entry, "button"))


class MergedButton(MergedEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self._call("button", "press")

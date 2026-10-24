"""Merged switches (act on the Tesla Custom switch)."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, is_on_state, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedSwitch(entry, spec) for spec in specs_for(entry, "switch"))


class MergedSwitch(MergedEntity, SwitchEntity):
    def _read(self, state: State):
        return is_on_state(state)

    @property
    def is_on(self):
        return self._value

    async def async_turn_on(self, **kwargs) -> None:
        await self._call("switch", "turn_on")

    async def async_turn_off(self, **kwargs) -> None:
        await self._call("switch", "turn_off")

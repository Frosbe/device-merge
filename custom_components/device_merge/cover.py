"""Merged covers (frunk, trunk, windows, charge port; TeslaMate open/closed merged in)."""

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, is_on_state, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedCover(entry, spec) for spec in specs_for(entry, "cover"))


class MergedCover(MergedEntity, CoverEntity):
    def _read(self, state: State):
        is_open = is_on_state(state)
        return None if is_open is None else not is_open

    @property
    def is_closed(self):
        return self._value

    @property
    def current_cover_position(self):
        return self._attr("current_position")

    @property
    def supported_features(self) -> CoverEntityFeature:
        return CoverEntityFeature(self._attr("supported_features", 0))

    async def async_open_cover(self, **kwargs) -> None:
        await self._call("cover", "open_cover")

    async def async_close_cover(self, **kwargs) -> None:
        await self._call("cover", "close_cover")

    async def async_stop_cover(self, **kwargs) -> None:
        await self._call("cover", "stop_cover")

    async def async_set_cover_position(self, **kwargs) -> None:
        await self._call("cover", "set_cover_position", position=kwargs["position"])

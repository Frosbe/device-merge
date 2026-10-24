"""Merged locks (state merged with TeslaMate 'locked', control via Tesla Custom)."""

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, is_on_state, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedLock(entry, spec) for spec in specs_for(entry, "lock"))


class MergedLock(MergedEntity, LockEntity):
    _attr_device_class = None

    def _read(self, state: State):
        unlocked = is_on_state(state)
        return None if unlocked is None else not unlocked

    @property
    def is_locked(self):
        return self._value

    @property
    def supported_features(self) -> LockEntityFeature:
        return LockEntityFeature(self._attr("supported_features", 0))

    async def async_lock(self, **kwargs) -> None:
        await self._call("lock", "lock")

    async def async_unlock(self, **kwargs) -> None:
        await self._call("lock", "unlock")

    async def async_open(self, **kwargs) -> None:
        await self._call("lock", "open")

"""Merged device trackers (position from the chosen source)."""

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .const import CONF_PICTURE
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    picture = entry.options.get(CONF_PICTURE) or None
    async_add_entities(MergedTracker(entry, spec, picture) for spec in specs_for(entry, "device_tracker"))


class MergedTracker(MergedEntity, TrackerEntity):
    def __init__(self, entry, spec, picture) -> None:
        super().__init__(entry, spec)
        self._picture = picture

    def _src(self, name, default=None):
        return self._source.attributes.get(name, default) if self._source else default

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self):
        return self._src("latitude")

    @property
    def longitude(self):
        return self._src("longitude")

    @property
    def location_accuracy(self) -> float:
        return self._src("gps_accuracy", 0) or 0

    @property
    def entity_picture(self):
        return self._picture or self._src("entity_picture")

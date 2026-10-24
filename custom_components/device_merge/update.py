"""Merged software update."""

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedUpdate(entry, spec) for spec in specs_for(entry, "update"))


class MergedUpdate(MergedEntity, UpdateEntity):
    @property
    def supported_features(self) -> UpdateEntityFeature:
        return UpdateEntityFeature(self._attr("supported_features", 0))

    @property
    def installed_version(self):
        return self._attr("installed_version")

    @property
    def latest_version(self):
        return self._attr("latest_version")

    @property
    def in_progress(self):
        return self._attr("in_progress")

    @property
    def release_url(self):
        return self._attr("release_url")

    @property
    def release_summary(self):
        return self._attr("release_summary")

    @property
    def title(self):
        return self._attr("title")

    @property
    def entity_picture(self):
        return None  # use the Device Merge brand icon

    async def async_install(self, version, backup, **kwargs) -> None:
        data = {"backup": backup}
        if version:
            data["version"] = version
        await self._call("update", "install", **data)

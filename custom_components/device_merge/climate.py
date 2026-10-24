"""Merged climate (mirrors and controls the Tesla Custom HVAC)."""

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedClimate(entry, spec) for spec in specs_for(entry, "climate"))


class MergedClimate(MergedEntity, ClimateEntity):
    _enable_turn_on_off_backwards_compatibility = False

    @property
    def temperature_unit(self) -> str:
        return self.hass.config.units.temperature_unit

    @property
    def supported_features(self) -> ClimateEntityFeature:
        return ClimateEntityFeature(self._attr("supported_features", 0))

    @property
    def hvac_mode(self):
        return HVACMode(self._value) if self._value in list(HVACMode) else None

    @property
    def hvac_modes(self):
        return [HVACMode(m) for m in self._attr("hvac_modes", [])]

    @property
    def current_temperature(self):
        return self._attr("current_temperature")

    @property
    def target_temperature(self):
        return self._attr("temperature")

    @property
    def min_temp(self):
        return self._attr("min_temp", 7)

    @property
    def max_temp(self):
        return self._attr("max_temp", 35)

    @property
    def target_temperature_step(self):
        return self._attr("target_temp_step")

    @property
    def preset_mode(self):
        return self._attr("preset_mode")

    @property
    def preset_modes(self):
        return self._attr("preset_modes")

    @property
    def fan_mode(self):
        return self._attr("fan_mode")

    @property
    def fan_modes(self):
        return self._attr("fan_modes")

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        await self._call("climate", "set_hvac_mode", hvac_mode=hvac_mode)

    async def async_set_temperature(self, **kwargs) -> None:
        await self._call("climate", "set_temperature", **kwargs)

    async def async_set_preset_mode(self, preset_mode) -> None:
        await self._call("climate", "set_preset_mode", preset_mode=preset_mode)

    async def async_set_fan_mode(self, fan_mode) -> None:
        await self._call("climate", "set_fan_mode", fan_mode=fan_mode)

    async def async_turn_on(self) -> None:
        await self._call("climate", "turn_on")

    async def async_turn_off(self) -> None:
        await self._call("climate", "turn_off")

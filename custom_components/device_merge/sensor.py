"""Merged sensors (merged across sources, with unit conversion)."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import DeviceMergeConfigEntry
from .entity import MergedEntity, specs_for

try:
    from homeassistant.components.sensor import UNIT_CONVERTERS
except ImportError:  # pragma: no cover
    UNIT_CONVERTERS = {}


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(MergedSensor(entry, spec) for spec in specs_for(entry, "sensor"))


class MergedSensor(MergedEntity, SensorEntity):
    def __init__(self, entry, spec) -> None:
        super().__init__(entry, spec)
        primary = spec.primary
        self._attr_native_unit_of_measurement = primary.unit_of_measurement
        self._attr_state_class = (primary.capabilities or {}).get("state_class")
        self._attr_options = (primary.capabilities or {}).get("options")

    async def async_added_to_hass(self) -> None:
        # Some sources (e.g. template helpers) keep their unit out of the registry; take it from the state.
        if self._attr_native_unit_of_measurement is None and (state := self.primary_state) is not None:
            self._attr_native_unit_of_measurement = state.attributes.get("unit_of_measurement")
        await super().async_added_to_hass()

    def _read(self, state: State):
        if self.device_class == SensorDeviceClass.TIMESTAMP:
            return dt_util.parse_datetime(state.state)
        target = self._attr_native_unit_of_measurement
        if target is None and self.state_class is None:
            return state.state
        try:
            value = float(state.state)
        except ValueError:
            return None if self.state_class else state.state
        unit = state.attributes.get("unit_of_measurement")
        if unit and target and unit != target:
            converter = UNIT_CONVERTERS.get(self.device_class)
            if converter is None:
                return None
            try:
                value = converter.convert(value, unit, target)
            except Exception:  # noqa: BLE001 - unknown unit pair, ignore this source
                return None
        return value

    @property
    def native_value(self):
        return self._value

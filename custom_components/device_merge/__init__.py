"""Device Merge: combine several devices (and their entities) into one device."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import (
    CONF_ENTITIES,
    CONF_HIDE_SOURCES,
    CONF_TAKE_OVER_IDS,
    DOMAIN,
    E_DOMAIN,
    E_ENTITY_ID,
    E_KEY,
    E_NAME,
    E_SOURCES,
    E_STRATEGY,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class MergedSpec:
    """One merged entity, resolved against the current entity registry."""

    key: str
    domain: str
    name: str
    entity_id: str
    unique_id: str
    strategy: str
    sources: list[er.RegistryEntry]

    @property
    def primary(self) -> er.RegistryEntry:
        """First source of the same domain (controls go here), else the first source."""
        return next((s for s in self.sources if s.domain == self.domain), self.sources[0])


type DeviceMergeConfigEntry = ConfigEntry[list[MergedSpec]]


def _resolve(ent_reg: er.EntityRegistry, ref: list[str]) -> er.RegistryEntry | None:
    entity_id = ent_reg.async_get_entity_id(ref[0], ref[1], ref[2])
    return ent_reg.async_get(entity_id) if entity_id else None


async def _prepare(hass: HomeAssistant, entry: DeviceMergeConfigEntry) -> list[MergedSpec]:
    ent_reg = er.async_get(hass)
    options = entry.options
    raw: list[tuple[dict[str, Any], list[er.RegistryEntry]]] = []
    for item in options.get(CONF_ENTITIES, []):
        sources = [s for s in (_resolve(ent_reg, ref) for ref in item[E_SOURCES]) if s is not None]
        if sources:
            raw.append((item, sources))
        else:
            _LOGGER.warning("%s: no source entities left for %s", entry.title, item[E_KEY])

    # Take over ids: move a source that holds the merged entity's id out of the way.
    renamed = False
    if options.get(CONF_TAKE_OVER_IDS):
        for item, sources in raw:
            for source in sources:
                if source.entity_id != item[E_ENTITY_ID]:
                    continue
                domain, object_id = source.entity_id.split(".", 1)
                base = f"{domain}.{object_id}_{slugify(source.platform)}"
                new_id, n = base, 2
                while ent_reg.async_get(new_id) is not None or not hass.states.async_available(new_id):
                    new_id, n = f"{base}_{n}", n + 1
                ent_reg.async_update_entity(source.entity_id, new_entity_id=new_id)
                _LOGGER.info("Renamed %s -> %s", source.entity_id, new_id)
                renamed = True
    if renamed:
        await asyncio.sleep(2)  # let renamed entities release their old state ids

    specs: list[MergedSpec] = []
    for item, sources in raw:
        sources = [s for s in (_resolve(ent_reg, [x.domain, x.platform, x.unique_id]) for x in sources) if s]
        spec = MergedSpec(
            key=item[E_KEY],
            domain=item[E_DOMAIN],
            name=item[E_NAME],
            entity_id=item[E_ENTITY_ID],
            unique_id=f"{entry.entry_id}_{item[E_KEY]}",
            strategy=item[E_STRATEGY],
            sources=sources,
        )
        # Our own entity registered under a fallback id (wanted_id_2) moves to the wanted id once it is free.
        # Any other id was chosen by the user and is left alone.
        own_id = ent_reg.async_get_entity_id(spec.domain, DOMAIN, spec.unique_id)
        fallback = own_id is not None and re.fullmatch(re.escape(spec.entity_id) + r"_\d+", own_id) is not None
        if fallback and ent_reg.async_get(spec.entity_id) is None:
            try:
                ent_reg.async_update_entity(own_id, new_entity_id=spec.entity_id)
            except ValueError:
                _LOGGER.warning("%s is still in use, keeping %s for now", spec.entity_id, own_id)
        hide = options.get(CONF_HIDE_SOURCES, True)
        for source in sources:
            if hide and source.hidden_by is None:
                ent_reg.async_update_entity(source.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
            elif not hide and source.hidden_by == er.RegistryEntryHider.INTEGRATION:
                ent_reg.async_update_entity(source.entity_id, hidden_by=None)
        specs.append(spec)

    # Remove our entities that are no longer configured.
    wanted = {spec.unique_id for spec in specs}
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.unique_id not in wanted:
            ent_reg.async_remove(reg_entry.entity_id)
    return specs


async def async_setup_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry) -> bool:
    entry.runtime_data = await _prepare(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: DeviceMergeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: DeviceMergeConfigEntry) -> None:
    """Unhide the source entities again (renamed ids are left as they are)."""
    ent_reg = er.async_get(hass)
    for item in entry.options.get(CONF_ENTITIES, []):
        for ref in item[E_SOURCES]:
            source = _resolve(ent_reg, ref)
            if source and source.hidden_by == er.RegistryEntryHider.INTEGRATION:
                ent_reg.async_update_entity(source.entity_id, hidden_by=None)

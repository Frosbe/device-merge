"""Config and options flow for Device Merge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_HIDE_SOURCES,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_PICTURE,
    CONF_TAKE_OVER_IDS,
    DOMAIN,
    E_DOMAIN,
    E_ENTITY_ID,
    E_KEY,
    E_NAME,
    E_SOURCES,
    E_STRATEGY,
    STRATEGY_FRESHEST,
    STRATEGY_LABELS,
    STRATEGY_SEPARATE,
    STRATEGY_SINGLE,
)
from .matching import Candidate, Group, auto_match, build_groups, collect, compatible, ref_key

CONF_PAIRING = "pairing"
CONF_EXCLUDED = "excluded"
OWN = "__own__"


def _general_schema(defaults: dict[str, Any], with_devices: bool) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): selector.TextSelector(),
    }
    if with_devices:
        fields[vol.Required(CONF_DEVICES, default=defaults.get(CONF_DEVICES, []))] = selector.DeviceSelector(
            selector.DeviceSelectorConfig(multiple=True)
        )
    fields.update(
        {
            vol.Optional(CONF_MANUFACTURER, default=defaults.get(CONF_MANUFACTURER, "")): selector.TextSelector(),
            vol.Optional(CONF_MODEL, default=defaults.get(CONF_MODEL, "")): selector.TextSelector(),
            vol.Optional(CONF_PICTURE, default=defaults.get(CONF_PICTURE, "")): selector.TextSelector(),
            vol.Required(CONF_HIDE_SOURCES, default=defaults.get(CONF_HIDE_SOURCES, True)): selector.BooleanSelector(),
            vol.Required(CONF_TAKE_OVER_IDS, default=defaults.get(CONF_TAKE_OVER_IDS, False)): selector.BooleanSelector(),
        }
    )
    return vol.Schema(fields)


def _unique(label: str, used: set[str]) -> str:
    out, n = label, 2
    while out in used:
        out, n = f"{label} #{n}", n + 1
    used.add(out)
    return out


class _MergeSteps:
    """Shared steps (pairing, strategies, entities) for config and options flow."""

    hass: Any
    _opts: dict[str, Any]
    _previous: dict[str, Any]
    _candidates: list[Candidate]
    _pairing: dict[str, str]
    _groups: list[Group]
    _strategies: dict[str, str]

    def _start_matching(self) -> None:
        self._candidates = collect(self.hass, self._opts[CONF_DEVICES])
        refs = {ref_key(c) for c in self._candidates}
        previous = {k: v for k, v in self._previous.get(CONF_PAIRING, {}).items() if k in refs}
        self._pairing = previous if self._previous.get(CONF_PAIRING) is not None else auto_match(self._candidates)

    # Step: which later-device entity merges into which earlier one
    def _pairing_fields(self) -> dict[str, tuple[Candidate, list[Candidate]]]:
        used: set[str] = set()
        fields: dict[str, tuple[Candidate, list[Candidate]]] = {}
        for cand in self._candidates:
            if cand.device_index == 0:
                continue
            options = [c for c in self._candidates if c.device_index < cand.device_index and compatible(c, cand)]
            if options:
                fields[_unique(cand.label, used)] = (cand, options)
        return fields

    async def async_step_pairing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fields = self._pairing_fields()
        if user_input is not None or not fields:
            if user_input is not None:
                for label, (cand, _options) in fields.items():
                    choice = user_input.get(label, OWN)
                    if choice == OWN:
                        self._pairing.pop(ref_key(cand), None)
                    else:
                        self._pairing[ref_key(cand)] = choice
            self._groups = build_groups(self._candidates, self._pairing)
            return await self.async_step_strategies()
        schema: dict[Any, Any] = {}
        for label, (cand, options) in fields.items():
            select_options = [selector.SelectOptionDict(value=OWN, label="(own entity, not merged)")]
            select_options += [selector.SelectOptionDict(value=ref_key(o), label=o.label) for o in options]
            schema[vol.Required(label, default=self._pairing.get(ref_key(cand), OWN))] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=select_options, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        return self.async_show_form(step_id="pairing", data_schema=vol.Schema(schema))

    # Step: how each merged value is combined
    def _strategy_fields(self) -> dict[str, Group]:
        used: set[str] = set()
        out: dict[str, Group] = {}
        for group in self._groups:
            if len(group.members) > 1:
                devices = " + ".join(dict.fromkeys(m.device_name for m in group.members))
                out[_unique(f"{group.name} [{group.domain}] ({devices})", used)] = group
        return out

    async def async_step_strategies(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fields = self._strategy_fields()
        previous = self._previous.get("strategies_by_anchor", {})
        if user_input is not None or not fields:
            self._strategies = {}
            for label, group in fields.items():
                choice = user_input.get(label, STRATEGY_FRESHEST) if user_input else STRATEGY_FRESHEST
                self._strategies[ref_key(group.anchor)] = choice
            return await self.async_step_entities()
        schema: dict[Any, Any] = {}
        for label, group in fields.items():
            options = [selector.SelectOptionDict(value=s, label=STRATEGY_LABELS[s]) for s in group.strategies()]
            default = previous.get(ref_key(group.anchor), STRATEGY_FRESHEST)
            if default not in group.strategies():
                default = STRATEGY_FRESHEST
            schema[vol.Required(label, default=default)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        return self.async_show_form(step_id="strategies", data_schema=vol.Schema(schema))

    # Step: which unmerged entities to include
    def _single_candidates(self) -> list[Candidate]:
        out: list[Candidate] = []
        for group in self._groups:
            if len(group.members) == 1 or self._strategies.get(ref_key(group.anchor)) == STRATEGY_SEPARATE:
                out.extend(group.members)
        return out

    async def async_step_entities(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        singles = self._single_candidates()
        excluded_before = set(self._previous.get(CONF_EXCLUDED, []))
        if user_input is not None or not singles:
            chosen = set(user_input.get("include", [])) if user_input is not None else {ref_key(c) for c in singles}
            excluded = [ref_key(c) for c in singles if ref_key(c) not in chosen]
            return self._finish(excluded)
        options = [selector.SelectOptionDict(value=ref_key(c), label=c.label) for c in singles]
        default = [ref_key(c) for c in singles if ref_key(c) not in excluded_before]
        schema = vol.Schema(
            {
                vol.Optional("include", default=default): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(step_id="entities", data_schema=schema)

    def _finish(self, excluded: list[str]) -> ConfigFlowResult:
        prior_ids = {e[E_KEY]: e[E_ENTITY_ID] for e in self._previous.get(CONF_ENTITIES, [])}
        name_slug = slugify(self._opts[CONF_NAME])
        used_keys: set[str] = set()
        used_ids: set[str] = set()
        entities: list[dict[str, Any]] = []

        def add(domain: str, name: str, members: list[Candidate], strategy: str) -> None:
            key = _unique(f"{domain}.{slugify(name)}", used_keys)
            entity_id = prior_ids.get(key)
            if entity_id is None and self._opts.get(CONF_TAKE_OVER_IDS):
                first = min((m for m in members if m.entry.domain == domain), key=lambda m: m.device_index, default=None)
                if first and first.device_index == 0:
                    entity_id = first.entry.entity_id
            if entity_id is None or entity_id in used_ids:
                entity_id = f"{domain}.{name_slug}_{slugify(name)}"
            base, n = entity_id, 2
            while entity_id in used_ids:
                entity_id, n = f"{base}_{n}", n + 1
            used_ids.add(entity_id)
            entities.append(
                {
                    E_KEY: key,
                    E_DOMAIN: domain,
                    E_NAME: name,
                    E_ENTITY_ID: entity_id,
                    E_STRATEGY: strategy,
                    E_SOURCES: [m.ref for m in sorted(members, key=lambda m: m.device_index)],
                }
            )

        for group in self._groups:
            strategy = self._strategies.get(ref_key(group.anchor), STRATEGY_SINGLE)
            if len(group.members) > 1 and strategy != STRATEGY_SEPARATE:
                add(group.domain, group.name, group.members, strategy)
                continue
            for member in group.members:
                if ref_key(member) not in excluded:
                    add(member.entry.domain, member.name, [member], STRATEGY_SINGLE)

        options = {
            **self._opts,
            CONF_ENTITIES: entities,
            CONF_PAIRING: self._pairing,
            "strategies_by_anchor": self._strategies,
            CONF_EXCLUDED: excluded,
        }
        return self._create(options)

    def _create(self, options: dict[str, Any]) -> ConfigFlowResult:
        raise NotImplementedError


class DeviceMergeConfigFlow(_MergeSteps, ConfigFlow, domain=DOMAIN):
    """Create a merged device."""

    VERSION = 1

    def __init__(self) -> None:
        self._opts = {}
        self._previous = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DeviceMergeOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if len(user_input.get(CONF_DEVICES, [])) < 2:
                errors[CONF_DEVICES] = "need_two_devices"
            else:
                self._opts = user_input
                self._start_matching()
                return await self.async_step_pairing()
        return self.async_show_form(step_id="user", data_schema=_general_schema(user_input or {}, True), errors=errors)

    def _create(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title=self._opts[CONF_NAME], data={}, options=options)


class DeviceMergeOptionsFlow(_MergeSteps, OptionsFlow):
    """Change a merged device."""

    def __init__(self) -> None:
        self._opts = {}
        self._previous = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._previous = dict(self.config_entry.options)
        if user_input is not None:
            self._opts = {**user_input, CONF_DEVICES: self._previous[CONF_DEVICES]}
            self._start_matching()
            return await self.async_step_pairing()
        return self.async_show_form(step_id="init", data_schema=_general_schema(self._previous, False))

    def _create(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=options)

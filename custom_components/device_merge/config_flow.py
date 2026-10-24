"""Config and options flow for Device Merge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.util import slugify

from .const import (
    CONF_DEVICES,
    CONF_ENTITIES,
    CONF_HIDE_SOURCES,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_PICTURE,
    CONF_REVIEW_ALL,
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
from .matching import (
    Candidate,
    Group,
    affinity,
    auto_match,
    build_groups,
    class_counter,
    collect,
    compatible,
    device_legend,
    ref_key,
)

CONF_PAIRING = "pairing"
CONF_EXCLUDED = "excluded"
CONF_SEEN = "seen"
OWN = "__own__"
MAX_VALUE_LEN = 24
ACTION = "action"
ACTION_CREATE = "create"
ACTION_BACK = "back"
ACTION_REVIEW_ALL = "review_all"
# Pairing sections, in display order; only "unsure" starts expanded.
SECTIONS = ("unsure", "auto", "alone")


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
            vol.Required(CONF_REVIEW_ALL, default=defaults.get(CONF_REVIEW_ALL, False)): selector.BooleanSelector(),
        }
    )
    return vol.Schema(fields)


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Form input with sections unpacked."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in SECTIONS and isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


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
    _legend: str
    _shown: dict[str, dict[str, Any]]
    _unsure: set[str]
    _reviewed: set[str]
    _result: dict[str, Any]

    def _start_matching(self) -> None:
        self._candidates = collect(self.hass, self._opts[CONF_DEVICES])
        self._legend = device_legend(self.hass, self._opts[CONF_DEVICES])
        self._shown = {}
        self._reviewed = set()
        self._strategies = {}
        self._excluded: list[str] | None = None
        refs = {ref_key(c) for c in self._candidates}
        suggested, self._unsure = auto_match(self._candidates)
        if self._previous.get(CONF_PAIRING) is not None:
            # Keep earlier choices; only entities that are new since then count as unsure.
            known = set(self._previous.get(CONF_SEEN, [])) | set(self._previous[CONF_PAIRING])
            self._pairing = {k: v for k, v in self._previous[CONF_PAIRING].items() if k in refs}
            for ref, anchor in suggested.items():
                if ref not in known:
                    self._pairing.setdefault(ref, anchor)
            self._unsure = {r for r in self._unsure if r not in known}
        else:
            self._pairing = suggested

    @property
    def _review_all(self) -> bool:
        return bool(self._opts.get(CONF_REVIEW_ALL))

    def _value(self, cand: Candidate) -> str:
        """Current value of a candidate, for the labels."""
        state = self.hass.states.get(cand.entry.entity_id)
        if state is None:
            return "?"
        unit = state.attributes.get("unit_of_measurement")
        text = f"{state.state} {unit}" if unit else state.state
        return text if len(text) <= MAX_VALUE_LEN else f"{text[: MAX_VALUE_LEN - 3]}..."

    def _show(self, step_id: str, fields: dict[str, Any], schema: vol.Schema) -> ConfigFlowResult:
        """Show a step and remember its labels: they hold live values, so they are not rebuilt on submit."""
        self._shown[step_id] = fields
        return self.async_show_form(step_id=step_id, data_schema=schema, description_placeholders={"legend": self._legend})

    # Step: which later-device entity merges into which earlier one
    def _pairing_fields(self) -> dict[str, tuple[Candidate, list[Candidate], str]]:
        used: set[str] = set()
        fields: dict[str, tuple[Candidate, list[Candidate], str]] = {}
        class_counts = class_counter(self._candidates)
        for cand in self._candidates:
            if cand.device_index == 0 or not (self._review_all or ref_key(cand) in self._unsure):
                continue
            options = [c for c in self._candidates if c.device_index < cand.device_index and compatible(c, cand)]
            options.sort(key=lambda o: affinity(o, cand, class_counts), reverse=True)  # likeliest first
            if options:
                ref = ref_key(cand)
                category = "unsure" if ref in self._unsure else "auto" if ref in self._pairing else "alone"
                fields[_unique(f"{cand.label} = {self._value(cand)}", used)] = (cand, options, category)
        return fields

    async def async_step_pairing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fields = self._shown.get("pairing") if user_input is not None else None
        fields = fields or self._pairing_fields()
        if user_input is not None or not fields:
            if user_input is not None:
                flat = _flatten(user_input)
                for label, (cand, _options, _category) in fields.items():
                    choice = flat.get(label, OWN)
                    if choice == OWN:
                        self._pairing.pop(ref_key(cand), None)
                    else:
                        self._pairing[ref_key(cand)] = choice
            self._reviewed = {ref_key(cand) for cand, _options, _category in fields.values()}
            self._groups = build_groups(self._candidates, self._pairing)
            return await self.async_step_strategies()
        by_section: dict[str, dict[Any, Any]] = {name: {} for name in SECTIONS}
        for label, (cand, options, category) in fields.items():
            select_options = [selector.SelectOptionDict(value=OWN, label="(own entity, not merged)")]
            select_options += [
                selector.SelectOptionDict(value=ref_key(o), label=f"{o.label} = {self._value(o)}") for o in options
            ]
            by_section[category][vol.Required(label, default=self._pairing.get(ref_key(cand), OWN))] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=select_options, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        used = [name for name in SECTIONS if by_section[name]]
        if len(used) == 1:
            schema: dict[Any, Any] = by_section[used[0]]
        else:
            schema = {
                vol.Required(name): section(vol.Schema(by_section[name]), {"collapsed": name != "unsure"}) for name in used
            }
        return self._show("pairing", fields, vol.Schema(schema))

    # Step: how each merged value is combined
    def _strategy_fields(self) -> dict[str, Group]:
        used: set[str] = set()
        out: dict[str, Group] = {}
        for group in self._groups:
            reviewed = self._review_all or any(ref_key(m) in self._reviewed for m in group.members)
            if len(group.members) > 1 and reviewed:
                values = ", ".join(f"{m.device_tag} {self._value(m)}" for m in group.members)
                out[_unique(f"{group.name} ({group.domain}): {values}", used)] = group
        return out

    async def async_step_strategies(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fields = self._shown.get("strategies") if user_input is not None else None
        fields = fields or self._strategy_fields()
        previous = {**self._previous.get("strategies_by_anchor", {}), **self._strategies}
        if user_input is not None or not fields:
            # Groups not on the form keep their earlier choice or get the default.
            self._strategies = {
                ref_key(g.anchor): self._default_strategy(g, previous) for g in self._groups if len(g.members) > 1
            }
            for label, group in fields.items():
                self._strategies[ref_key(group.anchor)] = (user_input or {}).get(label, self._default_strategy(group, previous))
            return await self.async_step_entities()
        schema: dict[Any, Any] = {}
        for label, group in fields.items():
            options = [selector.SelectOptionDict(value=s, label=STRATEGY_LABELS[s]) for s in group.strategies()]
            default = self._default_strategy(group, previous)
            schema[vol.Required(label, default=default)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        return self._show("strategies", fields, vol.Schema(schema))

    @staticmethod
    def _default_strategy(group: Group, previous: dict[str, str]) -> str:
        choice = previous.get(ref_key(group.anchor)) or group.default_strategy()
        return choice if choice in group.strategies() else STRATEGY_FRESHEST

    # Step: which unmerged entities to include
    def _single_candidates(self) -> list[Candidate]:
        out: list[Candidate] = []
        for group in self._groups:
            if len(group.members) == 1 or self._strategies.get(ref_key(group.anchor)) == STRATEGY_SEPARATE:
                out.extend(group.members)
        return out

    async def async_step_entities(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        singles = self._single_candidates()
        excluded_before = set(self._excluded if self._excluded is not None else self._previous.get(CONF_EXCLUDED, []))
        if not self._review_all and user_input is None:
            # Quick setup: include everything, keeping anything excluded earlier excluded.
            return await self._finish([ref_key(c) for c in singles if ref_key(c) in excluded_before])
        if user_input is not None or not singles:
            chosen = set(user_input.get("include", [])) if user_input is not None else {ref_key(c) for c in singles}
            excluded = [ref_key(c) for c in singles if ref_key(c) not in chosen]
            return await self._finish(excluded)
        options = [selector.SelectOptionDict(value=ref_key(c), label=f"{c.label} = {self._value(c)}") for c in singles]
        default = [ref_key(c) for c in singles if ref_key(c) not in excluded_before]
        schema = vol.Schema(
            {
                vol.Optional("include", default=default): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.LIST)
                )
            }
        )
        return self._show("entities", {}, schema)

    async def _finish(self, excluded: list[str]) -> ConfigFlowResult:
        self._excluded = excluded
        prior_ids = {e[E_KEY]: e[E_ENTITY_ID] for e in self._previous.get(CONF_ENTITIES, [])}
        if self._previous:
            # Ids the user renamed in the UI win over the stored ones.
            ent_reg = er.async_get(self.hass)
            entry_id = self._previous_entry_id
            for key in prior_ids:
                current = ent_reg.async_get_entity_id(key.split(".", 1)[0], DOMAIN, f"{entry_id}_{key}")
                if current:
                    prior_ids[key] = current
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
            CONF_SEEN: [ref_key(c) for c in self._candidates],
        }
        self._result = options
        return await self.async_step_confirm()

    # Step: show the finished device before creating it
    def _summary(self, entities: list[dict[str, Any]]) -> str:
        by_ref = {ref_key(c): c for c in self._candidates}

        def cell(text: str) -> str:
            return text.replace("|", "\\|")

        merged = ["| Entity | Sources | Combine |", "|---|---|---|"]
        single = ["| Entity | From | Value |", "|---|---|---|"]
        for item in entities:
            members = [m for m in (by_ref.get("|".join(r)) for r in item[E_SOURCES]) if m]
            name = f"{cell(item[E_NAME])} (`{item[E_ENTITY_ID]}`)"
            if len(members) > 1:
                sources = ", ".join(f"{m.device_tag} {cell(self._value(m))}" for m in members)
                merged.append(f"| {name} | {sources} | {STRATEGY_LABELS.get(item[E_STRATEGY], item[E_STRATEGY])} |")
            elif members:
                single.append(f"| {name} | {members[0].device_tag} | {cell(self._value(members[0]))} |")
        parts = [f"**Merged ({len(merged) - 2})**", "\n".join(merged)] if len(merged) > 2 else []
        if len(single) > 2:
            parts += [f"**From one device only ({len(single) - 2})**", "\n".join(single)]
        return "\n\n".join(parts) or "Nothing to create."

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            action = user_input.get(ACTION, ACTION_CREATE)
            if action == ACTION_CREATE:
                return self._create(self._result)
            if action == ACTION_REVIEW_ALL:
                self._opts = {**self._opts, CONF_REVIEW_ALL: True}
            return await self.async_step_pairing()
        actions = [
            selector.SelectOptionDict(value=ACTION_CREATE, label="Looks good, create it"),
            selector.SelectOptionDict(value=ACTION_BACK, label="Go back and change"),
        ]
        if not self._review_all:
            actions.append(selector.SelectOptionDict(value=ACTION_REVIEW_ALL, label="Go back and review everything"))
        schema = vol.Schema(
            {
                vol.Required(ACTION, default=ACTION_CREATE): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=actions, mode=selector.SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={"legend": self._legend, "summary": self._summary(self._result[CONF_ENTITIES])},
        )

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
        self._previous_entry_id = self.config_entry.entry_id
        if user_input is not None:
            self._opts = {**user_input, CONF_DEVICES: self._previous[CONF_DEVICES]}
            self._start_matching()
            return await self.async_step_pairing()
        return self.async_show_form(step_id="init", data_schema=_general_schema(self._previous, False))

    def _create(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=options)

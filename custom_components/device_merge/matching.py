"""Find entities on different devices that describe the same thing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

from .const import DOMAIN, NUMERIC_STRATEGIES, ONOFF_STRATEGIES, OTHER_STRATEGIES, PLATFORMS

ONOFF_DOMAINS = {"binary_sensor", "switch", "lock", "cover"}
COVER_LIKE = {"door", "opening", "garage_door", "window"}
# When a merged group spans domains, the entity becomes the first of these present.
TARGET_PRIORITY = ["climate", "lock", "cover", "switch", "number", "select", "text", "button", "update", "device_tracker", "sensor", "binary_sensor"]

STOPWORDS = {"level", "state", "status", "the", "of", "sensor", "value", "current", "is"}
SYNONYMS = {"tpms": ["tire", "pressure"], "tyre": ["tire"], "temp": ["temperature"], "interior": ["inside"], "exterior": ["outside"]}
MATCH_THRESHOLD = 0.5


@dataclass
class Candidate:
    """One source entity."""

    entry: er.RegistryEntry
    device_index: int
    device_name: str

    @property
    def ref(self) -> list[str]:
        return [self.entry.domain, self.entry.platform, self.entry.unique_id]

    @property
    def name(self) -> str:
        return self.entry.original_name or self.entry.name or self.entry.entity_id.split(".", 1)[1]

    @property
    def device_class(self) -> str | None:
        return self.entry.device_class or self.entry.original_device_class

    @property
    def label(self) -> str:
        return f"{self.device_name}: {self.name} ({self.entry.domain})"


@dataclass
class Group:
    """A merged entity: one or more candidates."""

    members: list[Candidate] = field(default_factory=list)

    @property
    def anchor(self) -> Candidate:
        return self.members[0]

    @property
    def domain(self) -> str:
        domains = {m.entry.domain for m in self.members}
        return next(d for d in TARGET_PRIORITY if d in domains)

    @property
    def name(self) -> str:
        same = [m for m in self.members if m.entry.domain == self.domain]
        return (same or self.members)[0].name

    @property
    def key(self) -> str:
        return f"{self.domain}.{slugify(self.name)}"

    def strategies(self) -> list[str]:
        if all(m.entry.domain in ONOFF_DOMAINS for m in self.members):
            return ONOFF_STRATEGIES
        if all(_kind(m)[0] == "num" for m in self.members):
            return NUMERIC_STRATEGIES
        return OTHER_STRATEGIES


def _tokens(name: str) -> set[str]:
    words = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
    out: set[str] = set()
    for word in words:
        for token in SYNONYMS.get(word, [word]):
            if token in STOPWORDS:
                continue
            out.add(_stem(token))
    return out


def _stem(word: str) -> str:
    """Very light stemming so charger/charging, door/doors, lock/locked compare equal."""
    for suffix in ("ing", "er", "ed", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _kind(c: Candidate) -> tuple[str, str | None]:
    entry = c.entry
    if entry.domain == "sensor":
        numeric = bool(entry.unit_of_measurement) or (entry.capabilities or {}).get("state_class") is not None
        return ("num", c.device_class or entry.unit_of_measurement) if numeric else ("text", c.device_class)
    if entry.domain == "number":
        return ("num", None)
    if entry.domain in ONOFF_DOMAINS:
        return ("onoff", None)
    return (entry.domain, c.device_class)


def compatible(a: Candidate, b: Candidate) -> bool:
    """Can a and b be merged into one entity?"""
    ka, kb = _kind(a), _kind(b)
    if ka[0] != kb[0]:
        return False
    if ka[0] == "num":
        if "number" in (a.entry.domain, b.entry.domain):
            return a.entry.unit_of_measurement == b.entry.unit_of_measurement
        if a.device_class and b.device_class:
            return a.device_class == b.device_class
        return a.entry.unit_of_measurement == b.entry.unit_of_measurement
    if ka[0] == "onoff":
        domains = {a.entry.domain, b.entry.domain}
        if len(domains) == 1:
            return a.device_class == b.device_class or None in (a.device_class, b.device_class)
        if domains == {"lock", "binary_sensor"}:
            return "lock" in (a.device_class, b.device_class)
        if domains == {"cover", "binary_sensor"}:
            binary = a if a.entry.domain == "binary_sensor" else b
            return binary.device_class in COVER_LIKE or binary.device_class is None
        return domains == {"switch", "binary_sensor"}
    return a.entry.domain == b.entry.domain and (ka[1] == kb[1] or None in (ka[1], kb[1]))


def score(a: Candidate, b: Candidate) -> float:
    ta, tb = _tokens(a.name), _tokens(b.name)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def collect(hass: HomeAssistant, device_ids: list[str]) -> list[Candidate]:
    """All enabled entities of the given devices, in device order."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    out: list[Candidate] = []
    for index, device_id in enumerate(device_ids):
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        name = device.name_by_user or device.name or device_id
        for entry in er.async_entries_for_device(ent_reg, device_id):
            if entry.disabled_by is not None or entry.platform == DOMAIN or entry.domain not in PLATFORMS:
                continue
            out.append(Candidate(entry, index, name))
    return out


def auto_match(candidates: list[Candidate]) -> dict[str, str]:
    """Suggested pairing: ref of a later-device candidate -> ref of the group anchor it joins."""
    groups: list[Group] = []
    pairing: dict[str, str] = {}
    class_counts = Counter((c.device_index, c.entry.domain, c.device_class) for c in candidates if c.device_class)
    for cand in candidates:
        best: tuple[float, Group] | None = None
        for group in groups:
            if any(m.device_index == cand.device_index for m in group.members):
                continue
            if not compatible(group.anchor, cand):
                continue
            value = score(group.anchor, cand)
            a = group.anchor
            if a.entry.domain != cand.entry.domain:
                value -= 0.15  # prefer a same-domain partner
            if (
                a.device_class
                and a.device_class == cand.device_class
                and class_counts[(a.device_index, a.entry.domain, a.device_class)] == 1
                and class_counts[(cand.device_index, cand.entry.domain, cand.device_class)] == 1
            ):
                value += 0.4  # the only entity of this kind on both devices
            if value >= MATCH_THRESHOLD and (best is None or value > best[0]):
                best = (value, group)
        if best:
            best[1].members.append(cand)
            pairing[ref_key(cand)] = ref_key(best[1].anchor)
        else:
            groups.append(Group([cand]))
    return pairing


def build_groups(candidates: list[Candidate], pairing: dict[str, str]) -> list[Group]:
    """Groups from an explicit pairing (candidate ref -> ref of the candidate it merges into)."""
    by_ref = {ref_key(c): c for c in candidates}

    def root(ref: str) -> str:
        seen = set()
        while ref in pairing and pairing[ref] in by_ref and ref not in seen:
            seen.add(ref)
            ref = pairing[ref]
        return ref

    groups: dict[str, Group] = {}
    for cand in candidates:
        groups.setdefault(root(ref_key(cand)), Group()).members.append(cand)
    return [g for g in groups.values() if g.members]


def ref_key(c: Candidate) -> str:
    return "|".join(c.ref)

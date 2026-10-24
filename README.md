# Device Merge

Combine two or more Home Assistant devices into one device. Useful when the same
thing is integrated twice, for example a car through both a cloud integration and
a local one (TeslaMate), where sometimes one is faster and sometimes the other.

## What it does

- Creates a new device with every entity of the chosen devices.
- Entities that describe the same thing on several devices are merged into one
  entity, combined with a strategy you choose per entity:
  - **Freshest**: whichever source reported most recently (default)
  - **Prefer first device**, falling back to the next
  - **Minimum / maximum / mean / median** for numbers (counters such as an
    odometer default to maximum)
  - **On if any is on / only if all are on** for on/off values
  - **Keep separate**
- Works with any number of devices: a value that three devices report becomes
  one entity with three sources.
- Units are converted when sources differ (psi vs bar, km/h vs m/s, ...).
- Merges across entity types where it makes sense: a lock with a "locked"
  binary sensor, a cover with an open/closed binary sensor, a switch with a
  binary sensor, a number with a sensor.
- Controls (switches, buttons, locks, covers, climate, selects, numbers, text,
  update) act through the source entity of the first device that has one.
- Each merged entity shows `source` (which entity the value came from),
  `source_integration`, `sources` and `strategy` as attributes.
- Optional: hide the source entities, and take over the first device's entity
  ids (its entities are renamed to `<id>_<integration>`), so existing
  dashboards and automations use the merged entities without changes.
- Entity ids you rename yourself are kept.

## Installation

1. HACS > Integrations > three-dot menu > Custom repositories. Add
   `https://github.com/frosbe/device-merge` with type Integration.
2. Install **Device Merge** and restart Home Assistant.
3. Settings > Devices & services > Add integration > Device Merge.

## Setup

1. Name the device and pick the devices in priority order. The first device (A)
   owns the controls. Devices are called A, B, C... in the next steps, with a
   legend showing each one's integration, make, model and entity count, so
   devices with the same name are easy to tell apart.
2. **Pair entities.** The automatic matching (names, device classes, units)
   pairs what it is sure about. Only the pairings it is unsure of are shown;
   each label carries the device letter and the current value, and the
   likeliest partner is listed first. Tick **Review everything** on the first
   page to see all pairings, grouped into collapsible sections.
3. **Combine values.** Choose a strategy for the pairings you reviewed; the rest
   uses the defaults.
4. **Check the result.** A summary table shows every entity of the new device
   with the current value of each source and its strategy. Create it, or go
   back and change things.

Everything can be changed later under **Configure**. Entities that appear on a
source device later are shown there as unsure.

## Limitations

- The setup is a regular Home Assistant config flow: the summary shows the
  result after each step, not live while you change the dropdowns.
- Entities without a device (for example some template or Composite trackers)
  cannot be added, because the setup picks devices.
- Home Assistant shows brand icons per integration, so every merged device shows
  the Device Merge icon. A picture can be set for the merged device trackers.
- Renamed entity ids are not changed back when you remove a merged device;
  hidden source entities are unhidden.

## License

MIT

---

*This integration was written with the help of an AI assistant (Claude, by
Anthropic). The code has been reviewed and tested on a real Home Assistant
installation, but please read it before relying on it and report any problems
in the issue tracker.*

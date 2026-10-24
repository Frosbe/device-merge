# Device Merge

Combine two or more Home Assistant devices into one device. Useful when the same
thing is integrated twice, for example a car through both an official/cloud
integration and a local one (TeslaMate), where sometimes one is faster and
sometimes the other.

## What it does

- Creates a new device with every entity of the chosen devices.
- Entities that describe the same thing on several devices are merged into one
  entity, combined with a strategy you choose per entity:
  - **Freshest**: whichever source reported most recently (default)
  - **Prefer first device**, falling back to the next
  - **Minimum / maximum / mean / median** for numbers
  - **On if any is on / only if all are on** for on/off values
  - **Keep separate**
- Units are converted when sources differ (psi vs bar, km/h vs m/s, ...).
- Merges across entity types where it makes sense: a lock with a "locked"
  binary sensor, a cover with an open/closed binary sensor, a switch with a
  binary sensor, a number with a sensor.
- Controls (switches, buttons, locks, covers, climate, selects, numbers, text,
  update) act through the source entity of the first device that has one.
- Each merged entity shows `source` (which entity the value came from),
  `sources` and `strategy` as attributes.
- Optional: hide the source entities, and take over the first device's entity
  ids (its entities are renamed to `<id>_<integration>`), so existing
  dashboards and automations use the merged entities without changes.

## Setup

1. Install through HACS (custom repository, type Integration) and restart.
2. Settings > Devices & services > Add integration > Device Merge.
3. Name the device and pick the devices in priority order. The first device owns
   the controls.
4. Pair entities: for every entity of a later device, pick the entity it is the
   same as, or keep it on its own. Suggestions are filled in from names, device
   classes and units.
5. Choose a strategy for each merged entity.
6. Tick which of the remaining (unpaired) entities to include.

Everything can be changed later under **Configure**.

## Limitations

- Home Assistant shows brand icons per integration, so every merged device shows
  the Device Merge icon. A picture can be set for the merged device trackers.
- Renamed entity ids are not changed back when you remove a merged device;
  hidden source entities are unhidden.
- New entities that appear on a source device later show up under **Configure**.

## License

MIT

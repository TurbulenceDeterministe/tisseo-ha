# Contributing

Thanks for your interest! Bug reports, fixes and ideas are welcome.

## Reporting a bug
Open an [issue](https://github.com/TurbulenceDeterministe/tisseo-ha/issues/new/choose) and include:
- the integration version (*Settings → Devices & services → Tisséo*) and your Home Assistant version;
- the stop, line or journey involved (e.g. `stop_area:SA_681`, line 25) and the time it happened;
- the **diagnostics** file (*⋮ → Download diagnostics* on the entry). Any API key in it is redacted automatically;
- relevant log lines. You can enable debug logging with:
  ```yaml
  logger:
    logs:
      custom_components.tisseo: debug
  ```

Please **never** paste API keys, Home Assistant tokens or passwords in issues.

## Development setup
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest tests                                   # offline: synthetic GTFS / GTFS-RT feeds, mocked HTTP
TISSEO_LIVE=1 pytest tests/test_live_ha.py -s  # optional: against the live open-data feeds
node --check custom_components/tisseo/frontend/tisseo-departures-card.js
```

CI runs the same tests, plus **hassfest** and the **HACS** validation, on every push and pull request.

## Ground rules
- **Open data only.** The integration uses the public GTFS, GTFS-RT and GBFS feeds, and optionally an API key the *user* provides. Do not add keys or tokens taken from the official Tisséo app, or anything that bypasses authentication or the bot protection of tisseo.fr. Pull requests that do will be closed.
- **Tests for fixes.** A bug fix should come with a test that reproduces it, ideally on a small synthetic feed (see `tests/conftest.py` and `tests/test_v111_ourliac.py`).
- **The card is one file.** `custom_components/tisseo/frontend/tisseo-departures-card.js` is self-contained: no external fonts, scripts or CDNs.
- **Translations.** Strings live in `strings.json` and `translations/en.json` / `fr.json`; keep both languages in sync. The card has its own EN/FR strings.
- **Versioning.** Bump `manifest.json` and `TDC_VERSION` in the card together, and add an entry to `CHANGELOG.md`.

## Pull requests
1. Fork, then create a branch from `main`.
2. Keep changes focused, and update the README (EN and FR) when behaviour changes.
3. Make sure `pytest tests` passes.
4. Describe what changed and how you tested it.

By contributing you agree that your contribution is licensed under the MIT licence of this project.

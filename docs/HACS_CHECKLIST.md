# Publishing checklist (HACS custom repository → default store)

Nothing has been published. Everything below is prepared locally.

1. **Set your GitHub user:** `python scripts/set_github_user.py <user>`. It replaces `your-github-user` in `manifest.json`, the README files, `REPO` and the workflows. `python scripts/set_github_user.py --check` must report no placeholder left.
2. **Create a public repository** named `tisseo-ha`, with a **description** and **topics** (e.g. `home-assistant`, `hacs`, `hacs-integration`, `toulouse`, `tisseo`, `gtfs`). The HACS action checks both. Enable Issues.
3. Push `main`. The CI must be green:
   - `hassfest.yaml` (home-assistant/actions/hassfest). It passed locally against HA core 2026.2.3.
   - `hacs.yaml` (hacs/action, category `integration`).
   - `tests.yaml` (pytest + `node --check` on the card).
4. **Brand.** `custom_components/tisseo/brand/icon.png` (256²) and `icon@2x.png` (512²) are included. HA ≥ 2026.3 reads brand images from the integration itself, and home-assistant/brands no longer accepts custom integrations. Known caveat: some HACS versions still show a placeholder icon in the HACS dashboard (hacs/integration#5171, #5223). This is cosmetic.
5. **Release.** Tag `v1.0.0` and create a GitHub **release** (not only a tag). The version must match `manifest.json`.
6. `hacs.json`: name, `homeassistant: 2025.1.0` minimum, `render_readme`.
7. Optional: open a PR on `hacs/default` to add the repository to the default store, once the action passes.

/*
 * tisseo-departures-card – Lovelace card for the Tisséo integration (design v2).
 * Vanilla web component, single file, no build step, no external resources.
 * Served by the integration at /tisseo_static/tisseo-departures-card.js.
 *
 *   type: custom:tisseo-departures-card
 *   entity: sensor.tisseo_capitole_departure_1   # any sensor of the stop works
 *   layout: default            # default | compact | board
 *   max_departures: 6          # rows (directions when grouped); legacy `max` still accepted
 *   group: true                # one row per line + direction, next departures as "then"
 *   hero: auto                 # highlight the next catchable departure (auto: default layout only)
 *   hero_line: "B|Borderouge"  # optional, pin the hero to a direction
 *   leave_entity: …            # optional, auto-detected "leave in" sensor of the stop
 *   alerts: banner             # banner | count | off   (legacy show_alerts: false → off)
 *   timetable_notice: true     # notice when tomorrow's timetable differs
 *   show_filters: false        # line / direction chips (selection saved per card in this browser)
 *   filter_lines: [B, L1]      # fixed filters; filter_destinations: [Ramonville]
 *   trip_dialog: true          # tap a row to see all the stops of that trip
 *   show_clock: false · badge_contrast: auto|brand · board_theme: dark|auto
 */
(() => {
const TDC_VERSION = "1.1.1";
const STYLES = `/* ==========================================================================
   tisseo-card.css — design system v2 for custom:tisseo-departures-card
   Drop-in: paste into the card's static styles (Shadow DOM). The root element
   is <ha-card class="tc" data-layout="default|compact|board" data-theme="light|dark">.
   Every variable falls back to a Home Assistant theme variable, then to a value.
   Override from an HA theme with the --tisseo-* variables.
   ========================================================================== */

/* ---------- 1. Design variables ---------------------------------------------------- */
.tc {
  /* surfaces & text — inherited from the HA theme */
  --tc-surface: var(--ha-card-background, var(--card-background-color, #ffffff));
  --tc-raised: var(--secondary-background-color, #f2f3f5);
  --tc-text: var(--primary-text-color, #212121);
  --tc-text-2: var(--secondary-text-color, #5f6368);
  --tc-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
  --tc-accent: var(--primary-color, #009ac7);
  --tc-hover: rgba(127, 127, 127, 0.08);

  /* status — tuned for ≥ 4.5:1 on the card surface (HA's --success-color is 2.8:1 on white) */
  --tc-live: var(--tisseo-live-color, #16803c);
  --tc-late: var(--tisseo-late-color, #9a5b00);
  --tc-early: var(--tisseo-early-color, #1565c0);
  --tc-cancel: var(--tisseo-cancel-color, #c21e1e);
  --tc-sev-info: var(--tisseo-info-color, #1565c0);
  --tc-sev-warning: var(--tisseo-warning-color, #9a5b00);
  --tc-sev-severe: var(--tisseo-severe-color, #c21e1e);
  --tc-badge-ring: rgba(0, 0, 0, 0.14);

  /* type — HA variables first, px fallback */
  --tc-font: var(--ha-font-family-body, Roboto, system-ui, -apple-system, "Segoe UI", sans-serif);
  --tc-fs-meta: var(--ha-font-size-s, 12px);
  --tc-fs-body: var(--ha-font-size-m, 14px);
  --tc-fs-dest: var(--ha-font-size-l, 16px);
  --tc-fs-title: 18px;
  --tc-fs-time: 24px;
  --tc-fs-hero-dest: 20px;
  --tc-fs-hero-time: 44px;

  /* space (4 px grid) & shape */
  --tc-s1: 4px; --tc-s2: 8px; --tc-s3: 12px; --tc-s4: 16px; --tc-s5: 20px; --tc-s6: 24px;
  --tc-radius: var(--ha-card-border-radius, 12px);
  --tc-radius-s: 8px;
  --tc-target: 44px;

  /* motion */
  --tc-ease: cubic-bezier(0.2, 0, 0, 1);        /* enter / standard */
  --tc-ease-exit: cubic-bezier(0.3, 0, 1, 1);   /* leave */
  --tc-d1: 120ms;  /* press, hover */
  --tc-d2: 200ms;  /* row enter/leave, digit tick */
  --tc-d3: 280ms;  /* reorder, expand */
  --tc-d4: 360ms;  /* dialog */

  container: tc / inline-size;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--tc-surface);
  color: var(--tc-text);
  font-family: var(--tc-font);
  font-size: var(--tc-fs-body);
  line-height: 1.4;
  -webkit-font-smoothing: antialiased;
}
.tc[data-theme="dark"] {
  --tc-live: var(--tisseo-live-color, #5fd07a);
  --tc-late: var(--tisseo-late-color, #ffb547);
  --tc-early: var(--tisseo-early-color, #8ab8ff);
  --tc-cancel: var(--tisseo-cancel-color, #ff8a80);
  --tc-sev-info: var(--tisseo-info-color, #8ab8ff);
  --tc-sev-warning: var(--tisseo-warning-color, #ffb547);
  --tc-sev-severe: var(--tisseo-severe-color, #ff8a80);
  --tc-badge-ring: rgba(255, 255, 255, 0.22);
  --tc-hover: rgba(255, 255, 255, 0.06);
}
:host { display: block; height: 100%; } /* fills a panel view; resolves to auto in masonry */
.tc *, .tc *::before, .tc *::after { box-sizing: border-box; }
.tc [hidden], .tc[hidden] { display: none !important; } /* component display rules must not beat the hidden attribute */
.tc button { font: inherit; color: inherit; }
.tc :focus-visible { outline: 2px solid var(--tc-accent); outline-offset: 2px; border-radius: var(--tc-radius-s); }
.tc-num { font-variant-numeric: tabular-nums; }

/* ---------- 2. Line badge ------------------------------------------------- */
/* --line / --line-text come from badgeColors() (text colour auto-corrected to AA) */
.tc-badge {
  --_h: 32px; --_fs: 14px; --_px: 0px;
  display: inline-flex; align-items: center; justify-content: center; gap: 3px;
  flex: none; height: var(--_h); min-width: var(--_h); padding: 0 var(--_px);
  background: var(--line, #757575); color: var(--line-text, #fff);
  box-shadow: inset 0 0 0 1px var(--tc-badge-ring);
  font: 700 var(--_fs)/1 var(--tc-font); letter-spacing: -0.01em; white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.tc-badge svg { width: 0.95em; height: 0.95em; fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
.tc-badge--metro   { border-radius: 50%; width: var(--_h); }                       /* circle */
.tc-badge--tram    { border-radius: 28%; --_px: 4px; }                              /* rounded square */
.tc-badge--lineo   { border-radius: 999px; --_px: 10px; --_h: 28px; }               /* pill */
.tc-badge--bus     { border-radius: 6px; --_px: 8px; --_h: 28px; }                  /* rectangle */
.tc-badge--shuttle { border-radius: 6px; --_px: 7px; --_h: 28px; }                  /* rectangle + plane */
.tc-badge--cable   { border-radius: 8px 8px 50% 50% / 8px 8px 30% 30%; --_px: 6px; } /* cabin */
.tc-badge--xs { --_h: 20px; --_fs: 11px; }
.tc-badge--xs.tc-badge--lineo, .tc-badge--xs.tc-badge--bus, .tc-badge--xs.tc-badge--shuttle { --_h: 18px; --_px: 6px; }
.tc-badge--l  { --_h: 44px; --_fs: 19px; }
.tc-badge--l.tc-badge--lineo, .tc-badge--l.tc-badge--bus, .tc-badge--l.tc-badge--shuttle { --_h: 38px; --_px: 13px; }
.tc-badge--xl { --_h: clamp(40px, 5.2cqi, 64px); --_fs: clamp(17px, 2.3cqi, 28px); }
.tc-badge--xl.tc-badge--lineo, .tc-badge--xl.tc-badge--bus, .tc-badge--xl.tc-badge--shuttle { --_h: clamp(34px, 4.4cqi, 54px); --_px: clamp(10px, 1.3cqi, 16px); }

/* ---------- 3. Status glyphs --------------------------------------------- */
.tc-live { width: 14px; height: 14px; flex: none; color: var(--tc-live); overflow: visible; }
.tc-live circle { fill: currentColor; }
.tc-live path { fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.tc-live--anim .a1 { animation: tc-arc 2.4s var(--tc-ease) infinite; }
.tc-live--anim .a2 { animation: tc-arc 2.4s var(--tc-ease) 0.3s infinite; }
.tc-ico { width: 18px; height: 18px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.tc-ico--s { width: 14px; height: 14px; stroke-width: 2; }

.tc-delay { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 5px; font-size: var(--tc-fs-meta); font-weight: 600; line-height: 1; white-space: nowrap; font-variant-numeric: tabular-nums; }
.tc-delay--late  { color: var(--tc-late);  background: rgba(154, 91, 0, 0.1);  background: color-mix(in srgb, var(--tc-late) 12%, transparent); }
.tc-delay--early { color: var(--tc-early); background: rgba(21, 101, 192, 0.1); background: color-mix(in srgb, var(--tc-early) 12%, transparent); }
.tc-cancel { color: var(--tc-cancel); font-weight: 600; }

/* ---------- 4. Header ----------------------------------------------------- */
.tc-head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: var(--tc-s3); padding: var(--tc-s4) var(--tc-s2) var(--tc-s2) var(--tc-s4); }
.tc-head__icon { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; color: var(--tc-accent); background: var(--tc-raised); background: color-mix(in srgb, var(--tc-accent) 14%, var(--tc-surface)); }
.tc-head__icon .tc-ico { width: 22px; height: 22px; }
.tc-head__title { margin: 0; font-size: var(--tc-fs-title); line-height: 24px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-head__sub { margin: 2px 0 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: var(--tc-fs-meta); line-height: 16px; color: var(--tc-text-2); }
.tc-head__sub .tc-ico--s { color: var(--tc-text-2); }
.tc-head__clock { font-size: var(--tc-fs-dest); font-weight: 500; color: var(--tc-text-2); font-variant-numeric: tabular-nums; padding-right: var(--tc-s2); }
.tc-iconbtn { position: relative; width: var(--tc-target); height: var(--tc-target); display: grid; place-items: center; border: 0; border-radius: 50%; background: transparent; color: var(--tc-text-2); cursor: pointer; transition: background var(--tc-d1) var(--tc-ease); }
.tc-iconbtn:hover { background: var(--tc-hover); }
.tc-iconbtn__count { position: absolute; top: 6px; right: 5px; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px; background: var(--tc-accent); color: var(--text-primary-color, #fff); font-size: 10px; font-weight: 700; line-height: 16px; text-align: center; }

/* ---------- 5. Filter chips (one scrolling row, never wraps) -------------- */
.tc-chips { display: flex; gap: var(--tc-s2); overflow-x: auto; padding: 2px var(--tc-s4) var(--tc-s2); scrollbar-width: none; -webkit-mask-image: linear-gradient(90deg, #000 calc(100% - 24px), transparent); mask-image: linear-gradient(90deg, #000 calc(100% - 24px), transparent); }
.tc-chips::-webkit-scrollbar { display: none; }
.tc-chip { position: relative; flex: none; display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px 0 8px; border: 1px solid var(--tc-divider); border-radius: 16px; background: transparent; font-size: 13px; font-weight: 500; cursor: pointer; transition: background var(--tc-d1) var(--tc-ease); }
.tc-chip::before { content: ""; position: absolute; inset: -6px 0; } /* 44 px tall hit area */
.tc-chip--text { padding: 0 12px; }
.tc-chip[aria-pressed="true"] { border-color: transparent; background: var(--tc-raised); background: color-mix(in srgb, var(--tc-accent) 18%, var(--tc-surface)); }

/* ---------- 6. Notices (feed down, stale, timetable change) -------------- */
.tc-notice { --_c: var(--tc-sev-info); display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; align-items: start; gap: var(--tc-s2) 10px; margin: 0 var(--tc-s3) var(--tc-s2); padding: 10px var(--tc-s3); border-radius: var(--tc-radius-s); background: var(--tc-raised); background: color-mix(in srgb, var(--_c) 10%, var(--tc-surface)); font-size: 13px; line-height: 18px; }
.tc-notice > .tc-ico { color: var(--_c); margin-top: 0; }
.tc-notice b { font-weight: 600; }
.tc-notice__sub { display: block; color: var(--tc-text-2); }
.tc-notice--warning { --_c: var(--tc-sev-warning); }
.tc-notice--severe  { --_c: var(--tc-sev-severe); }
.tc-textbtn { border: 0; background: none; padding: 0 var(--tc-s1); min-height: 32px; color: var(--tc-accent); font-weight: 600; font-size: 13px; cursor: pointer; border-radius: 6px; }

/* ---------- 7. Hero: next catchable departure ----------------------------- */
.tc-hero { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "eyebrow eyebrow eyebrow" "badge main time"; align-items: center; gap: 6px 14px; width: calc(100% - 2 * var(--tc-s3)); margin: var(--tc-s1) var(--tc-s3) var(--tc-s2); padding: var(--tc-s3) var(--tc-s4) 14px; border: 0; border-radius: calc(var(--tc-radius) - 2px); background: var(--tc-raised); background: color-mix(in srgb, var(--line) 13%, var(--tc-surface)); text-align: left; cursor: pointer; }
.tc[data-theme="dark"] .tc-hero { background: color-mix(in srgb, var(--line) 18%, var(--tc-surface)); }
.tc-hero__eyebrow { grid-area: eyebrow; display: flex; align-items: center; gap: 6px; font-size: var(--tc-fs-meta); font-weight: 500; letter-spacing: 0.02em; color: var(--tc-text-2); }
.tc-hero .tc-badge { grid-area: badge; }
.tc-hero__main { grid-area: main; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.tc-hero__dest { font-size: var(--tc-fs-hero-dest); line-height: 24px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-hero__meta { font-size: 13px; color: var(--tc-text-2); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-variant-numeric: tabular-nums; }
.tc-hero .tc-time { grid-area: time; }
.tc-hero .tc-time__num { font-size: var(--tc-fs-hero-time); letter-spacing: -0.02em; }
.tc-hero .tc-time__unit { font-size: 16px; }
.tc-hero .tc-time.is-due .tc-time__num { font-size: 26px; }

/* ---------- 8. Departure rows -------------------------------------------- */
.tc-list { list-style: none; margin: 0; padding: 0 var(--tc-s1) var(--tc-s2); }
.tc-row { display: grid; grid-template-rows: 1fr; position: relative; }
.tc-row + .tc-row::before { content: ""; position: absolute; top: 0; left: 68px; right: var(--tc-s3); height: 1px; background: var(--tc-divider); }
.tc-row__hit { display: grid; grid-template-columns: 48px minmax(0, 1fr) auto; align-items: center; gap: var(--tc-s3); width: 100%; min-height: 60px; padding: var(--tc-s2) var(--tc-s3) var(--tc-s2) var(--tc-s2); border: 0; border-radius: var(--tc-radius-s); background: transparent; text-align: left; cursor: pointer; overflow: hidden; transition: background var(--tc-d1) var(--tc-ease); }
.tc-row__hit:hover { background: var(--tc-hover); }
.tc-row__hit > .tc-badge { justify-self: center; }
.tc-row__main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.tc-row__dest { font-size: var(--tc-fs-dest); line-height: 20px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-row__meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 13px; line-height: 18px; color: var(--tc-text-2); font-variant-numeric: tabular-nums; }
.tc-row__dest .tc-ico, .tc-flag { width: 14px; height: 14px; margin-left: 4px; vertical-align: -1px; color: var(--tc-sev-warning); }
.tc-flag--severe { color: var(--tc-sev-severe); }
.tc-row.is-canceled .tc-row__dest { text-decoration: line-through; text-decoration-thickness: 1.5px; color: var(--tc-text-2); }

.tc-time { display: inline-flex; align-items: baseline; justify-content: flex-end; gap: 3px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.tc-time .tc-live { align-self: center; margin-right: 4px; }
.tc-time__num { font-size: var(--tc-fs-time); line-height: 1; font-weight: 700; display: inline-block; }
.tc-time__unit { font-size: 13px; font-weight: 500; color: var(--tc-text-2); }
.tc-time.is-due .tc-time__num { font-size: 15px; letter-spacing: 0.01em; }
.tc-time--canceled { align-items: center; gap: 4px; font-size: 13px; color: var(--tc-cancel); font-weight: 600; }
/* stale data: countdowns keep running client-side but read as approximate */
.tc.is-stale .tc-time__num, .tc.is-stale .tc-brow__time { color: var(--tc-text-2); }
.tc.is-stale .tc-live { color: var(--tc-text-2); }
/* feed down: live glyphs are simply not rendered; rows fall back to timetable */
.tc-then { font-size: 13px; color: var(--tc-text-2); font-variant-numeric: tabular-nums; white-space: nowrap; }

/* ---------- 9. Alerts: collapsed banner + expandable list ----------------- */
.tc-alert { --_c: var(--tc-sev-info); display: grid; grid-template-columns: 18px minmax(0, 1fr) auto 18px; align-items: center; gap: 10px; width: 100%; min-height: 48px; padding: 10px var(--tc-s4); border: 0; border-top: 1px solid var(--tc-divider); background: transparent; text-align: left; font-size: 13px; line-height: 18px; cursor: pointer; }
.tc-alert:hover { background: var(--tc-hover); }
.tc-alert > .tc-ico:first-child { color: var(--_c); }
.tc-alert__text { display: flex; align-items: center; gap: 6px; min-width: 0; }
.tc-alert__text > span:last-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-alert__count { padding: 0 7px; height: 20px; border-radius: 10px; background: var(--tc-raised); font-size: var(--tc-fs-meta); font-weight: 600; line-height: 20px; color: var(--tc-text-2); }
.tc-alert__chev { color: var(--tc-text-2); transition: transform var(--tc-d3) var(--tc-ease); }
.tc-alert[aria-expanded="true"] .tc-alert__chev { transform: rotate(180deg); }
.tc-alert--warning { --_c: var(--tc-sev-warning); }
.tc-alert--severe  { --_c: var(--tc-sev-severe); background: rgba(194, 30, 30, 0.06); background: color-mix(in srgb, var(--tc-sev-severe) 9%, transparent); font-weight: 500; }
.tc-alerts__list { list-style: none; margin: 0; padding: 0 var(--tc-s4) var(--tc-s3); display: grid; gap: var(--tc-s3); }
.tc-alerts__item { --_c: var(--tc-sev-info); display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 2px 10px; }
.tc-alerts__item > .tc-ico { color: var(--_c); grid-row: span 2; margin-top: 1px; }
.tc-alerts__item--warning { --_c: var(--tc-sev-warning); }
.tc-alerts__item--severe  { --_c: var(--tc-sev-severe); }
.tc-alerts__title { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: var(--tc-fs-body); font-weight: 500; line-height: 20px; }
.tc-alerts__desc { font-size: 13px; line-height: 18px; color: var(--tc-text-2); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.tc-alerts__group { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--tc-text-2); padding-top: var(--tc-s1); }

.tc-foot { display: flex; align-items: center; gap: 6px; padding: 0 var(--tc-s4) var(--tc-s3); font-size: var(--tc-fs-meta); color: var(--tc-text-2); }

/* ---------- 10. Empty / error / loading ---------------------------------- */
.tc-empty { display: grid; justify-items: center; gap: 6px; padding: var(--tc-s5) var(--tc-s6) var(--tc-s6); text-align: center; }
.tc-empty__icon { width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; background: var(--tc-raised); color: var(--tc-text-2); margin-bottom: var(--tc-s1); }
.tc-empty__icon .tc-ico { width: 24px; height: 24px; }
.tc-empty__title { margin: 0; font-size: var(--tc-fs-dest); font-weight: 500; }
.tc-empty__text { margin: 0; font-size: 13px; color: var(--tc-text-2); display: flex; align-items: center; gap: 6px; justify-content: center; flex-wrap: wrap; }
.tc-empty--error .tc-empty__icon { color: var(--tc-cancel); background: color-mix(in srgb, var(--tc-cancel) 12%, var(--tc-surface)); }
.tc-skel { display: block; height: 14px; border-radius: 6px; background: var(--tc-raised); background-image: linear-gradient(90deg, transparent, rgba(127, 127, 127, 0.12), transparent); background-size: 200% 100%; animation: tc-shimmer 1.4s linear infinite; }
.tc-skel--badge { width: 32px; height: 32px; border-radius: 50%; }
.tc-skel--num { width: 36px; height: 24px; }

/* ---------- 11. Compact layout ------------------------------------------- */
.tc[data-layout="compact"] .tc-head { padding: var(--tc-s3) var(--tc-s1) var(--tc-s1) var(--tc-s3); gap: 10px; }
.tc[data-layout="compact"] .tc-head__icon { width: 32px; height: 32px; border-radius: 10px; }
.tc[data-layout="compact"] .tc-head__icon .tc-ico { width: 18px; height: 18px; }
.tc[data-layout="compact"] .tc-head__title { font-size: var(--tc-fs-dest); line-height: 20px; }
.tc[data-layout="compact"] .tc-row + .tc-row::before { left: 56px; }
.tc[data-layout="compact"] .tc-row__hit { grid-template-columns: 40px minmax(0, 1fr) auto auto; gap: 10px; min-height: 44px; padding: 4px var(--tc-s3) 4px 6px; }
.tc[data-layout="compact"] .tc-row__dest { font-size: 15px; }
.tc[data-layout="compact"] .tc-row__meta { display: none; }
.tc[data-layout="compact"] .tc-badge { --_h: 26px; --_fs: 12px; }
.tc[data-layout="compact"] .tc-badge--lineo, .tc[data-layout="compact"] .tc-badge--bus, .tc[data-layout="compact"] .tc-badge--shuttle { --_h: 22px; --_px: 7px; }
.tc[data-layout="compact"] .tc-time__num { font-size: 18px; }
.tc[data-layout="compact"] .tc-time__unit { font-size: 12px; }
.tc[data-layout="compact"] .tc-then { min-width: 3.2em; text-align: right; }
.tc[data-layout="compact"] .tc-alert { min-height: 44px; padding: 8px var(--tc-s3); }
@container tc (max-width: 300px) {
  .tc-then, .tc-head__icon, .tc-head__sub, .tc-alert__text > span:last-child { display: none; }
  .tc[data-layout="compact"] .tc-row__hit { grid-template-columns: 30px minmax(0, 1fr) auto; }
  .tc-alert { grid-template-columns: 18px auto 1fr 18px; }
}
@container tc (min-width: 560px) {
  .tc[data-layout="default"] .tc-list { display: grid; grid-template-columns: 1fr 1fr; column-gap: var(--tc-s4); }
  .tc[data-layout="default"] .tc-row + .tc-row::before { display: none; }
}

/* ---------- 12. Board layout (wall tablet) ------------------------------- */
.tc[data-layout="board"] { height: 100%; }
.tc[data-layout="board"][data-board-theme="dark"] {
  --tc-surface: var(--tisseo-board-background, #0b1220);
  --tc-raised: #141d2e;
  --tc-text: #ffffff;
  --tc-text-2: #93a0b4;
  --tc-divider: rgba(255, 255, 255, 0.1);
  --tc-badge-ring: rgba(255, 255, 255, 0.22);
  --tc-live: #5fd07a; --tc-late: #ffb547; --tc-early: #8ab8ff; --tc-cancel: #ff8a80;
  --tc-sev-info: #8ab8ff; --tc-sev-warning: #ffb547; --tc-sev-severe: #ff8a80;
  --tc-board-time: var(--tisseo-board-time-color, #ffb800);
}
.tc-board__head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 2cqi; padding: clamp(14px, 2.4cqi, 32px) clamp(16px, 3cqi, 40px) clamp(10px, 1.6cqi, 20px); }
.tc-board__title { margin: 0; font-size: clamp(22px, 3.6cqi, 48px); font-weight: 700; line-height: 1.1; letter-spacing: -0.01em; }
.tc-board__sub { margin: 4px 0 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: clamp(13px, 1.5cqi, 19px); color: var(--tc-text-2); }
.tc-board__sub .tc-live { width: 1em; height: 1em; }
.tc-board__clock { font-size: clamp(24px, 3.8cqi, 52px); font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
.tc-board__cols { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0 3cqi; padding: 0 clamp(16px, 3cqi, 40px); flex: 1; align-content: start; }
@container tc (min-width: 880px) { .tc-board__cols--split { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
.tc-board__panel { min-width: 0; }
.tc-board__panel-title { display: flex; align-items: center; gap: 8px; margin: clamp(6px, 1cqi, 14px) 0 0; padding-bottom: 6px; font-size: clamp(11px, 1.1cqi, 14px); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--tc-text-2); }
.tc-bhead, .tc-brow { display: grid; grid-template-columns: clamp(48px, 6.4cqi, 88px) minmax(0, 1fr) clamp(64px, 8cqi, 116px) clamp(64px, 7cqi, 104px); align-items: center; column-gap: clamp(10px, 1.4cqi, 20px); }
.tc-bhead { padding: 6px 0; border-bottom: 1px solid var(--tc-divider); font-size: clamp(11px, 1.05cqi, 14px); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--tc-text-2); }
.tc-bhead > :nth-child(n + 3) { text-align: right; }
.tc-brow { min-height: clamp(56px, 7.2cqi, 100px); padding: 6px 0; border-bottom: 1px solid var(--tc-divider); }
.tc-brow > .tc-badge { justify-self: start; }
/* Destination is the most important word on a board: it wraps to 2 lines before it is ever truncated */
.tc-brow__dest { min-width: 0; font-size: clamp(18px, 2.4cqi, 34px); font-weight: 600; line-height: 1.1; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere; }
.tc-brow__note { display: flex; align-items: center; gap: 8px; margin-top: 2px; font-size: clamp(12px, 1.3cqi, 17px); font-weight: 500; color: var(--tc-text-2); }
.tc-brow__time { display: flex; align-items: baseline; justify-content: flex-end; gap: 4px; color: var(--tc-board-time, var(--tc-text)); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tc-brow__time .tc-live { align-self: center; width: 0.42em; height: 0.42em; margin-right: 0.12em; font-size: clamp(24px, 4cqi, 56px); }
.tc-brow__time b { font-size: clamp(24px, 4cqi, 56px); font-weight: 700; line-height: 1; letter-spacing: -0.02em; }
.tc-brow__time small { font-size: clamp(12px, 1.5cqi, 20px); font-weight: 500; color: var(--tc-text-2); }
.tc-brow__time--due b, .tc-brow__time.is-due b { font-size: clamp(16px, 2.2cqi, 30px); letter-spacing: 0.02em; }
.tc-brow__time--canceled { color: var(--tc-cancel); font-size: clamp(14px, 1.8cqi, 24px); font-weight: 700; align-items: center; }
.tc-brow__then { text-align: right; font-size: clamp(15px, 2cqi, 28px); font-weight: 500; color: var(--tc-text-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tc-board__foot { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; margin-top: auto; padding: clamp(10px, 1.6cqi, 20px) clamp(16px, 3cqi, 40px); border-top: 1px solid var(--tc-divider); background: var(--tc-raised); font-size: clamp(14px, 1.6cqi, 21px); }
.tc-board__foot .tc-ico { width: 1.2em; height: 1.2em; }
.tc-board__msg { display: flex; align-items: center; gap: 10px; min-width: 0; }
.tc-board__msg > span:last-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-pager { display: flex; align-items: center; gap: 6px; color: var(--tc-text-2); font-size: 0.8em; font-variant-numeric: tabular-nums; }
.tc-pager i { width: 6px; height: 6px; border-radius: 50%; background: var(--tc-divider); }
.tc-pager i.on { background: var(--tc-text-2); }

/* ---------- 13. Trip-stops dialog (native <dialog>, top layer) ---------- */
.tc-dialog { width: min(440px, calc(100vw - 32px)); max-height: min(760px, calc(100vh - 48px)); padding: 0; border: 0; border-radius: var(--ha-dialog-border-radius, 24px); background: var(--tc-surface); color: var(--tc-text); box-shadow: 0 12px 40px rgba(0, 0, 0, 0.28); overflow: hidden; display: flex; flex-direction: column; }
.tc-dialog::backdrop { background: rgba(0, 0, 0, 0.32); }
.tc-dialog[open] { animation: tc-dialog-in var(--tc-d4) var(--tc-ease); }
.tc-dlg__head { display: grid; grid-template-columns: auto minmax(0, 1fr) var(--tc-target); align-items: center; gap: var(--tc-s3); padding: var(--tc-s4) var(--tc-s2) var(--tc-s3) var(--tc-s5); border-bottom: 1px solid var(--tc-divider); }
.tc-dlg__title { margin: 0; font-size: var(--tc-fs-title); font-weight: 600; line-height: 24px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-dlg__sub { margin: 2px 0 0; display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--tc-text-2); }
.tc-dlg__body { overflow-y: auto; padding: var(--tc-s2) 0 var(--tc-s3); }
.tc-stops { list-style: none; margin: 0; padding: 0 var(--tc-s4) 0 var(--tc-s3); }
.tc-stop { position: relative; display: grid; grid-template-columns: 52px 24px minmax(0, 1fr) auto; align-items: center; column-gap: 8px; min-height: 40px; font-size: var(--tc-fs-body); }
.tc-stop__time { text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
.tc-stop__time s { display: block; font-size: 11px; font-weight: 400; color: var(--tc-text-2); line-height: 1; }
.tc-stop__rail { position: relative; align-self: stretch; }
.tc-stop__rail::before { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 4px; transform: translateX(-50%); background: var(--line-ink, var(--line)); }
.tc-stop:first-child .tc-stop__rail::before { top: 50%; }
.tc-stop:last-child .tc-stop__rail::before { bottom: 50%; }
.tc-stop__rail::after { content: ""; position: absolute; left: 50%; top: 50%; width: 12px; height: 12px; transform: translate(-50%, -50%); border-radius: 50%; background: var(--tc-surface); box-shadow: inset 0 0 0 3px var(--line-ink, var(--line)); }
.tc-stop__name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-stop--here { min-height: 56px; }
.tc-stop--here .tc-stop__rail::after { width: 20px; height: 20px; background: var(--line); box-shadow: 0 0 0 3px var(--tc-surface), 0 0 0 5px var(--line-ink, var(--line)); }
.tc-stop--here .tc-stop__name { font-weight: 600; }
.tc-stop--here .tc-stop__eyebrow { display: block; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--tc-text-2); line-height: 14px; }
.tc-stop--end .tc-stop__rail::after { border-radius: 3px; }
.tc-stop--end .tc-stop__name { font-weight: 600; }
.tc-stop--past .tc-stop__rail::before { background: repeating-linear-gradient(var(--line-ink, var(--line)) 0 4px, transparent 4px 8px); opacity: 0.6; }
.tc-stops__more { display: grid; grid-template-columns: 52px 24px minmax(0, 1fr); column-gap: 8px; align-items: center; width: 100%; min-height: 40px; border: 0; background: none; padding: 0; text-align: left; color: var(--tc-text-2); font-size: 13px; cursor: pointer; }
.tc-stops__more .tc-stop__rail::before { background: repeating-linear-gradient(var(--line-ink, var(--line)) 0 4px, transparent 4px 8px); opacity: 0.6; top: 50%; }
.tc-dlg__foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px var(--tc-s5); border-top: 1px solid var(--tc-divider); font-size: var(--tc-fs-meta); color: var(--tc-text-2); }

/* ---------- 14. Leave-now hero (card or section) ------------------------- */
.tc-leave { display: grid; gap: 10px; padding: var(--tc-s4) var(--tc-s5) var(--tc-s5); }
.tc-leave__eyebrow { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; color: var(--tc-text-2); }
.tc-leave__big { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin: 0; font-size: 22px; font-weight: 500; line-height: 1.1; }
.tc-leave__big b { font-size: 48px; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.tc-leave__target { display: flex; align-items: center; gap: 10px; min-width: 0; font-size: var(--tc-fs-dest); }
.tc-leave__target strong { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-leave__meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 13px; color: var(--tc-text-2); font-variant-numeric: tabular-nums; }
.tc-progress { height: 6px; border-radius: 3px; background: var(--tc-raised); overflow: hidden; }
.tc-progress > i { display: block; height: 100%; width: var(--p, 50%); border-radius: inherit; background: var(--line-ink, var(--tc-accent)); transition: width 1s linear; }
.tc-leave--now { background: var(--line); color: var(--line-text); }
.tc-leave--now .tc-leave__eyebrow, .tc-leave--now .tc-leave__meta { color: inherit; opacity: 0.86; }
.tc-leave--now .tc-badge { box-shadow: inset 0 0 0 2px currentColor; }
.tc-leave--now .tc-leave__walk { animation: tc-nudge 1s var(--tc-ease) 3; }
.tc-leave--now .tc-progress { background: rgba(0, 0, 0, 0.14); }
.tc-leave--now .tc-progress > i { background: currentColor; }

/* ---------- 15. Journey card --------------------------------------------- */
.tc-jrny { display: grid; gap: var(--tc-s3); padding: 0 var(--tc-s4) var(--tc-s4); }
.tc-jrny__times { display: grid; grid-template-columns: auto 1fr auto; align-items: end; gap: var(--tc-s3); }
.tc-jrny__t { display: grid; gap: 2px; }
.tc-jrny__t small { font-size: var(--tc-fs-meta); color: var(--tc-text-2); font-weight: 500; }
.tc-jrny__t b { font-size: 28px; line-height: 1; font-weight: 700; font-variant-numeric: tabular-nums; }
.tc-jrny__dur { text-align: center; font-size: 13px; color: var(--tc-text-2); padding-bottom: 4px; border-bottom: 2px dotted var(--tc-divider); }
.tc-legs { display: flex; gap: 3px; height: 30px; }
.tc-leg { flex: var(--w, 1) 1 0; min-width: 30px; display: flex; align-items: center; justify-content: center; gap: 4px; border-radius: 6px; font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }
.tc-leg--ride { background: var(--line); color: var(--line-text); box-shadow: inset 0 0 0 1px var(--tc-badge-ring); }
.tc-leg--walk, .tc-leg--wait { color: var(--tc-text-2); background: var(--tc-raised); font-weight: 600; }
.tc-leg--wait { background: repeating-linear-gradient(135deg, var(--tc-raised) 0 6px, transparent 6px 10px); }
.tc-steps { list-style: none; margin: 0; padding: 0; }
.tc-step { display: grid; grid-template-columns: 44px 24px minmax(0, 1fr); column-gap: 8px; align-items: center; min-height: 36px; font-size: var(--tc-fs-body); }
.tc-step__time { text-align: right; font-weight: 500; font-variant-numeric: tabular-nums; }
.tc-step__rail { position: relative; align-self: stretch; }
.tc-step__rail::before { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 4px; transform: translateX(-50%); background: var(--line-ink, var(--tc-divider)); }
.tc-step--walk .tc-step__rail::before { width: 0; border-left: 3px dotted var(--tc-text-2); background: none; }
.tc-step:first-child .tc-step__rail::before { top: 50%; }
.tc-step:last-child .tc-step__rail::before { bottom: 50%; }
.tc-step__rail::after { content: ""; position: absolute; left: 50%; top: 50%; width: 10px; height: 10px; transform: translate(-50%, -50%); border-radius: 50%; background: var(--tc-surface); box-shadow: inset 0 0 0 3px var(--tc-text-2); }
.tc-step--stop .tc-step__rail::after { box-shadow: inset 0 0 0 3px var(--line-ink, var(--tc-text)); }
.tc-step__what { display: flex; align-items: center; gap: 8px; min-width: 0; color: var(--tc-text); }
.tc-step__what span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-step__what em { font-style: normal; color: var(--tc-text-2); font-size: 13px; }

/* ---------- 16. Mini cards (bike, P+R, feed) ----------------------------- */
.tc-mini { display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 2px var(--tc-s3); padding: var(--tc-s3) var(--tc-s4) var(--tc-s4); }
.tc-mini .tc-head__icon { grid-row: span 2; align-self: start; }
.tc-mini__name { font-size: var(--tc-fs-body); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tc-mini__stats { display: flex; align-items: baseline; gap: var(--tc-s4); flex-wrap: wrap; }
.tc-mini__stat { display: flex; align-items: baseline; gap: 4px; font-size: 13px; color: var(--tc-text-2); }
.tc-mini__stat b { font-size: 26px; line-height: 1.1; font-weight: 700; color: var(--tc-text); font-variant-numeric: tabular-nums; }
.tc-mini__bar { grid-column: 1 / -1; margin-top: var(--tc-s2); display: flex; gap: 2px; height: 8px; border-radius: 4px; overflow: hidden; background: var(--tc-raised); }
.tc-mini__bar i { flex: var(--n) 1 0; background: var(--_fill, var(--tc-accent)); }
.tc-mini__bar i.free { background: transparent; }
.tc-mini__state { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; margin-top: 6px; font-size: var(--tc-fs-meta); font-weight: 600; }
.tc-mini__state--warn { color: var(--tc-late); }
.tc-mini__state--full { color: var(--tc-cancel); }
.tc-mini__state--ok { color: var(--tc-live); }

/* ---------- 17. Motion ----------------------------------------------------- */
.tc-row.is-entering { animation: tc-in var(--tc-d2) var(--tc-ease) both; }
.tc-row.is-leaving { animation: tc-out var(--tc-d2) var(--tc-ease-exit) forwards; pointer-events: none; }
.tc-time__num.is-ticking { animation: tc-tick var(--tc-d2) var(--tc-ease); }
.tc-row.is-due-now .tc-badge, .tc-hero.is-due-now .tc-badge { animation: tc-pulse 1.6s var(--tc-ease) 3; }
@keyframes tc-in { from { opacity: 0; transform: translateY(6px); } }
@keyframes tc-out { to { opacity: 0; grid-template-rows: 0fr; transform: translateX(-8px); } }
@keyframes tc-tick { from { opacity: 0; transform: translateY(-0.3em); } }
@keyframes tc-pulse { 0% { box-shadow: inset 0 0 0 1px var(--tc-badge-ring), 0 0 0 0 var(--line); } 70%, 100% { box-shadow: inset 0 0 0 1px var(--tc-badge-ring), 0 0 0 9px transparent; } }
@keyframes tc-arc { 0%, 100% { opacity: 0.35; } 40% { opacity: 1; } }
@keyframes tc-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@keyframes tc-dialog-in { from { opacity: 0; transform: translateY(12px) scale(0.98); } }
@keyframes tc-nudge { 0%, 100% { transform: none; } 40% { transform: translateX(3px); } }

@media (prefers-reduced-motion: reduce) {
  .tc *, .tc *::before, .tc *::after, .tc-dialog, .tc-dialog * { animation: none !important; transition-duration: 0.01ms !important; }
}
@media (prefers-contrast: more) {
  .tc { --tc-text-2: var(--tc-text); --tc-badge-ring: currentColor; }
  .tc-badge { box-shadow: inset 0 0 0 2px var(--tc-text); }
}
@media (forced-colors: active) {
  .tc-badge, .tc-leg--ride { forced-color-adjust: none; outline: 1px solid CanvasText; }
  .tc-live { color: Highlight; }
  .tc-hero, .tc-notice, .tc-leave--now { border: 1px solid CanvasText; }
}

/* ---------- 18. Integration additions (tisseo-ha 1.1.0) ------------------- */
.tc-dialog:not([open]) { display: none; } /* .tc sets display:flex, which would beat the UA rule */
div.tc-row__hit, div.tc-hero { cursor: default; }
.tc-brow.is-tap { cursor: pointer; border-radius: var(--tc-radius-s); }
.tc-brow.is-tap:hover { background: var(--tc-hover); }
.tc-chip .tc-badge { pointer-events: none; }
.tc-alerts__link { grid-column: 2; font-size: 13px; color: var(--tc-accent); font-weight: 500; }
.tc-head > span:empty { width: var(--tc-s2); }
.tc-stops__wrap { list-style: none; }
.tc-stop--past .tc-stop__time, .tc-stop--past .tc-stop__name { color: var(--tc-text-2); }
.tc-dlg__body .tc-empty { gap: 10px; }
.tc-dlg__body .tc-skel { height: 14px; }
button.tc-pager { border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }

/* 1.1.1: next scheduled departure when the 3 h window is empty */
.tc-next { flex-direction: column; gap: 6px; }
.tc-next__line { display: inline-flex; align-items: center; gap: 6px; color: var(--tc-text); font-weight: 500; }
`;

/* ───────── colour & contrast (from the design's tisseo-ui.js) ───────── */
function hexToRgb(hex) {
  let h = String(hex || "").replace("#", "").trim();
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-f]{6}$/i.test(h)) return null;
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
const toHex = (rgb) => "#" + rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();
function luminance(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return 0;
  const [r, g, b] = rgb.map((v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
function mix(a, b, k) { const A = hexToRgb(a), B = hexToRgb(b); return toHex(A.map((v, i) => v * (1 - k) + B[i] * k)); }
/* GTFS text colour kept when it reaches WCAG AA (4.5:1), else the better of black/white. "brand" keeps GTFS. */
function badgeColors(color, textColor, mode = "auto") {
  const bg = hexToRgb(color) ? "#" + String(color).replace("#", "").toUpperCase() : "#757575";
  const gtfsFg = hexToRgb(textColor) ? "#" + String(textColor).replace("#", "").toUpperCase() : null;
  if (mode === "brand" && gtfsFg) return { bg, fg: gtfsFg };
  if (gtfsFg && contrast(bg, gtfsFg) >= 4.5) return { bg, fg: gtfsFg };
  return { bg, fg: contrast(bg, "#000000") >= contrast(bg, "#FFFFFF") ? "#111111" : "#FFFFFF" };
}
/* "Ink" variant of a line colour for thin graphics (rails, bars) so they reach 3:1 on the surface. */
function inkColor(color, surface, target = 3) {
  if (!hexToRgb(color)) return color;
  if (contrast(color, surface) >= target) return color.toUpperCase();
  const towards = luminance(surface) > 0.5 ? "#000000" : "#FFFFFF";
  for (let k = 0.05; k <= 1; k += 0.05) { const c = mix(color, towards, k); if (contrast(c, surface) >= target) return c; }
  return towards;
}
/* Shape carries the mode for colour-blind users. */
function badgeShape(dep) {
  const mode = String(dep.mode || "").toLowerCase(), line = String(dep.line || "").toUpperCase();
  if (mode === "metro" || mode === "subway") return "metro";
  if (mode === "tram") return "tram";
  if (mode === "cable_car" || mode === "gondola" || line === "TELEO") return "cable";
  if (line === "AERO" || /navette|shuttle/i.test(dep.line_name || "")) return "shuttle";
  if (/^L\d{1,2}$/.test(line)) return "lineo";
  return "bus";
}

/* ───────── copy (FR / EN) ───────── */
const STRINGS = {
  fr: {
    min: "min", due: "Imminent", dueLong: "Départ imminent", canceled: "Supprimé",
    live: "Temps réel", scheduled: "Horaire théorique", metroSched: "Métro : horaire théorique",
    partlyLive: "en partie théorique",
    metroNoLive: "Tisséo ne publie pas de temps réel pour le métro",
    tripNoLive: "Pas de temps réel publié pour ce trajet",
    next: "Prochain départ", then: "puis", walk: (m) => `${m} min à pied`,
    late: (m) => `+${m} min`, early: (m) => `−${m} min`,
    lateLong: (m) => `en retard de ${m} min`, earlyLong: (m) => `en avance de ${m} min`,
    leaveIn: "Partez dans", leaveNow: "Partez maintenant", missed: "Trop juste",
    noDep: "Aucun départ dans les 3 h", nextService: "Prochain départ :", today: "aujourd'hui", tomorrow: "demain", noMatch: "Aucun départ pour ce filtre", showAll: "Tout afficher",
    feedDown: "Temps réel indisponible", feedDownSub: "Horaires théoriques affichés",
    stale: (m) => `Données d'il y a ${m} min`, entityMissing: "Arrêt introuvable",
    ttChange: "Horaires modifiés demain",
    ttSub: (a) => ttSummary(a, "fr", (t, r, pct) => `${t} départs demain contre ${r} le même jour la semaine suivante (${pct} %)`),
    disruptions: "Perturbations", filter: "Filtrer", all: "Toutes", more: "Plus d'infos",
    previousStops: (n) => `${n} arrêts précédents`, youAreHere: "Vous êtes ici", stops: "arrêts",
    skipped: "non desservi", close: "Fermer", loading: "Chargement…", tripErr: "Détail du trajet indisponible",
    line: "Ligne", destination: "Direction", departs: "Départ", thenCol: "Puis", metro: "Métro", other: "Bus & tram",
    in: "dans", at: "à", to: "vers", minutes: (m) => (m === 1 ? "1 minute" : `${m} minutes`),
  },
  en: {
    min: "min", due: "Due", dueLong: "Departing now", canceled: "Canceled",
    live: "Live", scheduled: "Scheduled", metroSched: "Metro: scheduled",
    partlyLive: "partly scheduled",
    metroNoLive: "Tisséo doesn't publish live times for the metro",
    tripNoLive: "No live data published for this trip",
    next: "Next departure", then: "then", walk: (m) => `${m} min walk`,
    late: (m) => `+${m} min`, early: (m) => `−${m} min`,
    lateLong: (m) => `${m} min late`, earlyLong: (m) => `${m} min early`,
    leaveIn: "Leave in", leaveNow: "Leave now", missed: "Too tight",
    noDep: "No departures in the next 3 h", nextService: "Next departure:", today: "today", tomorrow: "tomorrow", noMatch: "No departures match this filter", showAll: "Show all",
    feedDown: "Live data unavailable", feedDownSub: "Showing scheduled times",
    stale: (m) => `Data from ${m} min ago`, entityMissing: "Stop not found",
    ttChange: "Timetable changes tomorrow",
    ttSub: (a) => ttSummary(a, "en", (t, r, pct) => `${t} departures tomorrow vs ${r} the same day next week (${pct}%)`),
    disruptions: "Disruptions", filter: "Filter", all: "All", more: "More info",
    previousStops: (n) => `${n} earlier stops`, youAreHere: "You are here", stops: "stops",
    skipped: "skipped", close: "Close", loading: "Loading…", tripErr: "Trip details unavailable",
    line: "Line", destination: "To", departs: "Departs", thenCol: "Then", metro: "Metro", other: "Bus & tram",
    in: "in", at: "at", to: "to", minutes: (m) => (m === 1 ? "1 minute" : `${m} minutes`),
  },
};
function ttSummary(a, lang, fmt) {
  const t = Number(a.tomorrow_departures), r = Number(a.reference_departures);
  if (!(t >= 0) || !(r > 0)) return "";
  const pct = Math.round(((t - r) / r) * 100);
  return fmt(t.toLocaleString(lang), r.toLocaleString(lang), `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct)}`);
}
const tr = (lang) => STRINGS[String(lang || "en").slice(0, 2)] || STRINGS.en;

/* ───────── countdown & delays ───────── */
const DELAY_THRESHOLD_S = 90; // below this, GTFS-RT jitter: no chip
// HA's own time format setting (12 h / 24 h / language / system) is applied by the card on each render.
const TIMEFMT = { locale: undefined, hour12: undefined };
const hhmm = (ms) => new Date(ms).toLocaleTimeString(TIMEFMT.locale, { hour: "2-digit", minute: "2-digit", hour12: TIMEFMT.hour12 });
// "today 06:19" / "tomorrow 06:19" / "Monday 06:19" (local calendar days).
function dayTime(ms, nowMs, lang) {
  const s = tr(lang), when = new Date(ms), n = new Date(nowMs);
  const days = Math.round((new Date(when.getFullYear(), when.getMonth(), when.getDate()) - new Date(n.getFullYear(), n.getMonth(), n.getDate())) / 86400000);
  const day = days === 0 ? s.today : days === 1 ? s.tomorrow : when.toLocaleDateString(TIMEFMT.locale || lang, { weekday: "long" });
  return `${day} ${hhmm(ms)}`;
}
function formatCountdown(expectedMs, nowMs, lang) {
  const s = tr(lang), diff = Math.floor((expectedMs - nowMs) / 1000), min = Math.floor(diff / 60);
  if (diff < 60) return { kind: "due", word: s.due, text: s.due, minutes: 0 };
  if (min >= 60) { const v = hhmm(expectedMs, lang); return { kind: "clock", num: v, text: v, minutes: min }; }
  return { kind: "min", num: String(min), unit: s.min, text: `${min} ${s.min}`, minutes: min };
}
function delayInfo(dep, lang) {
  const s = tr(lang);
  if (dep.canceled) return { kind: "canceled", text: s.canceled };
  if (!dep.realtime || dep.delay_s == null) return null;
  if (Math.abs(dep.delay_s) < DELAY_THRESHOLD_S) return null;
  const m = Math.round(Math.abs(dep.delay_s) / 60);
  return dep.delay_s > 0 ? { kind: "late", text: s.late(m), long: s.lateLong(m) } : { kind: "early", text: s.early(m), long: s.earlyLong(m) };
}
function ariaLabel(group, nowMs, lang) {
  const s = tr(lang), x = group.next;
  const cd = formatCountdown(x.ms, nowMs, lang);
  const when = cd.kind === "due" ? s.dueLong : cd.kind === "clock" ? `${s.at} ${cd.num}` : `${s.in} ${s.minutes(cd.minutes)}`;
  const parts = [`${x.line} ${s.to} ${x.destination}`, x.canceled ? s.canceled : when];
  if (!x.canceled) parts.push(x.realtime ? s.live : s.scheduled);
  const dl = delayInfo(x, lang);
  if (dl && dl.long) parts.push(dl.long);
  return parts.join(", ");
}

/* ───────── grouping, hero, status, alerts ───────── */
function groupDepartures(deps, group, maxThen = 2) {
  if (!group) return deps.map((x) => ({ key: `${x.route_id || x.line}|${x.destination}|${x.trip_id || x.ms}`, next: x, then: [], canceled: [] }));
  const map = new Map();
  for (const x of deps) {
    const key = `${x.route_id || x.line}|${x.destination}`;
    if (!map.has(key)) map.set(key, { key, next: null, then: [], canceled: [] });
    const g = map.get(key);
    if (x.canceled) { g.canceled.push(x); continue; }
    if (!g.next) g.next = x; else if (g.then.length < maxThen) g.then.push(x);
  }
  for (const g of map.values()) if (!g.next && g.canceled.length) g.next = g.canceled.shift();
  return [...map.values()].sort((a, b) => a.next.ms - b.next.ms);
}
const pickHero = (deps, nowMs, minMinutes = 0) => deps.find((x) => !x.canceled && x.ms >= nowMs + minMinutes * 60000) || null;
function stopStatus(deps, health, ageS) {
  if (health === "down" || deps.some((x) => x.live_coverage === "feed_unavailable")) return "feed_down";
  if (ageS > 300) return "stale";
  const live = deps.some((x) => x.realtime), sched = deps.some((x) => !x.realtime);
  return live && sched ? "mixed" : live ? "live" : "scheduled";
}
const SEVERITY_RANK = { severe: 3, warning: 2, info: 1 };
/* Tisséo's GTFS-RT carries no severity: derive it from the effect (and Tisséo's 🔴/🟠 header prefix). */
function severityOf(alert) {
  const e = String(alert.effect || "").toUpperCase(), h = String(alert.header || "");
  if (e === "NO_SERVICE" || h.startsWith("🔴")) return "severe";
  if (/REDUCED_SERVICE|SIGNIFICANT_DELAYS|DETOUR|MODIFIED_SERVICE|STOP_MOVED/.test(e) || h.startsWith("🟠")) return "warning";
  return "info";
}

/* ───────── one ticker for the whole card ───────── */
class Ticker {
  constructor(host) {
    this.host = host; this.items = new Map(); this._visible = true; this._t = null;
    this._onVis = () => this._sync();
    this._tick = () => { const now = Date.now(); for (const el of [...this.items.keys()]) this._apply(el, now); this._schedule(); };
    this._io = "IntersectionObserver" in window
      ? new IntersectionObserver((e) => { this._visible = e.some((x) => x.isIntersecting); this._sync(); }) : null;
  }
  connect() { document.addEventListener("visibilitychange", this._onVis); this._io?.observe(this.host); this._sync(); }
  disconnect() { document.removeEventListener("visibilitychange", this._onVis); this._io?.disconnect(); clearTimeout(this._t); this._t = null; }
  track(el, render) {
    this.items.set(el, { render, last: null, seen: false });
    if (el.isConnected) this._apply(el, Date.now()); else queueMicrotask(() => this._apply(el, Date.now()));
  }
  _apply(el, now) {
    const it = this.items.get(el);
    if (!it) return;
    if (!el.isConnected) { if (it.seen) this.items.delete(el); return; }
    it.seen = true;
    const key = it.render(el, now, it.last);
    if (key !== undefined) it.last = key;
  }
  _schedule() { clearTimeout(this._t); this._t = setTimeout(this._tick, 1000 - (Date.now() % 1000) + 5); }
  _sync() {
    const run = !document.hidden && this._visible;
    if (run && !this._t) this._tick();
    if (!run && this._t) { clearTimeout(this._t); this._t = null; }
  }
}
/* Keyed list update: rows are patched in place, removed rows animate out. */
function reconcile(list, items, { key, create, update, reduceMotion = false }) {
  const existing = new Map([...list.children].filter((li) => !li.classList.contains("is-leaving")).map((li) => [li.dataset.key, li]));
  const keep = new Set();
  let cursor = list.firstElementChild;
  while (cursor && cursor.classList.contains("is-leaving")) cursor = cursor.nextElementSibling;
  for (const item of items) {
    const k = key(item);
    keep.add(k);
    let li = existing.get(k);
    if (li) { const nu = update(li, item) || li; if (nu !== li && cursor === li) cursor = nu; li = nu; }
    else {
      li = create(item); li.dataset.key = k;
      if (!reduceMotion) {
        li.classList.add("is-entering");
        li.addEventListener("animationend", () => li.classList.remove("is-entering"), { once: true });
        setTimeout(() => li.classList.remove("is-entering"), 600);
      }
    }
    if (li !== cursor) list.insertBefore(li, cursor);
    else cursor = cursor.nextElementSibling;
    while (cursor && cursor.classList.contains("is-leaving")) cursor = cursor.nextElementSibling;
  }
  for (const [k, li] of existing) {
    if (keep.has(k)) continue;
    if (reduceMotion) { li.remove(); continue; }
    li.classList.add("is-leaving");
    li.addEventListener("animationend", () => li.remove(), { once: true });
    setTimeout(() => li.remove(), 400);
  }
}

/* ───────── markup helpers ───────── */
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function lineVars(dep, surface, badgeMode) {
  const { bg, fg } = badgeColors(dep.color, dep.text_color, badgeMode);
  return `--line:${bg};--line-text:${fg};--line-ink:${inkColor(bg, surface)}`;
}
function badgeHTML(dep, size, badgeMode) {
  const { bg, fg } = badgeColors(dep.color, dep.text_color, badgeMode);
  return `<span class="tc-badge tc-badge--${badgeShape(dep)}${size ? ` tc-badge--${size}` : ""}" style="--line:${bg};--line-text:${fg}" aria-hidden="true">${esc(dep.line)}</span>`;
}
const LIVE_SVG = `<svg class="tc-live" viewBox="0 0 16 16" aria-hidden="true"><circle cx="4" cy="12" r="2"/><path class="a1" d="M4 7.5a4.5 4.5 0 0 1 4.5 4.5"/><path class="a2" d="M4 3a9 9 0 0 1 9 9"/></svg>`;
const LIVE_ANIM = LIVE_SVG.replace('class="tc-live"', 'class="tc-live tc-live--anim"');
const I = {
  stop: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="3" width="12" height="9" rx="2"/><path d="M9 7.5h6M12 12v9M9 21h6"/></svg>`,
  clock: `<svg class="tc-ico tc-ico--s" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
  filter: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/></svg>`,
  info: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>`,
  warning: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/></svg>`,
  severe: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2z"/><path d="M12 8v5M12 16v.5"/></svg>`,
  chevron: `<svg class="tc-ico tc-alert__chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`,
  close: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
  feedOff: `<svg class="tc-ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="18" r="1.6"/><path d="M6 12a6 6 0 0 1 6 6M6 6a12 12 0 0 1 12 12M3 3l18 18"/></svg>`,
  walk: `<svg class="tc-ico tc-ico--s" viewBox="0 0 24 24" aria-hidden="true"><circle cx="13" cy="4.5" r="1.8"/><path d="M11 21l1.5-5.5L15 18v3M8.5 12.5 10.5 8l3 .5 2 3.5 2.5 1M10.5 8l-1 6"/></svg>`,
};
/* Countdown renderer for .tc-time elements (DOM touched only when the text changes). */
function renderTime(lang) {
  return (el, now, last) => {
    const cd = formatCountdown(Number(el.dataset.expected), now, lang);
    if (cd.text === last) return last;
    const num = el.querySelector(".tc-time__num"), unit = el.querySelector(".tc-time__unit");
    el.classList.toggle("is-due", cd.kind === "due");
    el.closest(".tc-row, .tc-hero, .tc-brow")?.classList.toggle("is-due-now", cd.kind === "due");
    num.textContent = cd.kind === "due" ? cd.word : cd.num;
    unit.textContent = cd.unit || "";
    if (last !== null) { num.classList.remove("is-ticking"); void num.offsetWidth; num.classList.add("is-ticking"); }
    return cd.text;
  };
}

const DEFAULTS = {
  layout: "default", max_departures: 6, group: true, hero: "auto", hero_line: "", hero_min_minutes: 2,
  leave_entity: "", alerts: "banner", timetable_notice: true, show_clock: false, badge_contrast: "auto",
  board_theme: "dark", show_filters: false, trip_dialog: true,
};

class TisseoDeparturesCard extends HTMLElement {
  static getConfigElement() { return document.createElement("tisseo-departures-card-editor"); }
  static getStubConfig(hass) {
    const id = Object.keys(hass.states).find((e) => e.startsWith("sensor.") && Array.isArray(hass.states[e].attributes.upcoming));
    return { entity: id || "" };
  }

  constructor() {
    super();
    this._ticker = new Ticker(this);
    this._alertsOpen = null;
    this._chipsOpen = true;
    this._pageIdx = 0;
  }

  setConfig(config) {
    if (!config || (!config.entity && !config.device)) {
      throw new Error("Set 'entity' to a Tisséo departure sensor (e.g. sensor.tisseo_capitole_departure_1)");
    }
    const c = { ...DEFAULTS, ...config };
    // 1.0 option names keep working
    if (config.max_departures == null && config.max != null) c.max_departures = Number(config.max);
    if (config.alerts == null && config.show_alerts === false) c.alerts = "off";
    if (!config.filter_lines && Array.isArray(config.lines)) c.filter_lines = config.lines;
    c.max_departures = Math.max(1, Number(c.max_departures) || DEFAULTS.max_departures);
    c.layout = ["compact", "board"].includes(c.layout) ? c.layout : "default";
    this._config = c;
    this._sig = null;
    this._built = false;
    this._ids = null;
    this._sel = this._loadSel();
    if (this._hass) this.hass = this._hass;
  }

  connectedCallback() {
    this._ticker.connect();
    // Re-group once every 30 s so departed trains leave and "then" minutes stay right between sensor updates.
    clearInterval(this._regroup);
    this._regroup = setInterval(() => { if (this._built && this._hass && !document.hidden) this._render(); }, 30000);
  }
  disconnectedCallback() {
    this._ticker.disconnect();
    clearInterval(this._regroup); this._regroup = null;
    clearInterval(this._pager); this._pager = null;
    if (this._dialog?.open) this._dialog.close();
  }

  getCardSize() {
    const c = this._config || DEFAULTS;
    if (c.layout === "board") return 12;
    const heroOn = c.hero === "auto" ? c.layout === "default" : !!c.hero;
    return Math.ceil(1.5 + (heroOn ? 2 : 0) + c.max_departures * (c.layout === "compact" ? 0.9 : 1.2) + 1);
  }
  getGridOptions() {
    const l = (this._config || DEFAULTS).layout;
    if (l === "board") return { columns: "full", rows: "auto", min_columns: 12 };
    if (l === "compact") return { columns: 6, rows: "auto", min_columns: 3 };
    return { columns: 12, rows: "auto", min_columns: 6 };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const r = this._resolve();
    const sig = [r.dep, r.alerts, r.leave, r.health, r.tt].map((id) => id && hass.states[id]?.last_updated)
      .concat([hass.themes?.darkMode, hass.locale?.language, hass.language]).join("|");
    if (sig === this._sig && this._built) return;
    this._sig = sig;
    this._ids = r;
    this._render();
  }

  /* ---------- data ---------- */
  _resolve() {
    const h = this._hass, ents = h.entities || {}, c = this._config;
    const dev = c.device || ents[c.entity]?.device_id;
    const r = { dep: null, alerts: c.alerts_entity || null, leave: c.leave_entity || null, health: null, tt: null };
    if (dev) {
      for (const [id, e] of Object.entries(ents)) {
        if (e.device_id !== dev || !h.states[id]) continue;
        const a = h.states[id].attributes;
        if (Array.isArray(a.upcoming)) { if (!r.dep || /_departure_1$/.test(id)) r.dep = id; }
        else if (!r.alerts && Array.isArray(a.headlines)) r.alerts = id;
        else if (!r.leave && id.startsWith("sensor.") && "leave_at" in a) r.leave = id;
        else if (!r.health && a.feeds && typeof a.feeds === "object") r.health = id;
        else if (!r.tt && id.startsWith("binary_sensor.") && "tomorrow_departures" in a) r.tt = id;
      }
    }
    if (!r.dep && c.entity) {
      const guess = c.entity.replace(/_(departure_\d+|disruptions|leave_in)$/, "_departure_1");
      r.dep = h.states[guess] ? guess : c.entity;
    }
    const base = r.dep ? r.dep.replace(/_departure_\d+$/, "") : "";
    const guess = (k, id) => { if (!r[k] && base && h.states[id]) r[k] = id; };
    guess("alerts", `${base}_disruptions`);
    guess("leave", `${base}_leave_in`);
    guess("health", `${base}_feed_health`);
    guess("tt", `${base.replace(/^sensor\./, "binary_sensor.")}_timetable_change_tomorrow`);
    return r;
  }

  _norm(list) {
    // One shape for every departure: `delay_s` from delay_seconds (sensor) or delay (upcoming items).
    return (list || []).map((d) => ({ ...d, ms: Date.parse(d.expected), delay_s: d.delay_seconds ?? d.delay ?? null }))
      .filter((x) => !Number.isNaN(x.ms)).sort((a, b) => a.ms - b.ms);
  }

  _selKey() {
    const c = this._config;
    return `tisseo-card-filter:${c.entity || c.device}|${c.title || ""}|${c.layout || "default"}`;
  }
  _loadSel() {
    try {
      const v = JSON.parse(localStorage.getItem(this._selKey()) || "{}");
      return { lines: new Set(v.lines || []), dests: new Set(v.dests || []) };
    } catch (e) { return { lines: new Set(), dests: new Set() }; }
  }
  _saveSel() {
    try { localStorage.setItem(this._selKey(), JSON.stringify({ lines: [...this._sel.lines], dests: [...this._sel.dests] })); }
    catch (e) { /* storage unavailable */ }
  }
  _filter(list, useSel = true) {
    const c = this._config;
    const lines = (c.filter_lines || []).map((x) => String(x).toLowerCase());
    const dests = (c.filter_destinations || []).map((x) => String(x).toLowerCase()).filter(Boolean);
    const sel = useSel && c.show_filters ? this._sel : null; // chip selection only for cards that show chips
    return list.filter((x) => {
      const ln = String(x.line ?? "").toLowerCase(), de = String(x.destination ?? "").toLowerCase();
      if (lines.length && !lines.includes(ln) && !lines.includes(String(x.route_id ?? "").toLowerCase())) return false;
      if (dests.length && !dests.some((v) => de.includes(v))) return false;
      if (sel?.lines.size && !sel.lines.has(String(x.line))) return false;
      if (sel?.dests.size && !sel.dests.has(String(x.destination))) return false;
      return true;
    });
  }

  /* ---------- render ---------- */
  _render() {
    const hass = this._hass, c = this._config;
    if (!hass || !c) return;
    if (!this._ids) this._ids = this._resolve();
    const lang = (hass.locale?.language || hass.language || "en").slice(0, 2);
    const s = tr(lang);
    const dark = !!hass.themes?.darkMode;
    this._lang = lang; this._s = s;
    const tf = hass.locale?.time_format;
    TIMEFMT.locale = tf === "system" ? undefined : hass.locale?.language || hass.language;
    TIMEFMT.hour12 = tf === "12" ? true : tf === "24" ? false : undefined;
    this._surface = c.layout === "board" && c.board_theme !== "auto" ? "#0B1220" : dark ? "#1C1C1C" : "#FFFFFF";
    const st = this._ids.dep && hass.states[this._ids.dep];
    if (!this._built || this._builtLayout !== c.layout) this._buildSkeleton(c.layout);
    const card = this._card;
    card.dataset.layout = c.layout;
    card.dataset.theme = dark ? "dark" : "light";
    card.dataset.boardTheme = c.board_theme === "auto" ? (dark ? "dark" : "light") : "dark";
    if (!st) return this._renderError(s);

    const now = Date.now();
    // Departures more than a minute gone are dropped between two sensor updates.
    const all = this._norm(st.attributes.upcoming).filter((x) => x.ms > now - 60000);
    this._stopId = st.attributes.stop_id;
    this._routeLine = new Map(all.map((x) => [x.route_id, x]));
    const deps = this._filter(all);
    const health = this._ids.health ? hass.states[this._ids.health]?.state : null;
    const status = stopStatus(deps.length ? deps : all, health, (now - Date.parse(st.last_updated)) / 1000);
    card.classList.toggle("is-stale", status === "stale");
    const alerts = this._alertList(deps);

    if (c.layout === "board") return this._renderBoard(st, deps, status, alerts, now);

    this._renderHeader(st, all, status);
    this._renderChips(all);
    this._renderNotices(status, st);

    let hero = null, leave = null;
    const heroOn = c.hero === "auto" ? c.layout === "default" : !!c.hero;
    if (heroOn) ({ hero, leave } = this._pickHero(deps, now));
    this._renderHero(hero, leave, deps, now);

    // The hero is not repeated in the list. Its direction stays listed only when an earlier departure
    // (one you can no longer catch on foot) exists; later ones are already the hero's "then".
    const heroKey = hero ? `${hero.route_id || hero.line}|${hero.destination}` : null;
    const groups = groupDepartures(hero ? deps.filter((x) => x !== hero) : deps, c.group !== false)
      .filter((g) => !(c.group !== false && g.key === heroKey && g.next.ms > hero.ms)).slice(0, c.max_departures);
    if (!groups.length && !hero) this._renderEmpty(all.length > 0, st);
    else this._emptyEl.hidden = true;

    reconcile(this._list, groups, {
      key: (g) => g.key, reduceMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
      create: (g) => this._rowEl(g, now, alerts),
      update: (li, g) => this._patch(li, g, alerts, () => this._rowEl(g, now, alerts)),
    });
    this._renderAlerts(alerts);
  }

  _patch(el, g, alerts, make) {
    const sig = this._rowSig(g, alerts);
    if (el._sig === sig) { el._group = g; return el; }
    const fresh = make();
    fresh.dataset.key = el.dataset.key;
    el.replaceWith(fresh);
    return fresh;
  }

  _rowSig(g, alerts) {
    const x = g.next;
    return JSON.stringify([x.trip_id, x.ms, x.realtime, x.delay_s, x.canceled, g.then.map((y) => y.ms),
      g.canceled.map((y) => y.ms), this._flag(x, alerts), this._lang, Math.floor(Date.now() / 60000)]);
  }

  _flag(x, alerts) {
    let best = null;
    for (const a of alerts) if (a.routes.includes(x.route_id) && (!best || SEVERITY_RANK[a.severity] > SEVERITY_RANK[best])) best = a.severity;
    return best;
  }

  _rowEl(g, now, alerts) {
    const c = this._config, lang = this._lang, s = this._s, x = g.next;
    const dl = delayInfo(x, lang);
    const then = g.then.map((y) => Math.max(0, Math.floor((y.ms - now) / 60000)));
    const delayChip = dl && dl.kind !== "canceled" ? ` <span class="tc-delay tc-delay--${dl.kind}">${esc(dl.text)}</span>` : "";
    const skipped = g.canceled.find((y) => y.ms < x.ms);
    const skippedNote = skipped && !x.canceled
      ? `<span class="tc-cancel">${hhmm(Date.parse(skipped.scheduled || skipped.expected), lang)} ${esc(s.canceled.toLowerCase())}</span> · ` : "";
    const flag = this._flag(x, alerts);
    const flagIco = flag && flag !== "info"
      ? I[flag].replace('class="tc-ico"', `class="tc-ico tc-flag${flag === "severe" ? " tc-flag--severe" : ""}"`) : "";
    const tap = c.trip_dialog !== false && !!x.trip_id;
    const tag = tap ? "button" : "div";
    const li = document.createElement("li");
    li.className = ["tc-row", x.canceled ? "is-canceled" : "", x.realtime ? "is-live" : "is-sched"].filter(Boolean).join(" ");
    li.setAttribute("style", lineVars(x, this._surface, c.badge_contrast));
    li.innerHTML = `<${tag} class="tc-row__hit"${tap ? ' type="button"' : ""} aria-label="${esc(ariaLabel(g, now, lang))}">
      ${badgeHTML(x, "", c.badge_contrast)}
      <span class="tc-row__main">
        <span class="tc-row__dest">${esc(x.destination)}${flagIco}</span>
        <span class="tc-row__meta">${x.canceled ? `<span class="tc-cancel">${esc(s.canceled)}</span> · ` : skippedNote}${x.realtime ? "" : I.clock}${hhmm(x.ms, lang)}${delayChip}${then.length ? ` · ${esc(s.then)} ${then.join(", ")} ${s.min}` : ""}</span>
      </span>
      ${c.layout === "compact" ? `<span class="tc-then">${then.length ? `${then[0]} ${s.min}` : ""}</span>` : ""}
      ${x.canceled ? `<span class="tc-time tc-time--canceled">${esc(s.canceled)}</span>`
        : `<span class="tc-time" data-expected="${x.ms}">${x.realtime ? LIVE_SVG : ""}<span class="tc-time__num"></span><span class="tc-time__unit"></span></span>`}
    </${tag}>`;
    li._group = g;
    li._sig = this._rowSig(g, alerts);
    if (tap) li.firstElementChild.addEventListener("click", () => this._openTrip(li._group.next));
    const tEl = li.querySelector(".tc-time[data-expected]");
    if (tEl) this._ticker.track(tEl, renderTime(lang));
    return li;
  }

  _buildSkeleton(layout) {
    this._builtLayout = layout;
    clearInterval(this._pager); this._pager = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    let styleTag = "";
    if ("adoptedStyleSheets" in root && typeof CSSStyleSheet === "function" && "replaceSync" in CSSStyleSheet.prototype) {
      if (!TisseoDeparturesCard._sheet) { TisseoDeparturesCard._sheet = new CSSStyleSheet(); TisseoDeparturesCard._sheet.replaceSync(STYLES); }
      root.adoptedStyleSheets = [TisseoDeparturesCard._sheet];
    } else styleTag = `<style>${STYLES}</style>`;
    const dialog = `<dialog class="tc tc-dialog" aria-labelledby="tc-dlg-title"></dialog>`;
    if (layout === "board") {
      root.innerHTML = `${styleTag}
        <ha-card class="tc">
          <header class="tc-board__head"></header>
          <div class="tc-board__cols">
            ${["metro", "other"].map((p) => `<section class="tc-board__panel" data-panel="${p}" hidden>
              <h3 class="tc-board__panel-title"></h3>
              <div class="tc-bhead" aria-hidden="true"></div>
              <div class="tc-brows" role="table"></div></section>`).join("")}
          </div>
          <div class="tc-empty" hidden></div>
          <footer class="tc-board__foot" role="status" hidden></footer>
        </ha-card>${dialog}`;
      this._head = root.querySelector(".tc-board__head");
      this._emptyEl = root.querySelector(".tc-empty");
    } else {
      root.innerHTML = `${styleTag}
        <ha-card class="tc">
          <header class="tc-head"></header>
          <div class="tc-chips" role="toolbar" hidden></div>
          <div class="tc-notice-slot"></div>
          <div class="tc-hero-slot"></div>
          <div class="tc-empty" hidden></div>
          <ol class="tc-list"></ol>
          <div class="tc-alerts-slot"></div>
        </ha-card>${dialog}`;
      this._head = root.querySelector(".tc-head");
      this._chips = root.querySelector(".tc-chips");
      this._noticeSlot = root.querySelector(".tc-notice-slot");
      this._heroSlot = root.querySelector(".tc-hero-slot");
      this._emptyEl = root.querySelector(".tc-empty");
      this._list = root.querySelector(".tc-list");
      this._alertsSlot = root.querySelector(".tc-alerts-slot");
      const rerender = () => { this._chipSig = null; this._headHtml = null; this._render(); };
      this._chips.addEventListener("click", (ev) => {
        const b = ev.target.closest("button");
        if (!b) return;
        const kind = b.dataset.k, val = b.dataset.v;
        if (kind === "all") this._sel = { lines: new Set(), dests: new Set() };
        else { const set = this._sel[kind]; if (set.has(val)) set.delete(val); else set.add(val); }
        this._saveSel(); rerender();
      });
      this._head.addEventListener("click", (ev) => {
        if (!ev.target.closest(".tc-iconbtn")) return;
        this._chipsOpen = !this._chipsOpen; rerender();
      });
      this._emptyEl.addEventListener("click", (ev) => {
        if (!ev.target.closest(".tc-textbtn")) return;
        this._sel = { lines: new Set(), dests: new Set() }; this._saveSel(); rerender();
      });
    }
    this._card = root.querySelector(".tc");
    this._dialog = root.querySelector("dialog");
    this._dialog.addEventListener("click", (e) => { if (e.target === this._dialog) this._dialog.close(); });
    this._headHtml = null; this._chipSig = null; this._noticeHtml = null; this._heroKey = null; this._alertsHtml = null;
    this._built = true;
  }

  _renderHeader(st, all, status) {
    const c = this._config, s = this._s;
    const title = c.title || st.attributes.stop_name || "Tisséo";
    const metroSched = all.some((x) => !x.realtime && x.mode === "metro");
    const liveLines = st.attributes.live_lines || [];
    const sub = {
      live: `${LIVE_SVG}${esc(s.live)}`,
      stale: `${LIVE_SVG}${esc(s.live)}`,
      mixed: `${LIVE_SVG}${esc(s.live)} <span aria-hidden="true">·</span> ${I.clock}${esc(metroSched ? s.metroSched : s.partlyLive)}`,
      scheduled: `${I.clock}${esc(s.scheduled)}`,
      feed_down: `${I.clock}${esc(s.scheduled)}`,
    }[status];
    const nSel = this._sel.lines.size + this._sel.dests.size;
    const right = c.show_filters
      ? `<button class="tc-iconbtn" type="button" aria-label="${esc(s.filter)}" aria-expanded="${this._chipsOpen}">${I.filter}${nSel ? `<span class="tc-iconbtn__count">${nSel}</span>` : ""}</button>`
      : c.show_clock ? `<time class="tc-head__clock"></time>` : "<span></span>";
    const html = `<div class="tc-head__icon">${I.stop}</div>
      <div><h2 class="tc-head__title">${esc(title)}</h2><p class="tc-head__sub"${liveLines.length ? ` title="${esc(s.live)}: ${esc(liveLines.join(" · "))}"` : ""}>${sub}</p></div>${right}`;
    if (this._headHtml === html) return;
    this._headHtml = html;
    this._head.innerHTML = html;
    const clock = this._head.querySelector("time");
    if (clock) this._ticker.track(clock, (el, n, last) => { const v = hhmm(n, this._lang); if (v !== last) el.textContent = v; return v; });
  }

  _renderChips(all) {
    const c = this._config, s = this._s, el = this._chips;
    if (!c.show_filters || !this._chipsOpen) { el.hidden = true; return; }
    const base = this._filter(all, false);
    const lines = new Map(), freq = new Map();
    for (const x of base) {
      if (!lines.has(String(x.line))) lines.set(String(x.line), x);
      if (this._sel.lines.size && !this._sel.lines.has(String(x.line))) continue; // directions follow the selected lines
      freq.set(String(x.destination), (freq.get(String(x.destination)) || 0) + 1);
    }
    for (const l of this._sel.lines) if (!lines.has(l)) lines.set(l, { line: l });
    const dests = new Set([...freq].sort((a, b) => b[1] - a[1]).slice(0, 6).map((v) => v[0]));
    for (const v of this._sel.dests) dests.add(v);
    const sig = JSON.stringify([[...lines.keys()], [...dests], [...this._sel.lines], [...this._sel.dests], this._lang]);
    el.hidden = false;
    if (sig === this._chipSig) return;
    this._chipSig = sig;
    const none = !this._sel.lines.size && !this._sel.dests.size;
    const chip = (k, v, inner, text) => `<button type="button" class="tc-chip${text ? " tc-chip--text" : ""}" data-k="${k}" data-v="${esc(v)}" aria-pressed="${k === "all" ? none : this._sel[k].has(v)}">${inner}</button>`;
    el.innerHTML = chip("all", "", esc(s.all), true) +
      [...lines].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
        .map(([l, x]) => chip("lines", l, badgeHTML(x, "xs", c.badge_contrast))).join("") +
      (dests.size > 1 || this._sel.dests.size ? [...dests].sort().map((v) => chip("dests", v, `→ ${esc(v)}`, true)).join("") : "");
  }

  _renderNotices(status, st) {
    const s = this._s, c = this._config, hass = this._hass;
    let html = "";
    if (status === "feed_down") {
      html += `<div class="tc-notice tc-notice--warning" role="status">${I.feedOff}<span><b>${esc(s.feedDown)}</b><span class="tc-notice__sub">${esc(s.feedDownSub)}</span></span></div>`;
    } else if (status === "stale") {
      const m = Math.round((Date.now() - Date.parse(st.last_updated)) / 60000);
      html += `<div class="tc-notice" role="status">${I.info}<span><b>${esc(s.stale(m))}</b></span></div>`;
    }
    const tt = c.timetable_notice !== false && this._ids.tt ? hass.states[this._ids.tt] : null;
    if (tt?.state === "on") {
      html += `<div class="tc-notice" role="status">${I.info}<span><b>${esc(s.ttChange)}</b><span class="tc-notice__sub">${esc(s.ttSub(tt.attributes) || tt.attributes.description || "")}</span></span></div>`;
    }
    if (this._noticeHtml !== html) { this._noticeSlot.innerHTML = html; this._noticeHtml = html; }
  }

  /* Leave-now data comes from the integration's "leave in" sensor (walking time + buffer). */
  _leaveInfo() {
    const e = this._ids.leave && this._hass.states[this._ids.leave];
    const a = e?.attributes;
    if (!a || !(Number(a.walking_time) > 0)) return null;
    return { walk: Number(a.walking_time), buffer: Number(a.buffer || 0), next: a.next_catchable || null };
  }

  _pickHero(deps, now) {
    const c = this._config, L = this._leaveInfo();
    const minMinutes = L ? L.walk : Number(c.hero_min_minutes) || 0;
    let hero = null;
    if (c.hero_line) {
      hero = deps.find((x) => `${x.line}|${x.destination}` === c.hero_line && !x.canceled && x.ms - now >= minMinutes * 60000) || null;
    } else if (L?.next?.trip_id) {
      hero = deps.find((x) => x.trip_id === L.next.trip_id && !x.canceled) || null;
    }
    if (!hero) hero = pickHero(deps, now, minMinutes);
    const leave = L && hero ? { walk: L.walk, leaveAt: hero.ms - (L.walk + L.buffer) * 60000, catchBy: hero.ms - L.walk * 60000 } : null;
    return { hero, leave };
  }

  _renderHero(hero, leave, deps, now) {
    const c = this._config, s = this._s, lang = this._lang;
    if (!hero) { this._heroSlot.innerHTML = ""; this._heroKey = null; return; }
    const then = deps.filter((x) => x !== hero && x.line === hero.line && x.destination === hero.destination && !x.canceled && x.ms > hero.ms)
      .slice(0, 2).map((x) => Math.floor((x.ms - now) / 60000));
    const key = JSON.stringify([hero.trip_id, hero.ms, hero.realtime, hero.delay_s, then, leave?.leaveAt, lang, c.trip_dialog]);
    if (this._heroKey === key) return;
    this._heroKey = key;
    const dl = delayInfo(hero, lang);
    const tap = c.trip_dialog !== false && !!hero.trip_id;
    const tag = tap ? "button" : "div";
    this._heroSlot.innerHTML = `
      <${tag} class="tc-hero"${tap ? ' type="button"' : ""} style="${lineVars(hero, this._surface, c.badge_contrast)}">
        <span class="tc-hero__eyebrow"></span>
        ${badgeHTML(hero, "l", c.badge_contrast)}
        <span class="tc-hero__main">
          <span class="tc-hero__dest">${esc(hero.destination)}</span>
          <span class="tc-hero__meta">${hero.realtime ? "" : I.clock}${hhmm(hero.ms, lang)}${dl && dl.kind !== "canceled" ? ` <span class="tc-delay tc-delay--${dl.kind}">${esc(dl.text)}</span>` : ""}${then.length ? ` · ${esc(s.then)} ${then.join(", ")} ${s.min}` : ""}</span>
        </span>
        <span class="tc-time" data-expected="${hero.ms}">${hero.realtime ? LIVE_ANIM : ""}<span class="tc-time__num"></span><span class="tc-time__unit"></span></span>
      </${tag}>`;
    const btn = this._heroSlot.firstElementChild;
    if (tap) btn.addEventListener("click", () => this._openTrip(hero));
    this._ticker.track(btn.querySelector(".tc-time"), renderTime(lang));
    this._ticker.track(btn.querySelector(".tc-hero__eyebrow"), (el, n, last) => {
      let html = esc(s.next);
      if (leave) {
        const secs = Math.floor((leave.leaveAt - n) / 1000);
        if (n > leave.catchBy + 30000) html = `${I.walk}${esc(s.missed)} · ${esc(s.walk(leave.walk))}`;
        else if (secs > 60) html = `${I.walk}${esc(s.leaveIn)} ${Math.ceil(secs / 60)} ${s.min} · ${esc(s.walk(leave.walk))}`;
        else html = `${I.walk}<b>${esc(s.leaveNow)}</b> · ${esc(s.walk(leave.walk))}`;
      }
      if (html !== last) el.innerHTML = html;
      return html;
    });
  }

  _alertList(deps) {
    const st = this._ids.alerts && this._hass.states[this._ids.alerts];
    const raw = st?.attributes?.alerts || [];
    const visible = new Set(deps.map((x) => x.route_id));
    return raw.map((a) => ({
      title: a.header || "", description: a.description || "", url: a.url || "", severity: severityOf(a),
      routes: a.lines || [], network: !!a.network_wide,
    }))
      .filter((a) => !a.routes.length || !visible.size || a.routes.some((r) => visible.has(r)))
      .sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || (a.network - b.network));
  }

  _lineBadges(a, max = 3) {
    return a.routes.slice(0, max).map((r) => this._routeLine.get(r)).filter(Boolean)
      .map((x) => badgeHTML(x, "xs", this._config.badge_contrast)).join("");
  }

  _renderAlerts(list) {
    const c = this._config, s = this._s;
    if (c.alerts === "off" || !list.length) {
      if (this._alertsHtml !== "") { this._alertsSlot.innerHTML = ""; this._alertsHtml = ""; }
      return;
    }
    const top = list[0], rest = list.length - 1;
    const open = this._alertsOpen ?? top.severity === "severe";
    const items = list.map((a) => `<li class="tc-alerts__item tc-alerts__item--${a.severity}">${I[a.severity]}
        <span class="tc-alerts__title">${this._lineBadges(a)}${esc(a.title)}</span>
        <span class="tc-alerts__desc">${esc(a.description)}</span>
        ${a.url ? `<a class="tc-alerts__link" href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(s.more)}</a>` : ""}</li>`).join("");
    const count = c.alerts === "count";
    const html = `
      <button class="tc-alert tc-alert--${top.severity}" type="button" aria-expanded="${open}" aria-controls="tc-alerts">
        ${I[top.severity]}
        <span class="tc-alert__text">${count ? "" : this._lineBadges(top, 1)}<span>${esc(count ? `${list.length} · ${s.disruptions}` : top.title)}</span></span>
        ${rest && !count ? `<span class="tc-alert__count">+${rest}</span>` : "<span></span>"}
        ${I.chevron}
      </button>
      <ul class="tc-alerts__list" id="tc-alerts"${open ? "" : " hidden"}>${items}</ul>`;
    if (this._alertsHtml === html) return;
    this._alertsHtml = html;
    this._alertsSlot.innerHTML = html;
    this._alertsSlot.querySelector(".tc-alert").addEventListener("click", () => { this._alertsOpen = !open; this._renderAlerts(list); });
  }

  // No departure in the window: say when the next one is (e.g. no Sunday service on the line).
  _nextServiceHTML(st, now) {
    const n = st?.attributes?.next_service, ms = n && Date.parse(n.scheduled);
    if (!n || !(ms > now)) return "";
    return `<p class="tc-empty__text tc-next"><span>${esc(this._s.nextService)} ${esc(dayTime(ms, now, this._lang))}</span>
      <span class="tc-next__line">${badgeHTML(n, "", this._config.badge_contrast)}<span>${esc(n.destination || "")}</span></span></p>`;
  }

  _renderEmpty(hasAny, st) {
    const s = this._s, el = this._emptyEl;
    const filtered = hasAny && (this._sel.lines.size || this._sel.dests.size) && this._config.show_filters;
    el.hidden = false;
    el.innerHTML = filtered
      ? `<div class="tc-empty__icon">${I.filter}</div><p class="tc-empty__title">${esc(s.noMatch)}</p><button class="tc-textbtn" type="button">${esc(s.showAll)}</button>`
      : `<div class="tc-empty__icon">${I.clock}</div><p class="tc-empty__title">${esc(hasAny ? s.noMatch : s.noDep)}</p>${hasAny ? "" : this._nextServiceHTML(st, Date.now())}`;
  }

  _renderError(s) {
    this._card.innerHTML = `<div class="tc-empty tc-empty--error" role="alert"><div class="tc-empty__icon">${I.warning}</div>
      <p class="tc-empty__title">${esc(s.entityMissing)}</p><p class="tc-empty__text"><code>${esc(this._ids?.dep || this._config.entity)}</code></p></div>`;
    this._built = false; // rebuild the skeleton when the entity appears
  }

  /* ---------- departure board ---------- */
  _renderBoard(st, deps, status, alerts, now) {
    const c = this._config, lang = this._lang, s = this._s, r = this.shadowRoot;
    const sub = status === "feed_down" ? `${I.feedOff}${esc(s.feedDown)} · ${esc(s.feedDownSub)}`
      : deps.some((x) => x.realtime) ? `${LIVE_ANIM}${esc(s.live)}` : `${I.clock}${esc(s.scheduled)}`;
    const headHtml = `<div class="tc-head__icon">${I.stop}</div>
      <div><h2 class="tc-board__title">${esc(c.title || st.attributes.stop_name || "Tisséo")}</h2><p class="tc-board__sub">${sub}</p></div>
      <time class="tc-board__clock"></time>`;
    if (this._headHtml !== headHtml) {
      this._head.innerHTML = headHtml; this._headHtml = headHtml;
      this._ticker.track(this._head.querySelector("time"), (el, n, last) => { const v = hhmm(n, lang); if (v !== last) el.textContent = v; return v; });
    }
    const groups = groupDepartures(deps, c.group !== false).slice(0, c.max_departures);
    this._emptyEl.hidden = groups.length > 0;
    if (!groups.length) this._emptyEl.innerHTML = `<div class="tc-empty__icon">${I.clock}</div><p class="tc-empty__title">${esc(s.noDep)}</p>${this._nextServiceHTML(st, now)}`;
    const isMetro = (g) => g.next.mode === "metro";
    const panels = { metro: groups.filter(isMetro), other: groups.filter((g) => !isMetro(g)) };
    const both = panels.metro.length > 0 && panels.other.length > 0;
    r.querySelector(".tc-board__cols").classList.toggle("tc-board__cols--split", both);
    for (const [name, list] of Object.entries(panels)) {
      const sec = r.querySelector(`[data-panel="${name}"]`);
      sec.hidden = !list.length;
      const h3 = sec.querySelector(".tc-board__panel-title");
      h3.textContent = both ? s[name] : ""; h3.hidden = !both;
      sec.querySelector(".tc-bhead").innerHTML = `<span>${esc(s.line)}</span><span>${esc(s.destination)}</span><span>${esc(s.departs)}</span><span>${esc(s.thenCol)}</span>`;
      reconcile(sec.querySelector(".tc-brows"), list, {
        key: (g) => g.key, reduceMotion: true,
        create: (g) => this._boardRow(g, now, alerts),
        update: (row, g) => this._patch(row, g, alerts, () => this._boardRow(g, now, alerts)),
      });
    }
    // Footer: one disruption at a time, paged every 8 s (static under reduced motion), never a marquee.
    const foot = r.querySelector(".tc-board__foot");
    foot.hidden = !alerts.length || c.alerts === "off";
    if (foot.hidden) { clearInterval(this._pager); this._pager = null; return; }
    this._boardAlerts = alerts;
    this._pageIdx = Math.min(this._pageIdx || 0, alerts.length - 1);
    const paint = () => {
      const list = this._boardAlerts, a = list[this._pageIdx], n = list.length;
      const dots = list.slice(0, 5).map((_, i) => `<i class="${i === this._pageIdx % 5 ? "on" : ""}"></i>`).join("");
      foot.innerHTML = `<span style="color:var(--tc-sev-${a.severity})">${I[a.severity]}</span>
        <span class="tc-board__msg">${this._lineBadges(a, 2)}<span>${esc(a.title)}</span></span>
        <button class="tc-pager" type="button" aria-label="${this._pageIdx + 1} / ${n}">${dots}<span>${this._pageIdx + 1} / ${n}</span></button>`;
      foot.querySelector(".tc-pager").addEventListener("click", () => { this._pageIdx = (this._pageIdx + 1) % this._boardAlerts.length; paint(); });
    };
    paint();
    if (!this._pager && alerts.length > 1 && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      this._pager = setInterval(() => {
        if (foot.matches(":hover") || !this._boardAlerts?.length) return;
        this._pageIdx = (this._pageIdx + 1) % this._boardAlerts.length; paint();
      }, 8000);
    }
  }

  _boardRow(g, now, alerts) {
    const c = this._config, lang = this._lang, s = this._s, x = g.next;
    const dl = delayInfo(x, lang);
    const skipped = g.canceled.find((y) => y.ms < x.ms);
    let note = "";
    if (dl && dl.kind !== "canceled") note = `<span class="tc-delay tc-delay--${dl.kind}">${esc(dl.text)}</span>`;
    else if (skipped && !x.canceled) note = `<span class="tc-cancel">${hhmm(Date.parse(skipped.scheduled || skipped.expected), lang)} ${esc(s.canceled.toLowerCase())}</span>`;
    else if (!x.realtime && !x.canceled) note = `${I.clock}<span>${esc(s.scheduled)}</span>`;
    const nx = g.then[0];
    let thenTxt = "";
    if (nx) { const m = Math.floor((nx.ms - now) / 60000); thenTxt = m >= 60 ? hhmm(nx.ms, lang) : `${m} ${s.min}`; }
    const time = x.canceled
      ? `<div class="tc-brow__time tc-brow__time--canceled">${esc(s.canceled)}</div>`
      : `<div class="tc-brow__time tc-time" data-expected="${x.ms}">${x.realtime ? LIVE_SVG : ""}<b class="tc-time__num"></b><small class="tc-time__unit"></small></div>`;
    const tap = c.trip_dialog !== false && !!x.trip_id;
    const tpl = document.createElement("template");
    tpl.innerHTML = `<div class="tc-brow${x.canceled ? " is-canceled" : ""}${tap ? " is-tap" : ""}" role="row"${tap ? ' tabindex="0"' : ""} aria-label="${esc(ariaLabel(g, now, lang))}">
      ${badgeHTML(x, "xl", c.badge_contrast)}
      <div role="cell"><div class="tc-brow__dest">${esc(x.destination)}</div>${note ? `<div class="tc-brow__note">${note}</div>` : ""}</div>
      ${time}
      <div class="tc-brow__then" role="cell">${thenTxt}</div></div>`;
    const row = tpl.content.firstElementChild;
    row._group = g;
    row._sig = this._rowSig(g, alerts);
    if (tap) {
      row.addEventListener("click", () => this._openTrip(row._group.next));
      row.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this._openTrip(row._group.next); } });
    }
    const tEl = row.querySelector(".tc-time");
    if (tEl) this._ticker.track(tEl, renderTime(lang));
    return row;
  }

  /* ---------- trip dialog (native <dialog>: top layer, Esc closes, focus kept inside) ---------- */
  async _openTrip(dep) {
    if (!dep || !dep.trip_id || this._config.trip_dialog === false) return;
    const s = this._s, lang = this._lang, c = this._config, dlg = this._dialog;
    const dark = !!this._hass.themes?.darkMode;
    dlg.dataset.theme = dark ? "dark" : "light";
    dlg.setAttribute("style", lineVars(dep, dark ? "#1C1C1C" : "#FFFFFF", c.badge_contrast));
    const head = (sub) => `<header class="tc-dlg__head">${badgeHTML(dep, "l", c.badge_contrast)}
        <div><h2 class="tc-dlg__title" id="tc-dlg-title">${esc(dep.destination)}</h2><p class="tc-dlg__sub">${sub}</p></div>
        <button class="tc-iconbtn" type="button" aria-label="${esc(s.close)}" autofocus>${I.close}</button></header>`;
    const bindClose = () => dlg.querySelector(".tc-iconbtn").addEventListener("click", () => dlg.close());
    dlg.innerHTML = `${head(esc(s.loading))}<div class="tc-dlg__body"><div class="tc-empty"><span class="tc-skel" style="width:60%"></span><span class="tc-skel" style="width:40%"></span></div></div>`;
    bindClose();
    if (!dlg.open) { try { dlg.showModal(); } catch (e) { dlg.setAttribute("open", ""); } }
    const seq = (this._tripSeq = (this._tripSeq || 0) + 1);
    let res;
    try {
      const req = { type: "tisseo/trip_stops", trip_id: dep.trip_id };
      if (dep.stop_id || this._stopId) req.stop_id = dep.stop_id || this._stopId;
      if (dep.scheduled) req.scheduled = dep.scheduled;
      res = await this._hass.callWS(req);
    } catch (err) {
      if (seq !== this._tripSeq) return;
      dlg.querySelector(".tc-dlg__body").innerHTML = `<div class="tc-empty"><div class="tc-empty__icon">${I.warning}</div><p class="tc-empty__title">${esc(s.tripErr)}</p>${err?.message ? `<p class="tc-empty__text">${esc(err.message)}</p>` : ""}</div>`;
      return;
    }
    if (seq !== this._tripSeq) return;
    const stops = res.stops || [];
    const sel = Math.max(0, stops.findIndex((p) => p.is_selected));
    const before = stops.slice(0, sel), ahead = stops.slice(sel);
    const fmt = (iso) => (iso ? hhmm(Date.parse(iso), lang) : "");
    const live = !!res.realtime;
    const sub = `${live ? LIVE_SVG + esc(s.live) : I.clock + esc(s.scheduled)} · ${stops.length} ${esc(s.stops)}${res.canceled ? ` · <span class="tc-cancel">${esc(s.canceled)}</span>` : ""}`;
    const stopLi = (p, isEnd, isBefore) => {
      const t = fmt(p.expected || p.scheduled), sc = fmt(p.scheduled);
      const here = !!p.is_selected;
      const cls = ["tc-stop", here ? "tc-stop--here" : "", isEnd ? "tc-stop--end" : "", isBefore || p.past ? "tc-stop--past" : ""].filter(Boolean).join(" ");
      const late = p.realtime && Math.abs(p.delay ?? 0) >= DELAY_THRESHOLD_S;
      const tag = p.skipped ? `<span class="tc-cancel">${esc(s.skipped)}</span>`
        : late ? `<span class="tc-delay tc-delay--${p.delay > 0 ? "late" : "early"}">${p.delay > 0 ? "+" : "−"}${Math.round(Math.abs(p.delay) / 60)} ${s.min}</span>` : "";
      return `<li class="${cls}"${here ? ' aria-current="location"' : ""}>
        <span class="tc-stop__time">${esc(t)}${sc && sc !== t ? `<s>${esc(sc)}</s>` : ""}</span><span class="tc-stop__rail"></span>
        <span class="tc-stop__name">${here ? `<span class="tc-stop__eyebrow">${esc(s.youAreHere)}</span>` : ""}${esc(p.name)}</span><span>${tag}</span></li>`;
    };
    const foot = live ? "" : dep.mode === "metro" ? s.metroNoLive
      : dep.live_coverage === "feed_unavailable" ? `${s.feedDown} · ${s.feedDownSub}` : s.tripNoLive;
    dlg.innerHTML = `${head(sub)}
      <div class="tc-dlg__body"><ol class="tc-stops">
        ${before.length ? `<li class="tc-stops__wrap"><button class="tc-stops__more" type="button" aria-expanded="false"><span></span><span class="tc-stop__rail"></span><span>${esc(s.previousStops(before.length))}</span></button></li>` : ""}
        ${ahead.map((p, i) => stopLi(p, i === ahead.length - 1, false)).join("")}
      </ol></div>
      ${foot ? `<footer class="tc-dlg__foot"><span>${esc(foot)}</span></footer>` : ""}`;
    bindClose();
    const more = dlg.querySelector(".tc-stops__more");
    if (more) more.addEventListener("click", () => { more.closest("li").outerHTML = before.map((p) => stopLi(p, false, true)).join(""); });
    dlg.querySelector(".tc-stop--here")?.scrollIntoView({ block: "center" });
  }
}

/* ---------- visual editor: ha-form schema (HA-native, offline) ---------- */
const LABELS = {
  fr: { entity: "Arrêt (n'importe quel capteur de l'arrêt)", title: "Titre (facultatif)", layout: "Disposition", max_departures: "Lignes affichées",
        group: "Regrouper par direction", hero: "Mettre en avant le prochain départ", hero_line: "Direction mise en avant",
        leave_entity: "Capteur « Partir dans » (auto)", filter_lines: "Uniquement ces lignes", filter_destinations: "Destination contient",
        show_filters: "Filtres (puces) dans la carte", trip_dialog: "Toucher une ligne : arrêts du trajet",
        alerts: "Perturbations", timetable_notice: "Avertir des changements d'horaires", show_clock: "Horloge",
        badge_contrast: "Contraste des pastilles", board_theme: "Thème du tableau" },
  en: { entity: "Stop (any sensor of the stop)", title: "Title (optional)", layout: "Layout", max_departures: "Rows shown",
        group: "Group by direction", hero: "Highlight the next departure", hero_line: "Highlighted direction",
        leave_entity: "“Leave in” sensor (auto)", filter_lines: "Only these lines", filter_destinations: "Destination contains",
        show_filters: "Filter chips in the card", trip_dialog: "Tap a row for the trip's stops",
        alerts: "Disruptions", timetable_notice: "Timetable change notice", show_clock: "Clock",
        badge_contrast: "Badge contrast", board_theme: "Board theme" },
};
function tdcSchema(lang, lines, directions) {
  const fr = lang === "fr";
  return [
    { name: "entity", required: true, selector: { entity: { domain: "sensor", integration: "tisseo" } } },
    { name: "title", selector: { text: {} } },
    { type: "grid", name: "", schema: [
      { name: "layout", selector: { select: { mode: "dropdown", options: [
        { value: "default", label: fr ? "Standard" : "Default" },
        { value: "compact", label: fr ? "Compacte" : "Compact" },
        { value: "board", label: fr ? "Tableau des départs" : "Departure board" }] } } },
      { name: "max_departures", selector: { number: { min: 1, max: 12, mode: "box" } } },
    ] },
    { type: "grid", name: "", schema: [
      { name: "group", selector: { boolean: {} } },
      { name: "hero", selector: { boolean: {} } },
      { name: "trip_dialog", selector: { boolean: {} } },
      { name: "show_filters", selector: { boolean: {} } },
    ] },
    { name: "filter_lines", selector: { select: { multiple: true, custom_value: true, mode: "dropdown",
      options: lines.map((l) => ({ value: l, label: l })) } } },
    { name: "filter_destinations", selector: { text: { multiple: true } } },
    { type: "expandable", name: "", title: fr ? "Mon trajet" : "My trip", schema: [
      { name: "hero_line", selector: { select: { mode: "dropdown", options: directions } } },
      { name: "leave_entity", selector: { entity: { domain: "sensor", integration: "tisseo" } } },
    ] },
    { type: "grid", name: "", schema: [
      { name: "alerts", selector: { select: { mode: "dropdown", options: [
        { value: "banner", label: fr ? "Bandeau replié" : "Collapsed banner" },
        { value: "count", label: fr ? "Compteur seul" : "Count only" },
        { value: "off", label: fr ? "Masquées" : "Hidden" }] } } },
      { name: "timetable_notice", selector: { boolean: {} } },
      { name: "show_clock", selector: { boolean: {} } },
    ] },
    { type: "expandable", name: "", title: fr ? "Accessibilité et affichage avancé" : "Accessibility & advanced", schema: [
      { name: "badge_contrast", selector: { select: { mode: "dropdown", options: [
        { value: "auto", label: fr ? "Automatique (AA)" : "Automatic (AA)" },
        { value: "brand", label: fr ? "Couleurs Tisséo" : "Tisséo colours" }] } } },
      { name: "board_theme", selector: { select: { mode: "dropdown", options: [
        { value: "dark", label: fr ? "Toujours sombre" : "Always dark" },
        { value: "auto", label: fr ? "Suivre Home Assistant" : "Follow Home Assistant" }] } } },
    ] },
  ];
}

class TisseoDeparturesCardEditor extends HTMLElement {
  setConfig(config) { this._config = { ...config }; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _render() {
    if (!this._hass || !this._config) return;
    const lang = (this._hass.locale?.language || this._hass.language || "en").slice(0, 2) === "fr" ? "fr" : "en";
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        const prev = this._config;
        const cfg = { ...prev, ...ev.detail.value };
        for (const k of ["filter_lines", "filter_destinations"]) {
          if (Array.isArray(cfg[k]) && !cfg[k].filter((v) => v !== "").length) delete cfg[k];
        }
        for (const k of ["title", "hero_line", "leave_entity"]) if (cfg[k] === "" || cfg[k] == null) delete cfg[k];
        // keep the YAML short: values equal to the defaults are not written unless the user had set them
        for (const [k, v] of Object.entries(DEFAULTS)) if (cfg[k] === v && !(k in prev)) delete cfg[k];
        if (cfg.layout === "default") delete cfg.layout;
        if ("max_departures" in cfg) delete cfg.max;          // 1.0 name
        if ("alerts" in cfg) delete cfg.show_alerts;           // 1.0 name
        this._config = cfg;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    const st = this._hass.states[this._config.entity];
    const ups = st?.attributes?.upcoming || [];
    const lines = [...new Set(ups.map((u) => String(u.line)).concat((this._config.filter_lines || []).map(String)))]
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const directions = [{ value: "", label: lang === "fr" ? "Automatique" : "Automatic" },
      ...[...new Set(ups.map((u) => `${u.line}|${u.destination}`))].map((k) => ({ value: k, label: k.replace("|", " → ") }))];
    const labels = LABELS[lang];
    this._form.computeLabel = (sch) => labels[sch.name] || sch.name;
    this._form.hass = this._hass;
    const data = { ...DEFAULTS, ...this._config };
    if (this._config.max_departures == null && this._config.max != null) data.max_departures = Number(this._config.max);
    if (this._config.alerts == null && this._config.show_alerts === false) data.alerts = "off";
    if (data.hero === "auto") data.hero = (data.layout || "default") === "default";
    this._form.data = data;
    this._form.schema = tdcSchema(lang, lines, directions);
  }
}

// Home Assistant installs a scoped custom-element-registry polyfill that can replace
// window.customElements *after* this module ran (extra JS loads in parallel with the
// frontend). Definitions made on the old registry are then invisible, so (re)register
// on the current registry until the frontend has settled.
function tdcRegister() {
  for (const [tag, cls] of [["tisseo-departures-card", TisseoDeparturesCard],
                            ["tisseo-departures-card-editor", TisseoDeparturesCardEditor]]) {
    try { if (!customElements.get(tag)) customElements.define(tag, cls); }
    catch (err) { /* already defined on this registry */ }
  }
}
tdcRegister();
if (!window.__tisseoCardTimer) {
  let n = 0;
  window.__tisseoCardTimer = setInterval(() => { tdcRegister(); if (++n > 120) clearInterval(window.__tisseoCardTimer); }, 250);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((x) => x.type === "tisseo-departures-card")) {
  window.customCards.push({ type: "tisseo-departures-card", name: "Tisséo departures",
    description: "Next departures for a Tisséo stop: live countdowns, delays, disruptions, leave-now, departure board.",
    preview: true, documentationURL: "https://github.com/TurbulenceDeterministe/tisseo-ha" });
  console.info(`%c TISSEO-DEPARTURES-CARD %c v${TDC_VERSION} `,
    "background:#db001b;color:#fff;font-weight:700", "background:#ffdd00;color:#000");
}
})();

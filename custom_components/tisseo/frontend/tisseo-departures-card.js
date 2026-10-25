/*
 * tisseo-departures-card – animated Lovelace card for the Tisséo integration.
 * Vanilla web component, no build step. Served automatically by the integration
 * at /tisseo_static/tisseo-departures-card.js (or add it as a dashboard resource).
 *
 *   type: custom:tisseo-departures-card
 *   entity: sensor.tisseo_capitole_departure_1   # any sensor of the stop works
 *   title: Capitole            # optional (defaults to the stop name)
 *   max: 5                     # optional, max departures shown
 *   show_alerts: true          # optional, scrolling alerts ticker
 *   alerts_entity: sensor.…    # optional, auto-detected from the same device
 *   layout: default            # default | compact | board (station departure board)
 *   filter_lines: [A, "14"]    # optional, only these lines (short names)
 *   filter_destinations: [Balma]  # optional, destination contains any of these
 *   show_filters: false        # optional, tappable line / direction chips in the card
 *   trip_dialog: true          # tap a row to see all the stops of that trip
 */
const TDC_VERSION = "1.0.0";

const TDC_I18N = {
  en: { now: "now", min: "min", live: "live", timetable: "timetable", ontime: "on time",
        late: "late", early: "early", canceled: "canceled", nodep: "No departures in the next 3 h",
        livelines: "Live", nolive: "timetable only", alerts: "alerts", unavailable: "Entity not found",
        sched: "sched.", all: "All", stops: "stops", close: "Close", loading: "Loading…",
        tripErr: "Trip details unavailable", skipped: "skipped", board_line: "Line",
        board_dest: "Destination", board_time: "Departs", board_info: "Info", arr: "arr." },
  fr: { now: "à quai", min: "min", live: "temps réel", timetable: "théorique", ontime: "à l'heure",
        late: "retard", early: "avance", canceled: "supprimé", nodep: "Aucun départ dans les 3 h",
        livelines: "Temps réel", nolive: "horaires théoriques", alerts: "alertes",
        unavailable: "Entité introuvable", sched: "prévu", all: "Toutes", stops: "arrêts",
        close: "Fermer", loading: "Chargement…", tripErr: "Détail du trajet indisponible",
        skipped: "non desservi", board_line: "Ligne", board_dest: "Destination",
        board_time: "Départ", board_info: "Info", arr: "arr." },
};

const TDC_CSS = `
:host { --tdc-accent: var(--primary-color, #03a9f4); --tdc-late: var(--error-color, #db4437);
  --tdc-early: var(--success-color, #43a047); --tdc-muted: var(--secondary-text-color, #727272);
  --tdc-divider: var(--divider-color, rgba(127,127,127,.2)); display:block; }
ha-card { overflow: hidden; position: relative; }
[hidden] { display: none !important; }
.header { display:flex; align-items:center; gap:12px; padding:16px 16px 8px; }
.header .icon { width:40px; height:40px; border-radius:12px; display:grid; place-items:center;
  background: color-mix(in srgb, var(--tdc-accent) 15%, transparent); color: var(--tdc-accent); flex:none; }
.header .icon ha-icon { --mdc-icon-size: 24px; }
.header .t { flex:1; min-width:0; }
.header .title { font-size:1.25em; font-weight:600; color:var(--primary-text-color); white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.header .sub { font-size:.85em; color:var(--tdc-muted); display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.header .clock { font-variant-numeric: tabular-nums; font-size:1.05em; color:var(--tdc-muted); font-weight:500; }
.list { position:relative; padding: 4px 8px 8px; }
.row { position:relative; display:grid; grid-template-columns: auto 1fr auto; align-items:center; gap:12px;
  padding:10px 10px 12px 14px; margin:4px 0; border-radius:14px;
  background: color-mix(in srgb, var(--line-color, var(--tdc-accent)) 7%, transparent);
  transition: transform .45s cubic-bezier(.2,.8,.2,1), opacity .45s, background .3s; overflow:hidden; }
.row::before { content:""; position:absolute; left:0; top:8px; bottom:8px; width:4px; border-radius:4px;
  background: var(--line-color, var(--tdc-accent)); }
.row.enter { animation: tdc-in .55s cubic-bezier(.2,.8,.2,1) both; }
.row.leave { animation: tdc-out .45s ease-in both; pointer-events:none; }
@keyframes tdc-in { from { opacity:0; transform: translateX(28px) scale(.97); } to { opacity:1; transform:none; } }
@keyframes tdc-out { to { opacity:0; transform: translateX(-28px); height:0; margin:0; padding-top:0; padding-bottom:0; } }
.badge { min-width:2.3em; height:2.3em; padding:0 .45em; box-sizing:border-box; display:grid; place-items:center;
  font-weight:800; font-size:1.05em; letter-spacing:-.02em; background:var(--line-color, var(--tdc-accent));
  color:var(--line-text, #fff); border-radius:8px; box-shadow: 0 2px 6px color-mix(in srgb, var(--line-color, #000) 35%, transparent); }
.badge.metro { border-radius:50%; width:2.3em; padding:0; font-size:1.2em; }
.badge.tram { border-radius:10px 2px 10px 2px; }
.badge.bus { border-radius:999px; font-size:.95em; }
.mid { min-width:0; }
.dest { font-weight:600; color:var(--primary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.meta { display:flex; align-items:center; gap:8px; margin-top:3px; font-size:.8em; color:var(--tdc-muted); flex-wrap:wrap; }
.live { display:inline-flex; align-items:center; gap:5px; color: var(--tdc-early); font-weight:600; }
.dot { position:relative; width:8px; height:8px; border-radius:50%; background: var(--tdc-early); }
.dot::after, .dot::before { content:""; position:absolute; inset:0; border-radius:50%; border:2px solid var(--tdc-early);
  animation: tdc-radar 1.8s cubic-bezier(.2,.6,.4,1) infinite; }
.dot::before { animation-delay: .9s; }
@keyframes tdc-radar { from { transform: scale(1); opacity:.9; } to { transform: scale(3.2); opacity:0; } }
.tt { display:inline-flex; align-items:center; gap:4px; opacity:.75; }
.tt ha-icon { --mdc-icon-size: 14px; }
.chip { padding:1px 7px; border-radius:999px; font-weight:700; font-size:.95em; }
.chip.late { background: color-mix(in srgb, var(--tdc-late) 16%, transparent); color: var(--tdc-late); }
.chip.early, .chip.ok { background: color-mix(in srgb, var(--tdc-early) 16%, transparent); color: var(--tdc-early); }
.chip.cx { background: color-mix(in srgb, var(--tdc-late) 16%, transparent); color: var(--tdc-late); }
.row.canceled .dest { text-decoration: line-through; opacity:.6; }
.cd { text-align:right; font-variant-numeric: tabular-nums; line-height:1; min-width:3.6em; }
.cd .big { font-size:1.9em; font-weight:800; color:var(--primary-text-color); transition: color .3s; }
.cd .unit { font-size:.8em; font-weight:600; color:var(--tdc-muted); margin-left:2px; }
.cd .small { display:block; font-size:.75em; color:var(--tdc-muted); margin-top:4px; }
.row.imminent { animation: tdc-pulse 1.2s ease-in-out infinite; }
.row.imminent .cd .big { color: var(--primary-text-color); }
.row.gone { display: none; }
@keyframes tdc-pulse { 0%,100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--line-color, var(--tdc-accent)) 45%, transparent); }
  50% { box-shadow: 0 0 0 6px color-mix(in srgb, var(--line-color, var(--tdc-accent)) 0%, transparent);
        background: color-mix(in srgb, var(--line-color, var(--tdc-accent)) 16%, transparent); } }
.bar { position:absolute; left:0; right:0; bottom:0; height:3px; background: var(--tdc-divider); }
.bar > i { display:block; height:100%; width:0; background: linear-gradient(90deg,
  color-mix(in srgb, var(--line-color, var(--tdc-accent)) 60%, transparent), var(--line-color, var(--tdc-accent)));
  transition: width 1s linear; position:relative; overflow:hidden; }
.bar > i::after { content:""; position:absolute; inset:0; background: linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent);
  transform: translateX(-100%); animation: tdc-shine 2.2s ease-in-out infinite; }
@keyframes tdc-shine { to { transform: translateX(100%); } }
.empty { padding: 18px; text-align:center; color: var(--tdc-muted); }
.ticker { display:flex; align-items:center; gap:10px; border-top:1px solid var(--tdc-divider);
  padding:8px 0 8px 12px; font-size:.85em; color:var(--primary-text-color); overflow:hidden;
  background: color-mix(in srgb, var(--warning-color, #ffa600) 8%, transparent); }
.ticker .lbl { flex:none; display:flex; align-items:center; gap:4px; color: var(--warning-color, #ffa600); font-weight:700; }
.ticker .lbl ha-icon { --mdc-icon-size: 18px; animation: tdc-blink 2s ease-in-out infinite; }
@keyframes tdc-blink { 50% { opacity:.35; } }
.marquee { overflow:hidden; flex:1; mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent); }
.marquee .track { display:inline-flex; white-space:nowrap; animation: tdc-marquee var(--dur, 30s) linear infinite; }
.marquee .track span { padding-right: 3em; }
.marquee:hover .track { animation-play-state: paused; }
@keyframes tdc-marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
.row.tap { cursor: pointer; }
.row.tap:hover { background: color-mix(in srgb, var(--line-color, var(--tdc-accent)) 13%, transparent); }
.row.tap:focus-visible { outline: 2px solid var(--line-color, var(--tdc-accent)); outline-offset: 1px; }
.filters { display:flex; gap:6px; flex-wrap:wrap; padding: 0 16px 6px; }
.filters button { font: inherit; font-size:.8em; border:1px solid var(--tdc-divider); background:none; cursor:pointer;
  color: var(--primary-text-color); border-radius:999px; padding:3px 10px; display:inline-flex; align-items:center; gap:5px; }
.filters button i { width:9px; height:9px; border-radius:3px; background: var(--c, var(--tdc-accent)); }
.filters button.on { background: color-mix(in srgb, var(--c, var(--tdc-accent)) 20%, transparent);
  border-color: var(--c, var(--tdc-accent)); font-weight:700; }
.filters .sep { width:1px; background: var(--tdc-divider); margin: 2px 2px; }
/* compact layout */
ha-card.compact .header { padding: 10px 12px 4px; }
ha-card.compact .header .icon { width:30px; height:30px; border-radius:9px; }
ha-card.compact .header .title { font-size:1.05em; }
ha-card.compact .row { padding:5px 8px 6px 12px; margin:2px 0; gap:10px; border-radius:10px; }
ha-card.compact .badge { min-width:1.9em; height:1.9em; font-size:.9em; }
ha-card.compact .badge.metro { width:1.9em; font-size:1em; }
ha-card.compact .meta { display:none; }
ha-card.compact .dest { font-size:.95em; }
ha-card.compact .cd .big { font-size:1.3em; }
ha-card.compact .cd .small { display:none; }
ha-card.compact .row.rt .dest::after { content:""; display:inline-block; width:6px; height:6px; border-radius:50%;
  background: var(--tdc-early); margin-left:6px; vertical-align: middle; }
ha-card.compact .row.late .dest::after { background: var(--tdc-late); }
/* board layout: station departure board */
ha-card.board { background: #0b0f14; color: #ffd24a; --primary-text-color: #ffd24a; --tdc-muted: #b8a35a;
  --tdc-divider: rgba(255,210,74,.18); font-family: "DejaVu Sans Mono", ui-monospace, Menlo, Consolas, monospace; }
ha-card.board .header .icon { background: rgba(255,210,74,.14); color:#ffd24a; }
ha-card.board .header .title { color:#ffd24a; text-transform: uppercase; letter-spacing:.06em; }
ha-card.board .bhead { display:grid; grid-template-columns: 3.4em 1fr 4.2em 5.4em; gap:10px; padding: 4px 18px;
  font-size:.7em; text-transform: uppercase; letter-spacing:.12em; color:#b8a35a; border-bottom:1px solid rgba(255,210,74,.18); }
ha-card.board .list { padding: 2px 8px 8px; }
ha-card.board .row { grid-template-columns: 3.4em 1fr 4.2em 5.4em; border-radius:0; margin:0; padding:9px 10px;
  background: none; border-bottom:1px dashed rgba(255,210,74,.14); }
ha-card.board .row:nth-child(even) { background: rgba(255,255,255,.025); }
ha-card.board .row::before { display:none; }
ha-card.board .badge { box-shadow:none; }
ha-card.board .dest { color:#ffd24a; text-transform: uppercase; letter-spacing:.04em; }
ha-card.board .mid .meta { display:none; }
ha-card.board .cd { text-align:right; }
ha-card.board .cd .big { color:#ffd24a; font-size:1.25em; }
ha-card.board .cd .small { display:none; }
ha-card.board .binfo { font-size:.75em; text-align:right; color:#b8a35a; text-transform: uppercase; }
ha-card.board .binfo .late, ha-card.board .binfo .cx { color:#ff6b5a; font-weight:700; }
ha-card.board .binfo .ok { color:#7ee081; }
ha-card.board .row.imminent .cd .big { animation: tdc-blink 1s steps(2) infinite; }
ha-card.board .bar { display:none; }
ha-card.board .ticker { background: rgba(255,210,74,.08); color:#ffd24a; }
.binfo { display:none; }
ha-card.board .binfo { display:block; }
/* trip dialog */
.dlg { position:fixed; inset:0; z-index:9; display:grid; place-items:center; background: rgba(0,0,0,.45);
  animation: tdc-fade .2s ease-out; font-family: var(--paper-font-body1_-_font-family, inherit); }
@keyframes tdc-fade { from { opacity:0; } }
.dlg .box { width:min(440px, calc(100vw - 24px)); max-height:min(80vh, 720px); display:flex; flex-direction:column;
  background: var(--card-background-color, #fff); color: var(--primary-text-color); border-radius:18px;
  box-shadow: 0 12px 40px rgba(0,0,0,.35); overflow:hidden; animation: tdc-pop .25s cubic-bezier(.2,.8,.2,1); }
@keyframes tdc-pop { from { transform: translateY(16px) scale(.97); opacity:0; } }
.dlg .dh { display:flex; align-items:center; gap:12px; padding:14px 14px 12px 16px;
  background: color-mix(in srgb, var(--line-color, var(--tdc-accent)) 14%, transparent); }
.dlg .dh .t { flex:1; min-width:0; }
.dlg .dh .h1 { font-weight:700; font-size:1.1em; }
.dlg .dh .h2 { font-size:.8em; color: var(--secondary-text-color, #727272); }
.dlg .x { border:none; background:none; color:inherit; cursor:pointer; font-size:1.5em; line-height:1; padding:4px 8px; border-radius:8px; }
.dlg .x:hover { background: rgba(127,127,127,.15); }
.dlg .body { overflow:auto; padding: 8px 12px 14px 12px; }
.dlg .msg { padding: 24px; text-align:center; color: var(--secondary-text-color, #727272); }
.dlg ol { list-style:none; margin:0; padding:0; position:relative; }
.dlg li { display:grid; grid-template-columns: 3.4em 22px 1fr auto; align-items:center; gap:8px; min-height:34px;
  position:relative; font-size:.92em; }
.dlg li .tm { text-align:right; font-variant-numeric: tabular-nums; font-weight:600; }
.dlg li .tm s { display:block; font-weight:400; font-size:.8em; color: var(--secondary-text-color, #727272); }
.dlg li .rail { position:relative; align-self:stretch; }
.dlg li .rail::before { content:""; position:absolute; left:9px; top:0; bottom:0; width:4px;
  background: var(--line-color, var(--tdc-accent)); }
.dlg li:first-child .rail::before { top:50%; } .dlg li:last-child .rail::before { bottom:50%; }
.dlg li .rail::after { content:""; position:absolute; left:5px; top:50%; width:12px; height:12px; margin-top:-6px;
  border-radius:50%; background: var(--card-background-color, #fff); border:3px solid var(--line-color, var(--tdc-accent)); box-sizing:border-box; }
.dlg li.past { opacity:.45; }
.dlg li.sel { font-weight:700; }
.dlg li.sel .rail::after { width:18px; height:18px; left:2px; margin-top:-9px; background: var(--line-color, var(--tdc-accent)); }
.dlg li.next .rail::after { box-shadow: 0 0 0 4px color-mix(in srgb, var(--line-color, var(--tdc-accent)) 30%, transparent);
  animation: tdc-pulse2 1.4s ease-in-out infinite; }
@keyframes tdc-pulse2 { 50% { box-shadow: 0 0 0 8px color-mix(in srgb, var(--line-color, var(--tdc-accent)) 0%, transparent); } }
.dlg li.skip .nm { text-decoration: line-through; }
.dlg li .ch { font-size:.8em; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .marquee .track { white-space: normal; display:block; } .marquee .track span + span { display:none; }
}
`;

function tdcEsc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

class TisseoDeparturesCard extends HTMLElement {
  static getConfigElement() { return document.createElement("tisseo-departures-card-editor"); }

  static getStubConfig(hass) {
    const id = Object.keys(hass.states).find((e) => e.startsWith("sensor.") &&
      Array.isArray(hass.states[e].attributes.upcoming));
    return { entity: id || "", max: 5, show_alerts: true };
  }

  setConfig(config) {
    if (!config || (!config.entity && !config.device)) {
      throw new Error("Set 'entity' to a Tisséo departure sensor (e.g. sensor.tisseo_capitole_departure_1)");
    }
    this._config = { max: 5, show_alerts: true, ...config };
    this._rows = new Map();
    this._sig = null;
    this._alertSig = null;
    this._built = false;
    this._sel = this._loadSel();
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
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
    try {
      localStorage.setItem(this._selKey(), JSON.stringify({ lines: [...this._sel.lines], dests: [...this._sel.dests] }));
    } catch (e) { /* storage unavailable */ }
  }

  _filter(list) {
    const lines = (this._config.filter_lines || []).map((x) => String(x).toLowerCase());
    const dests = (this._config.filter_destinations || []).map((x) => String(x).toLowerCase()).filter(Boolean);
    // in-card chip selection only applies to cards that show the chips
    const sel = this._config.show_filters ? this._sel : null;
    const sl = sel?.lines || new Set(), sd = sel?.dests || new Set();
    return list.filter((d) => {
      const ln = String(d.line ?? "").toLowerCase(), de = String(d.destination ?? "").toLowerCase();
      if (lines.length && !lines.includes(ln) && !lines.includes(String(d.route_id ?? "").toLowerCase())) return false;
      if (dests.length && !dests.some((x) => de.includes(x))) return false;
      if (sl.size && !sl.has(String(d.line))) return false;
      if (sd.size && !sd.has(String(d.destination))) return false;
      return true;
    });
  }

  _renderFilters(all) {
    const f = this._el.filters;
    if (!this._config.show_filters) { f.hidden = true; return; }
    // chips come from departures already narrowed by the static (YAML) filters
    const base = this._filter.call({ _config: this._config, _sel: null }, all);
    const lines = new Map(), freq = new Map();
    for (const d of base) {
      if (!lines.has(String(d.line))) lines.set(String(d.line), d.color);
      // direction chips follow the selected lines, most frequent first (max 6)
      if (this._sel.lines.size && !this._sel.lines.has(String(d.line))) continue;
      freq.set(String(d.destination), (freq.get(String(d.destination)) || 0) + 1);
    }
    for (const l of this._sel.lines) if (!lines.has(l)) lines.set(l, null);
    const dests = new Set([...freq].sort((a, b) => b[1] - a[1]).slice(0, 6).map((x) => x[0]));
    for (const x of this._sel.dests) dests.add(x);
    const sig = JSON.stringify([[...lines], [...dests], [...this._sel.lines], [...this._sel.dests]]);
    if (sig === this._fsig) return;
    this._fsig = sig;
    const none = !this._sel.lines.size && !this._sel.dests.size;
    const btn = (k, v, label, c) => `<button data-k="${k}" data-v="${tdcEsc(v)}" class="${this._sel[k]?.has(v) ? "on" : ""}"` +
      `${c ? ` style="--c:${tdcEsc(c)}"` : ""}>${c !== undefined ? "<i></i>" : ""}${tdcEsc(label)}</button>`;
    f.innerHTML = `<button data-k="all" class="${none ? "on" : ""}">${this._t.all}</button>` +
      [...lines].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
        .map(([l, c]) => btn("lines", l, l, c || "var(--tdc-accent)")).join("") +
      (dests.size > 1 || this._sel.dests.size ? '<span class="sep"></span>' +
        [...dests].sort().map((x) => btn("dests", x, `→ ${x}`)).join("") : "");
    f.hidden = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._update();
  }

  connectedCallback() {
    if (!this._timer) this._timer = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    this._closeTrip();
    clearInterval(this._timer);
    this._timer = null;
  }

  getCardSize() {
    const n = Math.min(this._config?.max || 5, 8);
    return this._config?.layout === "compact" ? 1 + Math.ceil(n / 2) : 2 + n;
  }

  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

  get _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return TDC_I18N[lang] || TDC_I18N.en;
  }

  _build() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${TDC_CSS}</style>
      <ha-card>
        <div class="header">
          <div class="icon"><ha-icon icon="mdi:bus-clock"></ha-icon></div>
          <div class="t"><div class="title"></div><div class="sub"></div></div>
          <div class="clock"></div>
        </div>
        <div class="filters" hidden></div>
        <div class="bhead" hidden></div>
        <div class="list"></div>
        <div class="ticker" hidden>
          <div class="lbl"><ha-icon icon="mdi:alert"></ha-icon><span class="n"></span></div>
          <div class="marquee"><div class="track"></div></div>
        </div>
      </ha-card>`;
    const $ = (s) => this.shadowRoot.querySelector(s);
    this._el = { title: $(".title"), sub: $(".sub"), clock: $(".clock"), list: $(".list"),
                 ticker: $(".ticker"), track: $(".track"), n: $(".ticker .n"), icon: $(".header ha-icon"),
                 card: $("ha-card"), filters: $(".filters"), bhead: $(".bhead") };
    const layout = ["compact", "board"].includes(this._config.layout) ? this._config.layout : "default";
    this._el.card.classList.add(layout);
    this._layout = layout;
    if (layout === "board") {
      const t = this._t;
      this._el.bhead.hidden = false;
      this._el.bhead.innerHTML = `<span>${t.board_line}</span><span>${t.board_dest}</span>` +
        `<span style="text-align:right">${t.board_time}</span><span style="text-align:right">${t.board_info}</span>`;
    }
    this._el.list.addEventListener("click", (ev) => {
      const row = ev.target.closest(".row");
      if (row && row._d && this._config.trip_dialog !== false) this._openTrip(row._d);
    });
    this._el.list.addEventListener("keydown", (ev) => {
      const row = ev.target.closest(".row");
      if (row && (ev.key === "Enter" || ev.key === " ") && row._d && this._config.trip_dialog !== false) {
        ev.preventDefault(); this._openTrip(row._d);
      }
    });
    this._el.filters.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      const kind = b.dataset.k, val = b.dataset.v;
      if (kind === "all") { this._sel = { lines: new Set(), dests: new Set() }; }
      else {
        const set = this._sel[kind];
        set.has(val) ? set.delete(val) : set.add(val);
      }
      this._saveSel();
      this._sig = null; this._fsig = null;
      this._update();
    });
    this._built = true;
  }

  _resolve() {
    const h = this._hass, ents = h.entities || {};
    let dev = this._config.device || ents[this._config.entity]?.device_id;
    let dep = null, alerts = this._config.alerts_entity || null;
    if (dev) {
      for (const [id, e] of Object.entries(ents)) {
        if (e.device_id !== dev || !h.states[id]) continue;
        const a = h.states[id].attributes;
        if (Array.isArray(a.upcoming)) dep = id;
        else if (!alerts && Array.isArray(a.headlines)) alerts = id;
      }
    }
    if (!dep && this._config.entity) {
      const guess = this._config.entity.replace(/_(departure_\d+|disruptions)$/, "_departure_1");
      dep = h.states[guess] ? guess : this._config.entity;
    }
    if (!alerts && dep) {
      const guess = dep.replace(/_departure_\d+$/, "_disruptions");
      if (h.states[guess]) alerts = guess;
    }
    return { dep, alerts };
  }

  _update() {
    const { dep, alerts } = this._resolve();
    const st = dep && this._hass.states[dep];
    const t = this._t;
    if (!st) {
      this._el.title.textContent = this._config.title || "Tisséo";
      this._el.list.innerHTML = `<div class="empty">${t.unavailable}: ${tdcEsc(dep || this._config.entity)}</div>`;
      this._rows.clear();
      return;
    }
    const a = st.attributes;
    this._el.title.textContent = this._config.title || a.stop_name || "Tisséo";
    const live = a.live_lines || [];
    const sub = live.length
      ? `<span class="live"><span class="dot"></span>${t.livelines}: ${tdcEsc(live.join(" · "))}</span>`
      : `<span class="tt"><ha-icon icon="mdi:clock-outline"></ha-icon>${t.nolive}</span>`;
    if (this._el.sub.innerHTML !== sub) this._el.sub.innerHTML = sub;
    const first = (a.upcoming || [])[0];
    this._el.icon.setAttribute("icon", first?.mode === "metro" ? "mdi:subway-variant"
      : first?.mode === "tram" ? "mdi:tram" : "mdi:bus-clock");

    this._stopId = a.stop_id;
    this._renderFilters(a.upcoming || []);
    const deps = this._filter(a.upcoming || []).slice(0, this._config.max);
    const sig = JSON.stringify(deps.map((d) => [d.trip_id, d.expected, d.realtime, d.delay, d.canceled]));
    if (sig !== this._sig) {
      this._sig = sig;
      this._renderRows(deps);
    }
    this._renderAlerts(alerts ? this._hass.states[alerts] : null, deps);
    this._tick();
  }

  _key(d) { return d.trip_id || `${d.line}|${d.scheduled || d.expected}`; }

  _renderRows(deps) {
    const t = this._t, list = this._el.list;
    list.querySelector(".empty")?.remove();
    const keep = new Set();
    deps.forEach((d, i) => {
      const k = this._key(d);
      keep.add(k);
      let row = this._rows.get(k);
      const fresh = !row;
      if (fresh) {
        row = document.createElement("div");
        row.className = "row enter";
        row.style.animationDelay = `${i * 70}ms`;
        row.addEventListener("animationend", (ev) => {
          if (ev.animationName === "tdc-in") row.classList.remove("enter");
        });
        // another animation (e.g. "imminent") can replace tdc-in before it ends
        setTimeout(() => row.classList.remove("enter"), 700 + i * 70);
        this._rows.set(k, row);
      }
      row._d = d;
      row._exp = Date.parse(d.expected);
      row.style.setProperty("--line-color", d.color || "var(--tdc-accent)");
      row.style.setProperty("--line-text", d.text_color || "#fff");
      row.classList.toggle("canceled", !!d.canceled);
      row.classList.toggle("rt", !!d.realtime && !d.canceled);
      row.classList.toggle("late", !!d.realtime && (d.delay ?? 0) >= 60);
      const tap = this._config.trip_dialog !== false && !!d.trip_id;
      row.classList.toggle("tap", tap);
      if (tap) { row.tabIndex = 0; row.setAttribute("role", "button"); }
      const mode = ["metro", "tram"].includes(d.mode) ? d.mode : "bus";
      let status;
      if (d.canceled) status = `<span class="chip cx">${t.canceled}</span>`;
      else if (d.realtime) {
        const dl = d.delay ?? 0, m = Math.round(Math.abs(dl) / 60);
        const chip = Math.abs(dl) < 60 ? `<span class="chip ok">${t.ontime}</span>`
          : dl > 0 ? `<span class="chip late">+${m} ${t.min}</span>`
          : `<span class="chip early">−${m} ${t.min}</span>`;
        status = `<span class="live"><span class="dot"></span>${t.live}</span>${chip}`;
      } else {
        status = `<span class="tt"><ha-icon icon="mdi:clock-outline"></ha-icon>${t.timetable}</span>`;
      }
      const sched = d.scheduled ? new Date(d.scheduled).toLocaleTimeString(this._hass?.locale?.language || undefined,
        { hour: "2-digit", minute: "2-digit" }) : "";
      const html = `<div class="badge ${mode}">${tdcEsc(d.line)}</div>
        <div class="mid"><div class="dest">${tdcEsc(d.destination)}</div>
          <div class="meta">${status}${sched ? `<span>${t.sched} ${sched}</span>` : ""}</div></div>
        <div class="cd"><span class="big"></span><span class="unit"></span><span class="small"></span></div>
        ${this._layout === "board" ? `<div class="binfo">${this._boardInfo(d)}</div>` : ""}
        ${i === 0 ? '<div class="bar"><i></i></div>' : ""}`;
      if (row._html !== html) { row.innerHTML = html; row._html = html; }
      list.appendChild(row); // (re)orders existing rows, appends new ones
    });
    for (const [k, row] of this._rows) {
      if (keep.has(k)) continue;
      this._rows.delete(k);
      row.classList.remove("enter");
      row.classList.add("leave");
      list.insertBefore(row, list.firstChild);
      setTimeout(() => row.remove(), 480);
    }
    if (!deps.length && !list.querySelector(".empty")) {
      const e = document.createElement("div");
      e.className = "empty";
      e.textContent = t.nodep;
      list.appendChild(e);
    }
  }

  _boardInfo(d) {
    const t = this._t;
    if (d.canceled) return `<span class="cx">${t.canceled}</span>`;
    if (!d.realtime) return t.timetable;
    const dl = d.delay ?? 0, m = Math.round(Math.abs(dl) / 60);
    if (Math.abs(dl) < 60) return `<span class="ok">${t.ontime}</span>`;
    return dl > 0 ? `<span class="late">+${m} ${t.min}</span>` : `<span class="ok">−${m} ${t.min}</span>`;
  }

  _fmt(iso) {
    return iso ? new Date(iso).toLocaleTimeString(this._hass?.locale?.language || undefined,
      { hour: "2-digit", minute: "2-digit" }) : "";
  }

  _closeTrip() {
    this._dlg?.remove();
    this._dlg = null;
    if (this._dlgKey) { window.removeEventListener("keydown", this._dlgKey); this._dlgKey = null; }
  }

  async _openTrip(d) {
    this._closeTrip();
    const t = this._t, mode = ["metro", "tram"].includes(d.mode) ? d.mode : "bus";
    const dlg = document.createElement("div");
    dlg.className = "dlg";
    dlg.style.setProperty("--line-color", d.color || "var(--tdc-accent)");
    dlg.style.setProperty("--line-text", d.text_color || "#fff");
    dlg.innerHTML = `<div class="box" role="dialog" aria-modal="true">
        <div class="dh"><div class="badge ${mode}">${tdcEsc(d.line)}</div>
          <div class="t"><div class="h1">→ ${tdcEsc(d.destination)}</div><div class="h2"></div></div>
          <button class="x" aria-label="${t.close}" title="${t.close}">×</button></div>
        <div class="body"><div class="msg">${t.loading}</div></div></div>`;
    dlg.addEventListener("click", (ev) => { if (ev.target === dlg || ev.target.closest(".x")) this._closeTrip(); });
    this._dlgKey = (ev) => { if (ev.key === "Escape") this._closeTrip(); };
    window.addEventListener("keydown", this._dlgKey);
    this.shadowRoot.appendChild(dlg);
    this._dlg = dlg;
    dlg.querySelector(".x").focus();
    let res;
    try {
      const req = { type: "tisseo/trip_stops", trip_id: d.trip_id };
      if (d.stop_id || this._stopId) req.stop_id = d.stop_id || this._stopId;
      if (d.scheduled) req.scheduled = d.scheduled;
      res = await this._hass.callWS(req);
    } catch (err) {
      if (this._dlg === dlg) dlg.querySelector(".body").innerHTML =
        `<div class="msg">${t.tripErr}${err?.message ? `<br><small>${tdcEsc(err.message)}</small>` : ""}</div>`;
      return;
    }
    if (this._dlg !== dlg) return;
    const stops = res.stops || [];
    dlg.querySelector(".h2").textContent = `${stops.length} ${t.stops}` +
      (res.realtime ? ` · ${t.live}` : ` · ${t.timetable}`) + (res.canceled ? ` · ${t.canceled}` : "");
    const items = stops.map((s, i) => {
      const shown = s.expected || s.scheduled;
      const dl = s.delay ?? 0, m = Math.round(Math.abs(dl) / 60);
      const chip = s.skipped ? `<span class="chip cx">${t.skipped}</span>`
        : s.realtime && Math.abs(dl) >= 60 ? `<span class="chip ${dl > 0 ? "late" : "early"}">${dl > 0 ? "+" : "−"}${m}</span>`
        : s.realtime ? '<span class="live"><span class="dot"></span></span>' : "";
      const orig = s.realtime && Math.abs(dl) >= 60 ? `<s>${this._fmt(s.scheduled)}</s>` : "";
      const cls = [s.past ? "past" : "", s.is_selected ? "sel" : "", i === res.next_index ? "next" : "", s.skipped ? "skip" : ""].join(" ");
      return `<li class="${cls}"><span class="tm">${this._fmt(shown)}${orig}</span><span class="rail"></span>` +
        `<span class="nm">${tdcEsc(s.name)}</span><span class="ch">${chip}</span></li>`;
    }).join("");
    dlg.querySelector(".body").innerHTML = stops.length ? `<ol>${items}</ol>` : `<div class="msg">${t.tripErr}</div>`;
    dlg.querySelector("li.sel")?.scrollIntoView({ block: "center" });
  }

  _renderAlerts(st, deps) {
    const tk = this._el.ticker;
    let heads = [];
    if (this._config.show_alerts && st) {
      const lines = new Set(deps.map((d) => d.route_id).filter(Boolean));
      const alerts = st.attributes.alerts || [];
      // line alerts for lines shown first, then the rest
      const score = (al) => (al.lines || []).some((l) => lines.has(l)) ? 0 : al.network_wide ? 2 : 1;
      heads = alerts.slice().sort((x, y) => score(x) - score(y)).map((al) => al.header).filter(Boolean);
      if (!heads.length) heads = st.attributes.headlines || [];
    }
    const sig = heads.join("|");
    if (sig === this._alertSig) return;
    this._alertSig = sig;
    tk.hidden = !heads.length;
    if (!heads.length) return;
    this._el.n.textContent = String(heads.length);
    const text = heads.map(tdcEsc).join("  •  ");
    this._el.track.innerHTML = `<span>${text}</span><span aria-hidden="true">${text}</span>`;
    this._el.track.style.setProperty("--dur", `${Math.max(12, Math.round(text.length * 0.11))}s`);
  }

  _tick() {
    if (!this._built || !this._hass) return;
    const now = Date.now(), t = this._t;
    this._el.clock.textContent = new Date(now).toLocaleTimeString(this._hass?.locale?.language || undefined,
      { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    let idx = 0;
    for (const row of this._el.list.querySelectorAll(".row:not(.leave)")) {
      const rem = Math.round((row._exp - now) / 1000);
      const big = row.querySelector(".big"), unit = row.querySelector(".unit"), small = row.querySelector(".small");
      if (!big) continue;
      let b, u, s;
      if (rem <= 0) { b = t.now; u = ""; s = ""; }
      else if (rem < 3600) {
        const m = Math.floor(rem / 60), sec = rem % 60;
        b = m < 1 ? "<1" : String(m); u = t.min; s = `${m}:${String(sec).padStart(2, "0")}`;
      } else {
        b = new Date(row._exp).toLocaleTimeString(this._hass?.locale?.language || undefined, { hour: "2-digit", minute: "2-digit" });
        u = ""; s = "";
      }
      if (big.textContent !== b) big.textContent = b;
      if (unit.textContent !== u) unit.textContent = u;
      if (small.textContent !== s) small.textContent = s;
      row.classList.toggle("imminent", rem <= 60 && rem > -60 && !row._d?.canceled);
      // departed more than a minute ago: hide until the next sensor refresh drops it
      row.classList.toggle("gone", rem < -60);
      if (rem < -60) continue;
      if (idx === 0) {
        const bar = row.querySelector(".bar > i");
        if (bar) bar.style.width = `${Math.max(2, Math.min(100, (1 - rem / 600) * 100)).toFixed(1)}%`;
      }
      idx++;
    }
  }
}

function tdcSchema(lines) {
  return [
    { name: "entity", required: true, selector: { entity: { domain: "sensor", integration: "tisseo" } } },
    { name: "title", selector: { text: {} } },
    { type: "grid", name: "", schema: [
      { name: "layout", selector: { select: { mode: "dropdown", options: [
        { value: "default", label: "Default" }, { value: "compact", label: "Compact" },
        { value: "board", label: "Departure board" }] } } },
      { name: "max", selector: { number: { min: 1, max: 10, mode: "box" } } },
    ] },
    { type: "grid", name: "", schema: [
      { name: "show_alerts", selector: { boolean: {} } },
      { name: "show_filters", selector: { boolean: {} } },
      { name: "trip_dialog", selector: { boolean: {} } },
    ] },
    { name: "filter_lines", selector: { select: { multiple: true, custom_value: true, mode: "dropdown",
      options: lines.map((l) => ({ value: l, label: l })) } } },
    { name: "filter_destinations", selector: { text: { multiple: true } } },
  ];
}
const TDC_LABELS = {
  en: { entity: "Tisséo departure sensor (any sensor of the stop)", title: "Title", max: "Max departures",
        show_alerts: "Alerts ticker", layout: "Layout", show_filters: "Filter chips in the card",
        trip_dialog: "Tap a row for the trip's stops", filter_lines: "Only these lines",
        filter_destinations: "Destination contains" },
  fr: { entity: "Capteur de départs Tisséo (n'importe quel capteur de l'arrêt)", title: "Titre",
        max: "Nombre de départs", show_alerts: "Bandeau d'alertes", layout: "Disposition",
        show_filters: "Filtres (puces) dans la carte", trip_dialog: "Toucher une ligne : arrêts du trajet",
        filter_lines: "Uniquement ces lignes", filter_destinations: "Destination contient" },
};

class TisseoDeparturesCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _lines() {
    const st = this._hass?.states[this._config?.entity];
    const set = new Set((st?.attributes?.upcoming || []).map((x) => String(x.line)));
    for (const l of this._config?.filter_lines || []) set.add(String(l));
    return [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }
  _render() {
    if (!this._hass || !this._config) return;
    const lang = (this._hass.locale?.language || this._hass.language || "en").slice(0, 2);
    const labels = TDC_LABELS[lang] || TDC_LABELS.en;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        const cfg = { ...this._config, ...ev.detail.value };
        for (const k of ["filter_lines", "filter_destinations"]) {
          if (Array.isArray(cfg[k]) && !cfg[k].filter((x) => x !== "").length) delete cfg[k];
        }
        if (cfg.layout === "default") delete cfg.layout;
        if (cfg.title === "") delete cfg.title;
        this._config = cfg;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg },
          bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.computeLabel = (sch) => labels[sch.name] || sch.name;
    this._form.hass = this._hass;
    this._form.data = { max: 5, show_alerts: true, layout: "default", show_filters: false, trip_dialog: true,
      ...this._config };
    this._form.schema = tdcSchema(this._lines());
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
if (!window.customCards.some((c) => c.type === "tisseo-departures-card")) {
  window.customCards.push({ type: "tisseo-departures-card", name: "Tisséo departures",
    description: "Animated next departures (live countdown, delays, alerts ticker) for a Tisséo stop.",
    preview: true, documentationURL: "https://github.com/your-github-user/tisseo-ha" });
  console.info(`%c TISSEO-DEPARTURES-CARD %c v${TDC_VERSION} `,
    "background:#db001b;color:#fff;font-weight:700", "background:#ffdd00;color:#000");
}

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
 */
const TDC_VERSION = "0.3.0";

const TDC_I18N = {
  en: { now: "now", min: "min", live: "live", timetable: "timetable", ontime: "on time",
        late: "late", early: "early", canceled: "canceled", nodep: "No departures in the next 3 h",
        livelines: "Live", nolive: "timetable only", alerts: "alerts", unavailable: "Entity not found",
        sched: "sched." },
  fr: { now: "à quai", min: "min", live: "temps réel", timetable: "théorique", ontime: "à l'heure",
        late: "retard", early: "avance", canceled: "supprimé", nodep: "Aucun départ dans les 3 h",
        livelines: "Temps réel", nolive: "horaires théoriques", alerts: "alertes",
        unavailable: "Entité introuvable", sched: "prévu" },
};

const TDC_CSS = `
:host { --tdc-accent: var(--primary-color, #03a9f4); --tdc-late: var(--error-color, #db4437);
  --tdc-early: var(--success-color, #43a047); --tdc-muted: var(--secondary-text-color, #727272);
  --tdc-divider: var(--divider-color, rgba(127,127,127,.2)); display:block; }
ha-card { overflow: hidden; position: relative; }
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
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
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
    clearInterval(this._timer);
    this._timer = null;
  }

  getCardSize() { return 2 + Math.min(this._config?.max || 5, 8); }

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
        <div class="list"></div>
        <div class="ticker" hidden>
          <div class="lbl"><ha-icon icon="mdi:alert"></ha-icon><span class="n"></span></div>
          <div class="marquee"><div class="track"></div></div>
        </div>
      </ha-card>`;
    const $ = (s) => this.shadowRoot.querySelector(s);
    this._el = { title: $(".title"), sub: $(".sub"), clock: $(".clock"), list: $(".list"),
                 ticker: $(".ticker"), track: $(".track"), n: $(".ticker .n"), icon: $(".header ha-icon") };
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

    const deps = (a.upcoming || []).slice(0, this._config.max);
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
        this._rows.set(k, row);
      }
      row._d = d;
      row._exp = Date.parse(d.expected);
      row.style.setProperty("--line-color", d.color || "var(--tdc-accent)");
      row.style.setProperty("--line-text", d.text_color || "#fff");
      row.classList.toggle("canceled", !!d.canceled);
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

const TDC_SCHEMA = [
  { name: "entity", required: true, selector: { entity: { domain: "sensor", integration: "tisseo" } } },
  { name: "title", selector: { text: {} } },
  { name: "max", selector: { number: { min: 1, max: 10, mode: "box" } } },
  { name: "show_alerts", selector: { boolean: {} } },
];
const TDC_LABELS = { entity: "Tisséo departure sensor (any sensor of the stop)", title: "Title",
  max: "Max departures", show_alerts: "Show alerts ticker" };

class TisseoDeparturesCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => TDC_LABELS[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this._config = { ...this._config, ...ev.detail.value };
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config },
          bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { max: 5, show_alerts: true, ...this._config };
    this._form.schema = TDC_SCHEMA;
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

// Small SVG chart renderer for the Charts page. No dependencies.
// Charts redraw at their container's width, so text keeps its size on phones.
(function () {
  "use strict";

  const SVG = "http://www.w3.org/2000/svg";
  const BAR_MAX = 24;      // px, bar thickness cap
  const GAP = 2;           // px, surface gap between touching marks
  const RADIUS = 4;        // px, rounded data-end
  const AXIS_W = 52;       // px, room for y tick labels

  const money = (v) =>
    Math.round(v).toLocaleString("sv-SE").replace(/-/g, "−") + " kr";
  const compact = (v) => {
    const a = Math.abs(v);
    const s = a >= 1e6 ? (a / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M"
      : a >= 1e3 ? (a / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "k" : String(Math.round(a));
    return (v < 0 ? "−" : "") + s.replace(".0", "");
  };

  function el(name, attrs, parent) {
    const node = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function text(parent, x, y, value, attrs) {
    const t = el("text", Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = value;
    return t;
  }

  // Round numbers for the value axis, always including zero.
  function ticks(min, max, count) {
    min = Math.min(0, min);
    max = Math.max(0, max);
    if (min === max) max = 1;
    const raw = (max - min) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const out = [];
    for (let v = lo; v <= hi + step / 2; v += step) out.push(Math.round(v * 100) / 100);
    return out;
  }

  // A bar from the baseline (y0) to the data end (y1), rounded only at the data end.
  function barPath(x, w, y0, y1, rounded) {
    const up = y1 < y0;
    const h = Math.abs(y1 - y0);
    const r = rounded ? Math.min(RADIUS, w / 2, h) : 0;
    const top = up ? y1 : y0;
    const bottom = up ? y0 : y1;
    if (up) {
      return `M${x},${bottom}V${top + r}Q${x},${top} ${x + r},${top}H${x + w - r}` +
        `Q${x + w},${top} ${x + w},${top + r}V${bottom}Z`;
    }
    return `M${x},${top}V${bottom - r}Q${x},${bottom} ${x + r},${bottom}H${x + w - r}` +
      `Q${x + w},${bottom} ${x + w},${bottom - r}V${top}Z`;
  }

  // ---- tooltip -----------------------------------------------------------------------

  const tip = document.createElement("div");
  tip.className = "viz-tooltip";
  tip.setAttribute("role", "status");
  tip.hidden = true;
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tip));

  // rows: [{value, label, color, line}] - values lead, labels follow.
  function showTip(title, rows, x, y) {
    tip.replaceChildren();
    const head = document.createElement("div");
    head.className = "viz-tooltip-title";
    head.textContent = title;
    tip.appendChild(head);
    for (const r of rows) {
      const row = document.createElement("div");
      row.className = "viz-tooltip-row";
      if (r.color) {
        const key = document.createElement("span");
        key.className = r.line ? "viz-key-line" : "viz-key";
        key.style.background = r.color;
        row.appendChild(key);
      }
      const value = document.createElement("strong");
      value.textContent = r.value;
      row.appendChild(value);
      const label = document.createElement("span");
      label.textContent = r.label;
      row.appendChild(label);
      tip.appendChild(row);
    }
    tip.hidden = false;
    const pad = 12;
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    let left = x + pad;
    if (left + w > window.innerWidth - 8) left = x - w - pad;
    let top = y - h - pad;
    if (top < 8) top = y + pad;
    tip.style.left = Math.max(8, left) + window.scrollX + "px";
    tip.style.top = top + window.scrollY + "px";
  }

  function hideTip() {
    tip.hidden = true;
  }

  // Hover and keyboard focus show the same tooltip.
  function hoverable(target, onShow, onHide) {
    target.setAttribute("tabindex", "0");
    target.addEventListener("pointermove", (e) => onShow(e.clientX, e.clientY));
    target.addEventListener("pointerleave", () => { hideTip(); onHide && onHide(); });
    target.addEventListener("focus", () => {
      const b = target.getBoundingClientRect();
      onShow(b.left + b.width / 2, b.top);
    });
    target.addEventListener("blur", () => { hideTip(); onHide && onHide(); });
  }

  // Colors stay CSS variables so light/dark switches without a redraw.
  const color = (name) => `var(${name})`;

  // ---- legend --------------------------------------------------------------------------

  function legend(container, items) {
    const box = document.createElement("div");
    box.className = "viz-legend";
    for (const item of items) {
      const entry = document.createElement("span");
      const key = document.createElement("span");
      key.className = item.line ? "viz-key-line" : "viz-key";
      key.style.background = item.color;
      if (item.dashed) key.classList.add("dashed");
      entry.appendChild(key);
      entry.appendChild(document.createTextNode(item.name));
      box.appendChild(entry);
    }
    container.before(box);
  }

  // ---- value axis frame ------------------------------------------------------------------

  function frame(svg, width, height, top, bottom, values, labels) {
    const t = ticks(Math.min(...values), Math.max(...values), 4);
    const lo = t[0];
    const hi = t[t.length - 1];
    const plotH = height - top - bottom;
    const y = (v) => top + (hi - v) / (hi - lo) * plotH;
    const grid = el("g", { class: "viz-grid" }, svg);
    for (const v of t) {
      el("line", { x1: AXIS_W, x2: width, y1: y(v), y2: y(v), class: v === 0 ? "viz-baseline" : "" }, grid);
      text(grid, AXIS_W - 8, y(v) + 4, compact(v), { class: "viz-tick", "text-anchor": "end" });
    }
    const band = (width - AXIS_W) / labels.length;
    // Narrow screens get one-letter months; the tooltip still names the full month.
    const short = band < 32;
    labels.forEach((label, i) => {
      text(grid, AXIS_W + band * i + band / 2, height - 6, short ? label.charAt(0) : label,
        { class: "viz-tick", "text-anchor": "middle" });
    });
    return { y, band, x: (i) => AXIS_W + band * i };
  }

  // ---- column chart (grouped or stacked) ---------------------------------------------------

  function columns(container, opts) {
    const series = opts.series;
    legend(container, series.map((s) => ({ name: s.name, color: color(s.color) })));
    function draw() {
      container.replaceChildren();
      const width = container.clientWidth;
      const height = opts.height || 260;
      const svg = el("svg", { width, height, role: "img", "aria-label": opts.label }, container);
      const n = opts.labels.length;
      let extent = [];
      if (opts.stacked) {
        for (let i = 0; i < n; i++) {
          let pos = 0, neg = 0;
          for (const s of series) (s.values[i] >= 0 ? (pos += s.values[i]) : (neg += s.values[i]));
          extent.push(pos, neg);
        }
      } else {
        extent = series.flatMap((s) => s.values);
      }
      const f = frame(svg, width, height, 10, 26, extent, opts.labels);
      const marks = el("g", {}, svg);
      const groups = [];

      for (let i = 0; i < n; i++) {
        const g = el("g", { class: "viz-column" }, marks);
        groups.push(g);
        if (opts.stacked) {
          const w = Math.min(BAR_MAX, f.band * 0.6);
          const x = f.x(i) + (f.band - w) / 2;
          let pos = 0, neg = 0;
          const pieces = series.map((s) => ({ s, v: s.values[i] })).filter((p) => p.v);
          const lastPos = pieces.filter((p) => p.v > 0).pop();
          const lastNeg = pieces.filter((p) => p.v < 0).pop();
          for (const p of pieces) {
            const start = p.v > 0 ? pos : neg;
            const end = start + p.v;
            if (p.v > 0) pos = end; else neg = end;
            let y0 = f.y(start), y1 = f.y(end);
            // Surface gap between stacked segments, taken from the segment's far end.
            if (Math.abs(y1 - y0) > GAP) y1 += p.v > 0 ? GAP : -GAP;
            el("path", {
              d: barPath(x, w, y0, y1, p === lastPos || p === lastNeg),
              style: `fill:${color(p.s.color)}`,
            }, g);
          }
        } else {
          const k = series.length;
          const w = Math.min(BAR_MAX, (f.band * 0.7 - GAP * (k - 1)) / k);
          const x0 = f.x(i) + (f.band - (w * k + GAP * (k - 1))) / 2;
          series.forEach((s, j) => {
            if (!s.values[i]) return;
            el("path", {
              d: barPath(x0 + j * (w + GAP), w, f.y(0), f.y(s.values[i]), true),
              style: `fill:${color(s.color)}`,
            }, g);
          });
        }
        // The whole month band is the hit target.
        const hit = el("rect", {
          x: f.x(i), y: 0, width: f.band, height: height - 20, class: "viz-hit",
          "aria-label": opts.labels[i],
        }, g);
        hoverable(hit, (cx, cy) => {
          groups.forEach((other) => other.classList.toggle("dim", other !== g));
          const rows = series.filter((s) => s.values[i]).map((s) => ({
            value: money(s.values[i]), label: s.name, color: color(s.color),
          })).reverse();
          if (opts.stacked && rows.length > 1) {
            rows.push({ value: money(series.reduce((a, s) => a + s.values[i], 0)), label: "Total" });
          }
          if (!rows.length) rows.push({ value: money(0), label: "" });
          showTip(`${opts.fullLabels ? opts.fullLabels[i] : opts.labels[i]}`, rows, cx, cy);
        }, () => groups.forEach((other) => other.classList.remove("dim")));
      }
    }
    draw();
    observe(container, draw);
  }

  // ---- horizontal bars ------------------------------------------------------------------------

  function hbars(container, opts) {
    function draw() {
      container.replaceChildren();
      const items = opts.items;
      if (!items.length) return;
      const width = container.clientWidth;
      const row = 30;
      const height = items.length * row + 8;
      const svg = el("svg", { width, height, role: "img", "aria-label": opts.label }, container);
      const labelW = Math.min(170, width * 0.38);
      const valueW = 78;
      const max = Math.max(...items.map((d) => d.value), 0);
      const min = Math.min(...items.map((d) => d.value), 0);
      const span = (max - min) || 1;
      const plot = width - labelW - valueW;
      const x = (v) => labelW + (v - min) / span * plot;
      el("line", { x1: x(0), x2: x(0), y1: 0, y2: height, class: "viz-baseline" }, svg);
      items.forEach((d, i) => {
        const y = i * row + 4;
        const g = el("g", { class: "viz-hbar" + (d.key && d.key === opts.selected ? " selected" : "") }, svg);
        const label = text(g, labelW - 10, y + row / 2 + 4, d.label, { class: "viz-label", "text-anchor": "end" });
        if (d.href) label.classList.add("link");
        const h = Math.min(BAR_MAX - 6, row - 10);
        const top = y + (row - h) / 2;
        const x0 = x(0), x1 = x(d.value);
        if (d.value) {
          const r = Math.min(RADIUS, h / 2, Math.abs(x1 - x0));
          const right = x1 > x0;
          const a = Math.min(x0, x1), b = Math.max(x0, x1);
          const path = right
            ? `M${a},${top}H${b - r}Q${b},${top} ${b},${top + r}V${top + h - r}Q${b},${top + h} ${b - r},${top + h}H${a}Z`
            : `M${b},${top}H${a + r}Q${a},${top} ${a},${top + r}V${top + h - r}Q${a},${top + h} ${a + r},${top + h}H${b}Z`;
          el("path", { d: path, class: "viz-hbar-mark" }, g);
        }
        text(g, Math.max(x0, x1) + 6, y + row / 2 + 4, money(d.value), { class: "viz-value" });
        const hit = el("rect", { x: 0, y, width, height: row, class: "viz-hit", "aria-label": d.label }, g);
        hoverable(hit, (cx, cy) => {
          g.classList.add("hover");
          showTip(d.label, [{ value: money(d.value), label: opts.valueLabel || "" }], cx, cy);
        }, () => g.classList.remove("hover"));
        if (d.href) {
          hit.style.cursor = "pointer";
          hit.addEventListener("click", () => { location.href = d.href; });
          hit.addEventListener("keydown", (e) => { if (e.key === "Enter") location.href = d.href; });
        }
      });
    }
    draw();
    observe(container, draw);
  }

  // ---- line chart with crosshair ------------------------------------------------------------

  function lines(container, opts) {
    const series = opts.series;
    legend(container, series.map((s) => ({ name: s.name, color: color(s.color), line: true })));
    function draw() {
      container.replaceChildren();
      const width = container.clientWidth;
      const height = opts.height || 240;
      const svg = el("svg", { width, height, role: "img", "aria-label": opts.label }, container);
      const f = frame(svg, width, height, 12, 26, series.flatMap((s) => s.values), opts.labels);
      const cx = (i) => f.x(i) + f.band / 2;
      // Draw the context series first, so the main one sits on top.
      for (const s of [...series].reverse()) {
        if (!s.values.length) continue;
        const stroke = color(s.color);
        el("path", {
          d: s.values.map((v, i) => `${i ? "L" : "M"}${cx(i)},${f.y(v)}`).join(""),
          class: "viz-line", style: `stroke:${stroke}`,
        }, svg);
        const last = s.values.length - 1;
        el("circle", { cx: cx(last), cy: f.y(s.values[last]), r: 4, class: "viz-dot", style: `fill:${stroke}` }, svg);
      }
      const cross = el("line", { y1: 8, y2: height - 22, class: "viz-crosshair", visibility: "hidden" }, svg);
      const dots = series.map((s) => el("circle", {
        r: 4, class: "viz-dot", style: `fill:${color(s.color)}`, visibility: "hidden",
      }, svg));
      for (let i = 0; i < opts.labels.length; i++) {
        const hit = el("rect", { x: f.x(i), y: 0, width: f.band, height, class: "viz-hit", "aria-label": opts.labels[i] }, svg);
        hoverable(hit, (px, py) => {
          cross.setAttribute("x1", cx(i));
          cross.setAttribute("x2", cx(i));
          cross.setAttribute("visibility", "visible");
          const rows = [];
          series.forEach((s, j) => {
            const has = i < s.values.length;
            dots[j].setAttribute("visibility", has ? "visible" : "hidden");
            if (!has) return;
            dots[j].setAttribute("cx", cx(i));
            dots[j].setAttribute("cy", f.y(s.values[i]));
            rows.push({ value: money(s.values[i]), label: s.name, color: color(s.color), line: true });
          });
          showTip(opts.fullLabels ? opts.fullLabels[i] : opts.labels[i], rows, px, py);
        }, () => {
          cross.setAttribute("visibility", "hidden");
          dots.forEach((d) => d.setAttribute("visibility", "hidden"));
        });
      }
    }
    draw();
    observe(container, draw);
  }

  function observe(container, draw) {
    let last = container.clientWidth;
    new ResizeObserver(() => {
      if (container.clientWidth !== last) {
        last = container.clientWidth;
        draw();
      }
    }).observe(container);
  }

  window.EconomicsCharts = { columns, hbars, lines };
})();

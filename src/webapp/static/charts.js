// Charts for the Charts page, drawn with Plotly (vendor/plotly-basic.min.js, no CDN).
// Colors come from the CSS variables in style.css, so light and dark mode share one palette;
// the charts are redrawn when the color scheme changes.
(function () {
  "use strict";

  const BAR_MAX = 24;  // px, bar thickness cap
  const CONFIG = { displayModeBar: false, responsive: true, scrollZoom: false, doubleClick: false };
  const charts = [];   // {el, render} - re-rendered on resize and theme change

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const money = (v) =>
    Math.round(v).toLocaleString("sv-SE").replace(/-/g, "−") + " kr";

  function theme() {
    return {
      text: css("--text"), muted: css("--viz-muted"), grid: css("--viz-grid"),
      axis: css("--viz-axis"), surface: css("--surface"), border: css("--border"),
    };
  }

  function layout(t, extra) {
    const font = { family: getComputedStyle(document.body).fontFamily, size: 12, color: t.muted };
    return Object.assign({
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font,
      separators: ", ",  // decimal comma, space between thousands
      margin: { l: 48, r: 12, t: 8, b: 28 },
      dragmode: false,
      hovermode: "x unified",
      hoverlabel: { bgcolor: t.surface, bordercolor: t.border, font: { color: t.text, size: 13 } },
      showlegend: false,
      barcornerradius: 4,
    }, extra);
  }

  function valueAxis(t, extra) {
    return Object.assign({
      fixedrange: true, tickformat: "~s", gridcolor: t.grid, gridwidth: 1,
      zeroline: true, zerolinecolor: t.axis, zerolinewidth: 1, showline: false, ticks: "",
    }, extra);
  }

  // Month axis: the full label ("Jan 2025") goes to the tooltip, the tick shows "Jan", or
  // just "J" when the columns get narrow.
  function monthAxis(t, el, labels, fullLabels) {
    const short = el.clientWidth / labels.length < 34;
    return {
      fixedrange: true, type: "category", showgrid: false, showline: true, linecolor: t.axis,
      ticks: "", tickvals: fullLabels, ticktext: labels.map((l) => (short ? l.charAt(0) : l)),
    };
  }

  function legend(t) {
    return {
      showlegend: true,
      legend: {
        orientation: "h", x: 0, xanchor: "left", y: 1.02, yanchor: "bottom",
        font: { color: t.muted, size: 12 }, itemclick: "toggle", itemdoubleclick: false,
        traceorder: "normal",
      },
    };
  }

  // The legend wraps on narrow screens; give it room instead of squeezing the plot.
  function legendRows(el, names) {
    const perRow = Math.max(1, Math.floor(el.clientWidth / 120));
    return Math.ceil(names.length / perRow);
  }

  // Keep bars at most BAR_MAX px thick, whatever the width.
  function bargap(el, count, perBand) {
    const band = Math.max(1, (el.clientWidth - 60) / count);
    const used = Math.min(BAR_MAX * perBand + 2 * (perBand - 1), band * 0.7);
    return Math.max(0.15, 1 - used / band);
  }

  function draw(el, render) {
    const entry = { el, render };
    charts.push(entry);
    render();
    let width = el.clientWidth;
    new ResizeObserver(() => {
      if (el.clientWidth !== width) {
        width = el.clientWidth;
        render();
      }
    }).observe(el);
    return entry;
  }

  // ---- column chart (grouped or stacked) ---------------------------------------------------

  function columns(el, opts) {
    const x = opts.fullLabels || opts.labels;
    draw(el, () => {
      const t = theme();
      const traces = opts.series.map((s) => ({
        type: "bar", name: s.name, x, y: s.values,
        marker: { color: css(s.color), line: { width: 0 } },
        hovertemplate: "%{y:,.0f} kr",
        meta: s.key || null,
      }));
      if (opts.stacked && opts.series.length > 1) {
        // An invisible trace so the shared tooltip also lists the month's total.
        traces.push({
          type: "scatter", mode: "markers", name: "Total", x, showlegend: false,
          y: x.map((_, i) => opts.series.reduce((sum, s) => sum + s.values[i], 0)),
          marker: { opacity: 0 }, hovertemplate: "<b>%{y:,.0f} kr</b>",
        });
      }
      const perBand = opts.stacked ? 1 : opts.series.length;
      const rows = legendRows(el, opts.series);
      const l = layout(t, Object.assign({
        height: (opts.height || 250) + rows * 22,
        barmode: opts.stacked ? "relative" : "group",
        bargap: bargap(el, x.length, perBand),
        bargroupgap: opts.stacked ? 0 : 0.08,
        xaxis: monthAxis(t, el, opts.labels, x),
        yaxis: valueAxis(t),
        margin: { l: 48, r: 12, t: 14 + rows * 22, b: 28 },
      }, legend(t)));
      Plotly.react(el, traces, l, CONFIG);
    });

    // Legend click hides the category from the charts (for series with a key); other
    // series toggle in place, Plotly's default.
    if (opts.onHide) {
      el.on("plotly_legendclick", (event) => {
        const key = event.data[event.curveNumber].meta;
        if (key) {
          opts.onHide(key);
          return false;
        }
        return true;
      });
    }
  }

  // ---- horizontal bars ------------------------------------------------------------------------

  function hbars(el, opts) {
    const items = opts.items;
    if (!items.length) return;
    draw(el, () => {
      const t = theme();
      const accent = css("--series-1");
      const context = css("--viz-context");
      const trace = {
        type: "bar", orientation: "h",
        y: items.map((d) => d.label), x: items.map((d) => d.value),
        marker: {
          color: items.map((d) => (d.key && d.key === opts.selected ? accent : context)),
          line: { width: 0 },
        },
        text: items.map((d) => money(d.value)), textposition: "outside", cliponaxis: false,
        textfont: { color: t.muted, size: 12 },
        hovertemplate: "%{y}<br><b>%{x:,.0f} kr</b><extra></extra>",
      };
      const row = 30;
      const l = layout(t, {
        height: items.length * row + 16,
        hovermode: "closest",
        bargap: 0.35,
        margin: { l: 8, r: 90, t: 4, b: 4 },
        xaxis: { visible: false, fixedrange: true, zeroline: true, zerolinecolor: t.axis },
        yaxis: {
          fixedrange: true, autorange: "reversed", automargin: true, ticks: "",
          tickfont: { color: t.text, size: 13 }, showgrid: false, ticksuffix: "  ",
        },
      });
      Plotly.react(el, [trace], l, CONFIG);
    });

    if (items.some((d) => d.href)) {
      el.classList.add("clickable");
      el.on("plotly_click", (event) => {
        const item = items[event.points[0].pointIndex];
        if (item && item.href) location.href = item.href;
      });
    }
  }

  // ---- line chart --------------------------------------------------------------------------------

  function lines(el, opts) {
    const x = opts.fullLabels || opts.labels;
    draw(el, () => {
      const t = theme();
      // The context series first, so the main one is drawn on top.
      const traces = [...opts.series].reverse().filter((s) => s.values.length).map((s) => {
        const last = s.values.length - 1;
        return {
          type: "scatter", mode: "lines+markers", name: s.name, x: x.slice(0, s.values.length),
          y: s.values,
          line: { color: css(s.color), width: 2, shape: "linear" },
          // Only the end point gets a marker, ringed in the surface color.
          marker: {
            color: css(s.color), size: s.values.map((_, i) => (i === last ? 9 : 0)),
            line: { color: t.surface, width: 2 },
          },
          hovertemplate: "%{y:,.0f} kr",
        };
      });
      const xaxis = Object.assign(monthAxis(t, el, opts.labels, x), {
        showspikes: true, spikemode: "across", spikesnap: "cursor", spikethickness: 1,
        spikedash: "solid", spikecolor: t.axis,
      });
      const l = layout(t, Object.assign({
        height: opts.height || 250,
        xaxis,
        yaxis: valueAxis(t, { rangemode: "tozero" }),
        margin: { l: 48, r: 16, t: 36, b: 28 },
      }, legend(t)));
      Plotly.react(el, traces, l, CONFIG);
    });
  }

  // Redraw with the other palette when the color scheme changes.
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    charts.forEach((c) => c.render());
  });

  window.EconomicsCharts = { columns, hbars, lines };
})();

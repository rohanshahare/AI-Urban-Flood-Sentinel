// ui.js
// All server text is inserted with textContent (warnings come from a model).

function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    return node;
}

const show = (value, suffix = "") => (value === null || value === undefined ? "n/a" : `${value}${suffix}`);

function badge(label, level) {
    const node = el("span", "badge", label);
    node.style.background = LEVEL_COLORS[level] || NEUTRAL_COLOR;
    return node;
}

function drainSummary(drain) {
    const box = el("div");
    box.append(el("strong", "", drain.drain_id || "(no id)"), el("div", "", `Status: ${drain.processing_status}`),
        el("div", "", `Risk: ${show(drain.risk_level)} (score ${show(drain.flood_risk_score)})`),
        el("div", "", `Blockage: ${show(drain.blockage_percentage, "%")}`));
    if (drain.synthetic) box.append(el("em", "", "SYNTHETIC demo data"));
    return box;
}

function renderList(items, title) {
    const section = el("div", "list");
    section.append(el("h3", "", title));
    const list = el("ul");
    for (const item of items) list.append(el("li", "", item));
    section.append(list);
    return section;
}

function renderResult(result) {
    const out = document.getElementById("result");
    out.replaceChildren();
    if (result.processing_status === "error") return;

    const { vision, risk, rainfall } = result;
    const head = el("div", "result-head");
    if (result.processing_status === "completed") {
        head.append(badge(risk.risk_level, risk.risk_level), el("span", "", ` score ${risk.flood_risk_score}/100`));
    } else {
        head.append(badge("INCONCLUSIVE", null), el("span", "", " manual inspection required"));
    }
    out.append(head);

    const facts = [
        `Blockage detected: ${vision.blockage_detected === null ? "unknown" : vision.blockage_detected ? "yes" : "no"}`,
        `Blockage estimate: ${show(vision.blockage_percentage, "%")} (rough visual estimate)`,
        `Recommendation: ${show(risk.recommendation)}`,
        `Trend: ${risk.trend.direction}${risk.trend.change === null ? "" : ` (${risk.trend.change > 0 ? "+" : ""}${risk.trend.change} from ${risk.trend.previous_score})`}`,
    ];
    if (rainfall) {
        const mm = rainfall.mm_per_day === null ? "not provided" : `${rainfall.mm_per_day} mm/day`;
        facts.push(`Rainfall: ${mm}, category ${show(rainfall.category)} [${rainfall.source}]`);
    }
    out.append(renderList(facts, "Assessment"));
    if (risk.risk_factors.length) out.append(renderList(risk.risk_factors, "Contributing factors"));
    const warnings = [...vision.warnings, ...risk.warnings];
    if (warnings.length) out.append(renderList(warnings, "Warnings"));
}

function renderDrainList(drains) {
    const box = document.getElementById("drain-list");
    box.replaceChildren();
    const table = el("table");
    const header = el("tr");
    header.append(...["Drain", "Status", "Risk", "Score", "Blockage", "Location", "Data"].map((h) => el("th", "", h)));
    table.append(header);
    for (const drain of drains) {
        const row = el("tr");
        row.append(el("td", "", drain.drain_id || "(no id)"), el("td", "", drain.processing_status),
            el("td", "", show(drain.risk_level)), el("td", "", show(drain.flood_risk_score)),
            el("td", "", show(drain.blockage_percentage, "%")),
            el("td", "", hasCoordinates(drain) ? `${drain.lat}, ${drain.lon}` : "no coordinates"),
            el("td", "", drain.synthetic ? "SYNTHETIC" : "analysed"));
        row.addEventListener("click", () => focusDrain(drain));
        table.append(row);
    }
    box.append(table);
}

async function refreshDrains() {
    try {
        state.drains = await fetchDrains();
    } catch (err) {
        document.getElementById("drain-list").textContent = "Could not load drains from the backend.";
        return;
    }
    renderMarkers(state.drains);
    renderDrainList(state.drains);
}

async function onSubmit(event) {
    event.preventDefault();
    if (state.busy) return;
    const button = document.getElementById("submit-btn");
    state.busy = true;
    button.disabled = true;
    button.textContent = "Analysing…";
    state.result = await analyzeDrain(new FormData(event.target));
    renderAlert(state.result);
    renderResult(state.result);
    state.busy = false;
    button.disabled = false;
    button.textContent = "Analyse";
    refreshDrains();
}

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    document.getElementById("analyze-form").addEventListener("submit", onSubmit);
    refreshDrains();
});

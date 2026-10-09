// ui.js — DOM rendering. Every server-provided string goes in via textContent, never innerHTML.
// Colours come only from the CSS risk classes (.risk-LOW … .risk-UNKNOWN) so KPIs, badges,
// queue, alert and map markers can never disagree.
import { RAINFALL_SOURCE_LABEL, inputFlags, inspectionQueue, provenance, riskKey } from './models.js';
import { LABELS } from './map.js';

const $ = (id) => document.getElementById(id);

export function h(tag, className = '', text = '', ...children) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== '' && text !== null && text !== undefined) node.textContent = text;
    node.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
    return node;
}

const riskClass = (level) => `risk-${level ?? 'UNKNOWN'}`;
const TREND = {
    NEW: ['● New', 'first reading for this drain'],
    RISING: ['▲ Rising', null], FALLING: ['▼ Falling', null], STABLE: ['■ Stable', null],
    UNKNOWN: ['Not available', 'needs a drain ID and a scored result'],
};
const CHIP = { real: 'chip-real', synthetic: 'chip-synthetic', assumed: 'chip-assumed' };

function badge(view) {
    const label = view.level ?? (view.status === 'inconclusive' ? 'INCONCLUSIVE' : 'NO RESULT');
    return h('span', `badge ${riskClass(view.level)}`, label);
}

// ── Alert banner ─────────────────────────────────────────────────────────────
// Shown only when `view` is an analysis whose backend alert was triggered. Mock results are prefixed.
const ALERT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/></svg>';

export function showAlert(view, { mock = false } = {}) {
    const el = $('alert-banner');
    if (!view || !view.alert?.triggered) {
        el.className = 'alert-banner hidden';
        el.replaceChildren();
        return;
    }
    const a = view.alert;
    const icon = h('span');
    icon.innerHTML = ALERT_ICON; // static markup only
    el.replaceChildren(icon.firstElementChild, h('div', 'alert-text', '',
        h('strong', '', `${mock ? '[MOCK] ' : ''}${a.title ?? 'Alert'}${view.drainId ? ` · ${view.drainId}` : ''}`),
        h('span', '', ` — ${[a.recommendation, a.message].filter(Boolean).join('. ')}`)));
    el.className = `alert-banner ${riskClass(a.level)}`;
}

// ── KPIs ─────────────────────────────────────────────────────────────────────
const KPI_FIELDS = { total: 'total', critical: 'critical', high: 'high', moderate: 'moderate', low: 'low', needsInspection: 'inconclusive' };
const ATTENTION = ['critical', 'high', 'needsInspection'];

export function updateKPIs(counts, errorMessage = null) {
    for (const [key, id] of Object.entries(KPI_FIELDS)) {
        $(`kpi-${id}`).textContent = counts ? counts[key] : '–';
        $(`kpi-box-${id}`).classList.toggle('is-attention', Boolean(counts && ATTENTION.includes(key) && counts[key] > 0));
    }
    const note = $('kpi-note');
    note.classList.toggle('is-error', !counts);
    note.textContent = counts
        ? `${counts.synthetic} of ${counts.total} records are synthetic demo data. "Needs inspection" = no usable risk level (inconclusive image), counted separately.`
        : (errorMessage ?? 'Drain records unavailable.');
}

// ── Detail panel ─────────────────────────────────────────────────────────────
const PANELS = ['detail-waiting', 'detail-loading', 'detail-error', 'detail-body'];
function showPanel(id) {
    for (const p of PANELS) $(p).classList.toggle('hidden', p !== id);
}

// Bring the details panel into view when a new result or error appears (it sits below the form).
function revealDetails() {
    const panel = $('detail-body').closest('.panel');
    const box = panel.getBoundingClientRect();
    if (box.top >= 0 && box.top < window.innerHeight * 0.35) return;
    // Instant, after layout: smooth scrolling was cut short in testing and hid part of the result.
    setTimeout(() => panel.scrollIntoView({ block: 'start' }), 0);
}
export const showWaiting = () => showPanel('detail-waiting');
export function showLoading(message = 'Working…') {
    $('detail-loading').querySelector('p').textContent = message;
    showPanel('detail-loading');
}

function fact(label, value, note = null, wide = false) {
    return h('div', wide ? 'wide' : '', '', h('dt', '', label), h('dd', '', value, note ? h('small', '', note) : null));
}

function list(title, items) {
    if (!items.length) return null;
    return h('div', 'sublist', '', h('h4', '', title), h('ul', '', '', ...items.map((t) => h('li', '', t))));
}

function rainfallFact(view) {
    if (view.limited) return fact('Rainfall', 'Not in summary record');
    const r = view.rainfall;
    if (!r) return fact('Rainfall', 'Not used', 'no score was calculated');
    const value = r.mm === null ? (r.category ? `${r.category} (assumed)` : 'Not provided') : `${r.mm} mm/day${r.category ? ` · ${r.category}` : ''}`;
    return fact('Rainfall', value, RAINFALL_SOURCE_LABEL[r.source] ?? r.source);
}

function historyFact(view) {
    if (view.limited) return fact('History', 'Not in summary record');
    const hist = view.history;
    if (!hist) return fact('History', 'Not used', 'no score was calculated');
    if (!hist.category) return fact('History', 'Unavailable', 'score uses blockage and rainfall only');
    return fact('History', hist.category, hist.synthetic ? 'synthetic vulnerability data' : null);
}

function trendFact(t) {
    const [text, note] = TREND[t.direction];
    if (t.change === null) return fact('Trend', text, note);
    return fact('Trend', `${text} ${t.change > 0 ? '+' : ''}${t.change}`, `previous score ${t.previous}`);
}

function headline(view) {
    if (view.status === 'completed' && view.score !== null) {
        const fill = h('span');
        fill.style.width = `${view.score}%`;
        return h('div', `score ${riskClass(view.level)}`, '',
            h('div', 'score-row', '', h('span', 'score-num', String(view.score)), h('span', 'score-of', '/ 100 flood-risk score')),
            h('div', 'meter', '', fill),
            h('p', 'score-caption', 'Experimental composite of blockage, rainfall and history. Not a probability of flooding.'));
    }
    if (view.limited) {
        return h('div', 'notice', '', h('strong', '', 'Summary record only'),
            h('p', '', view.level ? 'This record has a level but no stored breakdown.' : 'No usable risk level in this record.'));
    }
    return h('div', 'notice', '',
        h('strong', '', 'Inconclusive: manual inspection required'),
        h('p', '', 'The image could not be assessed reliably. This is not evidence that the drain is clear, and no flood-risk score was calculated.'),
        h('small', '', 'The what-if simulator needs a scored baseline, so it is not offered for this result.'));
}

function placementNote(view) {
    if (view.limited) return null;
    if (!view.drainId) return 'No drain ID was given, so this result is not added to the queue or map.';
    if (!view.location) return 'No coordinates were given, so this drain is in the queue but not on the map.';
    return null;
}

export function renderDetail(view) {
    if (view.status === 'error') return showError(view.error, null);
    const completed = view.status === 'completed';
    const blockageNote = view.synthetic ? 'synthetic value, no image analysed' : 'rough visual estimate, not a measurement';
    const detected = view.blockageDetected === null ? 'Unknown' : view.blockageDetected ? 'Yes' : 'No';
    const warnings = [...view.visionWarnings, ...view.riskWarnings];

    const warningsBlock = warnings.length
        ? h('details', 'warnings', '', h('summary', '', `Warnings and limitations (${warnings.length})`),
            h('ul', '', '', ...warnings.map((w) => h('li', '', w))))
        : null;
    if (warningsBlock && !completed) warningsBlock.open = true; // why it is inconclusive matters most

    const method = view.method ? `Assessed by: ${view.method}` : null;
    const when = view.timestamp && !Number.isNaN(Date.parse(view.timestamp))
        ? ` · ${new Date(view.timestamp).toLocaleString()}` : '';

    $('detail-body').replaceChildren(...[
        h('div', 'result-head', '', h('div', '', '', h('div', 'eyebrow', view.synthetic ? 'Drain · synthetic record' : 'Drain'),
            h('h3', '', view.drainId ?? '(no drain ID)')), badge(view)),
        h('div', 'chips', '', ...provenance(view).map((t) => h('span', `chip ${CHIP[t.tone] ?? 'chip-assumed'}`, t.text))),
        headline(view),
        view.recommendation ? h('div', `callout ${riskClass(view.level)}`, '', h('div', 'eyebrow', 'Recommended action'), h('p', '', view.recommendation)) : null,
        h('dl', 'facts', '',
            fact('Blockage', view.blockage === null ? 'Not available' : `${view.blockage}%`, view.blockage === null ? null : blockageNote),
            fact('Blockage detected', view.limited ? 'Not recorded' : detected),
            rainfallFact(view),
            historyFact(view),
            trendFact(view.trend),
            fact('Alert', view.alert.triggered ? 'Triggered' : 'None', view.alert.triggered ? view.alert.title : null),
            fact('Model confidence', view.confidence === null ? 'Not provided' : String(view.confidence),
                view.confidence === null ? 'the model gives no calibrated confidence' : 'as reported by the backend'),
            fact('Location', view.location ? `${view.location.lat}, ${view.location.lon}` : 'No coordinates', view.location && view.synthetic ? 'synthetic demo location' : null)),
        list('Contributing factors', view.factors),
        warningsBlock,
        placementNote(view) ? h('p', 'footnote', placementNote(view)) : null,
        method ? h('p', 'footnote', `${method}${when}`) : null,
    ].filter(Boolean));
    showPanel('detail-body');
    revealDetails();
}

export function showError(error, onRetry) {
    // An error state never carries an alert or a simulator for a previous result.
    showAlert(null);
    $('sim-panel').classList.add('hidden');
    $('detail-error-code').textContent = error?.code ?? '';
    $('detail-error-message').textContent = error?.message ?? 'An unknown processing error occurred.';
    $('detail-error-retry').classList.toggle('hidden', !onRetry);
    showPanel('detail-error');
    revealDetails();
}

// ── Form ─────────────────────────────────────────────────────────────────────
export function setFormMessage(message) {
    const el = $('form-message');
    el.textContent = message ?? '';
    el.classList.toggle('hidden', !message);
}

// The submit button is enabled only with an image selected and no analysis running.
export function setSubmitState({ busy, hasFile }) {
    const btn = $('submit-btn');
    btn.disabled = busy || !hasFile;
    btn.classList.toggle('is-busy', busy);
    btn.replaceChildren(...(busy ? [h('span', 'spinner'), 'Analysing…'] : ['Run analysis']));
    $('submit-hint').textContent = busy ? 'The local model usually takes 5–20 seconds.' : hasFile ? '' : 'Choose an image to enable analysis.';
}

export function showFile(file, previewUrl) {
    const img = $('image-preview');
    $('dropzone').classList.toggle('has-file', Boolean(file));
    $('dropzone-empty').classList.toggle('hidden', Boolean(file));
    img.classList.toggle('hidden', !file);
    if (file) img.src = previewUrl; else img.removeAttribute('src');
    const meta = $('file-meta');
    meta.classList.toggle('hidden', !file);
    meta.replaceChildren(...(file ? [file.name, h('em', '', ` · ${(file.size / 1024).toFixed(0)} KB · click to change`)] : []));
}

// ── Inspection queue (every drain, including those without coordinates) ──────
const FLAG_CLASS = { 'analysed image': 'flag flag-real', 'synthetic demo record': 'flag flag-warn', 'synthetic history': 'flag flag-warn', 'assumed rainfall': 'flag flag-warn' };

function queueRow(d, onSelect, selectedId) {
    const key = riskKey(d);
    const scored = key !== 'UNKNOWN';
    const row = h('button', `queue-row${d.drainId && d.drainId === selectedId ? ' is-selected' : ''}`, '',
        h('span', `queue-badge ${riskClass(d.level)}`, '', h('b', '', scored ? String(d.score) : '?'), h('span', '', scored ? key : 'INSPECT')),
        h('span', 'queue-main', '',
            h('span', 'queue-id', d.drainId ?? '(no id)'),
            h('span', 'queue-rec', d.recommendation ?? (scored ? '' : 'Manual inspection required')),
            h('span', 'queue-flags', '', ...inputFlags(d).map((f) => h('span', FLAG_CLASS[f] ?? 'flag', f)))));
    row.type = 'button';
    row.setAttribute('aria-label', `${d.drainId ?? 'Drain'}: ${scored ? `${key}, score ${d.score}` : LABELS.UNKNOWN}`);
    row.addEventListener('click', () => onSelect(d));
    return row;
}

export function renderDrainList(drains, onSelect, selectedId) {
    $('drain-ids').replaceChildren(...drains.filter((d) => d.drainId).map((d) => Object.assign(document.createElement('option'), { value: d.drainId })));
    const box = $('drain-list');
    if (!drains.length) return box.replaceChildren(h('p', 'state-empty', 'No drain records.'));
    box.replaceChildren(...inspectionQueue(drains).filter((g) => g.items.length).map((g) => h('div', 'queue-group', '',
        h('div', 'queue-group-head', '', h('h3', '', g.title), h('span', 'queue-count', String(g.items.length))),
        h('p', 'queue-group-note', g.note),
        ...g.items.map((d) => queueRow(d, onSelect, selectedId)))));
}

export function showDrainListError(message, onRetry) {
    const retry = h('button', 'btn btn-secondary', 'Retry');
    retry.type = 'button';
    retry.style.marginTop = '8px';
    retry.addEventListener('click', onRetry);
    $('drain-list').replaceChildren(h('p', 'list-error', message), retry);
}

// ── Health ───────────────────────────────────────────────────────────────────
export function setHealth(state) {
    const labels = { ok: 'Backend connected', down: 'Backend unreachable', mock: 'Mock mode · no backend' };
    $('health-dot').className = `health-dot is-${state}`;
    $('health-label').textContent = labels[state];
}

// ── Simulator ────────────────────────────────────────────────────────────────
export function setupSimulator(baseline) {
    const panel = $('sim-panel');
    $('sim-result').replaceChildren();
    if (!baseline) return panel.classList.add('hidden');
    $('sim-blockage').value = Math.round(baseline.blockage_percentage);
    $('sim-rain').value = Math.round(baseline.rainfall_mm ?? 50);
    syncSimOutputs();
    panel.classList.remove('hidden');
}

export function syncSimOutputs() {
    $('sim-blockage-out').textContent = $('sim-blockage').value;
    $('sim-rain-out').textContent = $('sim-rain').value;
}

export function simValues() {
    return { blockage_percentage: Number($('sim-blockage').value), rainfall_mm: Number($('sim-rain').value) };
}

export function setSimBusy(busy) {
    $('sim-run').disabled = busy;
}

const simInputText = (c) => {
    const label = c.input === 'blockage_percentage' ? 'Blockage' : 'Rainfall';
    const unit = c.input === 'blockage_percentage' ? '%' : ' mm/day';
    const fmt = (v) => (v === null ? 'not provided (assumed default)' : `${v}${unit}`);
    return `${label}: ${fmt(c.from)} → ${fmt(c.to)}`;
};

export function renderSimulation(sim) {
    const side = (title, s, hypo) => h('div', `sim-side ${riskClass(s.level)}${hypo ? ' is-hypo' : ''}`, '',
        h('div', 'eyebrow', title),
        h('span', 'score-num', String(s.score)),
        h('div', '', '', h('span', 'badge', s.level)),
        h('small', '', s.rainfallCategory ? `Rainfall ${s.rainfallCategory}${s.rainfallSource?.startsWith('ASSUMED') ? ' (assumed)' : ''}` : ''));
    const { change } = sim;
    const delta = change.delta === 0 ? 'No score change' : `Score ${change.delta > 0 ? '+' : ''}${change.delta} points`;
    const level = change.levelChanged ? `category ${change.levelFrom} → ${change.levelTo}` : `category unchanged (${change.levelTo})`;
    $('sim-result').replaceChildren(
        h('p', 'sim-label', sim.label),
        h('div', 'sim-compare', '', side('Baseline (real result)', sim.baseline, false), h('span', 'sim-arrow', '→'), side('Hypothetical', sim.scenario, true)),
        h('p', 'sim-summary', `${delta}; ${level}.`),
        h('ul', 'sim-changes', '', ...(change.inputs.length ? change.inputs.map((c) => h('li', '', simInputText(c))) : [h('li', '', 'No input was changed.')])),
        ...(sim.scenario.syntheticHistory ? [h('p', 'footnote', 'Both scores use synthetic historical vulnerability data.')] : []),
    );
    setTimeout(() => $('sim-result').scrollIntoView({ block: 'nearest' }), 0);
}

export function showSimError(error) {
    $('sim-result').replaceChildren(h('p', 'sim-error', error.message));
}

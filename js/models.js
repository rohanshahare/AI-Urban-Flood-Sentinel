// models.js — pure functions (no DOM, no fetch) turning backend JSON into display view models.
//
// Raw backend responses follow docs/api-contract.md. Views are derived for display only and
// never invent values: anything missing stays null, and null is never rendered as 0, LOW or green.

export const LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL'];
const STATUSES = ['completed', 'inconclusive', 'error'];
const TREND_DIRECTIONS = ['NEW', 'RISING', 'FALLING', 'STABLE', 'UNKNOWN'];

export const RAINFALL_SOURCE_LABEL = {
    REQUEST: 'Operator-supplied (no live rainfall feed)',
    ASSUMED_DEFAULT: 'Assumed default: rainfall was not provided',
    SYNTHETIC_DEMO: 'Synthetic demo value',
};

export const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const text = (v) => (typeof v === 'string' && v.trim() ? v : null);
const list = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []);
export const level = (v) => {
    const upper = typeof v === 'string' ? v.toUpperCase() : null;
    return LEVELS.includes(upper) ? upper : null;
};

export function errorView(code, message, drainId = null) {
    return {
        kind: 'analysis', status: 'error', drainId, score: null, level: null, recommendation: null,
        factors: [], blockage: null, blockageDetected: null, confidence: null,
        visionWarnings: [], riskWarnings: [], rainfall: null, history: null,
        trend: { direction: 'UNKNOWN', change: null, previous: null },
        alert: { triggered: false, level: null, title: null, message: null, recommendation: null },
        location: null, synthetic: false, method: null, timestamp: null, limited: false,
        error: { code, message },
    };
}

const invalid = () => errorView('INVALID_RESPONSE', 'The server returned a response the dashboard cannot interpret.');

function coordinates(lat, lon) {
    const [a, b] = [num(lat), num(lon)];
    return a !== null && b !== null ? { lat: a, lon: b } : null;
}

// Full analysis envelope (POST /analyze, GET /drains/{id}, mock fixtures).
export function toAnalysisView(raw) {
    if (!raw || typeof raw !== 'object' || !STATUSES.includes(raw.processing_status)) return invalid();
    const { vision = {}, risk = {}, rainfall = null, alert = {}, drain = {}, error = null } = raw;
    const status = raw.processing_status;
    const score = num(risk?.flood_risk_score);
    const lvl = level(risk?.risk_level);

    if (status === 'completed' && (score === null || lvl === null)) return invalid();
    if (status === 'error') {
        return errorView(text(error?.code) ?? 'ERROR', text(error?.message) ?? 'Processing failed.', text(drain?.drain_id));
    }

    const inputs = risk?.inputs ?? null;
    const trend = risk?.trend ?? {};
    const completed = status === 'completed';
    return {
        kind: 'analysis',
        status,
        drainId: text(drain?.drain_id) ?? text(vision?.drain_id),
        score: completed ? score : null,
        level: completed ? lvl : null,
        recommendation: text(risk?.recommendation),
        factors: list(risk?.risk_factors),
        blockage: num(vision?.blockage_percentage),
        blockageDetected: typeof vision?.blockage_detected === 'boolean' ? vision.blockage_detected : null,
        confidence: num(vision?.confidence),
        visionWarnings: list(vision?.warnings),
        riskWarnings: list(risk?.warnings),
        rainfall: rainfall && typeof rainfall === 'object'
            ? { mm: num(rainfall.mm_per_day), category: text(rainfall.category), source: text(rainfall.source) }
            : null,
        history: inputs
            ? { category: text(inputs.history_category), synthetic: inputs.synthetic_data === true,
                rainfallSource: text(inputs.rainfall_source) }
            : null,
        trend: {
            direction: TREND_DIRECTIONS.includes(trend?.direction) ? trend.direction : 'UNKNOWN',
            change: num(trend?.change),
            previous: num(trend?.previous_score),
        },
        // An alert is shown only when the backend triggered it for a completed assessment.
        alert: {
            triggered: completed && alert?.triggered === true,
            level: level(alert?.level),
            title: text(alert?.title),
            message: text(alert?.message),
            recommendation: text(alert?.recommendation),
        },
        location: coordinates(drain?.lat, drain?.lon),
        synthetic: drain?.synthetic === true,
        method: text(vision?.method),
        timestamp: text(vision?.timestamp),
        limited: false,
        error: null,
    };
}

// GET /drains/{id}: the same envelope, but it must identify the drain that was asked for.
export function toDrainDetailView(raw, requestedId) {
    const view = toAnalysisView(raw);
    if (view.status === 'error') return { ...view, drainId: view.drainId ?? requestedId ?? null };
    if (view.drainId !== requestedId) return { ...invalid(), drainId: requestedId ?? null };
    return view;
}

// A mock fixture: parsed like an envelope, then forced to read as synthetic mock data, so a fixture
// can never be displayed as a real analysis even if its own flags were wrong.
export function toMockFixtureView(raw) {
    const view = toAnalysisView(raw);
    if (view.status === 'error') return { ...view, mock: true };
    const rainfall = view.rainfall ? { ...view.rainfall, source: 'SYNTHETIC_DEMO' } : null; // fixture inputs are invented
    return { ...view, mock: true, synthetic: true, rainfall };
}

// One item of GET /drains: a summary record, not an analysis envelope.
export function toDrainView(record) {
    if (!record || typeof record !== 'object') return null;
    const status = STATUSES.includes(record.processing_status) ? record.processing_status : 'unknown';
    const lvl = level(record.risk_level);
    const score = num(record.flood_risk_score);
    const scored = status === 'completed' && lvl !== null && score !== null;
    return {
        kind: 'drain',
        drainId: text(record.drain_id),
        status,
        level: scored ? lvl : null,
        score: scored ? score : null,
        blockage: num(record.blockage_percentage),
        location: coordinates(record.lat, record.lon),
        synthetic: record.synthetic === true,
        recommendation: text(record.recommendation),
        rainfallSource: text(record.rainfall_source),
        syntheticHistory: typeof record.synthetic_history === 'boolean' ? record.synthetic_history : null,
    };
}

export function toDrainViews(records) {
    if (!Array.isArray(records)) return null;
    return records.map(toDrainView).filter(Boolean);
}

// Single source of truth for marker colour and KPI bucket: a drain is either scored
// (its backend level) or "UNKNOWN" (needs inspection). Never derived from a score.
export const riskKey = (view) => view.level ?? 'UNKNOWN';

export function kpiCounts(drains) {
    const counts = { total: drains.length, critical: 0, high: 0, moderate: 0, low: 0, needsInspection: 0, synthetic: 0 };
    for (const d of drains) {
        if (d.synthetic) counts.synthetic++;
        const key = riskKey(d);
        if (key === 'UNKNOWN') counts.needsInspection++;
        else counts[key.toLowerCase()]++;
    }
    return counts;
}

// Inspection queue: ordering only. Groups follow the backend risk level exactly; nothing is re-scored.
// Unknown risk (inconclusive) sits above MODERATE/LOW so it is not buried under known lower risks.
export const QUEUE_GROUPS = [
    { key: 'act', title: 'Act first', note: 'CRITICAL and HIGH, highest score first', levels: ['CRITICAL', 'HIGH'] },
    { key: 'inspect', title: 'Needs manual inspection', note: 'No usable risk level: the image could not be assessed', levels: ['UNKNOWN'] },
    { key: 'schedule', title: 'Schedule', note: 'MODERATE', levels: ['MODERATE'] },
    { key: 'routine', title: 'Routine', note: 'LOW', levels: ['LOW'] },
];

export function inspectionQueue(drains) {
    const order = (a, b) => (b.score ?? -1) - (a.score ?? -1) || String(a.drainId).localeCompare(String(b.drainId));
    return QUEUE_GROUPS.map((g) => ({ ...g, items: drains.filter((d) => g.levels.includes(riskKey(d))).sort(order) }));
}

// Short flags that say what a drain's level rests on (shown in the queue).
export function inputFlags(d) {
    const flags = [d.synthetic ? 'synthetic demo record' : 'analysed image'];
    if (d.rainfallSource === 'ASSUMED_DEFAULT') flags.push('assumed rainfall');
    if (d.syntheticHistory) flags.push('synthetic history');
    if (!d.location) flags.push('no coordinates');
    return flags;
}

// Drain summary -> a limited detail view, used when no full envelope exists (mock mode).
export function drainToLimitedView(d) {
    const view = errorView(null, null, d.drainId);
    return {
        ...view, status: d.status === 'completed' ? 'completed' : 'inconclusive', error: null,
        score: d.score, level: d.level, blockage: d.blockage, location: d.location, synthetic: d.synthetic,
        limited: true,
        recommendation: d.recommendation ?? (d.level ? null : 'Manual inspection required.'),
    };
}

const scenarioSide = (s) => (s && num(s.flood_risk_score) !== null && level(s.risk_level)
    ? {
        score: s.flood_risk_score, level: s.risk_level, factors: list(s.risk_factors),
        warnings: list(s.warnings), recommendation: text(s.recommendation),
        rainfallCategory: text(s.inputs?.rainfall_category), rainfallSource: text(s.inputs?.rainfall_source),
        syntheticHistory: s.inputs?.synthetic_data === true,
    }
    : null);

// POST /simulate. Returns null for anything that is not a well-formed simulation.
export function toSimulationView(raw) {
    if (!raw || raw.simulation !== true) return null;
    const baseline = scenarioSide(raw.baseline);
    const scenario = scenarioSide(raw.scenario);
    const c = raw.change;
    if (!baseline || !scenario || !c || num(c.score_delta) === null) return null;
    return {
        label: text(raw.label) ?? 'HYPOTHETICAL SIMULATION',
        drainId: text(raw.drain_id),
        baseline,
        scenario,
        change: {
            delta: c.score_delta,
            levelFrom: c.level_from,
            levelTo: c.level_to,
            levelChanged: c.level_changed === true,
            inputs: Array.isArray(c.changed_inputs) ? c.changed_inputs : [],
        },
    };
}

// Provenance badges shown next to a result: what is real, synthetic or assumed.
export function provenance(view) {
    const tags = [];
    if (view.mock) tags.push({ text: 'Mock fixture: not a real analysis', tone: 'synthetic' });
    else if (view.synthetic) tags.push({ text: 'Synthetic demo record', tone: 'synthetic' });
    else if (view.method && /ollama|vision model/i.test(view.method)) tags.push({ text: 'Real image analysis (local model)', tone: 'real' });
    if (view.history?.synthetic) tags.push({ text: 'Synthetic historical data', tone: 'synthetic' });
    if (view.rainfall?.source === 'SYNTHETIC_DEMO') tags.push({ text: RAINFALL_SOURCE_LABEL.SYNTHETIC_DEMO, tone: 'synthetic' });
    else if (view.rainfall?.source && view.rainfall.source !== 'REQUEST') tags.push({ text: RAINFALL_SOURCE_LABEL[view.rainfall.source] ?? view.rainfall.source, tone: 'assumed' });
    return tags;
}

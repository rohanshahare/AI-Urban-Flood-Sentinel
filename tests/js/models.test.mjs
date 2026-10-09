import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
    drainToLimitedView, inputFlags, toDrainDetailView, toMockFixtureView, inspectionQueue, kpiCounts, provenance, riskKey, toAnalysisView, toDrainView, toDrainViews, toSimulationView,
} from '../../js/models.js';

const fixture = (name) => JSON.parse(readFileSync(new URL(`../../mock/${name}.json`, import.meta.url), 'utf8'));

test('completed envelope maps every important field', () => {
    const v = toAnalysisView(fixture('completed-critical'));
    assert.equal(v.status, 'completed');
    assert.equal(v.drainId, 'D-001');
    assert.equal(v.score, 94);
    assert.equal(v.level, 'CRITICAL');
    assert.equal(v.blockage, 90);
    assert.equal(v.confidence, null); // never invented
    assert.equal(v.factors.length, 3);
    assert.deepEqual(v.rainfall, { mm: 150, category: 'VERY_HEAVY', source: 'REQUEST' });
    assert.equal(v.history.synthetic, true);
    assert.equal(v.trend.direction, 'NEW');
    assert.equal(v.alert.triggered, true);
    assert.deepEqual(v.location, { lat: 12.975, lon: 77.59 });
    assert.equal(v.synthetic, true);
    assert.ok(v.visionWarnings.length > 0 && v.riskWarnings.length > 0);
});

test('inconclusive envelope keeps null score/level and never raises an alert', () => {
    const v = toAnalysisView(fixture('inconclusive'));
    assert.equal(v.status, 'inconclusive');
    assert.equal(v.score, null);
    assert.equal(v.level, null);
    assert.equal(v.blockage, null);
    assert.equal(v.blockageDetected, null);
    assert.equal(v.alert.triggered, false);
    assert.match(v.recommendation, /Manual inspection/);
    assert.ok(v.visionWarnings.some((w) => /not clearly visible/.test(w)));
});

test('an inconclusive result cannot display an alert even if the payload claims one', () => {
    const raw = fixture('inconclusive');
    raw.alert.triggered = true;
    assert.equal(toAnalysisView(raw).alert.triggered, false);
});

test('error envelope keeps the structured error and drops nothing into a fake result', () => {
    const v = toAnalysisView(fixture('error'));
    assert.equal(v.status, 'error');
    assert.equal(v.error.code, 'VISION_SERVICE_ERROR');
    assert.match(v.error.message, /unavailable/);
    assert.equal(v.score, null);
    assert.equal(v.level, null);
});

test('malformed responses become an explicit error, not a result', () => {
    for (const bad of [null, undefined, 'x', {}, { processing_status: 'weird' }]) {
        const v = toAnalysisView(bad);
        assert.equal(v.status, 'error');
        assert.equal(v.error.code, 'INVALID_RESPONSE');
    }
});

test('a "completed" response without a usable score or level is rejected, never shown as 0 or LOW', () => {
    for (const risk of [{}, { flood_risk_score: null, risk_level: null }, { flood_risk_score: 50 }, { risk_level: 'LOW' },
        { flood_risk_score: 50, risk_level: 'SAFE' }]) {
        assert.equal(toAnalysisView({ processing_status: 'completed', risk }).error.code, 'INVALID_RESPONSE');
    }
});

test('missing optional fields stay null; coordinates of 0 are real, absent ones are not', () => {
    const v = toAnalysisView({ processing_status: 'inconclusive' });
    assert.equal(v.location, null);
    assert.equal(v.rainfall, null);
    assert.equal(v.confidence, null);
    assert.equal(v.trend.direction, 'UNKNOWN');
    const equator = toAnalysisView({ ...fixture('completed-low'), drain: { drain_id: 'Z', lat: 0, lon: 0, synthetic: false } });
    assert.deepEqual(equator.location, { lat: 0, lon: 0 });
    const half = toAnalysisView({ ...fixture('completed-low'), drain: { drain_id: 'Z', lat: 12, lon: null } });
    assert.equal(half.location, null);
});

test('a real confidence value is passed through when the backend provides one', () => {
    const raw = fixture('completed-low');
    raw.vision.confidence = 0.8;
    assert.equal(toAnalysisView(raw).confidence, 0.8);
});

test('drain record normalizer is strict about coordinates, status and level', () => {
    const ok = toDrainView({ drain_id: 'D-1', lat: 12.9, lon: 77.5, processing_status: 'completed', risk_level: 'high', flood_risk_score: 60, blockage_percentage: 55, synthetic: true });
    assert.deepEqual([ok.level, ok.score, ok.synthetic, ok.location], ['HIGH', 60, true, { lat: 12.9, lon: 77.5 }]);

    const stringy = toDrainView({ drain_id: 'D-2', lat: '12.9', lon: '77.5', processing_status: 'completed', risk_level: 'LOW', flood_risk_score: 10 });
    assert.equal(stringy.location, null, 'string coordinates are not trusted');

    const legacy = toDrainView({ drain_id: 'D-3', location: { lat: 1, lng: 2 }, processing_status: 'completed', result: { score: 0.9, level: 'critical' } });
    assert.equal(legacy.level, null, 'legacy result.level is not a drain record field');
    assert.equal(riskKey(legacy), 'UNKNOWN');

    const noScore = toDrainView({ drain_id: 'D-4', processing_status: 'completed', risk_level: 'LOW', flood_risk_score: null });
    assert.equal(riskKey(noScore), 'UNKNOWN', 'a level without a score is not trusted');

    const inc = toDrainView({ drain_id: 'D-5', lat: 1, lon: 2, processing_status: 'inconclusive', risk_level: 'LOW', flood_risk_score: 5 });
    assert.equal(inc.level, null, 'inconclusive never carries a level');
    assert.equal(toDrainViews('nope'), null);
});

test('KPIs are computed from the drain records and keep inconclusive separate', () => {
    const drains = toDrainViews(fixture('drains'));
    const tally = { critical: 0, high: 0, moderate: 0, low: 0, needsInspection: 0 };
    for (const r of fixture('drains')) {
        if (r.processing_status === 'completed') tally[r.risk_level.toLowerCase()]++; else tally.needsInspection++;
    }
    const counts = kpiCounts(drains);
    assert.deepEqual({ ...counts, total: undefined, synthetic: undefined }, { ...tally, total: undefined, synthetic: undefined });
    assert.equal(counts.total, fixture('drains').length);
    assert.equal(counts.synthetic, counts.total);
    assert.ok(counts.needsInspection >= 1);
    assert.equal(counts.critical + counts.high + counts.moderate + counts.low + counts.needsInspection, counts.total);
});

test('summary-only drains give a limited view that never invents analysis details', () => {
    const v = drainToLimitedView(toDrainViews(fixture('drains'))[0]);
    assert.equal(v.limited, true);
    assert.equal(v.error, null);
    assert.equal(v.confidence, null);
    assert.equal(v.rainfall, null);
    const inc = drainToLimitedView(toDrainViews(fixture('drains')).find((d) => d.status === 'inconclusive'));
    assert.equal(inc.score, null);
    assert.equal(inc.level, null);
});

test('simulation response is validated', () => {
    const side = (score, level) => ({ flood_risk_score: score, risk_level: level, risk_factors: [], warnings: [], inputs: { rainfall_category: 'HEAVY', rainfall_source: 'PROVIDED', synthetic_data: true } });
    const raw = { simulation: true, label: 'HYPOTHETICAL SIMULATION', drain_id: 'D-1', baseline: side(50, 'MODERATE'), scenario: side(70, 'HIGH'),
        change: { score_delta: 20, level_from: 'MODERATE', level_to: 'HIGH', level_changed: true, changed_inputs: [{ input: 'rainfall', from: 10, to: 90 }] } };
    const v = toSimulationView(raw);
    assert.equal(v.change.delta, 20);
    assert.equal(v.change.levelChanged, true);
    assert.equal(v.scenario.syntheticHistory, true);
    assert.equal(toSimulationView({ ...raw, simulation: false }), null);
    assert.equal(toSimulationView({ ...raw, scenario: { flood_risk_score: null, risk_level: null } }), null);
    assert.equal(toSimulationView(null), null);
});

test('provenance distinguishes synthetic, real and assumed inputs', () => {
    const synthetic = provenance(toAnalysisView(fixture('completed-critical')));
    assert.ok(synthetic.some((t) => /Synthetic demo record/.test(t.text)));
    assert.ok(synthetic.some((t) => /Synthetic historical/.test(t.text)));

    const real = fixture('completed-low');
    real.drain.synthetic = false;
    real.vision.method = 'Local Ollama multimodal model (gemma3:12b); qualitative visual assessment';
    real.rainfall.source = 'ASSUMED_DEFAULT';
    const tags = provenance(toAnalysisView(real)).map((t) => t.text).join('|');
    assert.match(tags, /Real image analysis/);
    assert.match(tags, /Assumed default/);
    assert.doesNotMatch(tags, /Synthetic demo record/);
});

test('inspection queue groups by backend level only and never re-scores', () => {
    const rec = (id, status, level, score, extra = {}) => toDrainView({ drain_id: id, processing_status: status, risk_level: level, flood_risk_score: score, lat: 1, lon: 2, ...extra });
    const drains = [rec('A', 'completed', 'LOW', 10), rec('B', 'completed', 'HIGH', 60), rec('C', 'completed', 'CRITICAL', 90),
        rec('D', 'inconclusive', null, null), rec('E', 'completed', 'MODERATE', 40), rec('F', 'completed', 'HIGH', 70)];
    const groups = Object.fromEntries(inspectionQueue(drains).map((g) => [g.key, g.items.map((d) => d.drainId)]));
    assert.deepEqual(groups, { act: ['C', 'F', 'B'], inspect: ['D'], schedule: ['E'], routine: ['A'] });
    assert.deepEqual(inspectionQueue(drains).map((g) => g.key), ['act', 'inspect', 'schedule', 'routine']);
    const total = inspectionQueue(drains).reduce((n, g) => n + g.items.length, 0);
    assert.equal(total, drains.length, 'every drain appears exactly once');
    for (const g of inspectionQueue(drains)) for (const d of g.items) assert.equal(d, drains.find((x) => x.drainId === d.drainId));
});

test('queue flags show what a level rests on', () => {
    const d = toDrainView({ drain_id: 'X', processing_status: 'completed', risk_level: 'HIGH', flood_risk_score: 60, synthetic: false,
        rainfall_source: 'ASSUMED_DEFAULT', synthetic_history: true, recommendation: 'Priority cleaning within 24 hours' });
    assert.equal(d.recommendation, 'Priority cleaning within 24 hours');
    assert.deepEqual(inputFlags(d), ['analysed image', 'assumed rainfall', 'synthetic history', 'no coordinates']);
    const demo = toDrainViews(fixture('drains')).find((x) => x.drainId === 'D-001');
    assert.deepEqual(inputFlags(demo), ['synthetic demo record', 'synthetic history']);
    assert.equal(toDrainView({ drain_id: 'Y', processing_status: 'completed', synthetic_history: 'yes' }).syntheticHistory, null);
});

test('detail and mock-fixture normalizers', () => {
    const env = fixture('completed-critical');
    assert.equal(toDrainDetailView(env, 'D-001').score, 94);
    assert.equal(toDrainDetailView(env, 'D-002').error.code, 'INVALID_RESPONSE');
    assert.equal(toDrainDetailView(fixture('error'), 'D-ERR').status, 'error');
    const mock = toMockFixtureView(fixture('inconclusive'));
    assert.deepEqual([mock.mock, mock.synthetic, mock.score, mock.level], [true, true, null, null]);
    assert.equal(provenance(mock)[0].text, 'Mock fixture: not a real analysis');
    assert.equal(provenance(mock)[0].tone, 'synthetic');
    const critical = toMockFixtureView(fixture('completed-critical'));
    assert.equal(critical.rainfall.source, 'SYNTHETIC_DEMO', 'fixture rainfall is never shown as operator-supplied');
    assert.equal(critical.score, 94);
});

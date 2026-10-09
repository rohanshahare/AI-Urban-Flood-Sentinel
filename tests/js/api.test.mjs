import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import * as config from '../../js/config.js';
import { createClient } from '../../js/api.js';
import { validateSubmission } from '../../js/validate.js';

const fixture = (name) => JSON.parse(readFileSync(new URL(`../../mock/${name}.json`, import.meta.url), 'utf8'));
const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

// A fetch stub that records URLs and honours AbortSignal like the real one.
function stub(handler) {
    const calls = [];
    const fetchImpl = (url, init = {}) => {
        calls.push({ url, init });
        return new Promise((resolve, reject) => {
            init.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
            Promise.resolve().then(() => handler(url, init)).then(resolve, reject);
        });
    };
    return { calls, fetchImpl };
}

test('defaults: real backend mode, relative base, no placeholder endpoint', () => {
    assert.equal(config.USE_MOCK, false);
    assert.equal(config.API_BASE, '');
    assert.doesNotMatch(readFileSync(new URL('../../js/config.js', import.meta.url), 'utf8'), /example\.com/);
});

test('real mode posts to /analyze and never reads mock fixtures', async () => {
    const { calls, fetchImpl } = stub(() => json(fixture('completed-critical')));
    const view = await createClient({ mock: false, fetchImpl }).analyze(new FormData());
    assert.equal(view.status, 'completed');
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/analyze');
    assert.equal(calls[0].init.method, 'POST');
    assert.ok(calls.every((c) => !c.url.includes('/mock/')));
});

test('a failed real request is an error result, with no fallback to fabricated data', async () => {
    const { calls, fetchImpl } = stub(() => { throw new TypeError('fetch failed'); });
    const view = await createClient({ mock: false, fetchImpl }).analyze(new FormData());
    assert.equal(view.status, 'error');
    assert.equal(view.error.code, 'NETWORK_ERROR');
    assert.equal(view.score, null);
    assert.equal(calls.length, 1);
});

test('backend error envelopes keep their code and safe message', async () => {
    const env = { processing_status: 'error', error: { code: 'VISION_SERVICE_ERROR', message: 'The vision service is unavailable.' }, risk: {}, vision: {}, alert: {}, drain: {} };
    const view = await createClient({ fetchImpl: stub(() => json(env, 502)).fetchImpl }).analyze(new FormData());
    assert.equal(view.status, 'error');
    assert.equal(view.error.code, 'VISION_SERVICE_ERROR');
    assert.equal(view.error.message, 'The vision service is unavailable.');
});

test('invalid JSON, non-envelope HTTP errors and timeouts are reported without internals', async () => {
    const bad = { ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token < in JSON'); } };
    let v = await createClient({ fetchImpl: stub(() => bad).fetchImpl }).analyze(new FormData());
    assert.equal(v.error.code, 'INVALID_RESPONSE');
    assert.doesNotMatch(v.error.message, /token/i);

    v = await createClient({ fetchImpl: stub(() => json({ detail: 'Traceback (most recent call last)' }, 500)).fetchImpl }).analyze(new FormData());
    assert.equal(v.error.code, 'HTTP_500');
    assert.doesNotMatch(v.error.message, /Traceback/);

    v = await createClient({ fetchImpl: stub(() => new Promise(() => {})).fetchImpl, analyzeTimeoutMs: 20 }).analyze(new FormData());
    assert.equal(v.error.code, 'TIMEOUT');
});

test('a 200 response in an unknown shape is an error, not a result', async () => {
    const v = await createClient({ fetchImpl: stub(() => json({ result: { score: 0.9, level: 'critical' } })).fetchImpl }).analyze(new FormData());
    assert.equal(v.status, 'error');
});

test('mock mode reads fixtures explicitly; unknown fixtures are rejected', async () => {
    const { calls, fetchImpl } = stub((url) => json(fixture(url.match(/mock\/(.+)\.json/)[1])));
    const client = createClient({ mock: true, fetchImpl });
    assert.equal((await client.analyze(null, { fixture: 'inconclusive' })).status, 'inconclusive');
    assert.equal((await client.analyze(null, { fixture: 'error' })).status, 'error');
    assert.equal((await client.analyze(null, { fixture: '../secret' })).error.code, 'MOCK_ERROR');
    assert.deepEqual(calls.map((c) => c.url), ['/mock/inconclusive.json', '/mock/error.json']);
    assert.equal((await client.getDrains()).drains.length, fixture('drains').length);
});

test('getDrains validates the list and surfaces failures', async () => {
    const ok = await createClient({ fetchImpl: stub(() => json(fixture('drains'))).fetchImpl }).getDrains();
    assert.equal(ok.drains.length, fixture('drains').length);
    assert.equal((await createClient({ fetchImpl: stub(() => json({ not: 'a list' })).fetchImpl }).getDrains()).error.code, 'INVALID_RESPONSE');
    assert.equal((await createClient({ fetchImpl: stub(() => json({}, 500)).fetchImpl }).getDrains()).error.code, 'HTTP_500');
    assert.equal((await createClient({ fetchImpl: stub(() => { throw new Error('down'); }).fetchImpl }).getDrains()).error.code, 'NETWORK_ERROR');
});

test('drain detail requests the escaped id and falls back to a limited view only in mock mode', async () => {
    const env = fixture('completed-low');
    env.drain.drain_id = 'D 1/x';
    const { calls, fetchImpl } = stub(() => json(env));
    const view = await createClient({ fetchImpl }).getDrainDetail({ drainId: 'D 1/x' });
    assert.equal(view.status, 'completed');
    assert.equal(calls[0].url, '/drains/D%201%2Fx');
    const limited = await createClient({ mock: true, fetchImpl }).getDrainDetail({ drainId: 'D-1', status: 'completed', level: 'LOW', score: 9, location: null, synthetic: true });
    assert.equal(limited.limited, true);
    assert.equal(limited.mock, true);
    const failed = await createClient({ fetchImpl: stub(() => { throw new Error('x'); }).fetchImpl }).getDrainDetail({ drainId: 'D-1' });
    assert.equal(failed.status, 'error');
});

test('simulate posts JSON, parses the response and reports errors', async () => {
    const side = (s, l) => ({ flood_risk_score: s, risk_level: l, risk_factors: [], warnings: [], inputs: {} });
    const raw = { simulation: true, label: 'HYPOTHETICAL', baseline: side(40, 'MODERATE'), scenario: side(80, 'CRITICAL'), change: { score_delta: 40, level_from: 'MODERATE', level_to: 'CRITICAL', level_changed: true, changed_inputs: [] } };
    const { calls, fetchImpl } = stub(() => json(raw));
    const res = await createClient({ fetchImpl }).simulate({ a: 1 });
    assert.equal(res.simulation.change.delta, 40);
    assert.equal(calls[0].url, '/simulate');
    assert.equal(calls[0].init.headers['Content-Type'], 'application/json');

    const err = { processing_status: 'error', error: { code: 'INVALID_INPUT', message: 'scenario.blockage_percentage must be between 0 and 100.' } };
    assert.match((await createClient({ fetchImpl: stub(() => json(err, 400)).fetchImpl }).simulate({})).error.message, /between 0 and 100/);
    assert.equal((await createClient({ mock: true, fetchImpl }).simulate({})).error.code, 'MOCK_MODE');
});

test('health check requires the real backend to answer ok', async () => {
    assert.equal(await createClient({ fetchImpl: stub(() => json({ status: 'ok' })).fetchImpl }).checkHealth(), true);
    assert.equal(await createClient({ fetchImpl: stub(() => json({ status: 'bad' })).fetchImpl }).checkHealth(), false);
    assert.equal(await createClient({ fetchImpl: stub(() => { throw new Error('x'); }).fetchImpl }).checkHealth(), false);
    assert.equal(await createClient({ mock: true }).checkHealth(), false);
});

test('form validation mirrors backend rules', () => {
    const file = { type: 'image/jpeg', size: 1000 };
    assert.match(validateSubmission({}).error, /Choose an image/);
    assert.match(validateSubmission({ file: { type: 'text/plain', size: 5 } }).error, /not an image/);
    assert.match(validateSubmission({ file: { type: 'image/heic', size: 5 } }).error, /Unsupported image format/);
    for (const type of ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp']) assert.ok(validateSubmission({ file: { type, size: 5 } }).fields, type);
    assert.match(validateSubmission({ file: { type: 'image/png', size: 0 } }).error, /empty/);
    assert.match(validateSubmission({ file: { type: 'image/png', size: config.MAX_IMAGE_BYTES + 1 } }).error, /larger than/);
    assert.match(validateSubmission({ file, drainId: 'bad id' }).error, /Drain ID/);
    assert.match(validateSubmission({ file, lat: '12' }).error, /both/);
    assert.match(validateSubmission({ file, lat: '91', lon: '0' }).error, /Latitude/);
    assert.match(validateSubmission({ file, lat: '0', lon: 'abc' }).error, /Longitude/);
    assert.match(validateSubmission({ file, rainfall: '-1' }).error, /Rainfall/);
    assert.match(validateSubmission({ file, rainfall: 'x' }).error, /Rainfall/);
    assert.deepEqual(validateSubmission({ file, drainId: ' D-1 ', lat: '0', lon: '0', rainfall: '0' }).fields,
        { drain_id: 'D-1', lat: '0', lon: '0', rainfall_mm: '0' });
    assert.deepEqual(validateSubmission({ file }).fields, {});
});

test('a detail response for a different drain is rejected, not shown under the wrong ID', async () => {
    const view = await createClient({ fetchImpl: stub(() => json(fixture('completed-low'))).fetchImpl }).getDrainDetail({ drainId: 'D-999' });
    assert.equal(view.status, 'error');
    assert.equal(view.error.code, 'INVALID_RESPONSE');
    assert.equal(view.drainId, 'D-999');
});

test('mock fixtures are always marked as synthetic mock data', async () => {
    const real = fixture('completed-critical');
    real.drain.synthetic = false; // even a fixture with a wrong flag cannot pass as real
    const view = await createClient({ mock: true, fetchImpl: stub(() => json(real)).fetchImpl }).analyze(null, { fixture: 'completed-critical' });
    assert.equal(view.mock, true);
    assert.equal(view.synthetic, true);
    const realView = await createClient({ fetchImpl: stub(() => json(real)).fetchImpl }).analyze(new FormData());
    assert.equal(realView.mock, undefined);
});

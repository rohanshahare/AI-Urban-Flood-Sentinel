// api.js — backend client. Real mode never touches mock files, and a failed real request
// always yields an error result: it never falls back to fabricated data.
import * as config from './config.js';
import { drainToLimitedView, errorView, toAnalysisView, toDrainDetailView, toDrainViews, toMockFixtureView, toSimulationView } from './models.js';

const MOCK_FIXTURES = ['completed-critical', 'completed-low', 'inconclusive', 'error'];

// Resolves to { status, data } for any HTTP response with a JSON body, else { error: {code, message} }.
async function fetchJson(fetchImpl, url, init, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetchImpl(url, { ...init, signal: controller.signal });
        try {
            return { status: response.status, ok: response.ok, data: await response.json() };
        } catch {
            return { error: { code: 'INVALID_RESPONSE', message: 'The server returned an unreadable response.' } };
        }
    } catch (err) {
        if (err?.name === 'AbortError') return { error: { code: 'TIMEOUT', message: 'The request timed out.' } };
        return { error: { code: 'NETWORK_ERROR', message: 'Could not reach the backend.' } };
    } finally {
        clearTimeout(timer);
    }
}

const httpError = (res) => ({ code: `HTTP_${res.status}`, message: `The server returned an error (HTTP ${res.status}).` });
// Server error envelopes carry sanitised messages (no internals), so they are safe to show.
const serverError = (res) => (res.data?.error?.message
    ? { code: res.data.error.code ?? `HTTP_${res.status}`, message: res.data.error.message }
    : httpError(res));

export function createClient({
    base = config.API_BASE,
    mock = config.USE_MOCK,
    fetchImpl = (...args) => globalThis.fetch(...args),
    requestTimeoutMs = config.REQUEST_TIMEOUT_MS,
    analyzeTimeoutMs = config.ANALYZE_TIMEOUT_MS,
} = {}) {
    const get = (path, ms = requestTimeoutMs) => fetchJson(fetchImpl, `${base}${path}`, {}, ms);

    return {
        mock,

        async checkHealth() {
            if (mock) return false;
            const res = await get('/health', 4000);
            return !res.error && res.ok === true && res.data?.status === 'ok';
        },

        // -> analysis view (status completed | inconclusive | error)
        async analyze(formData, { fixture = 'completed-critical' } = {}) {
            if (mock) {
                if (!MOCK_FIXTURES.includes(fixture)) return errorView('MOCK_ERROR', 'Unknown mock fixture.');
                const res = await get(`/mock/${fixture}.json`);
                return res.error ? errorView(res.error.code, res.error.message) : toMockFixtureView(res.data);
            }
            const res = await fetchJson(fetchImpl, `${base}/analyze`, { method: 'POST', body: formData }, analyzeTimeoutMs);
            if (res.error) return errorView(res.error.code, res.error.message);
            // 4xx/5xx still carry the canonical envelope with processing_status "error".
            if (res.data?.processing_status) return toAnalysisView(res.data);
            return errorView(httpError(res).code, httpError(res).message);
        },

        // -> { drains: view[] } | { error }
        async getDrains() {
            const res = await get(mock ? '/mock/drains.json' : '/drains');
            if (res.error) return { error: res.error };
            if (res.ok === false) return { error: serverError(res) };
            const drains = toDrainViews(res.data);
            return drains ? { drains } : { error: { code: 'INVALID_RESPONSE', message: 'Unexpected drain list from the server.' } };
        },

        // -> analysis view for one drain. Mock mode only has summaries, so it returns a limited view.
        async getDrainDetail(drainView) {
            if (mock || !drainView.drainId) return { ...drainToLimitedView(drainView), mock };
            const res = await get(`/drains/${encodeURIComponent(drainView.drainId)}`);
            if (res.error) return errorView(res.error.code, res.error.message, drainView.drainId);
            if (res.data?.processing_status) return toDrainDetailView(res.data, drainView.drainId);
            return errorView(httpError(res).code, httpError(res).message, drainView.drainId);
        },

        // -> { simulation } | { error }
        async simulate(payload) {
            if (mock) return { error: { code: 'MOCK_MODE', message: 'The simulator needs the real backend.' } };
            const res = await fetchJson(fetchImpl, `${base}/simulate`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
            }, requestTimeoutMs);
            if (res.error) return { error: res.error };
            if (res.ok === false) return { error: serverError(res) };
            const simulation = toSimulationView(res.data);
            return simulation ? { simulation } : { error: { code: 'INVALID_RESPONSE', message: 'Unexpected simulation response.' } };
        },
    };
}

export const client = createClient();

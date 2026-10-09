import { client } from './api.js';
import { kpiCounts } from './models.js';
import { validateSubmission } from './validate.js';
import { initMap, addMapLegend, renderDrainsOnMap, focusLocation, onMapClick } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const state = { drains: [], selected: null, busy: false, retry: null, previewUrl: null, selectToken: 0 };
const selectedId = () => state.selected?.drainId ?? null;

// ── Selection / detail ───────────────────────────────────────────────────────
function simulatorBaseline(view) {
    // The simulator needs the real engine and a scored result with a blockage estimate.
    if (client.mock || view.status !== 'completed' || view.blockage === null) return null;
    return { blockage_percentage: view.blockage, rainfall_mm: view.rainfall?.mm ?? null };
}

function renderCollections({ fit = false } = {}) {
    ui.renderDrainList(state.drains, selectDrain, selectedId());
    renderDrainsOnMap(state.drains, selectDrain, { fit, selectedId: selectedId() });
}

function show(view) {
    state.selected = view;
    ui.renderDetail(view);
    ui.showAlert(view, { mock: client.mock });
    ui.setupSimulator(simulatorBaseline(view));
    renderCollections();
    focusLocation(view.location);
}

function clearSelection() {
    state.selected = null;
    renderCollections();
}

async function selectDrain(drain) {
    const token = ++state.selectToken; // ignore a slow response if the user has clicked elsewhere
    ui.showLoading('Loading drain…');
    ui.showAlert(null);
    ui.setupSimulator(null);
    const view = await client.getDrainDetail(drain);
    if (token !== state.selectToken) return;
    if (view.status === 'error') {
        state.retry = () => selectDrain(drain);
        ui.showError(view.error, state.retry);
        if (isConnectionError(view.error)) refreshHealth();
        clearSelection();
        return;
    }
    show(view);
}

// ── Drains ───────────────────────────────────────────────────────────────────
async function loadDrains({ fit = false } = {}) {
    const { drains, error } = await client.getDrains();
    if (error) {
        state.drains = [];
        ui.updateKPIs(null, `Drain records unavailable: ${error.message}`);
        ui.showDrainListError(`Could not load drains: ${error.message}`, () => loadDrains({ fit: true }));
        renderDrainsOnMap([], selectDrain);
        return;
    }
    state.drains = drains;
    ui.updateKPIs(kpiCounts(drains));
    renderCollections({ fit });
}

// ── Upload ───────────────────────────────────────────────────────────────────
const currentFile = () => $('upload-image').files[0] ?? null;
const refreshSubmit = () => ui.setSubmitState({ busy: state.busy, hasFile: Boolean(currentFile()) });

function setFile(file) {
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = file ? URL.createObjectURL(file) : null;
    ui.showFile(file, state.previewUrl);
    ui.setFormMessage(null);
    refreshSubmit();
}

function useFiles(files) {
    const file = files?.[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    $('upload-image').files = transfer.files;
    setFile(file);
}

async function runAnalysis(formData) {
    if (state.busy) return;
    state.busy = true;
    state.selectToken++;
    refreshSubmit();
    ui.showLoading('Analysing image with the local vision model…');
    ui.showAlert(null);
    ui.setupSimulator(null);
    try {
        const view = await client.analyze(formData, { fixture: currentFixture() });
        state.selectToken++; // the requested analysis wins over any drain clicked while it ran
        if (view.status === 'error') {
            state.retry = () => runAnalysis(formData);
            ui.showError(view.error, state.retry);
            if (isConnectionError(view.error)) refreshHealth();
            clearSelection();
        } else {
            state.retry = null;
            if (!client.mock) await loadDrains(); // the new record is in /drains before it is selected
            show(view);
        }
    } finally {
        state.busy = false;
        refreshSubmit();
    }
}

function onSubmit(event) {
    event.preventDefault();
    if (state.busy) return;
    const { error, fields } = validateSubmission({
        file: currentFile(), drainId: $('drain-id').value,
        lat: $('lat').value, lon: $('lon').value, rainfall: $('rainfall').value,
    });
    ui.setFormMessage(error);
    if (error) return;
    const formData = new FormData();
    formData.append('image', currentFile());
    for (const [key, value] of Object.entries(fields)) formData.append(key, value);
    runAnalysis(formData);
}

async function useSample(path, name) {
    try {
        const response = await fetch(path);
        if (!response.ok) throw new Error(String(response.status));
        useFiles([new File([await response.blob()], name, { type: 'image/jpeg' })]);
    } catch {
        ui.setFormMessage('Could not load the sample image from the backend.');
    }
}

function initDropzone() {
    const zone = $('dropzone');
    for (const type of ['dragenter', 'dragover']) {
        zone.addEventListener(type, (e) => { e.preventDefault(); zone.classList.add('is-dragover'); });
    }
    for (const type of ['dragleave', 'drop']) {
        zone.addEventListener(type, () => zone.classList.remove('is-dragover'));
    }
    zone.addEventListener('drop', (e) => { e.preventDefault(); useFiles(e.dataTransfer?.files); });
}

// ── Simulator ────────────────────────────────────────────────────────────────
async function runSimulation() {
    const view = state.selected;
    const baseline = view && simulatorBaseline(view);
    if (!baseline) return;
    ui.setSimBusy(true);
    const { simulation, error } = await client.simulate({
        drain_id: view.drainId, baseline, scenario: ui.simValues(),
    });
    ui.setSimBusy(false);
    if (state.selected !== view) return; // the user moved on; do not attach a stale scenario
    if (error) ui.showSimError(error); else ui.renderSimulation(simulation);
}

// ── Mock mode (explicit opt-in via ?mock=1) ──────────────────────────────────
const currentFixture = () => {
    const value = $('fixture-select').value;
    return value === 'drains' ? 'completed-low' : value;
};

function initMockTools() {
    $('demo-badge').classList.remove('hidden');
    $('dev-tools').classList.remove('hidden');
    $('fixture-select').addEventListener('change', async (e) => {
        state.selectToken++;
        if (e.target.value === 'drains') {
            ui.showWaiting();
            ui.showAlert(null);
            ui.setupSimulator(null);
            state.selected = null;
            return loadDrains({ fit: true });
        }
        ui.showLoading('Loading fixture…');
        const view = await client.analyze(null, { fixture: e.target.value });
        if (view.status === 'error') { ui.showError(view.error, null); clearSelection(); } else show(view);
    });
}

// A failed request is the earliest sign the backend went away; update the header at once.
const isConnectionError = (error) => error?.code === 'NETWORK_ERROR' || error?.code === 'TIMEOUT';

let lastHealth = null;
async function refreshHealth() {
    const health = client.mock ? 'mock' : (await client.checkHealth()) ? 'ok' : 'down';
    ui.setHealth(health);
    // After a backend restart the in-memory drain list is reset: reload it rather than show stale records.
    if (health === 'ok' && lastHealth === 'down') loadDrains({ fit: true });
    lastHealth = health;
}

document.addEventListener('DOMContentLoaded', () => {
    if (initMap()) {
        addMapLegend();
        onMapClick((lat, lon) => {
            $('lat').value = lat.toFixed(6);
            $('lon').value = lon.toFixed(6);
            document.querySelector('details.more').open = true;
        });
    }
    initDropzone();
    $('upload-form').addEventListener('submit', onSubmit);
    $('upload-image').addEventListener('change', () => setFile(currentFile()));
    $('sample-blocked').addEventListener('click', () => useSample('samples/blocked_drain.jpg', 'blocked_drain.jpg'));
    $('sample-clear').addEventListener('click', () => useSample('samples/clear_drain.jpg', 'clear_drain.jpg'));
    $('detail-error-retry').addEventListener('click', () => state.retry?.());
    for (const id of ['sim-blockage', 'sim-rain']) $(id).addEventListener('input', ui.syncSimOutputs);
    $('sim-run').addEventListener('click', runSimulation);
    $('sim-reset').addEventListener('click', () => state.selected && ui.setupSimulator(simulatorBaseline(state.selected)));
    window.addEventListener('beforeunload', () => state.previewUrl && URL.revokeObjectURL(state.previewUrl));

    if (client.mock) initMockTools();
    refreshSubmit();
    refreshHealth();
    setInterval(refreshHealth, 15000);
    loadDrains({ fit: true }); // the dashboard starts with no alert: banners come only from an explicit result
});

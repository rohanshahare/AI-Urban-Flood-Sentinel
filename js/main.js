import { USE_MOCK } from './config.js';
import { getDrains, normalize } from './api.js';
import { initMap, renderDrainsOnMap, addMapLegend } from './map.js';
import { updateKPIs, showDetailState, setupUploadForm, showAlert, refreshHealthDot } from './ui.js';

let currentDrains = [];

function markerClickHandler(drain) {
    if (drain.processing_status === 'completed') showDetailState('success', drain);
    else if (drain.processing_status === 'inconclusive') showDetailState('inconclusive', drain);
    else showDetailState('error', drain);
}

async function loadInitialDrains() {
    currentDrains = await getDrains();
    updateKPIs(currentDrains);
    // Banner starts hidden — never show alerts from the drain list on load
    showAlert(null);
    renderDrainsOnMap(currentDrains, markerClickHandler);
}

function initDevTools() {
    const devTools = document.getElementById('dev-tools');
    const fixtureSelect = document.getElementById('fixture-select');

    if (!USE_MOCK) {
        devTools.classList.add('hidden');
        return;
    }

    devTools.classList.remove('hidden');

    fixtureSelect.addEventListener('change', async (e) => {
        const fixture = e.target.value;
        const res = await fetch(`mock/${fixture}.json`);
        const data = await res.json();

        if (Array.isArray(data)) {
            currentDrains = data.map(normalize);
            updateKPIs(currentDrains);
            renderDrainsOnMap(currentDrains, markerClickHandler);
            showDetailState('waiting');  // resets banner via showAlert(null)
        } else {
            const normalized = normalize(data);
            if (normalized.processing_status === 'completed') showDetailState('success', normalized);
            else if (normalized.processing_status === 'inconclusive') showDetailState('inconclusive', normalized);
            else showDetailState('error', normalized);
        }
    });
}

function initDemoBadge() {
    const badge = document.getElementById('demo-badge');
    if (badge) badge.classList.toggle('hidden', !USE_MOCK);
}

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    addMapLegend();
    setupUploadForm();
    initDevTools();
    initDemoBadge();
    refreshHealthDot();
    loadInitialDrains();
});
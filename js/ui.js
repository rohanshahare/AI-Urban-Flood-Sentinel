import { analyze, getDrains, normalize, checkHealth } from './api.js';
import { USE_MOCK } from './config.js';

// ─── Alert Banner ────────────────────────────────────────────────────────────
// showAlert(null) hides the banner. Only call showAlert(view) after an
// analyze() response or when loading a specific drain's result.
export function showAlert(view) {
    const el = document.getElementById('alert-banner');
    if (!view || !view.alert || !view.alert.triggered) {
        el.classList.add('hidden');
        return;
    }
    el.textContent = view.alert.message ?? view.recommendation ?? 'Maintenance alert';
    el.classList.remove('hidden');
}

// ─── KPIs ─────────────────────────────────────────────────────────────────────
export function updateKPIs(drains) {
    let total = drains.length;
    let low = 0, moderate = 0, high = 0, critical = 0, inconclusive = 0;

    drains.forEach(d => {
        if (d.processing_status === 'inconclusive') {
            inconclusive++;
        } else {
            const level = d.result?.level?.toLowerCase();
            if (level === 'low') low++;
            else if (level === 'medium' || level === 'moderate') moderate++;
            else if (level === 'high') high++;
            else if (level === 'critical') critical++;
        }
    });

    document.getElementById('kpi-total').textContent = total;
    document.getElementById('kpi-low').textContent = low;
    document.getElementById('kpi-moderate').textContent = moderate;
    document.getElementById('kpi-high').textContent = high;
    document.getElementById('kpi-critical').textContent = critical;
    document.getElementById('kpi-inconclusive').textContent = inconclusive;
}

// ─── Detail Panel (4 states) ──────────────────────────────────────────────────
let currentRetryAction = null;

export function showDetailState(state, data = null) {
    ['detail-waiting', 'detail-loading', 'detail-success',
     'detail-error', 'detail-inconclusive'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });

    switch (state) {
        case 'loading':
            document.getElementById('detail-loading').classList.remove('hidden');
            break;

        case 'success': {
            document.getElementById('detail-success').classList.remove('hidden');
            document.getElementById('detail-drain-id').textContent = data.drain_id;
            document.getElementById('detail-score').textContent = data.result?.score ?? 'N/A';
            document.getElementById('detail-confidence').textContent = data.result?.confidence ?? 'N/A';
            document.getElementById('detail-recommendation').textContent = data.recommendation || 'None';

            const badge = document.getElementById('detail-level-badge');
            const level = (data.result?.level ?? 'unknown').toUpperCase();
            badge.textContent = level;
            badge.className = 'px-2 py-1 text-xs font-bold rounded text-white';
            const badgeColor = { LOW: 'bg-green-500', MODERATE: 'bg-yellow-500', MEDIUM: 'bg-yellow-500', HIGH: 'bg-orange-500', CRITICAL: 'bg-red-500' };
            badge.classList.add(badgeColor[level] || 'bg-gray-500');

            const synthetic = data.method === 'DEMO';
            document.getElementById('detail-synthetic-badge').classList.toggle('hidden', !synthetic);

            // Banner: only show if the backend said triggered: true on THIS result
            showAlert(data.alert?.triggered ? data : null);
            break;
        }

        case 'inconclusive': {
            document.getElementById('detail-inconclusive').classList.remove('hidden');
            document.getElementById('detail-inconclusive-recommendation').textContent =
                data.recommendation || 'No specific recommendations provided.';
            showAlert(null); // inconclusive carries no backend alert
            break;
        }

        case 'error': {
            document.getElementById('detail-error').classList.remove('hidden');
            document.getElementById('detail-error-message').textContent =
                data?.error?.message || 'An unknown processing error occurred.';
            showAlert(null);
            break;
        }

        default:
            document.getElementById('detail-waiting').classList.remove('hidden');
            showAlert(null);
    }
}

// ─── Upload Form ──────────────────────────────────────────────────────────────
export function setupUploadForm() {
    const form = document.getElementById('upload-form');
    const fileInput = document.getElementById('upload-image');
    const preview = document.getElementById('image-preview');
    const drainIdToggle = document.getElementById('drain-id-toggle');
    const drainIdInput = document.getElementById('drain-id-manual');

    // Image preview
    fileInput.addEventListener('change', () => {
        const file = fileInput.files[0];
        if (file) {
            const url = URL.createObjectURL(file);
            preview.src = url;
            preview.classList.remove('hidden');
        } else {
            preview.classList.add('hidden');
        }
    });

    // Toggle manual drain ID
    drainIdToggle.addEventListener('change', () => {
        drainIdInput.classList.toggle('hidden', drainIdToggle.value !== 'manual');
    });

    const performAnalysis = async (drainId, formData) => {
        showDetailState('loading');
        const result = await analyze(drainId, formData);

        if (result.processing_status === 'completed') {
            showDetailState('success', result);
        } else if (result.processing_status === 'inconclusive') {
            showDetailState('inconclusive', result);
        } else {
            showDetailState('error', result);
            currentRetryAction = () => performAnalysis(drainId, formData);
        }
    };

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        let drainId = drainIdToggle.value === 'manual'
            ? (drainIdInput.value.trim() || null)
            : drainIdToggle.value;

        const formData = new FormData();
        if (drainId) formData.append('drain_id', drainId);
        if (fileInput.files[0]) formData.append('image', fileInput.files[0]);

        performAnalysis(drainId, formData);
    });

    const retryBtn = document.getElementById('detail-error-retry');
    if (retryBtn) {
        retryBtn.addEventListener('click', () => { if (currentRetryAction) currentRetryAction(); });
    }
}

// ─── Backend Health ───────────────────────────────────────────────────────────
export async function refreshHealthDot() {
    const dot = document.getElementById('health-dot');
    const label = document.getElementById('health-label');
    if (USE_MOCK) {
        dot.className = 'w-2.5 h-2.5 rounded-full bg-yellow-400 inline-block mr-1';
        label.textContent = 'mock mode';
        return;
    }
    try {
        const ok = await checkHealth();
        if (ok) {
            dot.className = 'w-2.5 h-2.5 rounded-full bg-green-400 inline-block mr-1';
            label.textContent = 'backend connected';
        } else {
            throw new Error();
        }
    } catch {
        dot.className = 'w-2.5 h-2.5 rounded-full bg-red-500 inline-block mr-1';
        label.textContent = 'backend unreachable';
    }
}

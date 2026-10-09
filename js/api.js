import { API_BASE, USE_MOCK, ANALYZE_TIMEOUT_MS } from './config.js';

export function normalize(response) {
    return {
        drain_id: response?.drain_id || "UNKNOWN",
        timestamp: response?.timestamp || new Date().toISOString(),
        location: {
            lat: response?.location?.lat || null,
            lng: response?.location?.lng || null
        },
        method: response?.method || "DEMO",
        processing_status: response?.processing_status || "error",
        result: {
            score: response?.result?.score ?? null,
            level: response?.result?.level || null,
            confidence: response?.result?.confidence ?? null
        },
        recommendation: response?.recommendation || null,
        alert: {
            triggered: response?.alert?.triggered || false,
            // Use .message per the agreed envelope; fall back to .reason for legacy fixtures
            message: response?.alert?.message ?? response?.alert?.reason ?? null
        },
        error: response?.error || null
    };
}

export async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
        return res.ok;
    } catch {
        return false;
    }
}

export function normalizeDrain(d) {
  const loc = d.location || {};
  const level = d.risk_level ?? d.risk?.risk_level ?? d.result?.level ?? null;
  return {
    raw: d,
    drainId: d.drain_id ?? d.id ?? null,
    lat: num(d.lat ?? loc.lat),
    lon: num(d.lon ?? loc.lon ?? loc.lng),
    state: d.processing_status ?? null,           // completed | inconclusive | error
    level: level ? String(level).toUpperCase() : null,
    score: num(d.flood_risk_score ?? d.risk?.flood_risk_score),
    synthetic: !!d.synthetic
  };
}


export async function analyze(drainId, formData) {
    if (USE_MOCK) {
        let fixture = 'completed-low';
        if (drainId === 'critical') fixture = 'completed-critical';
        else if (drainId === 'error') fixture = 'error';
        else if (drainId === 'inconclusive') fixture = 'inconclusive';
        
        try {
            // Simulate network delay
            await new Promise(r => setTimeout(r, 1000));
            const res = await fetch(`mock/${fixture}.json`);
            if (!res.ok) throw new Error('Mock fetch failed');
            const data = await res.json();
            return normalize(data);
        } catch (e) {
            return normalize({ processing_status: 'error', error: { message: e.message }});
        }
    }

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
        
        const response = await fetch(`${API_BASE}/analyze`, {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }
        
        const data = await response.json();
        return normalize(data);
    } catch (error) {
        return normalize({
            processing_status: 'error',
            error: { message: error.message || 'Network error' }
        });
    }
}

export async function getDrains() {
    if (USE_MOCK) {
        try {
            const res = await fetch('mock/drains.json');
            const data = await res.json();
            return data.map(normalize);
        } catch (e) {
            console.error("Error fetching drains", e);
            return [];
        }
    }
    try {
        const res = await fetch(`${API_BASE}/drains`);
        const data = await res.json();
        return data.map(normalize);
    } catch(e) {
        console.error("Error fetching drains from API", e);
        return [];
    }
}
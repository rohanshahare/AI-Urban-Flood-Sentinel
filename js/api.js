// api.js

// Always resolves to a unified response envelope, even if the server is unreachable.
async function analyzeDrain(formData) {
    try {
        const response = await fetch(`${API_BASE}/analyze`, { method: "POST", body: formData });
        return await response.json();
    } catch (err) {
        return networkError();
    }
}

async function fetchDrains() {
    const response = await fetch(`${API_BASE}/drains`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

function networkError() {
    return {
        processing_status: "error", vision: null, risk: null, rainfall: null, alert: null, drain: null,
        error: { code: "NETWORK_ERROR", message: "Could not reach the backend." },
    };
}

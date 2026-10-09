// Real backend mode is the default. Same-origin when served by FastAPI (relative base).
// Mock mode must be requested explicitly: open the dashboard as /?mock=1.
// To use a separately hosted page, define window.API_BASE before loading this module.
const params = typeof location !== 'undefined' ? new URLSearchParams(location.search) : new URLSearchParams();

export const USE_MOCK = params.get('mock') === '1';
export const API_BASE = (typeof window !== 'undefined' && window.API_BASE) || '';
export const REQUEST_TIMEOUT_MS = 8000;
export const ANALYZE_TIMEOUT_MS = 200000; // just above the backend's 180 s model timeout
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024; // mirrors the backend limit

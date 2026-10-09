// validate.js — client-side checks that mirror the backend's rules (the backend still validates).
// Pure: takes plain values, returns { error } or { fields } so it can be unit-tested.
import { MAX_IMAGE_BYTES } from './config.js';

const DRAIN_ID = /^[A-Za-z0-9._-]{1,64}$/;
// The formats vision/drain_analysis.py recognises; anything else would only fail on the server.
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp'];
const blank = (v) => v === undefined || v === null || String(v).trim() === '';

// Number('') is 0, so callers check blank() first.
const number = (value) => Number(String(value).trim());

export function validateSubmission({ file, drainId, lat, lon, rainfall }) {
    if (!file) return { error: 'Choose an image first.' };
    if (!file.type || !file.type.startsWith('image/')) return { error: 'The selected file is not an image.' };
    if (!ACCEPTED_TYPES.includes(file.type)) return { error: 'Unsupported image format. Use JPEG, PNG, WebP, GIF or BMP.' };
    if (file.size === 0) return { error: 'The selected image is empty.' };
    if (file.size > MAX_IMAGE_BYTES) return { error: `The image is larger than ${MAX_IMAGE_BYTES / (1024 * 1024)} MiB.` };

    const fields = {};
    if (!blank(drainId)) {
        if (!DRAIN_ID.test(String(drainId).trim())) return { error: "Drain ID may only use letters, digits, '.', '_' and '-' (max 64)." };
        fields.drain_id = String(drainId).trim();
    }
    if (blank(lat) !== blank(lon)) return { error: 'Enter both latitude and longitude, or neither.' };
    if (!blank(lat)) {
        const [la, lo] = [number(lat), number(lon)];
        if (!Number.isFinite(la) || la < -90 || la > 90) return { error: 'Latitude must be a number between -90 and 90.' };
        if (!Number.isFinite(lo) || lo < -180 || lo > 180) return { error: 'Longitude must be a number between -180 and 180.' };
        fields.lat = String(la);
        fields.lon = String(lo);
    }
    if (!blank(rainfall)) {
        const mm = number(rainfall);
        if (!Number.isFinite(mm) || mm < 0) return { error: 'Rainfall must be a number of 0 or more (mm/day).' };
        fields.rainfall_mm = String(mm);
    }
    return { fields };
}

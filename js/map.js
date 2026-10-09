import { riskKey } from './models.js';

export let map;
let markersLayer;

const ORDER = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'UNKNOWN'];
export const LABELS = {
    CRITICAL: 'Critical', HIGH: 'High', MODERATE: 'Moderate', LOW: 'Low', UNKNOWN: 'Needs inspection',
};

export function initMap() {
    const el = document.getElementById('map');
    if (typeof L === 'undefined') {
        el.replaceChildren(Object.assign(document.createElement('div'), {
            className: 'map-fallback',
            textContent: 'The map library could not load (offline?). Every drain is still listed in the inspection queue.',
        }));
        return false;
    }
    map = L.map(el).setView([12.974, 77.597], 13);
    // Tiles are greyscaled in CSS so OSM's own red POI pins cannot be mistaken for risk markers.
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
    }).on('tileerror', showTileNotice).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
    return true;
}

let tileNotice = null;
function showTileNotice() {
    if (tileNotice) return;
    tileNotice = L.control({ position: 'topright' });
    tileNotice.onAdd = () => {
        const div = L.DomUtil.create('div', 'map-notice');
        div.textContent = 'Base-map tiles could not load (offline?). Markers, coordinates and the queue are unaffected.';
        return div;
    };
    tileNotice.addTo(map);
}

// Colour comes from the CSS risk class, the same one used by KPIs, badges and the queue.
function makeIcon(key, synthetic, selected) {
    const size = key === 'UNKNOWN' ? 24 : 20;
    const cls = ['marker', `risk-${key}`, key === 'CRITICAL' ? 'pulse' : '', synthetic ? 'synthetic' : '', selected ? 'selected' : ''].join(' ');
    return L.divIcon({
        className: '',
        html: `<div class="${cls}">${key === 'UNKNOWN' ? '?' : ''}</div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
    });
}

// Plots only drains with numeric coordinates; the rest stay available in the queue.
// Returns how many were plotted. The marker colour is the backend risk level (riskKey).
export function renderDrainsOnMap(drains, onMarkerClick, { fit = true, selectedId = null } = {}) {
    if (!map) return 0;
    markersLayer.clearLayers();
    const points = [];
    for (const d of drains) {
        if (!d.location) continue;
        const key = riskKey(d);
        const selected = Boolean(selectedId) && d.drainId === selectedId;
        const origin = d.synthetic ? 'synthetic demo location' : 'analysed drain';
        L.marker([d.location.lat, d.location.lon], {
            icon: makeIcon(key, d.synthetic, selected),
            title: `${d.drainId ?? 'Drain'}: ${LABELS[key]}${d.score !== null ? `, score ${d.score}` : ''} (${origin})`,
            zIndexOffset: selected ? 2000 : key === 'CRITICAL' ? 1000 : 0,
        }).on('click', () => onMarkerClick(d)).addTo(markersLayer);
        points.push([d.location.lat, d.location.lon]);
    }
    if (fit && points.length) map.fitBounds(points, { padding: [60, 60], maxZoom: 15 });
    return points.length;
}

// Bring a selected drain into view without losing the surrounding context.
export function focusLocation(location) {
    if (!map || !location) return;
    if (map.getZoom() < 14) map.setView([location.lat, location.lon], 14);
    else if (!map.getBounds().pad(-0.15).contains([location.lat, location.lon])) map.panTo([location.lat, location.lon]);
}

// Clicking the map hands the coordinates to the upload form.
export function onMapClick(cb) {
    if (map) map.on('click', (e) => cb(e.latlng.lat, e.latlng.lng));
}

export function addMapLegend() {
    if (!map) return;
    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
        const div = L.DomUtil.create('div', 'map-legend');
        const title = document.createElement('strong');
        title.textContent = 'Risk level (from the backend)';
        div.append(title);
        for (const key of ORDER) {
            const row = document.createElement('div');
            row.append(Object.assign(document.createElement('span'), { className: `legend-dot risk-${key}` }), LABELS[key]);
            div.append(row);
        }
        const synthetic = document.createElement('div');
        synthetic.append(Object.assign(document.createElement('span'), { className: 'legend-dot dashed' }), 'Synthetic demo location');
        const note = document.createElement('small');
        note.textContent = 'Markers are point estimates for a drain, not a flood extent.';
        div.append(synthetic, note);
        return div;
    };
    legend.addTo(map);
}

// map.js

let map = null;
let markerLayer = null;

function initMap() {
    if (typeof L === "undefined") {
        document.getElementById("map").textContent = "Map library failed to load (offline?). Drain list below still works.";
        return;
    }
    map = L.map("map").setView(MAP_CENTER, 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
}

function hasCoordinates(drain) {
    return Number.isFinite(drain.lat) && Number.isFinite(drain.lon);
}

// Drains without numeric coordinates are never plotted.
function renderMarkers(drains) {
    if (!map) return;
    markerLayer.clearLayers();
    for (const drain of drains.filter(hasCoordinates)) {
        const color = LEVEL_COLORS[drain.risk_level] || NEUTRAL_COLOR;
        const marker = L.circleMarker([drain.lat, drain.lon], { radius: 9, color, fillColor: color, fillOpacity: 0.8 });
        marker.bindPopup(drainSummary(drain));
        marker.addTo(markerLayer);
    }
}

function focusDrain(drain) {
    if (map && hasCoordinates(drain)) map.setView([drain.lat, drain.lon], 15);
}

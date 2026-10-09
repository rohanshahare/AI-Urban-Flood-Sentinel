export let map;
let markersLayer;

const COLORS = {
  CRITICAL: "#ef4444", HIGH: "#f97316", MODERATE: "#eab308",
  LOW: "#22c55e", UNKNOWN: "#9ca3af"
};
const LABELS = {
  CRITICAL: "Critical", HIGH: "High", MODERATE: "Moderate",
  LOW: "Low", UNKNOWN: "Needs inspection"
};

export function initMap() {
  map = L.map("map").setView([12.974, 77.597], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
}

// Color is keyed on the backend risk_level string only. No score thresholds here.
function markerKey(d) {
  if (d.state === "inconclusive" || d.state === "error") return "UNKNOWN";
  return COLORS[d.level] && d.level !== "UNKNOWN" ? d.level : "UNKNOWN";
}

function makeIcon(key) {
  const unknown = key === "UNKNOWN";
  const size = unknown ? 22 : 18;
  const cls = key === "CRITICAL" ? "marker pulse" : "marker";
  return L.divIcon({
    className: "",
    html: `<div class="${cls}" style="background:${COLORS[key]};width:${size}px;height:${size}px">${unknown ? "?" : ""}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2]
  });
}

export function renderDrainsOnMap(drains, onMarkerClick, fit = true) {
  markersLayer.clearLayers();
  const pts = [];
  drains.forEach((d) => {
    if (d.lat == null || d.lon == null) return;   // no coordinates: side panel only
    const key = markerKey(d);
    L.marker([d.lat, d.lon], {
      icon: makeIcon(key),
      title: `${d.drainId ?? "Drain"}: ${LABELS[key]}`,
      zIndexOffset: key === "CRITICAL" ? 1000 : 0
    }).on("click", () => onMarkerClick(d)).addTo(markersLayer);
    pts.push([d.lat, d.lon]);
  });
  if (fit && pts.length) map.fitBounds(pts, { padding: [60, 60], maxZoom: 15 });
}

export function onMapClick(cb) {                  // for "click map to set location"
  map.on("click", (e) => cb(e.latlng.lat, e.latlng.lng));
}

export function addMapLegend() {
  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "");
    div.style.cssText = "background:white;color:#0f172a;padding:10px 14px;border-radius:6px;box-shadow:0 1px 5px rgba(0,0,0,.3);font-size:12px;line-height:1.8;";
    div.innerHTML = "<strong style='display:block;margin-bottom:4px'>Risk Level</strong>" +
      Object.keys(COLORS).map((k) =>
        `<div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${COLORS[k]};margin-right:6px;vertical-align:middle"></span>${LABELS[k]}</div>`
      ).join("");
    return div;
  };
  legend.addTo(map);
}
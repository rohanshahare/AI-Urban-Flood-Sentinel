// config.js

// Same origin when served by the backend; set window.API_BASE before this
// script to point a separately hosted page at the API.
const API_BASE = window.API_BASE || "";

// Colours exist only for real risk levels. Missing levels (inconclusive,
// error) use NEUTRAL_COLOR so null is never drawn as green/LOW.
const LEVEL_COLORS = { LOW: "#2e7d32", MODERATE: "#f9a825", HIGH: "#ef6c00", CRITICAL: "#c62828" };
const NEUTRAL_COLOR = "#757575";
const MAP_CENTER = [12.9716, 77.5946];

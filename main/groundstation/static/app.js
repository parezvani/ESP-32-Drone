const POLL_MS = 500;

const map = L.map("map", { zoomControl: true }).setView([43.2609, -79.9192], 16);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "© OpenStreetMap",
}).addTo(map);

const droneIcon = L.divIcon({
  className: "drone-icon",
  html: "🛩️",
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

let droneMarker = null;
let trail = L.polyline([], { color: "#4aa3ff", weight: 2, opacity: 0.7 }).addTo(map);
const trailPoints = [];
const MAX_TRAIL = 400;

const fireLayer = L.layerGroup().addTo(map);
const seenFires = new Set();

let firstDroneFix = true;

const $ = (id) => document.getElementById(id);

function fmtCoords(lat, lon) {
  if (lat == null || lon == null) return "—";
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function fmtTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

function addFire(f) {
  const marker = L.circleMarker([f.lat, f.lon], {
    radius: 10,
    color: "#ffeb3b",
    weight: 2,
    fillColor: "#ff4a1c",
    fillOpacity: 0.85,
    className: "fire-marker",
  });
  const details = [
    f.size_m != null ? `Size: ${f.size_m} m` : null,
    f.area_m2 != null ? `Area: ${f.area_m2} m²` : null,
    f.confidence != null ? `Confidence: ${(f.confidence * 100).toFixed(0)}%` : null,
    `Time: ${fmtTime(f.ts)}`,
  ].filter(Boolean).join("<br>");
  marker.bindPopup(`<b>🔥 Fire #${f.id}</b><br>${details}`);
  marker.addTo(fireLayer);
}

async function poll() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) return;
    const s = await r.json();

    const d = s.drone;
    if (d.lat != null && d.lon != null) {
      const latlng = [d.lat, d.lon];
      if (!droneMarker) {
        droneMarker = L.marker(latlng, { icon: droneIcon }).addTo(map);
      } else {
        droneMarker.setLatLng(latlng);
      }
      trailPoints.push(latlng);
      if (trailPoints.length > MAX_TRAIL) trailPoints.shift();
      trail.setLatLngs(trailPoints);

      if (firstDroneFix) {
        map.setView(latlng, 17);
        firstDroneFix = false;
      } else if ($("follow").checked) {
        map.panTo(latlng, { animate: true, duration: 0.3 });
      }

      $("drone-coords").textContent = fmtCoords(d.lat, d.lon);
      $("drone-alt").textContent = d.alt_m != null ? `${d.alt_m.toFixed(1)} m` : "—";
      $("drone-hdg").textContent = d.heading_deg != null ? `${d.heading_deg.toFixed(0)}°` : "—";
    }

    for (const f of s.fires) {
      if (!seenFires.has(f.id)) {
        seenFires.add(f.id);
        addFire(f);
      }
    }

    $("fire-count").textContent = s.fires.length;
    $("last-update").textContent = fmtTime(s.server_ts);

    updateCamera(s.camera_url);
  } catch (e) {
    console.error("poll failed", e);
  }
}

let currentCamUrl = null;
function updateCamera(url) {
  if (url === currentCamUrl) return;
  currentCamUrl = url;
  const img = $("cam-stream");
  const ph = $("cam-placeholder");
  const foot = $("cam-url");
  if (url) {
    img.src = url;
    img.classList.add("live");
    ph.classList.add("hidden");
    foot.textContent = url;
  } else {
    img.removeAttribute("src");
    img.classList.remove("live");
    ph.classList.remove("hidden");
    foot.textContent = "no stream URL configured — POST one to /api/camera";
  }
}

$("cam-toggle").addEventListener("click", () => {
  $("cam-panel").classList.toggle("hidden");
});
$("cam-close").addEventListener("click", () => {
  $("cam-panel").classList.add("hidden");
});

setInterval(poll, POLL_MS);
poll();

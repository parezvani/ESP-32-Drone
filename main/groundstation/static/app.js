const POLL_MS = 500;
const STALE_DRONE_S = 5;
const STALE_FIRE_S = 60;
const FRESH_FIRE_S = 30;

const map = L.map("map", { zoomControl: true }).setView([36.995578, -122.058878], 16);

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

const droneMarkers = {};
const trails = {};
const trailPoints = {};
const sightLines = {};
const MAX_TRAIL = 400;

const fireLayer = L.layerGroup().addTo(map);
const fireMarkers = {};

let firstDroneFix = true;
let primaryDroneId = null;

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

function fmtAge(ts, now) {
  const sec = now - ts;
  if (sec < 60) return `${sec.toFixed(0)}s ago`;
  if (sec < 3600) return `${(sec / 60).toFixed(0)}m ago`;
  return `${(sec / 3600).toFixed(1)}h ago`;
}

function renderFireMarker(f, isStale) {
  const color = isStale ? "#888" : "#ffeb3b";
  const fill = isStale ? "#444" : "#ff4a1c";
  if (fireMarkers[f.id]) {
    fireMarkers[f.id].setStyle({ color, fillColor: fill, fillOpacity: isStale ? 0.4 : 0.85 });
    return;
  }
  const marker = L.circleMarker([f.lat, f.lon], {
    radius: 10,
    color, weight: 2,
    fillColor: fill, fillOpacity: 0.85,
    className: "fire-marker",
  });
  const details = [
    f.size_m != null ? `Size: ${f.size_m} m` : null,
    f.area_m2 != null ? `Area: ${f.area_m2} m²` : null,
    f.confidence != null ? `Confidence: ${(f.confidence * 100).toFixed(0)}%` : null,
    f.source ? `Source: ${f.source}` : null,
    `Time: ${fmtTime(f.ts)}`,
  ].filter(Boolean).join("<br>");
  marker.bindPopup(`<b>🔥 Fire #${f.id}</b><br>${details}`);
  marker.addTo(fireLayer);
  fireMarkers[f.id] = marker;
}

function renderDroneList(drones, now, anyFireSeen) {
  const list = $("drone-list");
  const ids = Object.keys(drones);
  $("drone-count").textContent = ids.length;

  if (ids.length === 0) {
    list.innerHTML = '<div class="empty">waiting for telemetry…</div>';
    return;
  }

  list.innerHTML = ids.map((id) => {
    const d = drones[id];
    const age = now - (d.ts || 0);
    const isStale = age > STALE_DRONE_S;
    const sees = !!d.fire_detected && !isStale;
    const cls = ["drone-card"];
    if (isStale) cls.push("stale");
    if (sees) cls.push("fire");

    const badge = sees
      ? '<span class="badge fire">FIRE</span>'
      : isStale
        ? '<span class="badge">stale</span>'
        : '<span class="badge live">live</span>';

    const lat = d.lat != null ? d.lat.toFixed(5) : "—";
    const lon = d.lon != null ? d.lon.toFixed(5) : "—";
    const alt = d.alt_m != null ? `${d.alt_m.toFixed(1)} m` : "—";
    const hdg = d.heading_deg != null ? `${d.heading_deg.toFixed(0)}°` : "—";
    const sats = d.sats != null ? d.sats : "—";
    const hdop = d.hdop != null ? d.hdop.toFixed(1) : "—";

    return `
      <div class="${cls.join(" ")}">
        <div class="drone-id"><span>${id}</span>${badge}</div>
        <div class="stats">
          <span class="label">lat</span><span>${lat}</span>
          <span class="label">lon</span><span>${lon}</span>
          <span class="label">alt</span><span>${alt}</span>
          <span class="label">hdg</span><span>${hdg}</span>
          <span class="label">sats</span><span>${sats}</span>
          <span class="label">hdop</span><span>${hdop}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderFireList(fires, now, anyFireSeen) {
  const list = $("fire-list");
  $("fire-count").textContent = fires.length;

  if (fires.length === 0) {
    list.innerHTML = '<div class="empty">none yet</div>';
    return;
  }

  const sorted = [...fires].sort((a, b) => b.ts - a.ts);
  list.innerHTML = sorted.map((f) => {
    const age = now - f.ts;
    const isFresh = age < FRESH_FIRE_S;
    const isStale = age > STALE_FIRE_S && !anyFireSeen;
    const cls = isStale ? "fire-card stale" : "fire-card";
    const badge = (isFresh || anyFireSeen)
      ? '<span class="badge active">active</span>'
      : '<span class="badge stale">stale</span>';
    const conf = f.confidence != null ? `${(f.confidence * 100).toFixed(0)}%` : "—";
    return `
      <div class="${cls}">
        <div class="fire-head">
          <span class="fire-id">#${f.id}</span>
          ${badge}
        </div>
        <div class="fire-meta">
          <span>${f.lat.toFixed(5)}, ${f.lon.toFixed(5)}</span>
          <span>${conf} · ${fmtAge(f.ts, now)}</span>
        </div>
      </div>
    `;
  }).join("");

  // also refresh markers' visual state on the map
  for (const f of fires) {
    const age = now - f.ts;
    const isStale = age > STALE_FIRE_S && !anyFireSeen;
    renderFireMarker(f, isStale);
  }
}

function updateAlert(anyFireSeen, droneCount) {
  const el = $("alert-banner");
  const txt = $("alert-text");
  if (anyFireSeen) {
    el.classList.remove("idle");
    el.classList.add("active");
    txt.textContent = "Fire detected — drones converging";
  } else {
    el.classList.remove("active");
    el.classList.add("idle");
    txt.textContent = droneCount > 0 ? "No fire detected" : "No drones connected";
  }
}

async function poll() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) return;
    const s = await r.json();
    const now = s.server_ts;

    let anyFireSeen = false;
    primaryDroneId = null;

    for (const [id, d] of Object.entries(s.drones)) {
      const droneAge = now - (d.ts || 0);
      if (d.fire_detected && droneAge < STALE_DRONE_S) anyFireSeen = true;

      if (d.lat == null || d.lon == null) continue;
      const latlng = [d.lat, d.lon];

      if (!primaryDroneId) primaryDroneId = id;

      if (!droneMarkers[id]) {
        droneMarkers[id] = L.marker(latlng, { icon: droneIcon })
          .addTo(map)
          .bindPopup(`<b>${id}</b>`);
        trailPoints[id] = [];
        trails[id] = L.polyline([], { color: "#4aa3ff", weight: 2, opacity: 0.7 }).addTo(map);
      } else {
        droneMarkers[id].setLatLng(latlng);
      }

      trailPoints[id].push(latlng);
      if (trailPoints[id].length > MAX_TRAIL) trailPoints[id].shift();
      trails[id].setLatLngs(trailPoints[id]);

      if (d.fire_detected && d.heading_deg != null && droneAge < STALE_DRONE_S) {
        const distDeg = 0.003;  // ~300m projection in lat-degree units
        const rad = d.heading_deg * (Math.PI / 180);
        const endLat = d.lat + Math.cos(rad) * distDeg;
        const endLon = d.lon + Math.sin(rad) * (distDeg / Math.cos(d.lat * Math.PI / 180));
        if (!sightLines[id]) {
          sightLines[id] = L.polyline([latlng, [endLat, endLon]], {
            color: "#ff4a1c",
            weight: 3,
            dashArray: "10, 10",
            opacity: 0.8,
          }).addTo(map);
        } else {
          sightLines[id].setLatLngs([latlng, [endLat, endLon]]);
        }
      } else if (sightLines[id]) {
        sightLines[id].remove();
        delete sightLines[id];
      }

      if (id === primaryDroneId) {
        if (firstDroneFix) {
          map.setView(latlng, 17);
          firstDroneFix = false;
        } else if ($("follow").checked) {
          map.panTo(latlng, { animate: true, duration: 0.3 });
        }
      }
    }

    // remove markers for drones no longer in state (dropped by reaper)
    for (const id of Object.keys(droneMarkers)) {
      if (!(id in s.drones)) {
        droneMarkers[id].remove();
        delete droneMarkers[id];
        if (trails[id]) { trails[id].remove(); delete trails[id]; delete trailPoints[id]; }
        if (sightLines[id]) { sightLines[id].remove(); delete sightLines[id]; }
      }
    }

    renderDroneList(s.drones, now, anyFireSeen);
    renderFireList(s.fires, now, anyFireSeen);
    updateAlert(anyFireSeen, Object.keys(s.drones).length);

    $("server-time").textContent = fmtTime(now);

    updateCamera(s.camera_url);
  } catch (e) {
    console.error("poll failed", e);
  }
}

let currentCamUrl = null;
function applyCamSrc() {
  const img = $("cam-stream");
  const ph = $("cam-placeholder");
  const foot = $("cam-url");
  const panelOpen = !$("cam-panel").classList.contains("hidden");

  if (currentCamUrl && panelOpen) {
    if (img.getAttribute("src") !== currentCamUrl) {
      img.src = currentCamUrl;
      img.classList.add("live");
    }
    ph.classList.add("hidden");
    foot.textContent = currentCamUrl;
  } else {
    img.removeAttribute("src");
    img.classList.remove("live");
    ph.classList.remove("hidden");
    foot.textContent = currentCamUrl || "no stream URL configured — authorized POST required";
  }
}

function updateCamera(url) {
  currentCamUrl = url || null;
  applyCamSrc();
}

$("cam-toggle").addEventListener("click", () => {
  $("cam-panel").classList.toggle("hidden");
  applyCamSrc();
});
$("cam-close").addEventListener("click", () => {
  $("cam-panel").classList.add("hidden");
  applyCamSrc();
});

$("triangulate-btn").addEventListener("click", async () => {
  const btn = $("triangulate-btn");
  btn.disabled = true;
  btn.textContent = "Working…";
  try {
    const r = await fetch("/api/triangulate", { method: "POST" });
    const j = await r.json();
    btn.textContent = j.fire ? "Fire located" : "No solution";
  } catch (e) {
    btn.textContent = "Failed";
  }
  setTimeout(() => {
    btn.disabled = false;
    btn.textContent = "Trigger triangulation";
  }, 1200);
});

$("reset-btn").addEventListener("click", async () => {
  if (!confirm("Wipe all drone state and fires?")) return;
  await fetch("/api/reset", { method: "POST" });
  for (const id of Object.keys(fireMarkers)) {
    fireMarkers[id].remove();
    delete fireMarkers[id];
  }
  for (const id of Object.keys(droneMarkers)) {
    droneMarkers[id].remove();
    delete droneMarkers[id];
  }
  for (const id of Object.keys(trails)) {
    trails[id].remove();
    delete trails[id];
    delete trailPoints[id];
  }
  for (const id of Object.keys(sightLines)) {
    sightLines[id].remove();
    delete sightLines[id];
  }
  firstDroneFix = true;
});

setInterval(poll, POLL_MS);
poll();

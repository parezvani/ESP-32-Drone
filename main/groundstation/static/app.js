const POLL_MS = 500;

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

// UPGRADE: Changed these to objects to hold multiple drones!
const droneMarkers = {};
const trails = {};
const trailPoints = {};
const sightLines = {};
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

    // UPGRADE: Loop through the new drones dictionary
    let primaryDroneId = null; 

    for (const [id, d] of Object.entries(s.drones)) {
      if (d.lat != null && d.lon != null) {
        const latlng = [d.lat, d.lon];
        
        // Pick the first drone we process to act as the "Primary" for the HUD and Camera Follow
        if (!primaryDroneId) primaryDroneId = id;

        // 1. Handle the Marker
        if (!droneMarkers[id]) {
          // New drone detected! Create its marker and trail.
          droneMarkers[id] = L.marker(latlng, { icon: droneIcon })
            .addTo(map)
            .bindPopup(`<b>${id}</b>`); // Name tag popup
            
          trailPoints[id] = [];
          trails[id] = L.polyline([], { color: "#4aa3ff", weight: 2, opacity: 0.7 }).addTo(map);
        } else {
          // Existing drone, just update position
          droneMarkers[id].setLatLng(latlng);
        }

        // 2. Handle the Trail
        trailPoints[id].push(latlng);
        if (trailPoints[id].length > MAX_TRAIL) trailPoints[id].shift();
        trails[id].setLatLngs(trailPoints[id]);

        if (d.fire_detected && d.heading_deg != null) {
          // Calculate a point roughly 300 meters away in the direction it is looking
          const distDeg = 0.003; 
          const rad = d.heading_deg * (Math.PI / 180);
          
          // Geometry to project a line forward based on heading
          const endLat = d.lat + Math.cos(rad) * distDeg;
          const endLon = d.lon + Math.sin(rad) * (distDeg / Math.cos(d.lat * Math.PI / 180));

          if (!sightLines[id]) {
            // Create a dashed red line extending from the drone
            sightLines[id] = L.polyline([latlng, [endLat, endLon]], {
              color: "#ff4a1c",
              weight: 3,
              dashArray: "10, 10",
              opacity: 0.8
            }).addTo(map);
          } else {
            // Update the line's position as the drone moves
            sightLines[id].setLatLngs([latlng, [endLat, endLon]]);
          }
        } else {
          // If the drone stops seeing smoke, erase the line
          if (sightLines[id]) {
            sightLines[id].remove();
            delete sightLines[id];
          }
        }
        // ==========================================

        // 3. Update HUD & Camera (Only for the Primary Drone)
        if (id === primaryDroneId) {
          if (firstDroneFix) {
            map.setView(latlng, 17);
            firstDroneFix = false;
          } else if ($("follow").checked) {
            map.panTo(latlng, { animate: true, duration: 0.3 });
          }

          $("drone-coords").textContent = fmtCoords(d.lat, d.lon);
          $("drone-alt").textContent = d.alt_m != null ? `${d.alt_m.toFixed(1)} m` : "—";
          $("drone-hdg").textContent = d.heading_deg != null ? `${d.heading_deg.toFixed(0)}°` : "—";
          
          // Optional: Update the HUD title to show which drone is driving the stats
          document.querySelector(".title").textContent = `FireFly (${id})`;
        }
      }
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
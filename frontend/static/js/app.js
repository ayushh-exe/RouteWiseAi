document.addEventListener("DOMContentLoaded", () => {
  const delayForm = document.getElementById("delayForm");
  const routeForm = document.getElementById("routeForm");
  const delayOutput = document.getElementById("delayOutput");
  const routeOutput = document.getElementById("routeOutput");

  const tomtomKey = "y3lqXrAZjVCThGRsEFVLiiJb5GSUpmI1";

  // Initialize Leaflet map centered over Delhi, India
  const map = L.map("map").setView([28.6139, 77.2090], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  let routeLayer;

  // Get lat/lon coordinates from address using TomTom Geocoding API
  async function getCoords(address) {
    const res = await axios.get(`https://api.tomtom.com/search/2/geocode/${encodeURIComponent(address)}.json?key=${tomtomKey}`);
    const pos = res.data.results[0]?.position;
    return pos ? [pos.lat, pos.lon] : null;
  }

  // Draw a single route between two points on the map
  async function drawSingleRoute(from, to) {
    const fromCoords = await getCoords(from);
    const toCoords = await getCoords(to);
    if (!fromCoords || !toCoords) return;

    const res = await axios.get(`https://api.tomtom.com/routing/1/calculateRoute/${fromCoords.join(",")}:${toCoords.join(",")}/json?key=${tomtomKey}&traffic=true`);
    const points = res.data.routes[0].legs[0].points.map(p => [p.latitude, p.longitude]);

    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.polyline(points, { color: "blue", weight: 5 }).addTo(map);
    map.fitBounds(routeLayer.getBounds());
  }

  // Draw multi-stop optimized route on the map
  async function drawMultiStopRoute(addresses) {
    const coordsList = await Promise.all(addresses.map(addr => getCoords(addr)));
    const validCoords = coordsList.filter(Boolean);
    if (validCoords.length < 2) return;

    if (routeLayer) map.removeLayer(routeLayer);

    let allPoints = [];
    for (let i = 0; i < validCoords.length - 1; i++) {
      const from = validCoords[i];
      const to = validCoords[i + 1];
      const res = await axios.get(`https://api.tomtom.com/routing/1/calculateRoute/${from.join(",")}:${to.join(",")}/json?key=${tomtomKey}&traffic=true`);
      const points = res.data.routes[0].legs[0].points.map(p => [p.latitude, p.longitude]);
      allPoints = allPoints.concat(points);
    }

    routeLayer = L.polyline(allPoints, { color: "green", weight: 4 }).addTo(map);
    map.fitBounds(routeLayer.getBounds());
  }

  // Traffic level descriptions
  function getTrafficDescription(level) {
    if (level >= 8) return "Severe Traffic";
    if (level >= 6) return "Heavy Traffic";
    if (level >= 4) return "Moderate Traffic";
    if (level >= 2) return "Light Traffic";
    return "Free Flowing";
  }

  // Traffic color for styling
  function getTrafficColor(level) {
    if (level >= 8) return "darkred";
    if (level >= 6) return "orangered";
    if (level >= 4) return "orange";
    if (level >= 2) return "yellowgreen";
    return "green";
  }

  // Handle delay prediction form submission
  delayForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const origin = document.getElementById("origin").value;
    const destination = document.getElementById("destination").value;
    const timestamp = document.getElementById("timestamp").value;

    try {
      const res = await axios.post("http://127.0.0.1:8000/predict-delay", {
        origin,
        destination,
        timestamp,
      });

      const data = res.data;
      const delay = data.predicted_delay_minutes;
      const trafficDesc = getTrafficDescription(data.traffic_level);
      const trafficColor = getTrafficColor(data.traffic_level);
      const totalTime = data.total_estimated_time;

      delayOutput.innerHTML = `
        <div style="background:#eafaf1; padding: 12px; border-left: 5px solid green; border-radius: 10px;">
          <strong>Predicted Delay:</strong> ${delay.toFixed(2)} min<br>
          <strong>Traffic Level:</strong> <span style="color:${trafficColor}; font-weight:bold">${trafficDesc}</span><br>
          <strong>Weather:</strong> ${data.weather}<br>
          <strong>Total Estimated Time:</strong> ${totalTime.toFixed(2)} min
        </div>
      `;

      drawSingleRoute(origin, destination);
    } catch (err) {
      delayOutput.innerHTML = `<span style="color:red">Error: ${err.response?.data?.error || err.message}</span>`;
    }
  });

  // Handle route optimization form submission
  routeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const stops = document.getElementById("stops").value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((address) => ({ address }));

    try {
      const res = await axios.post("http://127.0.0.1:8000/optimize-route", {
        stops,
      });

      const data = res.data;
      routeOutput.innerHTML = `
        <strong>Optimized Order:</strong><br>
        <ol>${data.optimized_order.map((stop) => `<li>${stop}</li>`).join("")}</ol>
      `;

      drawMultiStopRoute(data.optimized_order);
    } catch (err) {
      routeOutput.innerHTML = `<span style="color:red">Error: ${err.response?.data?.error || err.message}</span>`;
    }
  });
});

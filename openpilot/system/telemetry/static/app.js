(function () {
  const STEER_MAX = 90;

  const els = {
    status: document.getElementById("status"),
    speed: document.getElementById("speed"),
    targetSpeed: document.getElementById("target-speed"),
    opBadge: document.getElementById("op-badge"),
    gas: document.getElementById("gas"),
    brake: document.getElementById("brake"),
    steerOverride: document.getElementById("steer-override"),
    leftBlinker: document.getElementById("left-blinker"),
    rightBlinker: document.getElementById("right-blinker"),
    steerBar: document.getElementById("steer-bar"),
    steerAngle: document.getElementById("steer-angle"),
    gpsFix: document.getElementById("gps-fix"),
    lat: document.getElementById("lat"),
    lon: document.getElementById("lon"),
    accuracy: document.getElementById("accuracy"),
    sats: document.getElementById("sats"),
  };

  let map = null;
  let marker = null;
  let eventSource = null;
  let reconnectTimer = null;

  function initMap() {
    map = L.map("map", { zoomControl: true }).setView([0, 0], 2);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);
    marker = L.circleMarker([0, 0], {
      radius: 8,
      color: "#58a6ff",
      fillColor: "#58a6ff",
      fillOpacity: 0.8,
    }).addTo(map);
  }

  function setConnected(connected) {
    els.status.textContent = connected ? "Live" : "Disconnected";
    els.status.className = "status " + (connected ? "connected" : "disconnected");
  }

  function setPill(el, active) {
    el.classList.toggle("active", !!active);
  }

  function updateUI(data) {
    els.speed.textContent = Math.round(data.speed.kph);
    els.targetSpeed.textContent = Math.round(data.targetSpeed.kph);

    const engaged = data.openpilot.engaged || data.openpilot.active;
    els.opBadge.textContent = engaged ? "ENGAGED" : "OFF";
    els.opBadge.className = "badge " + (engaged ? "on" : "off");

    const d = data.driver;
    setPill(els.gas, d.gas);
    setPill(els.brake, d.brake);
    setPill(els.steerOverride, d.steeringPressed);
    setPill(els.leftBlinker, d.leftBlinker);
    setPill(els.rightBlinker, d.rightBlinker);

    const angle = d.steeringAngleDeg;
    els.steerAngle.textContent = angle.toFixed(1) + "°";
    const pct = 50 + (Math.max(-STEER_MAX, Math.min(STEER_MAX, angle)) / STEER_MAX) * 50;
    els.steerBar.style.left = pct + "%";

    const g = data.gps;
    if (g.hasFix && g.lat != null && g.lon != null) {
      els.gpsFix.textContent = "Fix acquired";
      els.gpsFix.className = "gps-fix has-fix";
      els.lat.textContent = g.lat.toFixed(6);
      els.lon.textContent = g.lon.toFixed(6);
      els.accuracy.textContent = g.accuracyM != null ? g.accuracyM.toFixed(1) : "--";
      els.sats.textContent = g.satellites;

      marker.setLatLng([g.lat, g.lon]);
      map.setView([g.lat, g.lon], map.getZoom() < 14 ? 16 : map.getZoom());
    } else {
      els.gpsFix.textContent = "No fix";
      els.gpsFix.className = "gps-fix no-fix";
      els.lat.textContent = "--";
      els.lon.textContent = "--";
      els.accuracy.textContent = "--";
      els.sats.textContent = g.satellites || "--";
    }
  }

  function eventsUrl() {
    const params = new URLSearchParams(location.search);
    const token = params.get("token");
    let url = "/api/events";
    if (token) url += "?token=" + encodeURIComponent(token);
    return url;
  }

  function connect() {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource(eventsUrl());

    eventSource.onopen = function () {
      setConnected(true);
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    eventSource.onmessage = function (event) {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "telemetry" && msg.data) {
          updateUI(msg.data);
        }
      } catch (e) {
        console.warn("bad message", e);
      }
    };

    eventSource.onerror = function () {
      setConnected(false);
      eventSource.close();
      reconnectTimer = setTimeout(connect, 2000);
    };
  }

  initMap();
  connect();
})();

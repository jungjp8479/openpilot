(function () {
  const STEER_MAX = 90;

  const els = {
    status: document.getElementById("status"),
    banner: document.getElementById("banner"),
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
  let ws = null;
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

  function setStatus(mode) {
    if (mode === "live") {
      els.status.textContent = "Live";
      els.status.className = "status connected";
      els.banner.className = "banner hidden";
    } else if (mode === "waiting") {
      els.status.textContent = "Connected";
      els.status.className = "status waiting";
      els.banner.textContent = "Waiting for ignition — live data will start when the car is onroad";
      els.banner.className = "banner waiting";
    } else {
      els.status.textContent = "Disconnected";
      els.status.className = "status disconnected";
      els.banner.className = "banner hidden";
    }
  }

  function setPill(el, active) {
    el.classList.toggle("active", !!active);
  }

  function clearUI() {
    els.speed.textContent = "--";
    els.targetSpeed.textContent = "--";
    els.opBadge.textContent = "OFF";
    els.opBadge.className = "badge off";
    setPill(els.gas, false);
    setPill(els.brake, false);
    setPill(els.steerOverride, false);
    setPill(els.leftBlinker, false);
    setPill(els.rightBlinker, false);
    els.steerAngle.textContent = "0°";
    els.steerBar.style.left = "50%";
    els.gpsFix.textContent = "No fix";
    els.gpsFix.className = "gps-fix no-fix";
    els.lat.textContent = "--";
    els.lon.textContent = "--";
    els.accuracy.textContent = "--";
    els.sats.textContent = "--";
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

  function handleMessage(msg) {
    if (msg.type === "telemetry" && msg.data) {
      setStatus("live");
      updateUI(msg.data);
    } else if (msg.type === "status" && msg.data) {
      if (msg.data.streaming) {
        setStatus("live");
      } else {
        setStatus("waiting");
        clearUI();
      }
    }
  }

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const params = new URLSearchParams(location.search);
    const token = params.get("token");
    let url = proto + "//" + location.host + "/ws";
    if (token) url += "?token=" + encodeURIComponent(token);
    return url;
  }

  function connect() {
    if (ws) {
      ws.onclose = null;
      ws.close();
    }

    ws = new WebSocket(wsUrl());

    ws.onopen = function () {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onmessage = function (event) {
      try {
        handleMessage(JSON.parse(event.data));
      } catch (e) {
        console.warn("bad message", e);
      }
    };

    ws.onclose = function () {
      setStatus("disconnected");
      reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  initMap();
  connect();
})();

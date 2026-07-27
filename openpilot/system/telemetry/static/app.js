(function () {
  const STEER_MAX = 90;
  const LOCKED_STATES = new Set(["armed", "countdown", "running"]);

  const els = {
    status: document.getElementById("status"),
    banner: document.getElementById("banner"),
    speed: document.getElementById("speed"),
    targetSpeed: document.getElementById("target-speed"),
    opBadge: document.getElementById("op-badge"),
    gas: document.getElementById("gas"),
    brake: document.getElementById("brake"),
    leftBlinker: document.getElementById("left-blinker"),
    rightBlinker: document.getElementById("right-blinker"),
    steerBar: document.getElementById("steer-bar"),
    steerAngle: document.getElementById("steer-angle"),
    gpsFix: document.getElementById("gps-fix"),
    lat: document.getElementById("lat"),
    lon: document.getElementById("lon"),
    accuracy: document.getElementById("accuracy"),
    sats: document.getElementById("sats"),
    btnSetPosition: document.getElementById("btn-set-position"),
    btnReady: document.getElementById("btn-ready"),
    readyHint: document.getElementById("ready-hint"),
    countdownOverlay: document.getElementById("countdown-overlay"),
    countdownValue: document.getElementById("countdown-value"),
  };

  let map = null;
  let marker = null;
  let triggerMarker = null;
  let ws = null;
  let reconnectTimer = null;
  let hintTimer = null;
  let lastTestSequence = null;
  let wakeLock = null;
  let wakeLockWanted = false;

  async function acquireWakeLock() {
    if (!("wakeLock" in navigator)) {
      return;
    }
    wakeLockWanted = true;
    if (wakeLock || document.visibilityState !== "visible") {
      return;
    }
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", function () {
        wakeLock = null;
        if (wakeLockWanted && document.visibilityState === "visible") {
          acquireWakeLock();
        }
      });
    } catch (e) {
      console.warn("wake lock unavailable", e);
    }
  }

  async function releaseWakeLock() {
    wakeLockWanted = false;
    if (!wakeLock) {
      return;
    }
    try {
      await wakeLock.release();
    } catch (e) {
      console.warn("wake lock release failed", e);
    }
    wakeLock = null;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && wakeLockWanted) {
      acquireWakeLock();
    }
  });

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
    triggerMarker = L.circleMarker([0, 0], {
      radius: 10,
      color: "#f85149",
      fillColor: "#f85149",
      fillOpacity: 0.5,
    });
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

  function showReadyHint(message, flash) {
    if (!message) {
      els.readyHint.className = "ready-hint hidden";
      els.readyHint.textContent = "";
      return;
    }
    els.readyHint.textContent = message;
    els.readyHint.className = "ready-hint" + (flash ? " flash" : "");
    if (flash) {
      if (hintTimer) window.clearTimeout(hintTimer);
      hintTimer = window.setTimeout(function () {
        updateReadyHint(lastTestSequence, false);
      }, 3000);
    }
  }

  function updateReadyButton(ts) {
    const btn = els.btnReady;
    btn.classList.remove("ready", "not-ready", "started", "locked");

    if (!ts) {
      btn.textContent = "READY";
      btn.classList.add("not-ready");
      return;
    }

    if (LOCKED_STATES.has(ts.state)) {
      btn.textContent = "STARTED";
      btn.classList.add("started", "locked");
      return;
    }

    btn.textContent = "READY";
    if (ts.ready) {
      btn.classList.add("ready");
    } else {
      btn.classList.add("not-ready");
    }
  }

  function updateReadyHint(ts, flash) {
    if (!ts || LOCKED_STATES.has(ts.state)) {
      showReadyHint(null);
      return;
    }
    if (ts.ready) {
      showReadyHint(null);
      return;
    }
    showReadyHint(ts.readyMessage || "", flash);
  }

  function updateCountdownOverlay(ts) {
    if (!ts || ts.state !== "countdown" || ts.countdownSec == null) {
      els.countdownOverlay.className = "countdown-overlay hidden";
      return;
    }
    els.countdownOverlay.className = "countdown-overlay";
    els.countdownValue.textContent = String(ts.countdownSec);
  }

  function updateTriggerMarker(ts) {
    if (!ts || !ts.triggerSet || ts.triggerLat == null || ts.triggerLon == null) {
      if (triggerMarker && map.hasLayer(triggerMarker)) {
        map.removeLayer(triggerMarker);
      }
      return;
    }
    triggerMarker.setLatLng([ts.triggerLat, ts.triggerLon]);
    if (!map.hasLayer(triggerMarker)) {
      triggerMarker.addTo(map);
    }
  }

  function clearUI() {
    els.speed.textContent = "--";
    els.targetSpeed.textContent = "--";
    els.opBadge.textContent = "OFF";
    els.opBadge.className = "badge off";
    setPill(els.gas, false);
    setPill(els.brake, false);
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
    lastTestSequence = null;
    updateReadyButton(null);
    updateReadyHint(null, false);
    updateCountdownOverlay(null);
  }

  function formatTargetSpeed(kph) {
    const rounded = Math.round(kph);
    return rounded === 255 ? "--" : String(rounded);
  }

  function updateUI(data) {
    els.speed.textContent = Math.round(data.speed.kph);
    els.targetSpeed.textContent = formatTargetSpeed(data.targetSpeed.kph);

    const engaged = data.openpilot.engaged || data.openpilot.active;
    els.opBadge.textContent = engaged ? "ENGAGED" : "OFF";
    els.opBadge.className = "badge " + (engaged ? "on" : "off");

    const d = data.driver;
    setPill(els.gas, d.gas);
    setPill(els.brake, d.brake);
    setPill(els.leftBlinker, d.leftBlinker);
    setPill(els.rightBlinker, d.rightBlinker);

    const angle = d.steeringAngleDeg;
    els.steerAngle.textContent = angle.toFixed(1) + "°";
    const pct = 50 - (Math.max(-STEER_MAX, Math.min(STEER_MAX, angle)) / STEER_MAX) * 50;
    els.steerBar.style.left = pct + "%";

    const g = data.gps;
    if (g.hasFix && g.lat != null && g.lon != null) {
      els.gpsFix.textContent = "Fix";
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

    lastTestSequence = data.testSequence || null;
    updateReadyButton(lastTestSequence);
    updateReadyHint(lastTestSequence, false);
    updateCountdownOverlay(lastTestSequence);
    updateTriggerMarker(lastTestSequence);
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
    } else if (msg.type === "ack") {
      updateReadyButton({ state: "armed", ready: false });
      els.btnReady.textContent = "STARTED";
      els.btnReady.className = "control-btn started locked";
      showReadyHint(null);
    } else if (msg.type === "error") {
      showReadyHint(msg.message || "Command failed", true);
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

  function sendCommand(name, params) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      showReadyHint("Not connected", true);
      return;
    }
    const id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
    ws.send(JSON.stringify({ type: "command", id: id, name: name, params: params || {} }));
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
      acquireWakeLock();
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
      releaseWakeLock();
      reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  initMap();
  connect();

  els.btnSetPosition.addEventListener("click", function () {
    els.btnSetPosition.classList.add("pressed");
    window.setTimeout(function () {
      els.btnSetPosition.classList.remove("pressed");
    }, 200);
    sendCommand("set_position");
  });

  els.btnReady.addEventListener("click", function () {
    if (LOCKED_STATES.has(lastTestSequence && lastTestSequence.state)) {
      return;
    }
    if (lastTestSequence && lastTestSequence.ready) {
      sendCommand("ready");
      return;
    }
    const msg = (lastTestSequence && lastTestSequence.readyMessage) || "Not ready";
    showReadyHint(msg, true);
  });
})();

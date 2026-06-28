const fmt = (value, suffix = "") => value === null || value === undefined ? "--" : `${value}${suffix}`;

const els = {
  airTemp: document.querySelector("#air-temp"),
  airHumidity: document.querySelector("#air-humidity"),
  soilMoisture: document.querySelector("#soil-moisture"),
  soilTemp: document.querySelector("#soil-temp"),
  lightLux: document.querySelector("#light-lux"),
  waterLevel: document.querySelector("#water-level"),
  pumpState: document.querySelector("#pump-state"),
  fanState: document.querySelector("#fan-state"),
  lightState: document.querySelector("#light-state"),
  serialState: document.querySelector("#serial-state"),
  predictions: document.querySelector("#predictions"),
  alerts: document.querySelector("#alerts"),
  events: document.querySelector("#events"),
  waterCard: document.querySelector(".metric.danger"),
  modeAuto: document.querySelector("#mode-auto"),
  modeManual: document.querySelector("#mode-manual"),
};

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderStatus(data) {
  const latest = data.latest || {};
  const state = data.state || {};
  els.airTemp.textContent = fmt(latest.air_temp, " C");
  els.airHumidity.textContent = fmt(latest.air_humidity, " %");
  els.soilMoisture.textContent = fmt(latest.soil_moisture, " %");
  els.soilTemp.textContent = fmt(latest.soil_temp, " C");
  els.lightLux.textContent = fmt(latest.light_lux, " lx");
  els.waterLevel.textContent = latest.water_level || "--";
  els.pumpState.textContent = state.pump || "--";
  els.fanState.textContent = state.fan || "--";
  els.lightState.textContent = state.light || "0";
  els.serialState.textContent = data.serial_connected ? "Serial" : "Simulator";
  els.waterCard.classList.toggle("low", latest.water_level === "low");

  els.modeAuto.classList.toggle("active", state.mode === "auto");
  els.modeManual.classList.toggle("active", state.mode === "manual");

  renderList(els.events, data.events || [], eventItem);
  renderList(els.alerts, data.alerts || [], alertItem);
  renderList(els.predictions, data.predictions || [], predictionItem);
}

function renderList(container, items, renderer) {
  container.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "item";
    empty.textContent = "기록 없음";
    container.appendChild(empty);
    return;
  }
  for (const item of items) container.appendChild(renderer(item));
}

function eventItem(item) {
  const node = document.createElement("div");
  node.className = "item";
  node.innerHTML = `<strong>${item.actuator} ${item.action}</strong><small>${item.timestamp} · ${item.source}</small><div>${item.reason || ""}</div>`;
  return node;
}

function alertItem(item) {
  const node = document.createElement("div");
  node.className = `item ${item.level || ""}`;
  node.innerHTML = `<strong>${item.level}</strong><small>${item.timestamp}</small><div>${item.message}</div>`;
  return node;
}

function predictionItem(item) {
  const node = document.createElement("div");
  node.className = "item";
  let prediction = {};
  try { prediction = JSON.parse(item.prediction); } catch {}
  node.innerHTML = `<strong>${item.model_name}</strong><small>${item.timestamp} · confidence ${fmt(item.confidence)}</small><div>${prediction.reason || prediction.label || ""}</div>`;
  return node;
}

async function loadStatus() {
  const res = await fetch("/api/status");
  renderStatus(await res.json());
}

async function loadHistory() {
  const res = await fetch("/api/history?hours=24");
  const {items} = await res.json();
  drawChart(items || []);
}

function drawChart(items) {
  const canvas = document.querySelector("#history-chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#fbfcfb";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#dce4dd";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = 30 + i * ((h - 60) / 4);
    ctx.beginPath();
    ctx.moveTo(40, y);
    ctx.lineTo(w - 20, y);
    ctx.stroke();
  }
  plotLine(ctx, items, "soil_moisture", "#2f7d57", 0, 100, w, h);
  plotLine(ctx, items, "air_temp", "#b27720", 0, 45, w, h);
  ctx.fillStyle = "#65716a";
  ctx.font = "14px system-ui";
  ctx.fillText("soil moisture", 48, 22);
  ctx.fillStyle = "#b27720";
  ctx.fillText("air temp", 164, 22);
}

function plotLine(ctx, items, key, color, min, max, w, h) {
  const vals = items.filter(x => x[key] !== null && x[key] !== undefined);
  if (vals.length < 2) return;
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.beginPath();
  vals.forEach((item, idx) => {
    const x = 40 + idx * ((w - 60) / Math.max(1, vals.length - 1));
    const y = h - 30 - ((Number(item[key]) - min) / (max - min)) * (h - 60);
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

document.querySelector("#mode-auto").addEventListener("click", () => postJson("/api/mode", {mode: "auto"}).then(loadStatus));
document.querySelector("#mode-manual").addEventListener("click", () => postJson("/api/mode", {mode: "manual"}).then(loadStatus));
document.querySelector("#pump-on").addEventListener("click", () => postJson("/api/control/pump", {action: "on", duration_ms: 5000}).then(loadStatus));
document.querySelector("#pump-off").addEventListener("click", () => postJson("/api/control/pump", {action: "off"}).then(loadStatus));
document.querySelector("#fan-on").addEventListener("click", () => postJson("/api/control/fan", {action: "on"}).then(loadStatus));
document.querySelector("#fan-off").addEventListener("click", () => postJson("/api/control/fan", {action: "off"}).then(loadStatus));
document.querySelector("#light-on").addEventListener("click", () => {
  const value = Number(document.querySelector("#light-value").value);
  postJson("/api/control/light", {action: "on", value}).then(loadStatus);
});
document.querySelector("#light-off").addEventListener("click", () => postJson("/api/control/light", {action: "off", value: 0}).then(loadStatus));
document.querySelector("#refresh-history").addEventListener("click", loadHistory);

document.querySelector("#image-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = document.querySelector("#image-file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("image", file);
  const res = await fetch("/api/camera/analyze", {method: "POST", body: form});
  document.querySelector("#disease-result").textContent = JSON.stringify(await res.json(), null, 2);
  await loadStatus();
});

const stream = new EventSource("/api/stream");
stream.addEventListener("status", event => renderStatus(JSON.parse(event.data)));

loadStatus();
loadHistory();
setInterval(loadHistory, 60000);

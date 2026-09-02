const TYPE_LABELS = {
  uwsgi: "uWSGI",
  rabbitmq: "RabbitMQ",
  http_error: "HTTP Error",
  grafana: "Grafana",
  generic: "Generic",
};

let currentFilter = "all";

function getSinceMinutes() {
  return document.getElementById("time-range").value;
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return res;
}

async function fetchStats() {
  const params = new URLSearchParams({ since_minutes: getSinceMinutes() });
  const res = await apiFetch(`/api/stats?${params}`);
  return res.json();
}

async function fetchAlerts(type = null, status = null) {
  const params = new URLSearchParams({ since_minutes: getSinceMinutes() });
  if (type) params.set("alert_type", type);
  if (status) params.set("status", status);
  const res = await apiFetch(`/api/alerts?${params}`);
  return res.json();
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString();
}

function truncate(text, len = 180) {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "…" : text;
}

function renderAlertCard(alert) {
  const meta = [];
  if (alert.agent) meta.push(`<span>Agent: <strong>${alert.agent}</strong></span>`);
  if (alert.container) meta.push(`<span>Container: <strong>${alert.container}</strong></span>`);
  if (alert.server) meta.push(`<span>Server: <strong>${alert.server}</strong></span>`);
  if (alert.queue) meta.push(`<span>Queue: <strong>${alert.queue}</strong></span>`);
  if (alert.metric) meta.push(`<span>HTTP <strong>${alert.metric}</strong></span>`);
  if (alert.count != null) meta.push(`<span>Count: <strong>${alert.count}</strong></span>`);
  if (alert.threshold != null) meta.push(`<span>Threshold: <strong>${alert.threshold}</strong></span>`);

  return `
    <article class="alert-card ${alert.status}" data-id="${alert.id}">
      <div class="alert-header">
        <div class="alert-badges">
          <span class="type-badge ${alert.alert_type}">${TYPE_LABELS[alert.alert_type] || alert.alert_type}</span>
          <span class="severity-badge ${alert.severity}">${alert.severity}</span>
          <span class="status-badge ${alert.status}">${alert.status}</span>
        </div>
        <span class="alert-time">${formatTime(alert.created_at)}</span>
      </div>
      <h4 class="alert-title">${escapeHtml(alert.title)}</h4>
      <p class="alert-message">${escapeHtml(truncate(alert.message))}</p>
      ${meta.length ? `<div class="alert-meta">${meta.join("")}</div>` : ""}
      ${alert.resolution ? `<div class="alert-meta"><span>Resolution: <strong>${escapeHtml(alert.resolution)}</strong></span></div>` : ""}
      <div class="alert-actions">
        <button onclick="event.stopPropagation(); updateStatus(${alert.id}, 'acknowledged')">Ack</button>
        <button onclick="event.stopPropagation(); updateStatus(${alert.id}, 'resolved')">Resolve</button>
      </div>
    </article>
  `;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderAlerts(alerts) {
  const container = document.getElementById("alerts-container");
  const empty = document.getElementById("empty-state");

  if (!alerts.length) {
    container.innerHTML = "";
    empty.classList.remove("hidden");
    document.getElementById("alert-count").textContent = "0 alerts";
    return;
  }

  empty.classList.add("hidden");
  container.innerHTML = alerts.map(renderAlertCard).join("");
  document.getElementById("alert-count").textContent = `${alerts.length} alert${alerts.length === 1 ? "" : "s"}`;

  container.querySelectorAll(".alert-card").forEach((card) => {
    card.addEventListener("click", () => showDetail(parseInt(card.dataset.id, 10)));
  });
}

function renderStats(stats) {
  document.getElementById("stat-total").textContent = stats.total;
  document.getElementById("stat-firing").textContent = stats.firing;
  document.getElementById("stat-uwsgi").textContent = stats.by_type.uwsgi || 0;
  document.getElementById("stat-rabbitmq").textContent = stats.by_type.rabbitmq || 0;
  document.getElementById("stat-http").textContent = stats.by_type.http_error || 0;
  document.getElementById("stat-grafana").textContent = stats.by_type.grafana || 0;
}

function updateTimeLabel() {
  const select = document.getElementById("time-range");
  const label = document.getElementById("time-range-label");
  if (select && label) {
    label.textContent = select.options[select.selectedIndex].text;
  }
}

async function loadDashboard() {
  try {
    const [stats, alertsData] = await Promise.all([
      fetchStats(),
      getFilteredAlerts(),
    ]);
    renderStats(stats);
    renderAlerts(alertsData.alerts);
  } catch (err) {
    console.error("Dashboard load failed:", err);
  }
}

async function getFilteredAlerts() {
  if (currentFilter === "all") return fetchAlerts();
  if (currentFilter === "firing") return fetchAlerts(null, "firing");
  return fetchAlerts(currentFilter);
}

async function updateStatus(id, status) {
  await apiFetch(`/api/alerts/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  loadDashboard();
}

async function showDetail(id) {
  const res = await apiFetch(`/api/alerts/${id}`);
  const alert = await res.json();
  const modal = document.getElementById("modal");
  const body = document.getElementById("modal-body");

  const fields = [
    ["Type", TYPE_LABELS[alert.alert_type]],
    ["Severity", alert.severity],
    ["Status", alert.status],
    ["Source", alert.source],
    ["Agent", alert.agent],
    ["Container", alert.container],
    ["Server", alert.server],
    ["Queue", alert.queue],
    ["Metric", alert.metric],
    ["Count", alert.count],
    ["Threshold", alert.threshold],
    ["Resolution", alert.resolution],
    ["Created", formatTime(alert.created_at)],
  ].filter(([, v]) => v != null && v !== "");

  body.innerHTML = `
    <div class="modal-detail">
      <h2>${escapeHtml(alert.title)}</h2>
      <div class="alert-badges">
        <span class="type-badge ${alert.alert_type}">${TYPE_LABELS[alert.alert_type]}</span>
        <span class="severity-badge ${alert.severity}">${alert.severity}</span>
      </div>
      <dl class="detail-grid">
        ${fields.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(String(v))}</dd>`).join("")}
      </dl>
      <p>${escapeHtml(alert.message)}</p>
      ${alert.raw_payload ? `<h3 style="margin:16px 0 8px;font-size:13px;color:var(--muted)">Raw payload</h3><pre>${escapeHtml(alert.raw_payload)}</pre>` : ""}
    </div>
  `;
  modal.classList.remove("hidden");
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;

    const titles = {
      all: "All Alerts",
      firing: "Firing Alerts",
      uwsgi: "uWSGI Alerts",
      rabbitmq: "RabbitMQ Alerts",
      http_error: "HTTP Error Alerts",
      grafana: "Grafana Alerts",
    };
    document.getElementById("section-title").textContent = titles[currentFilter] || "Alerts";
    loadDashboard();
  });
});

document.getElementById("time-range").addEventListener("change", () => {
  updateTimeLabel();
  loadDashboard();
});
document.getElementById("refresh-btn").addEventListener("click", loadDashboard);
document.getElementById("modal-close").addEventListener("click", () => {
  document.getElementById("modal").classList.add("hidden");
});
document.querySelector(".modal-backdrop").addEventListener("click", () => {
  document.getElementById("modal").classList.add("hidden");
});

const base = window.location.origin;
document.getElementById("webhook-url").textContent = base + "/webhook";

updateTimeLabel();
loadDashboard();
setInterval(loadDashboard, 15000);

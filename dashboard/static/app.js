/**
 * ENI Enterprise Admin Dashboard — Application JS
 * ================================================
 * Zero-dependency vanilla JS dashboard with auto-refresh.
 * Polls API endpoints every few seconds, renders cards, and handles
 * feature-flag toggling.
 */

(function () {
    "use strict";

    // ── Configuration ──────────────────────────────────────────────────────
    const CONFIG = {
        REFRESH_INTERVAL_MS: 5000,
        API_BASE: "/api",
        ENDPOINTS: {
            health: "/api/health",
            modules: "/api/modules",
            agents: "/api/agents",
            incidents: "/api/incidents",
            resources: "/api/resources",
            tenants: "/api/tenants",
            compliance: "/api/compliance",
            features: "/api/feature-flags",
        },
        SEVERITY_ORDER: { critical: 0, high: 1, medium: 2, low: 3 },
    };

    // ── State ──────────────────────────────────────────────────────────────
    let refreshTimer = null;
    let lastFetchTime = null;
    let fetchLatency = 0;

    // ── Utilities ──────────────────────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);
    const fmt = (n, decimals) => Number(n).toFixed(decimals ?? 1);
    const el = (tag, attrs, ...children) => {
        const e = document.createElement(tag);
        if (attrs) Object.entries(attrs).forEach(([k, v]) => {
            if (k === "class") e.className = v;
            else if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
            else e.setAttribute(k, v);
        });
        children.forEach(c => {
            if (typeof c === "string") e.appendChild(document.createTextNode(c));
            else if (c) e.appendChild(c);
        });
        return e;
    };

    function timeAgo(isoStr) {
        if (!isoStr) return "--";
        const diff = Date.now() - new Date(isoStr).getTime();
        const secs = Math.floor(diff / 1000);
        if (secs < 60) return `${secs}s ago`;
        if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
        if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
        return `${Math.floor(secs / 86400)}d ago`;
    }

    function formatDuration(minutes) {
        if (minutes == null) return "--";
        if (minutes < 60) return `${minutes}m`;
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return `${h}h ${m}m`;
    }

    // ── Toast Notifications ────────────────────────────────────────────────
    function toast(msg, type) {
        type = type || "info";
        const container = $(".toast-container") || (() => {
            const c = el("div", { class: "toast-container" });
            document.body.appendChild(c);
            return c;
        })();
        const t = el("div", { class: `toast ${type}` }, msg);
        container.appendChild(t);
        setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity 0.3s"; setTimeout(() => t.remove(), 300); }, 3500);
    }

    // ── API Fetch ──────────────────────────────────────────────────────────
    async function fetchJSON(url) {
        const start = performance.now();
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            fetchLatency = Math.round(performance.now() - start);
            lastFetchTime = new Date();
            return data;
        } catch (err) {
            console.error(`[Dashboard] fetch failed: ${url}`, err);
            return null;
        }
    }

    // ── Render: Header ─────────────────────────────────────────────────────
    function updateHeader(health) {
        const dot = $(".status-dot");
        const text = $("#header-status-text");
        const badge = $("#health-badge");

        dot.className = `status-dot ${health.overall}`;
        text.textContent = health.overall === "healthy"
            ? "All Systems Operational"
            : health.overall === "degraded"
            ? "Degraded Performance"
            : "System Outage Detected";
        badge.textContent = health.overall.toUpperCase();
        badge.className = `card-badge ${health.overall}`;
    }

    function updateClock() {
        $("#header-clock").textContent = new Date().toLocaleTimeString("en-US", {
            hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
        });
    }

    // ── Render: Health Metrics ─────────────────────────────────────────────
    function renderHealthMetrics(health) {
        $("#metric-uptime").textContent = health.uptime_human || "--";
        $("#metric-modules").textContent = `${health.modules_healthy}/${health.modules_total}`;
        $("#metric-modules").className = `health-metric-value ${health.modules_degraded > 0 ? "degraded" : "healthy"}`;
        $("#metric-agents").textContent = `${health.agents_active}/${health.agents_total}`;
        $("#metric-incidents").textContent = health.open_incidents;
        $("#metric-incidents").className = `health-metric-value ${health.open_incidents > 0 ? "degraded" : ""}`;
        $("#metric-alerts").textContent = health.alerts_24h;
    }

    // ── Render: Resources ──────────────────────────────────────────────────
    function renderResources(res) {
        const cpu = res.cpu;
        const mem = res.memory;
        const gpu = res.gpu;
        const disk = res.disk;
        const net = res.network;

        $("#res-cpu").style.width = `${cpu.percent}%`;
        $("#res-cpu-val").textContent = `${fmt(cpu.percent)}%`;
        $("#res-mem").style.width = `${mem.percent}%`;
        $("#res-mem-val").textContent = `${fmt(mem.percent)}%`;
        $("#res-gpu").style.width = `${gpu.utilization_pct}%`;
        $("#res-gpu-val").textContent = `${fmt(gpu.utilization_pct)}%`;
        $("#res-disk").style.width = `${disk.percent}%`;
        $("#res-disk-val").textContent = `${fmt(disk.percent)}%`;

        $("#resource-details").innerHTML =
            `<span>Load: ${cpu.load_avg.join(" / ")}</span> &nbsp;|&nbsp; ` +
            `<span>Mem: ${mem.used_gb}/${mem.total_gb} GB</span> &nbsp;|&nbsp; ` +
            `<span>GPU: ${gpu.count}x ${gpu.device} · ${gpu.memory_used_gb}/${gpu.memory_total_gb} GB · ${gpu.temperature_c}°C</span> &nbsp;|&nbsp; ` +
            `<span>Net: ↓${net.rx_mbps} ↑${net.tx_mbps} Mbps · ${net.connections} conn</span>`;
    }

    // ── Render: Module Grid ────────────────────────────────────────────────
    function renderModules(modules) {
        const grid = $("#module-grid");
        const sorted = [...modules].sort((a, b) => {
            const order = { healthy: 0, degraded: 1, down: 2 };
            return (order[a.status] ?? 3) - (order[b.status] ?? 3);
        });

        grid.innerHTML = "";
        sorted.forEach(m => {
            const card = el("div", { class: "module-card" },
                el("div", { class: "module-card-header" },
                    el("span", { class: "module-card-name" }, m.name),
                    el("span", { class: `module-status-dot ${m.status}` })
                ),
                el("div", { class: "module-card-meta" },
                    el("span", null, `v${m.version} · ${fmt(m.uptime_pct, 2)}%`),
                    m.alert_count > 0 ? el("span", { class: "module-card-alert" }, `⚠ ${m.alert_count}`) : null
                ),
                el("div", { class: "module-card-meta" },
                    el("span", null, `${fmt(m.metrics.latency_ms)}ms · ${fmt(m.metrics.error_rate, 2)}% err · ${m.metrics.throughput_rps} rps`)
                )
            );
            grid.appendChild(card);
        });

        const degraded = modules.filter(m => m.status === "degraded" || m.status === "down").length;
        $("#modules-meta").textContent = degraded > 0 ? `${degraded} degraded` : "All healthy";
    }

    // ── Render: Agent List ─────────────────────────────────────────────────
    function renderAgents(agents) {
        const list = $("#agent-list");
        const sorted = [...agents].sort((a, b) => {
            const order = { active: 0, busy: 1, idle: 2, offline: 3 };
            return (order[a.status] ?? 4) - (order[b.status] ?? 4);
        });

        list.innerHTML = "";
        sorted.forEach(a => {
            const initials = a.name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
            const row = el("div", { class: "agent-row" },
                el("div", { class: "agent-info" },
                    el("span", { class: `agent-avatar ${a.status}` }, initials),
                    el("div", null,
                        el("div", { class: "agent-name" }, a.name),
                        el("div", { class: "agent-role" }, `${a.role} · ${a.status}`)
                    )
                ),
                el("div", { class: "agent-role" }, `${a.tasks_active > 0 ? a.tasks_active + " tasks · " : ""}${timeAgo(a.last_heartbeat)}`)
            );
            list.appendChild(row);
        });

        const active = agents.filter(a => a.status === "active" || a.status === "busy").length;
        $("#agents-meta").textContent = `${active}/${agents.length} active`;
    }

    // ── Render: Incidents ──────────────────────────────────────────────────
    function renderIncidents(incidents) {
        const list = $("#incident-list");
        const sorted = [...incidents].sort((a, b) =>
            (CONFIG.SEVERITY_ORDER[a.severity] ?? 99) - (CONFIG.SEVERITY_ORDER[b.severity] ?? 99)
        );

        list.innerHTML = "";
        sorted.slice(0, 8).forEach(inc => {
            const row = el("div", { class: `incident-row severity-${inc.severity}` },
                el("span", { class: `incident-severity ${inc.severity}` }, inc.severity),
                el("div", { class: "incident-body" },
                    el("div", { class: "incident-title" }, inc.title),
                    el("div", { class: "incident-meta" }, `${inc.module} · ${timeAgo(inc.detected)} · ${formatDuration(inc.duration_minutes)}`)
                ),
                el("span", { class: `incident-status ${inc.status}` }, inc.status)
            );
            list.appendChild(row);
        });
    }

    // ── Render: Compliance ─────────────────────────────────────────────────
    function renderCompliance(compliance) {
        const grid = $("#compliance-grid");
        const frameworks = compliance.frameworks;
        $("#compliance-score").textContent = compliance.overall_score;

        grid.innerHTML = "";
        Object.entries(frameworks).forEach(([key, fw]) => {
            const row = el("div", { class: "compliance-row" },
                el("span", { class: "compliance-name" }, fw.name),
                el("span", { class: `compliance-status ${fw.status}` }, fw.status.replace("_", " ")),
                el("span", { class: "compliance-score-small" }, `${fw.score}%`)
            );
            grid.appendChild(row);
        });

        // Update footer compliance metric
        $("#metric-compliance").textContent = `${compliance.overall_score}%`;
    }

    // ── Render: Tenants ────────────────────────────────────────────────────
    function renderTenants(tenants) {
        const list = $("#tenant-list");

        list.innerHTML = "";
        tenants.forEach(t => {
            const row = el("div", { class: "tenant-row" },
                el("div", { class: "tenant-info" },
                    el("div", { class: "tenant-name" }, t.name),
                    el("span", { class: `tenant-tier ${t.tier}` }, `${t.tier} · ${t.status}`)
                ),
                el("div", { class: "tenant-stats" },
                    el("div", null, `${t.users.toLocaleString()} users`),
                    el("div", null, `${t.agents_deployed} agents · ${(t.api_calls_24h / 1000).toFixed(1)}k calls`)
                )
            );
            list.appendChild(row);
        });

        const active = tenants.filter(t => t.status === "active").length;
        $("#tenants-meta").textContent = `${active}/${tenants.length} active`;
    }

    // ── Render: Feature Flags ──────────────────────────────────────────────
    function renderFeatureFlags(features) {
        const grid = $("#feature-grid");
        const flags = features.flags;

        grid.innerHTML = "";
        Object.entries(flags).forEach(([key, flag]) => {
            const card = el("div", { class: "feature-card", "data-flag": key },
                el("div", { class: "feature-card-header" },
                    el("span", { class: "feature-card-name" }, flag.name),
                    el("div", { class: `feature-toggle ${flag.enabled ? "on" : "off"}` })
                ),
                el("div", { class: "feature-card-meta" }, `key: ${key}`),
                el("div", { class: "feature-rollout" }, `Rollout: ${flag.rollout_pct}%`)
            );

            card.addEventListener("click", async () => {
                try {
                    const res = await fetch(`${CONFIG.API_BASE}/feature-flags/${key}/toggle`, { method: "POST" });
                    if (!res.ok) throw new Error("Toggle failed");
                    const updated = await res.json();
                    flag.enabled = updated.enabled;
                    const toggle = card.querySelector(".feature-toggle");
                    toggle.className = `feature-toggle ${updated.enabled ? "on" : "off"}`;
                    toast(`${flag.name}: ${updated.enabled ? "ENABLED" : "DISABLED"}`, "success");
                    updateFeatureMeta(features);
                } catch (err) {
                    toast(`Failed to toggle ${flag.name}`, "error");
                }
            });

            grid.appendChild(card);
        });

        updateFeatureMeta(features);
    }

    function updateFeatureMeta(features) {
        const flags = features.flags;
        const total = Object.keys(flags).length;
        const enabled = Object.values(flags).filter(f => f.enabled).length;
        $("#features-meta").textContent = `${enabled}/${total} enabled`;
    }

    // ── Render: Footer ─────────────────────────────────────────────────────
    function updateFooter() {
        const now = new Date();
        $("#footer-last-update").textContent = `Last updated: ${now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}`;
        $("#footer-latency").textContent = `Latency: ${fetchLatency}ms`;
    }

    // ── Data Fetching ──────────────────────────────────────────────────────
    async function fetchAll() {
        const [health, modules, agents, incidents, resources, tenants, compliance, features] = await Promise.all([
            fetchJSON(CONFIG.ENDPOINTS.health),
            fetchJSON(CONFIG.ENDPOINTS.modules),
            fetchJSON(CONFIG.ENDPOINTS.agents),
            fetchJSON(CONFIG.ENDPOINTS.incidents),
            fetchJSON(CONFIG.ENDPOINTS.resources),
            fetchJSON(CONFIG.ENDPOINTS.tenants),
            fetchJSON(CONFIG.ENDPOINTS.compliance),
            fetchJSON(CONFIG.ENDPOINTS.features),
        ]);

        const results = { health, modules, agents, incidents, resources, tenants, compliance, features };
        const failures = Object.entries(results).filter(([, v]) => v === null);

        if (failures.length > 3) {
            console.warn("[Dashboard] Multiple endpoints failed:", failures.map(f => f[0]));
            return;
        }

        if (health) {
            updateHeader(health);
            renderHealthMetrics(health);
        }
        if (modules) renderModules(modules.modules);
        if (agents) renderAgents(agents.agents);
        if (incidents) renderIncidents(incidents.incidents);
        if (resources) renderResources(resources);
        if (tenants) renderTenants(tenants.tenants);
        if (compliance) renderCompliance(compliance);
        if (features) renderFeatureFlags(features);
        updateFooter();
    }

    // ── SSE Connection (optional real-time stream) ─────────────────────────
    function connectSSE() {
        const evtSource = new EventSource("/api/events/stream");
        evtSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                // Update just the header status dot and resource bars from SSE
                const dot = $(".status-dot");
                dot.className = `status-dot ${data.health}`;
                if (data.cpu_pct != null) {
                    $("#res-cpu").style.width = `${data.cpu_pct}%`;
                    $("#res-cpu-val").textContent = `${fmt(data.cpu_pct)}%`;
                }
                if (data.memory_pct != null) {
                    $("#res-mem").style.width = `${data.memory_pct}%`;
                    $("#res-mem-val").textContent = `${fmt(data.memory_pct)}%`;
                }
                if (data.gpu_pct != null) {
                    $("#res-gpu").style.width = `${data.gpu_pct}%`;
                    $("#res-gpu-val").textContent = `${fmt(data.gpu_pct)}%`;
                }
            } catch (e) { /* ignore malformed SSE */ }
        };
        evtSource.onerror = () => {
            // SSE failed, we'll rely on polling
            evtSource.close();
        };
    }

    // ── Refresh Loop ───────────────────────────────────────────────────────
    function startRefresh() {
        fetchAll();
        refreshTimer = setInterval(fetchAll, CONFIG.REFRESH_INTERVAL_MS);
    }

    function stopRefresh() {
        if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    }

    // ── Event Listeners ────────────────────────────────────────────────────
    $("#btn-refresh").addEventListener("click", () => {
        fetchAll();
        toast("Dashboard refreshed", "info");
    });

    $("#btn-theme").addEventListener("click", () => {
        document.body.classList.toggle("light-theme");
        toast("Theme toggled (light theme WIP)", "info");
    });

    // Clock update every second
    setInterval(updateClock, 1000);

    // Handle visibility change - pause when tab hidden
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopRefresh();
        } else {
            fetchAll();
            startRefresh();
        }
    });

    // ── Init ───────────────────────────────────────────────────────────────
    updateClock();
    startRefresh();
    connectSSE();

    console.log("%c ENI Enterprise Dashboard %c v1.0.0 %c Ready",
        "color: #00d4ff; font-weight: bold; font-size: 1.1em;",
        "color: #8888a0;",
        "color: #22c55e;");
})();
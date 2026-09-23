(function ($) {
  "use strict";

  const config = window.KPI_CONFIG || {};
  const API_BASE = config.apiBase || "/api/v1";
  const TOKEN_KEY = "kpi_access_token";
  const USER_KEY = "kpi_user";
  const EXP_KEY = "kpi_token_expires_at";
  const state = {
    page: $("body").data("page"),
    user: null,
    catalogs: null,
    charts: {},
    googlePromise: null,
    jobPollTimer: null,
  };

  const pageMeta = {
    atm: {
      title: "ATM Network Operations & Cash Monitoring:",
      subtitle: "Dominican Republic",
      active: "atm",
      typeLabel: "ATM Type",
      typeValues: "tipos_atm",
      loader: loadAtmPage,
    },
    branches: {
      title: "Bank Branch Operations & Queue Management:",
      subtitle: "Dominican Republic",
      active: "branches",
      typeLabel: "Branch View",
      typeValues: null,
      loader: loadBranchPage,
    },
    planning: {
      title: "Branch Location Planning & Geospatial Analytics:",
      subtitle: "Dominican Republic",
      active: "planning",
      typeLabel: "Location Type",
      typeValues: "tipos_ubicacion",
      loader: loadPlanningPage,
    },
    subagents: {
      title: "Subagent Network & Partner Coverage:",
      subtitle: "Dominican Republic",
      active: "subagents",
      typeLabel: "",
      typeValues: null,
      showDate: false,
      loader: loadSubagentPage,
    },
    jobs: {
      title: "Data Synchronization Jobs:",
      subtitle: "Banco BHD",
      active: "jobs",
      typeLabel: "",
      typeValues: null,
      hideFilters: true,
      loader: loadJobsPage,
    },
  };

  const navItems = [
    ["atm", "/dashboard/atm.html", "bi-house-door", "ATM Operations"],
    ["branches", "/dashboard/branches.html", "bi-diagram-3", "Branch Operations"],
    ["subagents", "/dashboard/subagents.html", "bi-shop", "Subagentes"],
    ["planning", "/dashboard/planning.html", "bi-globe-americas", "Geospatial Analytics"],
    ["jobs", "/dashboard/jobs.html", "bi-arrow-repeat", "Jobs"],
    ["docs", "/docs", "bi-file-earmark-code", "API Docs"],
  ];

  const colors = {
    primary: "#35C83E",
    primaryHover: "#45D64E",
    secondary: "#C6CEC6",
    muted: "#929C92",
    icon: "#65BD63",
    iconBackground: "#293329",
    danger: "#E06C75",
    amber: "#D8B44C",
    darkGrid: "rgba(198,206,198,0.12)",
    text: "#F4F7F4",
  };

  $(function () {
    if (state.page === "login") {
      initLogin();
      return;
    }
    initDashboard();
  });

  function token() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(EXP_KEY);
  }

  function redirectToLogin() {
    clearSession();
    window.location.href = "/dashboard/";
  }

  function api(path, params, options) {
    const opts = options || {};
    const headers = opts.headers || {};
    if (token()) {
      headers.Authorization = "Bearer " + token();
    }
    return $.ajax({
      url: API_BASE + path,
      method: opts.method || "GET",
      data: params || undefined,
      contentType: opts.contentType,
      headers,
    }).fail(function (xhr) {
      if (xhr.status === 401) {
        redirectToLogin();
      }
    });
  }

  function initLogin() {
    if (token()) {
      window.location.href = "/dashboard/atm.html";
      return;
    }

    $("#login-form").on("submit", function (event) {
      event.preventDefault();
      const $form = $(this);
      const $button = $form.find("button");
      const $error = $("#login-error");
      $button.prop("disabled", true);
      $error.text("");

      $.ajax({
        url: API_BASE + "/auth/login",
        method: "POST",
        data: {
          username: $form.find("[name=username]").val(),
          password: $form.find("[name=password]").val(),
        },
      })
        .then(function (result) {
          localStorage.setItem(TOKEN_KEY, result.access_token);
          localStorage.setItem(EXP_KEY, String(Date.now() + result.expires_in * 1000));
          return api("/auth/me");
        })
        .then(function (user) {
          localStorage.setItem(USER_KEY, JSON.stringify(user));
          window.location.href = "/dashboard/atm.html";
        })
        .fail(function (xhr) {
          const message = xhr.responseJSON && xhr.responseJSON.detail
            ? xhr.responseJSON.detail
            : "No se pudo iniciar sesion.";
          $error.text(message);
        })
        .always(function () {
          $button.prop("disabled", false);
        });
    });
  }

  async function initDashboard() {
    if (!token()) {
      redirectToLogin();
      return;
    }
    buildSidebar();
    buildTopbar();
    bindControls();
    setLoading();

    try {
      const saved = localStorage.getItem(USER_KEY);
      state.user = saved ? JSON.parse(saved) : await api("/auth/me");
      localStorage.setItem(USER_KEY, JSON.stringify(state.user));
      hydrateUser();
      state.catalogs = await api("/catalogs/filters");
      hydrateFilters();
      await refreshPage();
    } catch (error) {
      showNotice("No se pudo cargar el dashboard. Revisa la API y la sesion.");
    }
  }

  function buildSidebar() {
    const meta = pageMeta[state.page];
    const links = navItems
      .map(function (item) {
        const isActive = item[0] === meta.active ? " active" : "";
        return `<a class="nav-link${isActive}" href="${item[1]}"><i class="bi ${item[2]}"></i><span>${item[3]}</span></a>`;
      })
      .join("");
    $("#sidebar").html(`
      <div class="brand"><span class="brand-mark">BHD</span><span>BHD Leon</span></div>
      <nav class="nav-list">${links}</nav>
      <div class="sidebar-bottom">
        <a class="nav-link" href="/dashboard/atm.html"><i class="bi bi-gear"></i><span>Settings</span></a>
      </div>
    `);
  }

  function buildTopbar() {
    const meta = pageMeta[state.page];
    $("#topbar").html(`
      <div class="title-block">
        <h1>${meta.title}<strong>${meta.subtitle}</strong></h1>
        <p class="period" id="period-label">Period: loading...</p>
      </div>
      <div class="top-actions">
        <div class="filter-group">
          <label for="filter-region">Region</label>
          <select id="filter-region" class="filter-select"><option value="">All regions</option></select>
        </div>
        <div class="filter-group">
          <label for="filter-province">Province</label>
          <select id="filter-province" class="filter-select"><option value="">All provinces</option></select>
        </div>
        <div class="filter-group">
          <label for="filter-period">Date</label>
          <select id="filter-period" class="filter-select">
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="ytd">Current year</option>
            <option value="730">Last 24 months</option>
          </select>
        </div>
        <div class="filter-group" id="type-filter-group">
          <label for="filter-type">${meta.typeLabel}</label>
          <select id="filter-type" class="filter-select"><option value="">All</option></select>
        </div>
        <div class="user-pill"><i class="bi bi-person-circle"></i><span id="user-name">User</span></div>
        <button id="logout-button" class="icon-button" type="button" title="Logout"><i class="bi bi-box-arrow-right"></i></button>
      </div>
    `);
    if (!meta.typeValues) {
      $("#type-filter-group").hide();
    }
    if (meta.showDate === false) {
      $("#filter-period").closest(".filter-group").hide();
    }
    if (meta.hideFilters) {
      $(".filter-group").hide();
    }
  }

  function hydrateUser() {
    const name = state.user && state.user.full_name ? state.user.full_name : "User";
    $("#user-name").text(name);
  }

  function hydrateFilters() {
    const catalogs = state.catalogs || {};
    fillSelect("#filter-region", catalogs.regiones || [], "All regions");
    fillSelect(
      "#filter-province",
      (catalogs.provincias || []).map(function (item) { return item.nombre; }),
      "All provinces"
    );

    const typeKey = pageMeta[state.page].typeValues;
    if (typeKey) {
      fillSelect("#filter-type", catalogs[typeKey] || [], "All");
    }
  }

  function fillSelect(selector, values, firstLabel) {
    const options = [`<option value="">${escapeHtml(firstLabel)}</option>`].concat(
      values.map(function (value) {
        return `<option value="${escapeAttr(value)}">${escapeHtml(labelize(value))}</option>`;
      })
    );
    $(selector).html(options.join(""));
  }

  function bindControls() {
    $("#topbar").on("change", ".filter-select", function () {
      refreshPage();
    });
    $(".refresh-button").on("click", function () {
      refreshPage();
    });
    $("#subagent-search-form").on("submit", function (event) {
      event.preventDefault();
      refreshPage();
    });
    $("#run-bhd-job").on("click", startBhdJob);
    $("#logout-button").on("click", async function () {
      try {
        await api("/auth/logout", null, { method: "POST" });
      } finally {
        redirectToLogin();
      }
    });
  }

  async function refreshPage() {
    $("#notice").prop("hidden", true).text("");
    setLoading();
    try {
      await pageMeta[state.page].loader();
    } catch (error) {
      showNotice(readError(error));
    }
  }

  function filterParams(extra) {
    const params = Object.assign({}, periodParams(), extra || {});
    const region = $("#filter-region").val();
    const provincia = $("#filter-province").val();
    const tipo = $("#filter-type").val();
    if (region) params.region = region;
    if (provincia) params.provincia = provincia;
    if (tipo) params.tipo = tipo;
    return params;
  }

  function atmParams(extra) {
    const params = filterParams(extra);
    const tipo = $("#filter-type").val();
    if (tipo) params.tipo = tipo;
    return params;
  }

  function periodParams() {
    const value = $("#filter-period").val() || "30";
    if (value === "30") return {};

    const today = new Date();
    const desde = new Date(today.getTime());
    if (value === "ytd") {
      desde.setMonth(0, 1);
    } else {
      desde.setDate(today.getDate() - Number(value) + 1);
    }
    return {
      desde: formatDateOnly(desde),
      hasta: formatDateOnly(today),
    };
  }

  async function loadAtmPage() {
    const params = atmParams();
    const [summary, trends, cash, density, status, comparison, incidents, refills, geo] =
      await Promise.all([
        api("/metrics/summary", params),
        api("/metrics/atm-trends", Object.assign({}, params, { agrupacion: "day" })),
        api("/metrics/cash-trends", params),
        api("/metrics/network-density", params),
        api("/metrics/atms/status", Object.assign({}, params, { limit: 10 })),
        api("/competitors/comparison", stripType(params)),
        api("/incidents", { limit: 5 }),
        api("/logistics", { limit: 5 }),
        api("/geo/locations", Object.assign({}, params, { capa: "atms", limit: 200 })),
      ]);

    updatePeriod(summary.meta);
    renderKpis([
      stat("Total ATMs", formatInt(summary.total_atms), `${summary.atms_operando} operating`, trends.items, "transacciones"),
      stat("Network coverage", formatPct(summary.cobertura_provincias_pct), `${summary.provincias_cubiertas} provinces`, trends.items, "uptime_pct"),
      stat("Total transactions", formatCompact(summary.total_transacciones), `${summary.lecturas} readings`, trends.items, "transacciones"),
      stat("Average utilization", formatPct(summary.utilizacion_pct), "weighted by observed time", trends.items, "utilizacion_pct"),
    ]);
    renderMap("#network-map", geo.features, "atm");
    renderLegend("#atm-map-legend", [
      ["BHD Leon ATMs", colors.primary],
      ["Competitor ATMs", colors.muted],
      ["Coverage Heatmap", colors.icon, "background: radial-gradient(circle, #65BD63 0%, #35C83E 55%, #293329 100%);"]
    ]);
    renderCashChart(cash.items);
    renderDensityChart("#density-chart", density.items, "atms");
    renderTransactionChart(trends.items);
    renderAtmTable(status.items);
    renderComparison("#comparison-matrix", comparison.items, [
      ["ATMs", "total_atms"],
      ["Branch share", "cuota_sucursales_pct"],
      ["Trans. vol", "transacciones"],
      ["Deposits", "depositos"],
      ["Avg. util.", "utilizacion_pct"],
    ]);
    renderAtmAlerts(summary, incidents.items || [], refills.items || []);
  }

  async function loadBranchPage() {
    const params = filterParams();
    delete params.tipo;
    const [summary, trend, hourly, status, geo] = await Promise.all([
      api("/metrics/branches/summary", params),
      api("/metrics/branches/trends", Object.assign({}, params, { agrupacion: "day" })),
      api("/metrics/branches/hourly-traffic", params),
      api("/metrics/branches/status", Object.assign({}, params, { limit: 10 })),
      api("/geo/locations", Object.assign({}, params, { capa: "sucursales", limit: 200 })),
    ]);

    updatePeriod(summary.meta);
    renderKpis([
      stat("Average customer wait time", `${formatNumber(summary.espera_promedio_minutos)} min`, `${summary.clientes_atendidos} served`, trend.items, "espera_promedio_minutos"),
      stat("Branch SLA compliance", formatPct(summary.cumplimiento_sla_pct), `${summary.lecturas} readings`, trend.items, "cumplimiento_sla_pct"),
      stat("Teller utilization rate", formatPct(summary.utilizacion_cajeros_pct), "available teller time", trend.items, "cumplimiento_sla_pct"),
      stat("Total visitors", formatCompact(summary.total_visitantes), "selected period", trend.items, "visitantes"),
    ]);
    renderMap("#branch-map", geo.features, "branches");
    renderLegend("#branch-map-legend", [
      ["BHD Leon Branches", colors.primary],
      ["Competitor Branches", colors.muted],
      ["Coverage Heatmap", colors.icon, "background: radial-gradient(circle, #65BD63 0%, #35C83E 55%, #293329 100%);"]
    ]);
    renderHourlyChart(hourly.items);
    renderBranchTrendChart(trend.items);
    renderBranchTable(status.items);
    renderBranchAlerts(summary, status.items);
  }

  async function loadPlanningPage() {
    const params = filterParams();
    const geoParams = Object.assign({}, params, { capa: "todas", limit: 200 });
    const [summary, density, candidates, comparison, geo] = await Promise.all([
      api("/metrics/planning/summary", stripType(params)),
      api("/metrics/network-density", stripType(params)),
      api("/planning/candidates", Object.assign({}, params, { limit: 10, radio_km: 5 })),
      api("/competitors/comparison", stripType(params)),
      api("/geo/locations", geoParams),
    ]);

    updatePeriod(summary.meta);
    renderKpis([
      stat("Total branches", formatInt(summary.total_sucursales), `${summary.sucursales_con_saldos} with balances`, density.items, "sucursales"),
      stat("Network coverage", formatPct(summary.cobertura_provincias_pct), `${summary.provincias_cubiertas} provinces`, density.items, "sucursales"),
      stat("Market share", formatPct(summary.cuota_sucursales_pct), `${summary.total_sucursales} of ${summary.total_sucursales_mercado} observed branches`, comparison.items, "cuota_sucursales_pct"),
      stat("Total branch deposits", formatMoney(summary.total_depositos), "latest balance cut", comparison.items, "depositos"),
    ]);
    renderMap("#planning-map", geo.features, "planning");
    renderLegend("#planning-map-legend", [
      ["BHD Leon Network", colors.primary],
      ["Competitor", colors.muted],
      ["Candidate", colors.icon],
      ["Coverage Heatmap", colors.icon, "background: radial-gradient(circle, #65BD63 0%, #35C83E 55%, #293329 100%);"]
    ]);
    renderDensityChart("#planning-density-chart", density.items, "sucursales");
    renderCandidateTable(candidates.items);
    renderComparison("#planning-comparison-matrix", comparison.items, [
      ["Branches", "total_sucursales"],
      ["Market share", "cuota_sucursales_pct"],
      ["Avg. util.", "utilizacion_pct"],
    ]);
    renderPlanningAlerts(summary, candidates.items);
  }

  function inventoryParams(extra) {
    const params = Object.assign({}, extra || {});
    const region = $("#filter-region").val();
    const provincia = $("#filter-province").val();
    if (region) params.region = region;
    if (provincia) params.provincia = provincia;
    return params;
  }

  async function loadAllGeoFeatures(params) {
    let offset = 0;
    let total = 0;
    const features = [];
    do {
      const page = await api("/geo/locations", Object.assign({}, params, { limit: 200, offset }));
      total = page.total || 0;
      features.push.apply(features, page.features || []);
      offset += page.features ? page.features.length : 0;
    } while (offset < total && offset > 0);
    return { total, features };
  }

  async function loadSubagentPage() {
    const params = inventoryParams();
    const search = String($("#subagent-search").val() || "").trim();
    const listParams = Object.assign({}, params, { limit: 50 });
    if (search) listParams.search = search;
    const [summary, listing, geo] = await Promise.all([
      api("/subagents/summary", params),
      api("/subagents", listParams),
      loadAllGeoFeatures(Object.assign({}, params, { capa: "subagentes" })),
    ]);

    $("#period-label").text("Inventario oficial BHD · actualización bajo demanda");
    renderKpis([
      stat("Total subagentes", formatInt(summary.total), `${summary.activos} activos`),
      stat("Cobertura geográfica", formatInt(summary.provincias), "provincias representadas"),
      stat("Con coordenadas", formatInt(summary.con_coordenadas), `${summary.sin_coordenadas} sin punto geográfico`),
      stat("Horario extendido", formatInt(summary.horario_extendido), "según la fuente BHD"),
    ]);
    renderMap("#subagent-map", geo.features, "subagents");
    renderLegend("#subagent-map-legend", [["Subagentes BHD", colors.primary]]);
    $("#subagent-quality").html(`
      ${mini("Con coordenadas", summary.con_coordenadas, percentage(summary.con_coordenadas, summary.total), "ok")}
      ${mini("Sin coordenadas", summary.sin_coordenadas, percentage(summary.sin_coordenadas, summary.total), "warn")}
      ${mini("Horario extendido", summary.horario_extendido, percentage(summary.horario_extendido, summary.total), "ok")}
      <article class="mini-card"><span>Última actualización de fuente</span><strong class="mini-date">${escapeHtml(formatDateTime(summary.ultima_actualizacion_fuente))}</strong></article>
    `);
    $("#subagent-table-note").text(`${formatInt(listing.total)} resultados · mostrando hasta 50`);
    renderSubagentTable(listing.items || []);
  }

  async function startBhdJob() {
    const $button = $("#run-bhd-job");
    if ($button.prop("disabled")) return;
    $button.prop("disabled", true).html('<i class="bi bi-hourglass-split"></i> Iniciando...');
    try {
      await api("/jobs/bhd-locations", null, { method: "POST" });
      await loadJobsPage();
    } catch (error) {
      showNotice(readError(error));
      await loadJobsPage();
    }
  }

  async function loadJobsPage() {
    if (state.jobPollTimer) {
      window.clearTimeout(state.jobPollTimer);
      state.jobPollTimer = null;
    }
    const response = await api("/jobs", { limit: 30, job_key: "bhd_locations_sync" });
    const jobs = response.items || [];
    const active = jobs.find(function (job) {
      return job.status === "PENDING" || job.status === "RUNNING";
    });
    const latest = jobs[0] || null;
    const successes = jobs.filter(function (job) { return job.status === "SUCCEEDED"; }).length;
    const failures = jobs.filter(function (job) { return job.status === "FAILED"; }).length;
    const latestRows = latest && latest.result && latest.result.extraction
      ? latest.result.extraction.rows
      : 0;

    $("#period-label").text("Historial persistente de sincronizaciones");
    renderKpis([
      stat("Ejecuciones", formatInt(response.total), "sincronizaciones registradas"),
      stat("Completadas", formatInt(successes), "en las últimas 30 ejecuciones"),
      stat("Fallidas", formatInt(failures), failures ? "requieren revisión" : "sin errores recientes"),
      stat("Última extracción", formatInt(latestRows), "registros recibidos de BHD"),
    ]);
    renderCurrentJob(active || latest);
    renderJobsTable(jobs);

    const canRun = state.user && ["ADMIN", "OPERATOR"].includes(state.user.role);
    const $button = $("#run-bhd-job");
    $button
      .prop("disabled", !canRun || Boolean(active))
      .html(active
        ? '<i class="bi bi-arrow-repeat spin"></i> Actualización en curso'
        : '<i class="bi bi-play-fill"></i> Ejecutar actualización');
    $("#job-permission-note").text(
      canRun ? "Solo puede existir una sincronización activa." : "Tu rol permite consultar, pero no ejecutar jobs."
    );
    if (active) {
      state.jobPollTimer = window.setTimeout(function () {
        loadJobsPage().catch(function (error) { showNotice(readError(error)); });
      }, 2500);
    }
  }

  function setLoading() {
    $("#kpi-grid").html('<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>');
    $(".data-table").html("");
    $(".matrix").html('<div class="skeleton"></div>');
    $(".mini-stack").html('<div class="skeleton"></div>');
    $("#current-job").html('<div class="skeleton"></div>');
  }

  function showNotice(message) {
    $("#notice").prop("hidden", false).text(message);
  }

  function updatePeriod(meta) {
    if (!meta) return;
    $("#period-label").text(`Period: ${meta.desde} - ${meta.hasta}`);
  }

  function stat(title, value, note, series, key) {
    return { title, value, note, series: series || [], key };
  }

  function renderKpis(cards) {
    $("#kpi-grid").html(cards.map(function (card, index) {
      return `
        <article class="stat-card">
          <h2>${escapeHtml(card.title)}</h2>
          <div class="stat-value">${escapeHtml(card.value)}</div>
          <div class="stat-note"><i class="bi bi-activity"></i>${escapeHtml(card.note || "API data")}</div>
          <canvas id="spark-${index}"></canvas>
        </article>
      `;
    }).join(""));

    cards.forEach(function (card, index) {
      const values = (card.series || []).map(function (item) { return number(item[card.key]); });
      renderSpark(`spark-${index}`, values);
    });
  }

  function renderSpark(id, values) {
    if (!window.Chart || values.length === 0) return;
    renderChart(id, {
      type: "line",
      data: {
        labels: values.map(function (_, i) { return i + 1; }),
        datasets: [{
          data: values,
          borderColor: colors.primaryHover,
          backgroundColor: "rgba(53, 200, 62, 0.25)",
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.35,
        }],
      },
      options: sparkOptions(),
    });
  }

  function renderCashChart(items) {
    const grouped = groupBy(items, "provincia");
    const provinces = Object.keys(grouped).slice(0, 5);
    const labels = unique(items.map(function (item) { return item.periodo; }));
    const palette = [colors.primary, colors.icon, colors.primaryHover, colors.secondary, colors.muted];
    const datasets = provinces.map(function (province, index) {
      const byPeriod = indexBy(grouped[province], "periodo");
      return {
        label: province,
        data: labels.map(function (period) {
          return number((byPeriod[period] || {}).efectivo_promedio_pct);
        }),
        borderColor: palette[index],
        backgroundColor: palette[index],
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.3,
      };
    });
    renderChart("cash-chart", lineChart(labels, datasets, "%"));
  }

  function renderTransactionChart(items) {
    renderChart("transactions-chart", lineChart(
      items.map(function (item) { return compactPeriod(item.periodo); }),
      [{
        label: "Transactions",
        data: items.map(function (item) { return item.transacciones; }),
        borderColor: colors.primaryHover,
        backgroundColor: "rgba(53,200,62,0.28)",
        fill: true,
        pointRadius: 0,
        tension: 0.3,
      }],
      ""
    ));
  }

  function renderBranchTrendChart(items) {
    renderChart("branch-trend-chart", lineChart(
      items.map(function (item) { return compactPeriod(item.periodo); }),
      [
        {
          label: "SLA %",
          data: items.map(function (item) { return item.cumplimiento_sla_pct; }),
          borderColor: colors.icon,
          backgroundColor: "rgba(101,189,99,0.18)",
          pointRadius: 0,
          tension: 0.3,
          yAxisID: "y",
        },
        {
          label: "Wait min",
          data: items.map(function (item) { return item.espera_promedio_minutos; }),
          borderColor: colors.primaryHover,
          backgroundColor: "rgba(53,200,62,0.2)",
          pointRadius: 0,
          tension: 0.3,
          yAxisID: "y1",
        },
      ],
      ""
    ));
  }

  function renderHourlyChart(items) {
    renderChart("hourly-chart", {
      type: "bar",
      data: {
        labels: items.map(function (item) { return hourLabel(item.hora); }),
        datasets: [{
          label: "Visitors",
          data: items.map(function (item) { return item.visitantes; }),
          backgroundColor: "rgba(53,200,62,0.88)",
          borderColor: colors.primaryHover,
          borderWidth: 1,
        }],
      },
      options: chartOptions(),
    });
  }

  function renderDensityChart(selector, items, key) {
    const id = selector.replace("#", "");
    const sorted = (items || []).slice().sort(function (a, b) {
      return number(b[key]) - number(a[key]);
    }).slice(0, 6);
    renderChart(id, {
      type: "bar",
      data: {
        labels: sorted.map(function (item) { return shortProvince(item.provincia); }),
        datasets: [{
          label: key === "atms" ? "ATMs" : "Branches",
          data: sorted.map(function (item) { return item[key]; }),
          backgroundColor: "rgba(53,200,62,0.9)",
          borderColor: colors.primaryHover,
          borderWidth: 1,
        }],
      },
      options: chartOptions(),
    });
  }

  function renderAtmTable(items) {
    const rows = items.map(function (item) {
      return `
        <tr>
          <td>${escapeHtml(item.codigo_unico)}</td>
          <td>${escapeHtml(item.provincia)}</td>
          <td>${statusPill(item.estado)}</td>
          <td>${formatPct(item.nivel_efectivo_pct)}</td>
          <td>${formatPct(item.uptime_pct)}</td>
          <td>${formatMoney(item.efectivo_estimado)}</td>
        </tr>
      `;
    }).join("");
    $("#atm-table").html(`
      <thead><tr><th>ATM ID</th><th>Location</th><th>Status</th><th>Cash</th><th>Uptime</th><th>Cash est.</th></tr></thead>
      <tbody>${rows || emptyRow(6)}</tbody>
    `);
  }

  function renderBranchTable(items) {
    const rows = items.map(function (item) {
      return `
        <tr>
          <td>${escapeHtml(item.nombre)}</td>
          <td>${statusPill(item.estado)}</td>
          <td>${formatInt(item.cajeros_disponibles)}</td>
          <td>${formatInt(item.cola_actual)}</td>
          <td>${item.lectura_desactualizada ? statusPill("STALE") : statusPill("OK")}</td>
        </tr>
      `;
    }).join("");
    $("#branch-table").html(`
      <thead><tr><th>Branch Name</th><th>Status</th><th>Tellers</th><th>Queue</th><th>Reading</th></tr></thead>
      <tbody>${rows || emptyRow(5)}</tbody>
    `);
  }

  function renderCandidateTable(items) {
    const rows = items.map(function (item) {
      return `
        <tr>
          <td>${escapeHtml(item.codigo)}</td>
          <td>${escapeHtml(item.provincia)}</td>
          <td>${formatNumber(item.potencial_mercado)}</td>
          <td>${formatNumber(item.densidad_poblacional)}</td>
          <td>${formatInt(item.competidores_cercanos)}</td>
          <td>${statusPill(item.estado)}</td>
        </tr>
      `;
    }).join("");
    $("#candidate-table").html(`
      <thead><tr><th>Location ID</th><th>Province</th><th>Market potential</th><th>Density</th><th>Competitors</th><th>Status</th></tr></thead>
      <tbody>${rows || emptyRow(6)}</tbody>
    `);
  }

  function renderSubagentTable(items) {
    const rows = items.map(function (item) {
      return `
        <tr>
          <td>${escapeHtml(item.codigo_unico)}</td>
          <td><strong>${escapeHtml(item.nombre)}</strong><br><span class="cell-muted">${escapeHtml(item.direccion)}</span></td>
          <td>${escapeHtml(item.provincia || "Sin asignar")}</td>
          <td>${escapeHtml(item.zona || "—")}</td>
          <td>${escapeHtml(item.telefono || "—")}</td>
          <td>${item.latitud === null ? statusPill("SIN_COORDENADAS") : statusPill("GEOLOCALIZADO")}</td>
          <td>${statusPill(item.activo ? "ACTIVO" : "INACTIVO")}</td>
        </tr>
      `;
    }).join("");
    $("#subagent-table").html(`
      <thead><tr><th>Código</th><th>Subagente</th><th>Provincia</th><th>Zona BHD</th><th>Teléfono</th><th>Ubicación</th><th>Estado</th></tr></thead>
      <tbody>${rows || emptyRow(7)}</tbody>
    `);
  }

  function renderCurrentJob(job) {
    if (!job) {
      $("#current-job").html(`
        <div class="empty-state"><i class="bi bi-clock-history"></i><strong>Sin ejecuciones</strong><span>Ejecuta la primera actualización BHD.</span></div>
      `);
      return;
    }
    const total = number(job.progress_total);
    const progress = total ? Math.min(100, number(job.progress_current) / total * 100) : 0;
    const load = job.result && job.result.load ? job.result.load : {};
    const inserted = sumValues(load.inserted);
    const updated = sumValues(load.updated);
    const skipped = sumValues(load.skipped);
    $("#current-job").html(`
      <div class="job-status-row">
        <div>
          <span class="job-id">${escapeHtml(job.job_key)}</span>
          <h3>${escapeHtml(job.message || labelize(job.status))}</h3>
        </div>
        ${statusPill(job.status)}
      </div>
      <div class="job-progress-track"><div class="job-progress-fill" style="width:${progress}%"></div></div>
      <div class="job-progress-meta">
        <span>${job.progress_total ? `${job.progress_current} / ${job.progress_total} pasos` : "Preparando ejecución"}</span>
        <span>${formatPct(progress)}</span>
      </div>
      <div class="job-result-grid">
        <div><span>Insertados</span><strong>${formatInt(inserted)}</strong></div>
        <div><span>Actualizados</span><strong>${formatInt(updated)}</strong></div>
        <div><span>Omitidos</span><strong>${formatInt(skipped)}</strong></div>
        <div><span>Duración</span><strong>${escapeHtml(jobDuration(job))}</strong></div>
      </div>
      ${job.error ? `<p class="job-error"><i class="bi bi-exclamation-triangle"></i>${escapeHtml(job.error)}</p>` : ""}
    `);
  }

  function renderJobsTable(items) {
    const rows = items.map(function (job) {
      const load = job.result && job.result.load ? job.result.load : {};
      return `
        <tr>
          <td>${escapeHtml(formatDateTime(job.created_at))}</td>
          <td>${statusPill(job.status)}</td>
          <td>${formatInt(sumValues(load.inserted))}</td>
          <td>${formatInt(sumValues(load.updated))}</td>
          <td>${formatInt(sumValues(load.skipped))}</td>
          <td>${escapeHtml(jobDuration(job))}</td>
          <td class="job-message-cell">${escapeHtml(job.error || job.message || "—")}</td>
        </tr>
      `;
    }).join("");
    $("#jobs-table").html(`
      <thead><tr><th>Inicio</th><th>Estado</th><th>Insertados</th><th>Actualizados</th><th>Omitidos</th><th>Duración</th><th>Resultado</th></tr></thead>
      <tbody>${rows || emptyRow(7)}</tbody>
    `);
  }

  function renderAtmAlerts(summary, incidents, refills) {
    $("#atm-alerts").html(`
      ${mini("Low cash alerts", summary.alertas_bajo_efectivo, percentage(summary.alertas_bajo_efectivo, summary.total_atms), "danger")}
      ${mini("Under maintenance", summary.atms_mantenimiento, percentage(summary.atms_mantenimiento, summary.total_atms), "warn")}
      ${mini("Critical incidents", summary.incidencias_criticas_abiertas, percentage(summary.incidencias_criticas_abiertas, Math.max(1, incidents.length)), "danger")}
      ${mini("Scheduled CIT", refills.length, percentage(refills.length, 5), "ok")}
    `);
  }

  function renderBranchAlerts(summary, branches) {
    const busy = branches.filter(function (item) { return number(item.cola_actual) >= 8; }).length;
    $("#branch-alerts").html(`
      ${mini("Queues above target", busy, percentage(busy, branches.length || 1), "warn")}
      ${mini("SLA compliance", formatPct(summary.cumplimiento_sla_pct), number(summary.cumplimiento_sla_pct), "ok")}
      ${mini("Avg wait", `${formatNumber(summary.espera_promedio_minutos)} min`, Math.min(100, number(summary.espera_promedio_minutos) * 10), "warn")}
    `);
  }

  function renderPlanningAlerts(summary, candidates) {
    const approved = candidates.filter(function (item) { return item.estado === "APROBADA"; }).length;
    const top = candidates.length ? candidates[0].potencial_mercado : 0;
    $("#planning-alerts").html(`
      ${mini("Top market potential", formatPct(top), number(top), "ok")}
      ${mini("Approved locations", approved, percentage(approved, candidates.length || 1), "ok")}
      ${mini("Branch network share", formatPct(summary.cuota_sucursales_pct), number(summary.cuota_sucursales_pct), "ok")}
    `);
  }

  function mini(title, value, pct, mood) {
    const width = Math.max(0, Math.min(100, number(pct)));
    const fill = mood === "ok" ? colors.icon : mood === "warn" ? colors.amber : colors.danger;
    return `
      <article class="mini-card">
        <span>${escapeHtml(title)}</span>
        <strong>${escapeHtml(String(value))}</strong>
        <div class="progress-track"><div class="progress-fill" style="width:${width}%;background:${fill}"></div></div>
      </article>
    `;
  }

  function renderComparison(selector, rows, metrics) {
    rows = rows || [];
    const maxima = {};
    metrics.forEach(function (metric) {
      maxima[metric[1]] = Math.max.apply(null, rows.map(function (row) { return number(row[metric[1]]); }).concat([0]));
    });
    const header = rows.map(function (row) { return `<th>${escapeHtml(row.nombre)}</th>`; }).join("");
    const body = metrics.map(function (metric) {
      const cells = rows.map(function (row) {
        const value = number(row[metric[1]]);
        const width = maxima[metric[1]] ? (value / maxima[metric[1]]) * 100 : 0;
        const color = row.es_propia ? colors.primary : colors.muted;
        return `
          <td>
            <div class="matrix-bar">
              <span class="matrix-track"><span class="matrix-fill" style="width:${width}%;background:${escapeAttr(color)}"></span></span>
              <span class="matrix-value">${escapeHtml(formatMetric(metric[1], row[metric[1]]))}</span>
            </div>
          </td>
        `;
      }).join("");
      return `<tr><th>${escapeHtml(metric[0])}</th>${cells}</tr>`;
    }).join("");
    $(selector).html(`<table><thead><tr><th>Metric</th>${header}</tr></thead><tbody>${body}</tbody></table>`);
  }

  function renderMap(selector, features, mode) {
    const $el = $(selector);
    $el.empty();

    if (!config.googleMapsApiKey) {
      $el.html(`
        <div class="map-placeholder">
          <div>
            <strong>Google Maps API key pendiente</strong>
            <span>Agrega GOOGLE_MAPS_API_KEY en .env y reinicia FastAPI.</span>
          </div>
        </div>
      `);
      return;
    }

    ensureGoogleMaps()
      .then(function () {
        const element = $el[0];

        const map = new google.maps.Map(element, {
          center: { lat: 18.7357, lng: -70.1627 },
          zoom: 8,
          styles: darkMapStyle(),
          disableDefaultUI: true,
          zoomControl: true,
          streetViewControl: false,
          fullscreenControl: true,
          mapTypeControl: false,
        });

        const bounds = new google.maps.LatLngBounds();
        const info = new google.maps.InfoWindow();

        (features || []).forEach(function (feature) {
          const coords = feature.geometry.coordinates;
          const props = feature.properties || {};
          const position = { lat: coords[1], lng: coords[0] };
          bounds.extend(position);

          // ===== Coverage / Heat =====
          if (mode === "branches") {
            // Branch: cobertura fija de 15 km
            addCoverageHeat(map, position, 15000, "branch");
          } else if (mode === "subagents") {
            addCoverageHeat(map, position, 1800, "subagent", props);
          } else if (mode === "planning") {
            // Planning: cobertura moderada
            addCoverageHeat(map, position, 10000, "planning", props);
          } else {
            // ATM: heat por intensidad
            addCoverageHeat(map, position, 5000, "atm", props);
          }

          // ===== Pin =====
          const ownPoint =
            props.es_propia === true ||
            props.capa === "sucursales" ||
            props.capa === "atms" ||
            props.capa === "subagentes" ||
            props.capa === "propia";

          const pinColor = ownPoint ? colors.primary : colors.muted;
          const pinLabel = pinText(props, mode);

          const marker = new google.maps.Marker({
            map,
            position,
            title: props.nombre || props.codigo || "Location",
            icon: {
              url: makePinSvg(pinColor, pinLabel),
              scaledSize: new google.maps.Size(32, 42),
              anchor: new google.maps.Point(16, 42),
            },
            zIndex: ownPoint ? 30 : 20,
          });

          marker.addListener("click", function () {
            const extraCoverage = mode === "branches"
              ? "<br><span style='font-size:12px;color:#929C92'>Coverage radius: 5 km</span>"
              : "";

            info.setContent(`
              <div style="color:#101410;min-width:180px">
                <strong>${escapeHtml(props.nombre || props.codigo || "Location")}</strong><br>
                ${escapeHtml(props.provincia || "")}<br>
                ${escapeHtml(labelize(props.estado || props.capa || ""))}
                ${extraCoverage}
              </div>
            `);
            info.open(map, marker);
          });
        });

        if (features && features.length) {
          map.fitBounds(bounds, 42);
        }
      })
      .catch(function () {
        $el.html(`
          <div class="map-placeholder">
            <div>
              <strong>No se pudo cargar Google Maps</strong>
              <span>Verifica la API key, el billing y las restricciones HTTP.</span>
            </div>
          </div>
        `);
      });
    }

  function ensureGoogleMaps() {
    if (window.google && window.google.maps) {
      return Promise.resolve();
    }
    if (state.googlePromise) {
      return state.googlePromise;
    }
    state.googlePromise = new Promise(function (resolve, reject) {
      window.__kpiGoogleMapsReady = function () { resolve(); };
      const script = document.createElement("script");
      script.src = "https://maps.googleapis.com/maps/api/js?key=" +
        encodeURIComponent(config.googleMapsApiKey) + "&callback=__kpiGoogleMapsReady&v=weekly";
      script.async = true;
      script.defer = true;
      script.onerror = reject;
      document.head.appendChild(script);
    });
    return state.googlePromise;
  }

  function addCoverageHeat(map, position, radiusMeters, mode, props) {
    let outerRadius = radiusMeters;
    let midRadius = Math.round(radiusMeters * 0.68);
    let innerRadius = Math.round(radiusMeters * 0.38);

    let intensity = 1;
    if (props && props.intensidad) {
      intensity = Math.max(1, number(props.intensidad));
    }

    if (mode === "atm") {
      outerRadius = radiusMeters + Math.min(1800, intensity * 25);
      midRadius = Math.round(outerRadius * 0.62);
      innerRadius = Math.round(outerRadius * 0.34);
    }

    // Capa exterior
    new google.maps.Circle({
      map,
      center: position,
      radius: outerRadius,
      clickable: false,
      strokeOpacity: 0,
      fillColor: colors.iconBackground,
      fillOpacity: mode === "branch" ? 0.10 : 0.08,
      zIndex: 1,
    });

    // Capa media
    new google.maps.Circle({
      map,
      center: position,
      radius: midRadius,
      clickable: false,
      strokeOpacity: 0,
      fillColor: colors.primary,
      fillOpacity: mode === "branch" ? 0.11 : 0.10,
      zIndex: 2,
    });

    // Núcleo
    new google.maps.Circle({
      map,
      center: position,
      radius: innerRadius,
      clickable: false,
      strokeOpacity: 0,
      fillColor: colors.icon,
      fillOpacity: 0.14,
      zIndex: 3,
    });

    // Solo branches: anillo visible de 5 km
    if (mode === "branch") {
      new google.maps.Circle({
        map,
        center: position,
        radius: 5000,
        clickable: false,
        strokeColor: colors.primaryHover,
        strokeOpacity: 0.45,
        strokeWeight: 1.2,
        fillOpacity: 0,
        zIndex: 4,
      });
    }
  }

  function makePinSvg(fill, label) {
    const safeLabel = String(label || "").substring(0, 3);
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="36" height="46" viewBox="0 0 36 46">
        <defs>
          <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.35"/>
          </filter>
        </defs>
        <path filter="url(#shadow)" d="M18 1C9.2 1 2 8.2 2 17c0 11.5 13.2 24.3 15.1 26.1a1.3 1.3 0 0 0 1.8 0C20.8 41.3 34 28.5 34 17 34 8.2 26.8 1 18 1z"
              fill="${fill}" stroke="rgba(255,255,255,0.88)" stroke-width="1.3"/>
        <circle cx="18" cy="17" r="8.5" fill="rgba(255,255,255,0.18)"/>
        <text x="18" y="20.5" text-anchor="middle"
              font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="#ffffff">${safeLabel}</text>
      </svg>
    `;
    return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
  }

  function pinText(props, mode) {
    if (mode === "branches") return "";
    if (props && props.cluster_count) return String(props.cluster_count);
    if (props && props.total) return String(props.total);
    return "";
  }

    function addHeatCircle(map, position, props, mode) {
      const intensity = Math.max(1, number(props.intensidad));
      const base = mode === "atm" ? 80 : 260;
      const radius = base + Math.min(2200, intensity * (mode === "atm" ? 10 : 55));
      new google.maps.Circle({
        map,
        center: position,
        radius,
        strokeOpacity: 0,
        fillColor: colors.primary,
        fillOpacity: Math.min(0.34, 0.06 + intensity / 420),
      });
    }

    function addBranchCoverage(map, position) {
      // Circulo exterior: limite minimo de cobertura de 5 km.
      new google.maps.Circle({
        map,
        center: position,
        radius: 5000,
        clickable: false,
        strokeColor: colors.primary,
        strokeOpacity: 0.65,
        strokeWeight: 1.4,
        fillColor: colors.primary,
        fillOpacity: 0.10,
        zIndex: 1,
      });

      // Anillos interiores suaves para dar lectura tipo heatmap.
      // Al superponerse coberturas de varias sucursales la intensidad aumenta.
      [3500, 2000].forEach(function (radius, index) {
        new google.maps.Circle({
          map,
          center: position,
          radius,
          clickable: false,
          strokeOpacity: 0,
          fillColor: index === 0 ? colors.primaryHover : colors.primary,
          fillOpacity: index === 0 ? 0.055 : 0.045,
          zIndex: 2 + index,
        });
      });
    }

  function markerColor(props) {
    if (props.capa === "competencia") return colors.muted;
    if (props.capa === "candidatos") return colors.icon;
    if (props.estado === "OPERATIVO" || props.estado === "OPERATIVA") return colors.icon;
    if (props.estado === "BAJO_EFECTIVO") return colors.amber;
    if (props.estado === "MANTENIMIENTO") return colors.muted;
    if (props.estado === "FUERA_DE_SERVICIO") return colors.danger;
    return colors.danger;
  }

  function renderLegend(selector, items) {
    const html = `
      <div class="legend-card">
        <div class="legend-title">Legend</div>
        ${items.map(function (item) {
          return `
            <div class="legend-row">
              <span class="legend-swatch" style="${item[2] || `background:${item[1]};`}"></span>
              <span>${escapeHtml(item[0])}</span>
            </div>
          `;
        }).join("")}
      </div>
    `;
    $(selector).html(html);
  }

  function renderChart(id, configObject) {
    if (!window.Chart) return;
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (state.charts[id]) {
      state.charts[id].destroy();
    }
    state.charts[id] = new Chart(canvas, configObject);
  }

  function lineChart(labels, datasets, suffix) {
    return {
      type: "line",
      data: { labels, datasets },
      options: chartOptions(suffix),
    };
  }

  function chartOptions(suffix) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { labels: { color: colors.muted, boxWidth: 10, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              return `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}${suffix || ""}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: colors.muted, maxRotation: 45, minRotation: 0 }, grid: { color: "transparent" } },
        y: { ticks: { color: colors.muted }, grid: { color: colors.darkGrid }, beginAtZero: true },
        y1: {
          display: false,
          position: "right",
          grid: { drawOnChartArea: false },
          beginAtZero: true,
        },
      },
    };
  }

  function sparkOptions() {
    return {
      responsive: false,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    };
  }

  function darkMapStyle() {
    return [
      { elementType: "geometry", stylers: [{ color: "#161C16" }] },
      { elementType: "labels.text.stroke", stylers: [{ color: "#101410" }] },
      { elementType: "labels.text.fill", stylers: [{ color: "#929C92" }] },

      { featureType: "administrative", elementType: "geometry.stroke", stylers: [{ color: "#293329" }] },
      { featureType: "administrative.province", elementType: "labels.text.fill", stylers: [{ color: "#C6CEC6" }] },

      { featureType: "landscape", elementType: "geometry", stylers: [{ color: "#1A211A" }] },
      { featureType: "poi", stylers: [{ visibility: "off" }] },

      { featureType: "road", elementType: "geometry", stylers: [{ color: "#232D23" }] },
      { featureType: "road", elementType: "labels", stylers: [{ visibility: "off" }] },

      { featureType: "transit", stylers: [{ visibility: "off" }] },

      { featureType: "water", elementType: "geometry", stylers: [{ color: "#101410" }] },
      { featureType: "water", elementType: "labels.text.fill", stylers: [{ color: "#929C92" }] }
    ];
  }

  function statusPill(value) {
    const val = String(value || "N/A");
    let mood = "neutral";
    if (["OPERATIVO", "OPERATIVA", "OK", "PROPUESTA", "APROBADA", "ACTIVO", "GEOLOCALIZADO", "SUCCEEDED"].includes(val)) mood = "";
    if (["BAJO_EFECTIVO", "EN_EVALUACION", "STALE", "PENDING", "RUNNING"].includes(val)) mood = "warn";
    if (["FUERA_DE_SERVICIO", "CERRADA", "CRITICA", "CANCELADA", "FAILED", "INACTIVO"].includes(val)) mood = "danger";
    return `<span class="status-pill ${mood}">${escapeHtml(labelize(val))}</span>`;
  }

  function stripType(params) {
    const copy = Object.assign({}, params);
    delete copy.tipo;
    return copy;
  }

  function groupBy(items, key) {
    return (items || []).reduce(function (acc, item) {
      const value = item[key] || "N/A";
      if (!acc[value]) acc[value] = [];
      acc[value].push(item);
      return acc;
    }, {});
  }

  function indexBy(items, key) {
    return (items || []).reduce(function (acc, item) {
      acc[item[key]] = item;
      return acc;
    }, {});
  }

  function unique(items) {
    return Array.from(new Set(items));
  }

  function percentage(value, total) {
    return total ? (number(value) / number(total)) * 100 : 0;
  }

  function number(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function sumValues(value) {
    return Object.keys(value || {}).reduce(function (total, key) {
      return total + number(value[key]);
    }, 0);
  }

  function formatNumber(value, decimals) {
    if (value === null || value === undefined || value === "") return "0";
    const digits = decimals === undefined ? 1 : decimals;
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(number(value));
  }

  function formatInt(value) {
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(number(value));
  }

  function formatCompact(value) {
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(number(value));
  }

  function formatPct(value) {
    if (value === null || value === undefined) return "0%";
    return `${formatNumber(value)}%`;
  }

  function formatMoney(value) {
    const n = number(value);
    if (n >= 1000000) return `RD$ ${formatNumber(n / 1000000)}M`;
    if (n >= 1000) return `RD$ ${formatNumber(n / 1000)}K`;
    return `RD$ ${formatNumber(n)}`;
  }

  function formatMetric(key, value) {
    if (key.includes("pct") || key.includes("utilizacion")) return formatPct(value);
    if (key.includes("depositos") || key.includes("prestamos")) return formatMoney(value);
    return formatCompact(value);
  }

  function hourLabel(hour) {
    const h = Number(hour);
    const suffix = h >= 12 ? "PM" : "AM";
    const shown = h % 12 || 12;
    return `${shown} ${suffix}`;
  }

  function compactPeriod(value) {
    if (!value) return "";
    const parts = String(value).split("-");
    if (parts.length >= 3) return `${parts[1]}/${parts[2]}`;
    if (parts.length >= 2) return `${parts[0]}-${parts[1]}`;
    return value;
  }

  function shortProvince(value) {
    return String(value || "").replace("Distrito Nacional", "Distrito N.").replace("Santo Domingo", "S. Domingo");
  }

  function labelize(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, function (char) { return char.toUpperCase(); });
  }

  function formatDateOnly(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatDateTime(value) {
    if (!value) return "Sin datos";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Sin datos";
    return new Intl.DateTimeFormat("es-DO", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function jobDuration(job) {
    if (!job || !job.started_at) return "—";
    const start = new Date(job.started_at).getTime();
    const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
    const seconds = Math.max(0, Math.round((end - start) / 1000));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${seconds % 60}s`;
  }

  function readError(error) {
    if (error && error.responseJSON && error.responseJSON.detail) {
      if (Array.isArray(error.responseJSON.detail)) {
        return error.responseJSON.detail.map(function (item) { return item.msg; }).join(" ");
      }
      return error.responseJSON.detail;
    }
    return "No se pudo cargar la informacion del API.";
  }

  function emptyRow(cols) {
    return `<tr><td colspan="${cols}">No data</td></tr>`;
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }
})(jQuery);

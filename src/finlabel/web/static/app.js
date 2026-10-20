(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const sourceSelect = document.querySelector("#source-select");
  const schemaEditor = document.querySelector("#schema-json");
  const schemaStatus = document.querySelector("#monitor-findings");
  const analysisStatus = document.querySelector("#analysis-status");
  const resultSection = document.querySelector("#analysis-result");

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...(options.headers || {}),
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `A requisição falhou (${response.status}).`);
    return payload;
  }

  function showNotice(element, message, kind = "") {
    element.textContent = message;
    element.className = `notice ${kind}`.trim();
  }

  function selectedSource() {
    return sourceSelect?.value || "";
  }

  document.querySelector("#capture-schema")?.addEventListener("click", async () => {
    try {
      showNotice(schemaStatus, "Capturando metadados do esquema…");
      const payload = await request("/api/schema/capture", {
        method: "POST", body: JSON.stringify({ source: selectedSource() }),
      });
      schemaEditor.value = JSON.stringify(payload.candidate, null, 2);
      showNotice(schemaStatus, "Candidato carregado. Revise os campos antes de confirmar.", "success");
    } catch (error) { showNotice(schemaStatus, error.message, "error"); }
  });

  document.querySelector("#confirm-schema")?.addEventListener("click", async () => {
    try {
      const baseline = JSON.parse(schemaEditor.value);
      await request("/api/schema/confirm", {
        method: "POST", body: JSON.stringify({ source: selectedSource(), baseline }),
      });
      showNotice(schemaStatus, "Esquema confirmado e salvo neste projeto.", "success");
    } catch (error) { showNotice(schemaStatus, error.message, "error"); }
  });

  document.querySelector("#monitor-source")?.addEventListener("click", async () => {
    try {
      const payload = await request(`/api/monitor?source=${encodeURIComponent(selectedSource())}`);
      const summary = payload.findings.length
        ? payload.findings.map(item => `${item.severity.toUpperCase()} · ${item.code} · ${item.message}`).join("\n")
        : "Nenhum desvio encontrado em relação ao esquema confirmado.";
      showNotice(schemaStatus, summary, payload.findings.some(item => item.severity === "error") ? "error" : "success");
    } catch (error) { showNotice(schemaStatus, error.message, "error"); }
  });

  document.querySelector("#propose-plan")?.addEventListener("click", async () => {
    try {
      showNotice(analysisStatus, "A IA local está preparando um plano…");
      const payload = await request("/api/plan", {
        method: "POST", body: JSON.stringify({ source: selectedSource(), question: document.querySelector("#question").value }),
      });
      document.querySelector("#plan-json").value = JSON.stringify(payload.plan, null, 2);
      showNotice(analysisStatus, "Plano proposto. Revise ou edite o JSON antes de executar.", "success");
    } catch (error) { showNotice(analysisStatus, error.message, "error"); }
  });

  function renderRows(rows) {
    const table = document.querySelector("#result-table");
    table.replaceChildren();
    if (!rows.length) return;
    const keys = Object.keys(rows[0]);
    const thead = document.createElement("thead");
    const heading = document.createElement("tr");
    for (const key of keys) {
      const th = document.createElement("th");
      th.textContent = key;
      heading.append(th);
    }
    thead.append(heading);
    const tbody = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const key of keys) {
        const td = document.createElement("td");
        td.textContent = row[key] === null ? "—" : String(row[key]);
        tr.append(td);
      }
      tbody.append(tr);
    }
    table.append(thead, tbody);
  }

  document.querySelector("#run-analysis")?.addEventListener("click", async () => {
    try {
      const plan = JSON.parse(document.querySelector("#plan-json").value);
      showNotice(analysisStatus, "Executando as operações determinísticas…");
      const payload = await request("/api/analyze", {
        method: "POST",
        body: JSON.stringify({ source: selectedSource(), question: document.querySelector("#question").value, plan }),
      });
      renderRows(payload.rows);
      const highlightList = document.querySelector("#highlights");
      highlightList.replaceChildren();
      for (const text of payload.highlights) {
        const item = document.createElement("p");
        item.className = "highlight";
        item.textContent = text;
        highlightList.append(item);
      }
      document.querySelector("#result-count").textContent = `Exibindo ${payload.rows.length} de ${payload.total_rows} grupos calculados.`;
      document.querySelector("#open-analysis").href = payload.analysis_url;
      document.querySelector("#chart-frame").src = payload.chart_url;
      resultSection.hidden = false;
      showNotice(analysisStatus, "Análise salva em uma nova execução local.", "success");
    } catch (error) { showNotice(analysisStatus, error.message, "error"); }
  });
})();

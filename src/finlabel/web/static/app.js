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

  const labelStatus = document.querySelector("#label-status");
  const suggestionsList = document.querySelector("#label-suggestions");
  const runIdInput = document.querySelector("#label-run-id");

  async function loadSuggestions(runId) {
    const payload = await request(`/api/label/suggestions?run_id=${encodeURIComponent(runId)}`, { method: "GET", headers: {} });
    suggestionsList.replaceChildren();
    document.querySelector("#label-count").textContent = `${payload.suggestions.length} de ${payload.total}`;
    for (const suggestion of payload.suggestions) {
      const article = document.createElement("article");
      article.className = `suggestion-card ${suggestion.stale ? "stale" : ""}`.trim();
      const title = document.createElement("h3");
      title.textContent = `Rótulo sugerido: ${suggestion.suggested_label}`;
      const fields = document.createElement("pre");
      fields.textContent = JSON.stringify(suggestion.fields, null, 2);
      const status = document.createElement("p");
      status.className = suggestion.stale ? "error-text" : "helper";
      status.textContent = suggestion.stale
        ? "Fonte alterada desde a sugestão. Esta linha não pode ser revisada."
        : suggestion.review_action
          ? `Última decisão: ${suggestion.review_action}${suggestion.final_label ? ` · ${suggestion.final_label}` : ""}`
          : "Ainda sem revisão.";
      article.append(title, fields, status);
      if (!suggestion.stale) {
        const correction = document.createElement("select");
        correction.setAttribute("aria-label", "Rótulo corrigido");
        for (const label of suggestion.labels) {
          const option = document.createElement("option");
          option.value = label;
          option.textContent = label;
          correction.append(option);
        }
        if (suggestion.labels.includes(suggestion.suggested_label)) correction.value = suggestion.suggested_label;
        const actions = document.createElement("div");
        actions.className = "button-row";
        const submitReview = async (action, finalLabel = undefined) => {
          try {
            await request("/api/label/review", {
              method: "POST",
              body: JSON.stringify({
                run_id: runId, suggestion_id: suggestion.suggestion_id,
                record_id: suggestion.record_id, input_digest: suggestion.input_digest,
                idempotency_key: crypto.randomUUID().replaceAll("-", ""), action, final_label: finalLabel,
              }),
            });
            showNotice(labelStatus, "Decisão registrada localmente.", "success");
            await loadSuggestions(runId);
          } catch (error) { showNotice(labelStatus, error.message, "error"); }
        };
        for (const [caption, action] of [["Aceitar", "accepted"], ["Rejeitar", "rejected"]]) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "button ghost";
          button.textContent = caption;
          button.addEventListener("click", () => submitReview(action));
          actions.append(button);
        }
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "button secondary";
        edit.textContent = "Salvar correção";
        edit.addEventListener("click", () => submitReview("corrected", correction.value));
        actions.append(correction, edit);
        article.append(actions);
      }
      suggestionsList.append(article);
    }
    if (payload.truncated) showNotice(labelStatus, "Exibindo a primeira página. O limite protege o painel; use a CLI para execuções maiores.");
  }

  document.querySelector("#start-label-run")?.addEventListener("click", async () => {
    try {
      showNotice(labelStatus, "Gerando sugestões para os campos selecionados…");
      const payload = await request("/api/label/start", {
        method: "POST", body: JSON.stringify({ source: document.querySelector("#label-source").value,
          task: document.querySelector("#label-task").value }),
      });
      runIdInput.value = payload.run_id;
      showNotice(labelStatus, `Execução criada: ${payload.suggestions} sugestões válidas; ${payload.invalid} inválidas.`, "success");
      await loadSuggestions(payload.run_id);
    } catch (error) { showNotice(labelStatus, error.message, "error"); }
  });
  document.querySelector("#load-label-run")?.addEventListener("click", async () => {
    try { await loadSuggestions(runIdInput.value.trim()); showNotice(labelStatus, "Execução carregada.", "success"); }
    catch (error) { showNotice(labelStatus, error.message, "error"); }
  });
  document.querySelector("#prepare-dataset")?.addEventListener("click", async () => {
    const datasetStatus = document.querySelector("#dataset-status");
    try {
      const payload = await request("/api/dataset/prepare", {
        method: "POST", body: JSON.stringify({ run_id: runIdInput.value.trim(), output_name: document.querySelector("#dataset-name").value.trim() }),
      });
      showNotice(datasetStatus, `Dataset salvo (${payload.rows} linhas): ${payload.path}`, "success");
    } catch (error) { showNotice(datasetStatus, error.message, "error"); }
  });

  const trainingDataset = document.querySelector("#training-dataset");
  const trainingStatus = document.querySelector("#training-status");
  function updateTrainingSummary() {
    const option = trainingDataset?.selectedOptions?.[0];
    if (!option) return;
    document.querySelector("#training-model").textContent = option.dataset.model || "";
    document.querySelector("#training-task").textContent = option.dataset.task || "";
    document.querySelector("#training-rows").textContent = option.dataset.rows || "";
    document.querySelector("#training-hash").textContent = option.dataset.hash || "";
  }
  trainingDataset?.addEventListener("change", updateTrainingSummary);
  updateTrainingSummary();
  document.querySelector("#submit-training")?.addEventListener("click", async () => {
    try {
      const option = trainingDataset.selectedOptions[0];
      const confirmed = document.querySelector("#training-confirm").checked;
      const modelRef = option.dataset.model || "";
      const separator = modelRef.indexOf("@");
      showNotice(trainingStatus, "Validando gate, manifesto e dataset local…");
      const payload = await request("/api/train/submit", {
        method: "POST",
        body: JSON.stringify({
          confirmed, dataset_name: option.value,
          model_id: separator < 0 ? modelRef : modelRef.slice(0, separator),
          revision: separator < 0 ? null : modelRef.slice(separator + 1),
          epochs: Number(document.querySelector("#training-epochs").value),
          batch_size: Number(document.querySelector("#training-batch").value),
          learning_rate: Number(document.querySelector("#training-rate").value),
          lora_rank: Number(document.querySelector("#training-rank").value),
        }),
      });
      showNotice(trainingStatus, `Trabalho ${payload.job_id}: ${payload.state}. ${payload.progress}`, "success");
      const poll = async () => {
        const status = await request(`/api/train/jobs/${encodeURIComponent(payload.job_id)}`, { method: "GET", headers: {} });
        showNotice(trainingStatus, `Trabalho ${status.job_id}: ${status.state}. ${status.progress}${status.error ? ` ${status.error}` : ""}`,
          status.state === "failed" ? "error" : status.state === "succeeded" ? "success" : "");
        if (status.state === "queued" || status.state === "running") window.setTimeout(poll, 1500);
      };
      window.setTimeout(poll, 800);
    } catch (error) { showNotice(trainingStatus, error.message, "error"); }
  });
})();

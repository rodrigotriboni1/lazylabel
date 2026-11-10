# Inferência LazyLabel com adapter local — 26/10/2026

## Execução reproduzida

O smoke foi executado pela implementação `TransformersTextGenerationBackend` do LazyLabel, com o adapter Qwen LoRA existente e os 24 exemplos reservados sintéticos. A geração usa o chat template salvo no tokenizer do adapter, o prompt comum da tarefa e decodificação gulosa. O script salva apenas índice e rótulos de referência/previsão; não copia as descrições dos exemplos para o resultado.

Reproduzido em 26/10/2026 a partir da branch integrada `codex/lazylabel-autonomous-mvp`. Execute a partir da raiz `Documents/ChatGPT/TCC`:

```bash
EXP="$PWD/tcc/experimentos/sintetico-qwen-0.5b"
REPO="$PWD/codigo/lazylabel/.worktrees/autonomous-mvp"
HF_HOME="$EXP/model-cache" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
PYTHONPATH="$REPO/src" "$EXP/.venv/bin/python" \
  "$EXP/scripts/evaluate_synthetic_backend.py" \
  --experiment "$EXP" \
  --output "$EXP/results/live-inference-2026-10-26-integration-final.json" \
  --device mps
```

- Python 3.12.14; Transformers 5.20.2; PEFT 0.21.2; PyTorch 2.14.1; Datasets 5.1.0; TRL 1.16.0.
- Modelo `Qwen/Qwen2.5-0.5B-Instruct`, revisão `7ae557604adf67be50417f59c2c2f167def9a775`.
- Dispositivo Apple MPS; `do_sample=false`; `max_new_tokens=64`.
- Resultado reproduzido na integração: 24 previsões válidas em 24; acurácia exata 17/24 (70,83%); macro-F1 0,7056; duração 12,099 s.
- JSON de previsões sem texto de origem: `tcc/experimentos/sintetico-qwen-0.5b/results/live-inference-2026-10-26-integration-final.json`.

## Limites e identidade

Os dados e rótulos são sintéticos e a amostra reservada tem somente 24 registros. As métricas não demonstram desempenho em dados de clientes nem generalização financeira.

O adapter foi treinado antes do contrato atual e não inclui o digest de árvore esperado pelo registro nem um calibrador ligado à identidade de modelo, tarefa e política. Por isso, o script testa a inferência real usando diretamente o backend e o adapter local, mas esse artefato histórico não pode ser ativado ou promovido pelo fluxo autônomo. A promoção exige os arquivos verificados e a calibragem congelada produzida pelo ciclo atual.

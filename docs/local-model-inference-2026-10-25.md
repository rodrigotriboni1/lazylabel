# Avaliação local do Qwen LoRA — 25/10/2026

## Execução

Reproduzi a inferência do adapter Qwen2.5-0.5B-Instruct com os 24 exemplos sintéticos reservados do experimento. O script usa o prompt da tarefa FinLabel, aplica o chat template oficial do tokenizer e compara com as referências sintéticas congeladas.

```bash
EXP="$PWD/.scratch/biblioteca-rotulagem-financeira/experiments/qwen25-05b-synthetic-2026-10-20"
HF_HOME="$EXP/model-cache" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
PYTHONPATH="$PWD/codigo/finlabel/.worktrees/training-backend/src" \
"$EXP/.venv/bin/python" "$EXP/scripts/evaluate.py" \
  --adapter "$EXP/adapter" \
  --output "$EXP/results/live-inference-2026-10-25.json" \
  --chat-template
```

- Python 3.12.14; Transformers 5.20.2; PEFT 0.21.2; PyTorch 2.14.1; Datasets 5.1.0; TRL 1.16.0.
- Modelo `Qwen/Qwen2.5-0.5B-Instruct`, revisão `7ae557604adf67be50417f59c2c2f167def9a775`.
- Dispositivo Apple MPS; geração gulosa, `max_new_tokens=64`.
- Resultado: 24 previsões válidas em 24; acurácia exata 17/24 (70,83%); macro-F1 0,7056; duração 9,321 s.
- JSON completo: `.scratch/biblioteca-rotulagem-financeira/experiments/qwen25-05b-synthetic-2026-10-20/results/live-inference-2026-10-25.json`.

## Limites

Todos os dados são sintéticos. Os 24 exemplos não medem desempenho em dados financeiros reais nem estabelecem generalização fora dos padrões usados no experimento. A avaliação foi executada pelo script do experimento usando os serviços de prompt e validação do checkout, com a aplicação manual do adapter PEFT.

Este adapter histórico foi criado antes do contrato de artefatos verificados: não possui hashes FinLabel para adapter/tokenizer e não possui calibrador ligado à identidade do modelo. Portanto, o novo carregador do modelo ativo corretamente o rejeita. A reprodução confirma a inferência e as métricas do adapter; não demonstra ativação automática, calibração, promoção nem o ciclo atual de ponta a ponta.

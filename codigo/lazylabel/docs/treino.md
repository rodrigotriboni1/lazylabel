# Rótulos confiáveis e ciclo de treino

Como preparar e rodar o ciclo de fine-tuning com gates. Visão geral em [../README.md](../README.md); verificação detalhada em [verified-training-cycle.md](verified-training-cycle.md).

Para treinar, registre uma coluna de referência externa, separada das previsões e dos logs do LazyLabel. CSV ou SQLite continua somente para leitura. `.lazylabel/project.json` guarda proveniência, contagem e hash do snapshot, sem copiar linhas ou rótulos para logs. `trust_kind` e `provenance` são declarações do operador: LazyLabel valida formato, mapeamento e origem, mas não autentica criptograficamente quem produziu ou aprovou os rótulos. A coluna de rótulo nunca pode entrar em `input_columns` da tarefa.

```bash
lazylabel supervision add carteira \
  --task risk \
  --label-column reference_label \
  --provenance auditoria-2026-10 \
  --trust-kind provided_ground_truth \
  --project ./meu-projeto
```

Os tipos aceitos são `provided_ground_truth` e `validated_rule`. Use `--label-map` quando a taxonomia da fonte diferir dos rótulos da tarefa. Uma alteração posterior na fonte bloqueia a carga; depois de confirmar a proveniência da nova versão, repita o comando com `--refresh`.

Antes do ciclo, registre os itens autorizados em `.lazylabel/training-gate.json`:

```json
{
  "model_id": "REFERENCIA-EXATA-APROVADA",
  "license": "licença verificada para este uso",
  "hardware": "hardware e limites de memória disponíveis",
  "data_policy": "política aprovada para estes exemplos locais",
  "evaluation_protocol": "protocolo e partições de validação definidos",
  "authorized": true
}
```

Configure também a política de rotulagem da tarefa e os gates de promoção versionados em `.lazylabel/models/promotion-policies/<task>.json`. Então inicie o ciclo completo:

```bash
lazylabel run --task risk --source carteira --project ./meu-projeto
lazylabel run-status RUN_ID --project ./meu-projeto
lazylabel model-status risk --project ./meu-projeto
```

O ciclo valida a fonte confiável, congela partições disjuntas de treino/calibração/holdout, treina um candidato local com PEFT/LoRA, compara candidato e incumbente no mesmo holdout e aplica os gates configurados. Um candidato só é promovido quando todas as evidências e regras passam. Ausência de política, rótulos confiáveis, artefatos ou gates bloqueia o ciclo e mantém o modelo ativo. O CLI e o painel mostram o histórico de promoção, rejeição e rollback; nenhuma aprovação por linha é necessária.

O comando `lazylabel train` continua disponível como backend explícito de fine-tuning, mas não promove um modelo nem substitui o ciclo verificado. `ReviewLog` e artefatos de revisão anteriores permanecem legíveis por compatibilidade histórica; não fazem parte da rotulagem autônoma atual.

O backend usa Transformers, TRL `SFTTrainer` e PEFT `LoraConfig`, não publica adapters e desativa telemetria do trainer. LazyLabel não distribui pesos nem presume compatibilidade: verifique licença, termos de uso, memória disponível e protocolo de avaliação. Consulte [TRL SFTTrainer](https://huggingface.co/docs/trl/sft_trainer) e [PEFT LoRA](https://huggingface.co/docs/peft/en/package_reference/lora). O smoke real local do Qwen com exemplos sintéticos está em `tcc/experimentos/sintetico-qwen-0.5b/inferencia-local-2026-10-26.md`; não demonstra desempenho financeiro e o adapter histórico não pode ser promovido pelo ciclo atual.

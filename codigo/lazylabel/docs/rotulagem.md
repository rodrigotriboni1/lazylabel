# Rotulagem autônoma: tarefa, política e contrato de previsão

Detalhes do fluxo de rotulagem. Visão geral e comandos em [../README.md](../README.md).

## Tarefas e rotulagem autônoma

Uma tarefa declarativa define instruções, colunas permitidas, rótulos e o modelo local. Salve este JSON como `risk.json`:

```json
{
  "task_id": "risk",
  "instructions": "Classifique risco conforme os critérios definidos pela equipe.",
  "input_columns": ["exposure", "days_past_due"],
  "labels": ["low", "medium", "high"],
  "model_id": "REFERENCIA-DO-MODELO-ESCOLHIDO",
  "model_revision": null
}
```

```bash
lazylabel task add ./risk.json --project ./meu-projeto
python -m pip install -e '.[models]'
lazylabel label carteira --task risk --project ./meu-projeto
lazylabel label-run RUN_ID --project ./meu-projeto
```

O modelo recebe somente `input_columns` serializadas como dados, nunca a linha completa. A biblioteca aplica automaticamente apenas previsões com política válida, regras satisfeitas, origem atual e confiança calibrada acima do limite configurado. Registros inválidos, incertos ou sem evidência compatível de calibração vão para quarentena com um código de motivo. Os resultados são imutáveis e guardam somente referências opacas, digests, rótulos permitidos, confiança calibrada e proveniência; não gravam prompts, valores da fonte ou justificativas livres.

`lazylabel label-run` verifica o hash de `outcomes.jsonl` e confere os totais antes de exibir somente metadados agregados. O comando de revisão por registro foi retirado; artefatos antigos de revisão podem ser lidos como histórico e não alimentam o novo ciclo.

Para executar uma rodada única de rotulagem seguida do ciclo local de treino:

```bash
lazylabel run --task risk --source carteira --project ./meu-projeto
lazylabel run-status RUN_ID --project ./meu-projeto
```

`run` salva um manifesto combinado em `.lazylabel/pipeline-runs/` que referencia
os artefatos de rotulagem e o ciclo de treino por ID e hash. O resumo contém
contagens aplicadas/em quarentena, motivos, estado do treino, ação de promoção e
modelo ativo; não inclui linhas nem prompts. `run-status` verifica os hashes e a
identidade dos artefatos antes de mostrar o resumo. `model-status risk` mostra o
modelo ativo e o histórico local de promoção/rejeição/rollback. A execução é
iniciada pelo operador e não instala um daemon. Política ou evidência ausentes
bloqueiam o treino ou a promoção e mantêm o modelo ativo sem alteração.

## Política de rotulagem autônoma (contrato de configuração)

A tarefa aceita `"policy_path": "./risk-policy.json"` opcional. `load_task`
resolve esse caminho a partir da pasta do JSON da tarefa, valida a política e
preserva os rótulos e a identidade/revisão do modelo. Ao importar uma tarefa, o
caminho normalizado é absoluto; mantenha o arquivo de política disponível nesse
local. Tarefas antigas, sem `policy_path`, continuam legíveis.

Exemplo de `risk-policy.json` para a tarefa `risk` acima:

```json
{
  "policy_id": "risk-policy-v1",
  "task_id": "risk",
  "allowed_labels": ["low", "medium", "high"],
  "rules_version": "risk-rules-v1",
  "rules": [
    {"field": "exposure", "operator": "number_between", "minimum": 0},
    {"field": "days_past_due", "operator": "number_between", "minimum": 0}
  ],
  "calibration_ref": null,
  "min_calibrated_confidence": 0.95,
  "max_staleness_seconds": 300
}
```

- `policy_id`: referência versionada e não vazia da política.
- `task_id`: deve coincidir com a tarefa que carrega a política.
- `allowed_labels`: conjunto exato de rótulos da tarefa, sem duplicatas; a ordem pode variar.
- `rules_version`: versão da lista `rules`, validada e executada pelo serviço.
- `rules`: lista obrigatória e não vazia. Cada regra é uma condição que todos os registros precisam satisfazer; uma falha gera quarentena `rule_conflict` antes da inferência. Operadores suportados: `not_empty`, `equals`, `one_of` e `number_between`. Campos extras, operadores desconhecidos e colunas fora de `input_columns` são rejeitados. A política não aceita expressões nem código.
- `calibration_ref`: referência à evidência de calibração da tarefa ou `null` quando indisponível.
- `min_calibrated_confidence`: número finito entre 0 e 1; `0.95` é apenas ilustrativo e exige validação específica da tarefa.
- `max_staleness_seconds`: inteiro positivo que limita, por registro, o tempo entre o início da inferência e a conclusão da calibração. O tempo gasto processando outros registros não entra nesse limite.

```python
from lazylabel.adapters.outbound.persistence.tasks import load_task, load_task_policy

# load_task rejeita políticas ilegíveis, malformadas ou incompatíveis.
task = load_task("./risk.json")
policy = load_task_policy(task)  # None se policy_path não estiver configurado
```

`LabelingPolicy` é imutável, inclusive rótulos e regras. O carregador rejeita
regras ausentes, vazias ou não suportadas; campos desconhecidos; IDs divergentes;
taxonomia diferente; regras que usem colunas não selecionadas; e valores inválidos.
`has_calibration_configuration` indica somente que existe uma referência;
ela não comprova calibração. O runtime deve validar a evidência e sua ligação com
a tarefa, política, modelo e método de pontuação antes de aplicar qualquer
rótulo. Sem política, regras determinísticas ou calibrador validado, os registros
ficam em quarentena. Nenhum limite, regra ou referência permissiva é criado por
padrão. Antes da primeira promoção não existe calibrador ativo; por isso, mesmo previsões
válidas ficam em quarentena com motivo `uncalibrated`. O CLI informa esse estado sem apresentar dados das linhas.

Cada resultado grava o `input_digest` dos campos selecionados e uma referência
opaca do registro. O `processed_batch_sha256` de `run.json` agrega as referências
e digests distintos que entraram na execução; ele não é o hash de uma captura
completa da fonte. Depois de preparar os arquivos temporários, o serviço
relê as colunas selecionadas imediatamente antes de publicar o diretório e coloca
em quarentena registros que mudaram até essa releitura. CSV e SQLite não oferecem
um lock comum ao serviço: uma alteração posterior à última releitura ainda é
possível. Consumidores devem recalcular o digest da linha atual e só tratar o
rótulo aplicado como atual quando ele corresponder ao `input_digest` do resultado.

## Contrato de previsão local estruturada

Backends locais implementam `predict(selected_values, *, task, max_new_tokens)`
e retornam `lazylabel.domain.labeling.prediction.Prediction`, um objeto imutável com rótulo,
justificativa opcional, evidência por classe, método e digest SHA-256 da resposta.
O mapa de evidência também é imutável. JSON inválido recebe `PredictionError`
com `reason_code="invalid_output"`; classe fora da tarefa recebe `unknown_label`.
Campos de confiança autorreportados pelo modelo são rejeitados.

`TransformersTextGenerationBackend` usa o chat template do tokenizer quando
presente (incluindo Qwen); somente tokenizers sem template usam texto simples.
`generate(prompt, max_new_tokens=...)` continua disponível para consumidores
legados explícitos. `predict` valida modelo/revisão e recebe exatamente as
colunas da tarefa, sem selecionar campos extras da fonte.

O método `label_json_mean_log_likelihood_v2` calcula, em ordem da taxonomia,
a média dos logaritmos das probabilidades dos tokens do JSON canônico
`{"label":"CLASSE"}` para cada classe, condicionada ao mesmo prompt. Prompt e
continuação são tokenizados juntos, e somente os tokens que cobrem exatamente o
texto JSON são pontuados. Tokenizers sem offsets ou com token atravessando a
fronteira entre prompt e JSON falham de forma segura. O método v2 é incompatível
com calibrações produzidas para v1.
Esses números brutos não são probabilidades calibradas, não são o texto da
justificativa e não permitem aplicar um rótulo sozinhos. Esse cálculo exige uma
passagem adicional do modelo por classe e pode custar memória/tempo em tarefas
com muitas classes.

O backend Transformers bruto devolve `calibrated_confidence=None` e
`calibration_ref=None`. O caminho de inferência ativo pode anexar confiança de
um artefato de calibração validado para política, tarefa, modelo e método. Sem
essa evidência/calibrador, o resultado permanece em quarentena. A construção de `Prediction` rejeita
NaN, infinitos, escores booleanos e confiança fora de `[0, 1]`; sua validação
estrutural não substitui a verificação da origem do calibrador pelo serviço.

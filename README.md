# FinLabel Local

Biblioteca em desenvolvimento para análise local e rotulagem autônoma de dados financeiros. Inclui conectores somente de leitura para CSV e SQLite, monitoramento de esquema, análises determinísticas, gráficos offline, painel web e fluxos locais de calibração e treino.

O contrato de fine-tuning PEFT/LoRA está implementado. A execução com pesos reais permanece bloqueada até registrar e autorizar modelo, licença, hardware, política de dados e protocolo de avaliação no projeto. Nenhum peso é carregado implicitamente.

## Instalação local

```bash
python -m pip install -e .
```

## Projeto e fontes

```bash
finlabel project init ./meu-projeto
finlabel source add-csv vendas ./dados/vendas.csv --project ./meu-projeto
finlabel source add-sqlite carteira ./dados/carteira.db --table contratos --id-column contrato_id --project ./meu-projeto
finlabel source set-type vendas valor decimal --project ./meu-projeto
```

A configuração fica em `.finlabel/project.json`. Caminhos relativos são resolvidos a partir da pasta do projeto. CSV e SQLite são abertos somente para leitura. Agregações SQLite não exigem ID; revisão persistente exige uma coluna única e não nula. CSV usa a posição lógica do registro e um digest dos campos selecionados. O contrato `DataSource` descreve IDs, leitura, streaming e seleção de colunas.

## Captura e monitoramento de esquema

```bash
finlabel schema capture vendas --output ./candidate-schema.json --project ./meu-projeto
finlabel monitor vendas --baseline ./candidate-schema.json --project ./meu-projeto
```

A captura grava um candidato editável. Tipos são inferências; confirme colunas obrigatórias e limites para valores ausentes antes de salvar um baseline. Nenhum limite de qualidade é presumido.

## Análises e gráficos

```bash
finlabel analyze vendas --question "Como as vendas mudaram por mês?" --plan ./analysis-plan.json --project ./meu-projeto
```

Planos JSON revisáveis podem ser executados sem modelo. Alternativamente, `--model-id` usa Transformers local quando o comando de análise é chamado. O planejador recebe pergunta e nomes/tipos de colunas, nunca as linhas da fonte. As operações numéricas usam `Decimal`; datas e números exigem mapeamento explícito por `source set-type`. Share exige medida, dimensão e escopo de denominador claros.

Cada execução cria `.finlabel/analyses/<run_id>/` com plano, resultados, `chart.html` independente de CDN e hashes. A saída tabulada é a referência numérica. O painel limita visualização a 100 linhas, 2.000 pontos e 1 MiB por resposta JSON.

## Painel web local

```bash
python -m pip install -e '.[web]'
finlabel serve --project ./meu-projeto --host 127.0.0.1 --port 8765
```

Abra `http://127.0.0.1:8765`. O serviço só faz bind em loopback, valida `Host`, `Origin` e CSRF, limita requisições e usa templates escapados. A captura de esquema não salva até confirmação explícita. Gráficos têm CSP sandbox ao serem exibidos no painel.

Use `/labeling` para gerar e revisar rótulos; `/training` lista datasets preparados e oferece envio explícito de trabalho LoRA depois que o gate do projeto estiver completo.

## Tarefas e rotulagem assistida

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
finlabel task add ./risk.json --project ./meu-projeto
python -m pip install -e '.[models]'
finlabel label carteira --task risk --project ./meu-projeto
finlabel label-run RUN_ID --project ./meu-projeto
```

O modelo recebe somente `input_columns` serializadas como dados, nunca a linha completa. A biblioteca aplica automaticamente apenas previsões com política válida, regras satisfeitas, origem atual e confiança calibrada acima do limite configurado. Registros inválidos, incertos ou sem evidência compatível de calibração vão para quarentena com um código de motivo. Os resultados são imutáveis e guardam somente referências opacas, digests, rótulos permitidos, confiança calibrada e proveniência; não gravam prompts, valores da fonte ou justificativas livres.

`finlabel label-run` verifica o hash de `outcomes.jsonl` e confere os totais antes de exibir somente metadados agregados. Não é necessário revisar cada linha para concluir uma execução. O comando histórico `finlabel review` continua disponível para consultar execuções antigas baseadas em sugestões, mas não faz parte do fluxo autônomo.

Para executar uma rodada única de rotulagem seguida da checagem de elegibilidade
do ciclo de treino confiável:

```bash
finlabel run --task risk --source carteira --project ./meu-projeto
finlabel run-status RUN_ID --project ./meu-projeto
```

`run` salva um manifesto combinado em `.finlabel/pipeline-runs/` que referencia
os artefatos de rotulagem e o manifesto do ciclo de treino por ID e hash. O
resumo contém contagens aplicadas/em quarentena, motivos, estado do treino,
ação de promoção, modelo ativo e caminhos dos artefatos; linhas, prompts e
justificativas não são incluídos. `run-status` verifica os hashes e a identidade
dos artefatos antes de mostrar o resumo. A execução é iniciada pelo operador e
não instala um daemon. A promoção permanece bloqueada até existir avaliação
verificável de calibração e holdout; nesse caso o motivo explícito é
`verifiable_calibration_and_holdout_evaluator_unavailable`.

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
from finlabel.labeling.task import load_task, load_task_policy

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
padrão. No estado atual, o backend Transformers ainda não produz confiança
calibrada; portanto, mesmo previsões válidas ficam em quarentena com motivo
`uncalibrated`. O CLI informa esse estado sem apresentar dados das linhas.

Cada resultado grava o `input_digest` dos campos selecionados e uma referência
opaca do registro. O `processed_batch_sha256` de `run.json` agrega as referências
e digests distintos que entraram na execução; ele não é o hash de uma captura
completa da fonte. Depois de preparar os arquivos temporários, o serviço
relê as colunas selecionadas imediatamente antes de publicar o diretório e coloca
em quarentena registros que mudaram até essa releitura. CSV e SQLite não oferecem
um lock comum ao serviço: uma alteração posterior à última releitura ainda é
possível. Consumidores devem recalcular o digest da linha atual e só tratar o
rótulo aplicado como atual quando ele corresponder ao `input_digest` do resultado.

## Preparação do dataset e fine-tuning

Para o fluxo de treino autônomo, registre uma coluna de referência externa, separada
das previsões e dos logs do FinLabel. A fonte CSV ou SQLite permanece somente para
leitura; o registro em `.finlabel/project.json` guarda proveniência, contagem e
hash do snapshot, sem copiar linhas ou rótulos para logs. Esse arquivo é a única
fonte de verdade da configuração e do snapshot. `trust_kind` e `provenance` são
declarações do operador: FinLabel valida formato, mapeamento e origem configurada,
mas não autentica criptograficamente quem produziu ou aprovou os rótulos. A coluna de rótulo nunca pode entrar em
`input_columns` da tarefa.

Exemplo quando a coluna já usa os rótulos da tarefa:

```bash
finlabel supervision add carteira \
  --task risk \
  --label-column reference_label \
  --provenance auditoria-2026-10 \
  --trust-kind provided_ground_truth \
  --project ./meu-projeto
```

Se os valores tiverem outra taxonomia, informe o mapeamento explicitamente:

```bash
finlabel supervision add carteira \
  --task risk \
  --label-column reference_label \
  --label-map '{"baixo":"low","medio":"medium","alto":"high"}' \
  --provenance regra-validada-v1 \
  --trust-kind validated_rule \
  --project ./meu-projeto
```

Os únicos tipos aceitos são `provided_ground_truth` e `validated_rule`.
Fontes dentro de `.finlabel` e fontes identificáveis como saídas de modelo,
sugestões, resultados de execução ou logs de revisão são rejeitadas. O registro
valida IDs estáveis, rótulos conhecidos, colunas selecionadas e leitura somente
antes de gravar atomicamente a configuração e o digest do snapshot.
Uma alteração posterior na fonte bloqueia a carga; depois de confirmar que a nova
versão conserva a proveniência declarada, repita o mesmo comando com `--refresh`
para registrar o novo snapshot.

Só uma ação explícita prepara exemplos. O JSONL contém prompt com as colunas escolhidas e completion em JSON com o rótulo humano final (o mesmo contrato estruturado esperado na inferência):

```bash
finlabel dataset prepare RUN_ID --output ./meu-projeto/.finlabel/training/reviewed.jsonl --project ./meu-projeto
```

Aceitos e corrigidos entram; rejeitados, sem revisão e linhas desatualizadas ficam de fora. O manifesto ao lado lista eventos/sugestões incluídos, colunas, contagens excluídas, snapshot e hashes. CSV é hasheado antes/depois da leitura; SQLite é percorrido por um cursor local de leitura.

Antes de permitir treino, registre os cinco itens acordados em `.finlabel/training-gate.json`:

```json
{
  "model_id": "REFERENCIA-EXATA-APROVADA",
  "license": "licença verificada para este uso",
  "hardware": "hardware e limites de memória disponíveis",
  "data_policy": "política aprovada para estes exemplos locais",
  "evaluation_protocol": "avaliação acadêmica e separação de validação definidas",
  "authorized": true
}
```

`authorized: true` só deve ser gravado depois que modelo, licença, hardware, política de dados e protocolo acadêmico estiverem decididos e a pessoa responsável autorizar a execução. O CLI e o painel recusam treino antes desse gate e verificam que o modelo coincide com o manifesto do dataset. Só o comando explícito pode carregar pesos e baixá-los quando necessário:

```bash
python -m pip install -e '.[train]'
finlabel train ./meu-projeto/.finlabel/training/reviewed.jsonl \
  --model-id REFERENCIA-EXATA-APROVADA \
  --output ./meu-projeto/.finlabel/models/adapters/risk-v1 \
  --project ./meu-projeto
```

O backend usa TRL `SFTTrainer` com PEFT `LoraConfig`, não publica adapters e desativa integrações de telemetria do trainer. FinLabel não distribui pesos nem presume compatibilidade: verifique licença, termos de uso, compatibilidade do modelo, memória disponível e protocolo de avaliação. Consulte a documentação oficial de [TRL SFTTrainer](https://huggingface.co/docs/trl/sft_trainer) e [PEFT LoRA](https://huggingface.co/docs/peft/en/package_reference/lora). Esta branch validou configuração e manifestos com dados sintéticos, sem baixar pesos ou treinar.

## API Python de revisão

```python
from finlabel import ReviewAction, ReviewLog

log = ReviewLog(".finlabel/review.jsonl")
log.record(
    record_id="row-00042",  # use referência opaca, nunca CPF/CNPJ ou dado bruto
    suggested_label="high",
    action=ReviewAction.CORRECTED,
    final_label="medium",
    model_ref="local-model-name@revision",
)
decisions = log.read()
```

O log não guarda linha, prompt ou notas livres. O MVP é para um processo escritor local; retenção, controle de acesso e compliance normativo não estão implementados.

## Contrato de previsão local estruturada

Backends autônomos implementam `predict(selected_values, *, task, max_new_tokens)`
e retornam `finlabel.labeling.prediction.Prediction`, um objeto imutável com rótulo,
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

O backend sempre devolve `calibrated_confidence=None` e `calibration_ref=None`.
O serviço autônomo só pode preencher confiança com um artefato de calibração
validado para política, tarefa, modelo e método. Sem evidência/calibrador,
o resultado permanece em quarentena. A construção de `Prediction` rejeita
NaN, infinitos, escores booleanos e confiança fora de `[0, 1]`; sua validação
estrutural não substitui a verificação da origem do calibrador pelo serviço.

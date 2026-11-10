# LazyLabel Local

Biblioteca em desenvolvimento para análise local e rotulagem autônoma de dados financeiros. Inclui conectores somente de leitura para CSV e SQLite, monitoramento de esquema, análises determinísticas, gráficos offline, painel web e fluxos locais de calibração e treino.

Inferência local usa Transformers quando o modelo é selecionado. O fine-tuning PEFT/LoRA e a promoção automática exigem política, rótulos confiáveis, evidência de avaliação e gates específicos da tarefa. Pesos só são baixados quando uma execução local explicitamente selecionada precisa deles.

English quickstart: [docs/quickstart.md](docs/quickstart.md)

## Instalação local

```bash
python -m pip install -e .
```

## Projeto e fontes

```bash
lazylabel project init ./meu-projeto
lazylabel source add-csv vendas ./dados/vendas.csv --project ./meu-projeto
lazylabel source add-sqlite carteira ./dados/carteira.db --table contratos --id-column contrato_id --project ./meu-projeto
lazylabel source set-type vendas valor decimal --project ./meu-projeto
```

A configuração fica em `.lazylabel/project.json`. Caminhos relativos são resolvidos a partir da pasta do projeto. CSV e SQLite são abertos somente para leitura. Análises agregadas não exigem ID; fluxos que comparam registros usam referências opacas e digests dos campos selecionados. O contrato `DataSource` descreve IDs, leitura, streaming e seleção de colunas.

## Captura e monitoramento de esquema

```bash
lazylabel schema capture vendas --output ./candidate-schema.json --project ./meu-projeto
lazylabel monitor vendas --baseline ./candidate-schema.json --project ./meu-projeto
```

A captura grava um candidato editável. Tipos são inferências; confirme colunas obrigatórias e limites para valores ausentes antes de salvar um baseline. Nenhum limite de qualidade é presumido.

## Análises e gráficos

```bash
lazylabel analyze vendas --question "Como as vendas mudaram por mês?" --plan ./analysis-plan.json --project ./meu-projeto
```

Planos JSON revisáveis podem ser executados sem modelo. Alternativamente, `--model-id` usa Transformers local quando o comando de análise é chamado. O planejador recebe pergunta e nomes/tipos de colunas, nunca as linhas da fonte. As operações numéricas usam `Decimal`; datas e números exigem mapeamento explícito por `source set-type`. Share exige medida, dimensão e escopo de denominador claros.

Cada execução cria `.lazylabel/analyses/<run_id>/` com plano, resultados, `chart.html` independente de CDN e hashes. A saída tabulada é a referência numérica. O painel limita visualização a 100 linhas, 2.000 pontos e 1 MiB por resposta JSON.

## Modelos na nuvem (Vercel AI Gateway)

Um id de modelo com prefixo `gateway:` usa o Vercel AI Gateway em vez de um modelo local (decisão 8 em `tcc/decisoes.md`):

```bash
export AI_GATEWAY_API_KEY=...   # chave criada no painel da Vercel
lazylabel analyze <fonte> --question "..." --model-id gateway:anthropic/claude-haiku-4.5 --project ./meu-projeto
```

Vale para o planejador de análise e para a tela **Perguntar** do painel (`/ask`): você pergunta, o LazyLabel calcula as linhas de forma exata e o modelo (`LAZYLABEL_UI_MODEL`, padrão `gateway:anthropic/claude-haiku-4.5`) só monta o layout com esses valores, usando um catálogo json-render de exibição, sem botões nem formulários. A tela gerada aponta para a análise com os números exatos. A rotulagem continua com modelo local: ela precisa da probabilidade de cada rótulo para calibrar a confiança, e o Gateway não fornece isso.

## Painel web local

```bash
python -m pip install -e '.[web]'
lazylabel serve --project ./meu-projeto --host 127.0.0.1 --port 8765
```

Abra `http://127.0.0.1:8765`. O serviço só faz bind em loopback, valida `Host`, `Origin` e CSRF e limita requisições. O painel React local mostra fontes e resultados agregados. A captura de esquema não salva até confirmação explícita. Gráficos têm CSP sandbox ao serem exibidos no painel.

Use `/labeling` para executar rotulagem, quarentena e ciclo de treino; `/training` mostra as etapas, avaliação congelada, estado do modelo, promoção, rejeição e rollback automáticos. Não há decisão manual por registro nem botão manual de promoção.

## Início rápido com dados sintéticos

```bash
lazylabel quickstart ./meu-projeto --model-id REFERENCIA-DO-MODELO-ESCOLHIDO [--model-revision REV]
```

O comando cria um projeto de exemplo com dados falsos, sem baixar nem escolher modelo:

- `lazylabel-sample-synthetic.csv`: 40 linhas sintéticas (`fake_amount`, `fake_days_past_due`, `fake_utilization` e `reference_label`);
- `task.json` e `policy.json`: tarefa e política `sample` (a coluna `reference_label` não é entrada de inferência);
- `.lazylabel/`: projeto inicializado, com a fonte `sample` e a tarefa `sample` já registradas, e a coluna `reference_label` registrada como rótulos confiáveis da tarefa `sample` (`provenance` `synthetic-sample`, `trust_kind` `provided_ground_truth`).

Esses rótulos são sintéticos e o `provenance` é uma declaração do operador (operator declaration), não uma verificação. Se o registro falhar, o comando informa o erro e mantém os arquivos, o projeto, a fonte e a tarefa já escritos.

`--model-id` é obrigatório; o valor só é gravado em `task.json`, e nenhum modelo é baixado, validado ou executado. O comando só escreve em um diretório inexistente ou vazio e recusa qualquer diretório não vazio (inclusive um projeto LazyLabel existente) sem alterar nada.

Os valores da política (`0.95` e `300`) são ilustrativos e precisam ser validados para a sua tarefa. Como `calibration_ref` é `null`, toda previsão fica em quarentena (`uncalibrated`) até existir evidência de calibração.

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

## Rótulos confiáveis e ciclo de fine-tuning

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

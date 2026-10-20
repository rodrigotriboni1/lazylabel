# FinLabel Local

Biblioteca em desenvolvimento para análise local e rotulagem assistida de dados financeiros, com revisão humana e rastreabilidade. Inclui conectores somente de leitura para CSV e SQLite, monitoramento explícito de esquema, análises determinísticas, gráficos offline, painel web e preparação de datasets para treino local.

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
finlabel review RUN_ID --project ./meu-projeto
```

O modelo recebe somente `input_columns` serializadas como dados, nunca a linha completa. A saída esperada é JSON com um rótulo configurado e uma justificativa curta opcional. Respostas inválidas são contadas e ignoradas. O arquivo imutável de sugestões guarda ID opaco, digest, rótulo, justificativa, tarefa e referência do modelo; não grava prompts ou linhas da fonte.

Na revisão CLI, use `accept`, `edit RÓTULO`, `reject` ou `skip`. O painel oferece as mesmas decisões e bloqueia linhas cuja fonte mudou. Eventos append-only ficam em `.finlabel/review.jsonl`; eventos antigos de esquema v1 continuam legíveis e os novos de v2 incluem proveniência.

## Preparação do dataset e fine-tuning

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

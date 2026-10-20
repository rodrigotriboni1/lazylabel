# FinLabel Local

Biblioteca em desenvolvimento para facilitar rotulagem assistida de dados financeiros com modelos locais, revisão humana e rastreabilidade.

O primeiro incremento implementa inspeção local de CSV. Fine-tuning e inferência serão adicionados depois de definir modelo, hardware e protocolo de avaliação.

## Instalação local

```bash
python -m pip install -e .
```

## Inspecionar um CSV

```bash
finlabel inspect caminho/para/dados.csv
finlabel inspect caminho/para/dados.csv --target classe
```

O comando calcula a contagem de linhas, nomes de colunas, tipos aproximados, valores ausentes e, opcionalmente, a distribuição da coluna-alvo. A leitura ocorre localmente e os registros não são impressos nem enviados pela rede. A estimativa de tipo usa no máximo as primeiras 1.000 células não vazias de cada coluna; as contagens de linhas, valores ausentes e classes são calculadas no arquivo inteiro.

O perfilamento não valida o significado da variável-alvo, não detecta PII e não substitui uma avaliação de qualidade ou compliance.

## Projeto local

```python
from finlabel import init_project, load_project

config_path = init_project("./meu-projeto")
project = load_project(config_path)
```

A configuração fica em `.finlabel/project.json`; os diretórios locais para esquemas, análises, execuções e tarefas são criados sem copiar os arquivos de origem. Caminhos relativos das fontes são resolvidos a partir da pasta do projeto. `DataSource` declara se oferece IDs estáveis, leitura somente, streaming e seleção de colunas. Fontes sem IDs estáveis servem para agregações; revisão persistente de linhas exige um identificador único e digest dos campos selecionados.

O núcleo continua sem dependências de interface ou modelos. Instale os extras `finlabel-local[web]` ou `finlabel-local[models]` somente quando precisar desses recursos.

## Adicionar fontes somente de leitura

```bash
finlabel project init ./meu-projeto
finlabel source add-csv vendas ./dados/vendas.csv --project ./meu-projeto
finlabel source add-sqlite carteira ./dados/carteira.db --table contratos --id-column contrato_id --project ./meu-projeto
finlabel source set-type vendas valor decimal --project ./meu-projeto
```

CSV identifica registros pela posição lógica no arquivo e calcula um digest dos campos selecionados. SQLite abre a base com `mode=ro`; a análise agregada não exige ID, mas revisão persistente de linhas exige uma coluna configurada com valores únicos e não nulos. Nenhum conector grava na fonte.

## Capturar e monitorar esquema

```bash
finlabel schema capture vendas --output ./candidate-schema.json --project ./meu-projeto
finlabel monitor vendas --baseline ./candidate-schema.json --project ./meu-projeto
```

O primeiro comando grava um candidato editável. Tipos capturados são inferências iniciais; confirme ou ajuste colunas obrigatórias e limites de valores ausentes antes de usar o arquivo como baseline. Nenhum limite de qualidade é presumido.

## Registrar revisão humana

```python
from finlabel import ReviewAction, ReviewLog

log = ReviewLog("artifacts/review.jsonl")
log.record(
    record_id="row-00042",  # use um identificador opaco, não CPF/CNPJ ou dado bruto
    suggested_label="bad",
    action=ReviewAction.CORRECTED,
    final_label="good",
    model_ref="local-model-name@revision",
)
decisions = log.read()
```

O log armazena apenas identificador fornecido pelo chamador, rótulo sugerido, decisão, rótulo final, referência opcional do modelo e horário UTC. Não armazena linha, prompt ou notas livres. O primeiro formato é append-only JSONL e suporta um único processo escritor; retenção, controle de acesso e requisitos normativos ainda não estão implementados.

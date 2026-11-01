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

# 01: Criar núcleo local para inspecionar CSV

**Status:** ready-for-human

**What to build:** Um pacote Python inicial com interface de linha de comando para inspecionar a estrutura de um CSV local sem exibir valores de linhas. Ver `.scratch/biblioteca-rotulagem-financeira/spec.md`.

## Critérios de aceite

- `finlabel inspect arquivo.csv` retorna contagem de linhas, nomes e quantidade de colunas, estimativa de tipo e contagem de valores ausentes.
- Com `--target coluna`, mostra distribuição das classes dessa coluna.
- Dados brutos não são enviados pela rede nem impressos no relatório.
- Erros de arquivo, encoding, CSV malformado ou coluna-alvo inexistente recebem mensagem clara.
- A biblioteca disponibiliza `inspect_csv(path, target=None)` e resultado serializável.
- O pacote declara versão mínima suportada de Python e instrução de instalação/uso.

## Fora do escopo

- Treino/fine-tuning ou inferência de LLM.
- Detecção automática de PII, compliance ou anomalias sem definição.
- Interface web.

## Notas

- Evitar dependências pesadas no núcleo.
- Não inferir que a variável-alvo é semanticamente válida só porque existe.

## Comments

- 19/10/2026: Implementado em `codigo/finlabel/` o pacote `finlabel-local`, com `inspect_csv`, perfil serializável e CLI `finlabel inspect`. Não foram adicionadas nem executadas verificações automatizadas nesta etapa.

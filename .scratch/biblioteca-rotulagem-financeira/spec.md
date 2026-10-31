# Biblioteca open source de rotulagem financeira local

## Objetivo

Criar uma biblioteca Python que simplifique a preparação, o fine-tuning local de modelos leves, a sugestão de rótulos financeiros, a revisão humana e a rastreabilidade das execuções.

## Primeiro incremento

Começar pelo núcleo sem dependência de modelo: ler um CSV local, validar a estrutura e produzir um perfil resumido sem imprimir ou enviar valores das linhas. Este módulo prepara uma seam estável para adapters de modelos locais em incrementos futuros. A execução de fine-tuning fica para um ticket próprio porque ainda depende de modelo, hardware, método de ajuste e protocolo aprovados.

O desenvolvimento segue o [loop local por tickets](LOOP.md): uma tarefa por ciclo, estado atualizado e revisão humana antes de avançar.

## Interfaces iniciais

- Python 3.9+.
- `finlabel inspect <csv> [--target COLUNA]` mostra estrutura, tipos aproximados, faltantes e distribuição do alvo, sem expor registros individuais.
- A biblioteca também expõe `inspect_csv(path, target=None)` e retorna um objeto de perfil serializável.
- Arquivos permanecem locais; o primeiro incremento não chama rede nem carrega modelos.

## Limites e critérios

- Tipo de coluna é inferido por amostra e deve ser apresentado como estimativa.
- Ausência inclui célula vazia; sentinelas como `NA`, `?` ou `unknown` exigirão configuração futura.
- O perfil não é auditoria de compliance nem detector completo de dados pessoais.
- O código não treina nem sugere rótulos ainda.
- Os incrementos seguintes devem suportar configuração de tarefa, adapters locais de inferência/fine-tuning, revisão humana, avaliação e trilha de auditoria.
- O núcleo também oferece `ReviewLog` para persistir decisões humanas em JSONL local, sem conteúdo das linhas; ver README do pacote para o contrato atual.

## Decisões abertas

- Escolher modelo Gemma exato, licença/termos aplicáveis, método de ajuste e hardware mínimo.
- Definir se o MVP usa fine-tuning eficiente (por exemplo, adaptadores) ou primeiro compara inferência sem ajuste.
- Definir dataset(s), política de serialização tabular, baseline e métricas.
- Confirmar com o orientador se esse escopo implementável corresponde à contribuição acadêmica aprovada.

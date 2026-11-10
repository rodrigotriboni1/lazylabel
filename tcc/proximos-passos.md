# Próximos passos

Atualizado em 09/11/2026. Faça na ordem; cada passo destrava o seguinte.

## Estado hoje

- **Funciona:** 427 testes Python e 53 do painel passam (`bash factory/checks.sh`).
- **Falta evidência:** o único experimento é sintético (24 exemplos, Qwen 0.5B, em `experimentos/sintetico-qwen-0.5b/`); o ciclo de treino só rodou com stub; não há comparação com baseline nem segunda base.

## 1. Fechar o tema com o orientador

- Levar as perguntas de [perguntas-orientador.md](perguntas-orientador.md).
- Registrar as respostas e atualizar a situação das decisões 7 e 8 em [decisoes.md](decisoes.md).
- Confirmar o prazo oficial de entrega e defesa e as regras sobre uso de IA ([uso-de-ia.md](uso-de-ia.md)).

## 2. Alinhar o protocolo

- Reescrever [protocolo-experimental.md](protocolo-experimental.md), que ainda descreve redes bayesianas, para o tema aprovado.

## 3. Rodar o experimento real

- Seguir [plano-experimento-real.md](plano-experimento-real.md): South German Credit, baseline de regressão logística (`codigo/experimento/baseline_logreg.py`) e LazyLabel avaliados no mesmo teste final, aberto uma única vez.
- Guardar o original da base, com hash, e os resultados em `tcc/experimentos/`.

## 4. Testar a portabilidade

- Aplicar o mesmo fluxo a uma segunda base; registrar o que mudou em configuração e o que exigiu mudar o código.

## 5. Escrever

- Monografia e apresentação final, usando [produto.md](produto.md), [decisoes.md](decisoes.md) e os resultados dos passos 3 e 4.

## Melhorias de software (só se sobrar tempo)

- Definir quando as fachadas antigas saem e fixar a versão do pacote (`0.1.0`).
- Ter calibrador e política de exemplo versionados, para o fluxo não começar com cobertura zero.

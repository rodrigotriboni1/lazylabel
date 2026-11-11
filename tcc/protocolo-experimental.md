# Protocolo experimental

Versão 0.2 — 10/11/2026. Substitui a versão 0.1 (27/09/2026, redes bayesianas e utilidade esperada), que continua no histórico do git. Vale para o tema da [decisão 7](decisoes.md), ainda pendente de aprovação do orientador; base, baseline e segunda base dependem das perguntas 3 e 4 de [perguntas-orientador.md](perguntas-orientador.md). A execução passo a passo está em [plano-experimento-real.md](plano-experimento-real.md).

## Pergunta

Até que ponto um fluxo configurável de rotulagem de dados financeiros, implementado como biblioteca (o LazyLabel), pode ser reaplicado a outras tarefas e bases sem alterar seu núcleo, mantendo rastreabilidade e controle de qualidade?

São dois estudos:

- **E1 — Qualidade na primeira base.** Os rótulos que o LazyLabel aplica são tão bons quanto os de um baseline simples? Em quantos registros ele aplica?
- **E2 — Reutilização na segunda base.** O mesmo fluxo roda em outra base mudando só configuração? O que exigiu mudar código?

Não é requisito de sucesso o LazyLabel vencer o baseline. Em dados tabulares, um modelo simples pode empatar ou vencer; esse resultado será reportado como tal.

## Hipóteses (E1)

Fixadas e datadas em [plano-experimento-real.md](plano-experimento-real.md) antes de qualquer resultado.

- **H1:** nos registros aplicados, a acurácia do LazyLabel é maior ou igual à do baseline nesses mesmos registros.
- **H2:** depois de um ciclo com promoção, a cobertura no teste é maior que zero.
- **H3:** a confiança do LazyLabel é calibrada (erro de calibração abaixo do limite registrado).

## Base e variável alvo

**South German Credit**, versão corrigida da UCI (escolha do orientador em 19/10/2026): 1000 registros e 20 variáveis preditoras. Preservar o arquivo original com as categorias codificadas e documentar nomes e significados a partir do código de leitura e da tabela da base.

O alvo é `kredit` (`credit_risk`): no código bruto, `0` é risco ruim (`bad`) e `1` é risco bom (`good`). No LazyLabel, os rótulos da tarefa são `bad` e `good`, com o mapeamento `{"0": "bad", "1": "good"}`. Nas métricas binárias, a classe positiva é `bad`. A recodificação fica explícita na configuração e nos resultados.

A amostra é estratificada (300 ruins e 700 bons); essa frequência não é prevalência populacional. O rótulo não equivale a inadimplência num horizonte definido.

Registrar fonte, data de obtenção, SHA-256 do arquivo, número de linhas, dicionário, mapeamento e proporção observada de classes.

## Separação e prevenção de vazamento

1. Divisão estratificada em 80% para desenvolvimento e 20% para teste final, com semente 42 e índices salvos (`split-indices.json`). Havendo duplicatas ou registros relacionados, revisar antes de dividir.
2. **Baseline:** cinco partições estratificadas só no desenvolvimento. Todo pré-processamento aprendido (codificação, escala) acontece dentro do treino de cada partição.
3. **LazyLabel:** recebe só o desenvolvimento como fonte e cria suas próprias partições congeladas (treino, calibração e holdout interno). O holdout interno decide a promoção; o teste final não participa.
4. A coluna `kredit` nunca entra nas colunas de entrada da tarefa.
5. Antes de abrir o teste final, registrar e congelar num commit: configuração do baseline, tarefa, políticas, `training-gate.json` e limiares.
6. O teste final é avaliado **uma única vez**, pelos dois sistemas. Se um erro exigir repetir, registrar a correção e não apresentar mais o teste como intocado.

## Sistemas comparados

1. **Baseline:** regressão logística com pré-processamento adequado às variáveis (`codigo/experimento/baseline_logreg.py`).
2. **LazyLabel:** modelo local de linguagem (candidato: `Qwen/Qwen2.5-0.5B-Instruct`) ajustado com LoRA pelo ciclo `lazylabel run`, com calibração e quarentena. O modelo é local porque a calibração precisa da probabilidade de cada rótulo, que o AI Gateway não fornece (decisão 8).

Se o orientador pedir (pergunta 2), acrescentar o LazyLabel com o modelo-base sem ajuste, para separar o efeito do ajuste fino. Não acrescentar sistemas só para tentar vencer no teste.

## Métricas (E1)

No teste final:

| Métrica | Baseline (todos) | Baseline (só aplicados pelo LazyLabel) | LazyLabel (aplicados) |
|---|---|---|---|
| Acurácia | ✓ | ✓ | ✓ |
| Macro-F1 | ✓ | ✓ | ✓ |
| Brier | ✓ | ✓ | ✓ |
| Erro de calibração (ECE, 10 faixas de mesma largura) | ✓ | ✓ | ✓ |
| Cobertura (aplicados ÷ total) | 100% | — | ✓ |

A comparação justa para H1 é a coluna do meio contra a da direita: os dois sistemas nos mesmos registros. Reportar também a curva de risco por cobertura do baseline (acurácia ao manter só os x% de maior confiança), para comparar com a cobertura que o LazyLabel escolheu.

## Medida de reutilização (E2)

Na segunda base (candidata: UCI Default of Credit Card Clients, sujeita à pergunta 4 e à checagem de vazamento temporal):

1. Repetir o mesmo fluxo e as mesmas métricas do E1.
2. Registrar cada alteração em duas colunas: **só configuração** (tarefa, política, mapeamento de rótulos, tipos de coluna, `training-gate.json`) e **exigiu mudar código** (qualquer diff em `codigo/lazylabel/src/`, com o `git diff` anexado).
3. Registrar os passos executados e o tempo de cada um, sem alegar economia de tempo sem uma tarefa de referência comparável.

"Exigiu mudar código" também é resultado válido e responde à pergunta da tese.

## Incerteza

O teste tem cerca de 200 registros, e o subconjunto aplicado pode ser menor. Para as diferenças principais, usar bootstrap pareado e estratificado com 1000 reamostragens, reutilizando os mesmos casos em cada comparação. Esses intervalos descrevem a incerteza de amostragem condicionada aos modelos ajustados, não toda a variabilidade do treino. Não concluir superioridade com diferenças pequenas ou intervalos amplos.

## Reprodutibilidade

Guardar em `tcc/experimentos/<experimento>/`: arquivo original e hash, índices da divisão, configurações congeladas, versões das bibliotecas, sementes, comandos executados, saídas de `run-status` e `model-status`, previsões por caso e tabela de resultados. O commit do código usado fica anotado no plano.

## Limitações conhecidas

- Uma base de crédito alemã antiga não permite afirmar nada sobre carteiras brasileiras.
- O holdout interno do LazyLabel sai de cerca de 800 registros divididos em três partições; o mínimo de holdout para promoção precisa caber nisso.
- Antes da primeira promoção, toda previsão pode ficar em quarentena; o resultado pode ser cobertura zero.
- O ciclo de treino real ainda não rodou de ponta a ponta fora de testes com stub.

## Fontes

- [UCI South German Credit](https://archive.ics.uci.edu/dataset/573/south+german+credit+update): correção da documentação e contexto amostral.
- [Grömping (2019), *South German Credit Data: Correcting a Widely Used Data Set*](https://www1.beuth-hochschule.de/FB_II/reports/Report-2019-004.pdf), apêndice B: codificação do alvo.
- [UCI Default of Credit Card Clients](https://archive.ics.uci.edu/dataset/350/defaultofcreditcardclients): segunda base candidata.
- [scikit-learn sobre calibração](https://scikit-learn.org/stable/modules/calibration.html): métricas probabilísticas e separação de dados para calibração.

Proporções de divisão, sementes, número de faixas e reamostragens são propostas deste protocolo, não exigências da UCI, da UFU ou do projeto original.

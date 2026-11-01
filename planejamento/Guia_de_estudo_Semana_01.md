# Guia de estudo da semana 1 do TCC

**Rodrigo Mialichi Triboni · Engenharia de Controle e Automação · UFU**  
**Orientador: Fabio Vincenzi**  
**Tema: Redes bayesianas e utilidade esperada aplicadas à seleção de next best action em sistemas automatizados de decisão**

Este guia reúne os conceitos necessários para entender e começar a executar seu projeto. Ao terminar, você deverá conseguir explicar o problema, a função de cada modelo, a separação dos dados e a forma de avaliar os resultados.

Você informou que Fabio já submeteu o documento enviado. Portanto, o projeto submetido é a referência de trabalho. A semana 1 serve para compreender e detalhar sua execução, sem reiniciar a aprovação do tema. Divisão 80/20, cinco partes de validação e outras configurações apresentadas aqui são propostas operacionais; não são exigências da UFU nem escolhas já confirmadas pelo orientador.

## 1. O que você está construindo

Seu sistema terá duas tarefas distintas:

1. **Estimar risco:** receber informações de um caso e calcular a probabilidade da classe de risco ruim.
2. **Escolher uma ação:** usar essa probabilidade e os custos e benefícios definidos para recomendar uma ação.

O fluxo pode ser resumido assim:

```text
Informações do caso
        ↓
Modelo probabilístico
        ↓
Probabilidade de risco
        ↓
Ações possíveis + custos e benefícios
        ↓
Cálculo da utilidade esperada
        ↓
Ação recomendada e justificativa
```

No trabalho, a rede bayesiana será comparada com a regressão logística na primeira tarefa. Na segunda, você estudará políticas de decisão e sua sensibilidade aos critérios adotados.

Uma explicação curta para usar em uma conversa:

> Vou comparar modelos que estimam risco de crédito e usar suas probabilidades para recomendar ações com custos e benefícios explícitos. Vou avaliar separadamente a qualidade das previsões e as decisões produzidas em cenários simulados.

## 2. Tema, pergunta, objetivo e escopo

Esses termos organizam o trabalho, mas têm funções diferentes.

| Termo | Significado | Aplicação ao seu TCC |
|---|---|---|
| Tema | Assunto estudado | Redes bayesianas e decisão por utilidade esperada |
| Pergunta de pesquisa | Questão que os experimentos procuram responder | Como os modelos estimam risco e como as políticas se comportam sob diferentes custos? |
| Objetivo | O que você fará para responder | Desenvolver, comparar e avaliar os modelos e as decisões |
| Hipótese | Expectativa que pode ou não ser sustentada | Probabilidades adequadas e utilidades explícitas podem apoiar boas decisões segundo o critério adotado |
| Escopo | Limites do que será realizado | Uma base pública, os modelos previstos, experimentos e protótipo simples |
| Metodologia | Caminho usado para investigar | Preparar dados, separar conjuntos, treinar, avaliar e documentar |

**Você não precisa demonstrar que a rede bayesiana sempre vence.** Um resultado equivalente ou inferior também é relevante se a comparação for correta e as limitações forem explicadas.

O projeto já prevê revisão bibliográfica, preparação de dados, modelagem, decisão, validação, protótipo e escrita. A interface vem depois da validação metodológica.

## 3. Entendendo os dados

Uma base de dados pode ser vista como uma tabela. Cada linha corresponde a um registro; as colunas descrevem suas características e, neste estudo, uma classe de risco conhecida.

| Conceito | O que significa |
|---|---|
| Registro ou observação | Um caso da base |
| Atributo, variável de entrada ou feature | Uma informação usada na previsão |
| Alvo, classe ou rótulo | O resultado que queremos prever |
| Evidência | Valor de uma variável conhecido no momento da inferência |
| Dataset | Conjunto de dados utilizado |
| Prevalência amostral | Proporção de uma classe na amostra |

O projeto utiliza o **Statlog German Credit Data**. Segundo a [UCI](https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data), a base possui 1.000 registros e 20 atributos de entrada. As contagens e os códigos deverão ser conferidos ao carregar os arquivos.

Para os exemplos deste guia, adotamos:

- `y = 1`: classe de risco ruim.
- `y = 0`: classe de risco bom.
- `p`: probabilidade estimada de `y = 1`.

Essa é nossa convenção de trabalho. Não se deve presumir que os códigos originais do arquivo já correspondam a ela. Também não se deve chamar o alvo de “inadimplência em 12 meses”, por exemplo, sem documentação que sustente esse significado.

**Ponto a registrar:** a [UCI disponibiliza o South German Credit](https://archive.ics.uci.edu/dataset/573/south+german+credit+update), que corrige problemas da documentação de codificação do Statlog e explica a sobreamostragem de créditos ruins. A versão da base e a interpretação dos códigos precisam ser documentadas; não vamos substituir silenciosamente a base do projeto. A proporção de casos ruins da amostra não é automaticamente a frequência de uma população real.

## 4. Probabilidade e rede bayesiana

Uma probabilidade representa incerteza. Estimar risco de 20% não significa que uma pessoa será “20% ruim”; significa atribuir probabilidade 0,20 ao evento definido como classe ruim, dadas as informações disponíveis.

**Probabilidade condicional** é uma probabilidade calculada considerando alguma informação. A expressão `P(Y = 1 | X = x)` pode ser lida como:

> Probabilidade de classe ruim, dadas as características observadas deste caso.

Uma **rede bayesiana** representa variáveis e suas dependências por um grafo acíclico dirigido:

- **Nós:** variáveis.
- **Setas:** dependências representadas na estrutura.
- **Acíclico:** não existe caminho seguindo as setas que volte ao mesmo nó.
- **Probabilidades condicionais:** quantificam como a distribuição de cada variável depende de seus pais no grafo.

“Pais” são os nós com setas chegando diretamente a um nó. As setas não comprovam causalidade por si só.

Na rede, distinguimos:

- **Estrutura:** quais relações são representadas.
- **Parâmetros:** os valores das probabilidades associadas à estrutura.
- **Inferência:** calcular uma probabilidade a partir das evidências disponíveis.

Uma probabilidade **a priori** é considerada antes das evidências do caso; a **posterior** é atualizada após incorporá-las. No seu estudo, você poderá mostrar quanto o risco muda em relação à estimativa sem essas evidências.

O projeto prevê comparar estrutura orientada por conhecimento e estrutura aprendida com dados. Na semana 1, basta entender essa diferença; os algoritmos de busca e a matemática detalhada ficam para a modelagem.

## 5. Regressão logística e baseline

Apesar do nome, a regressão logística é usada em classificação. Ela combina as entradas por coeficientes e transforma o resultado em uma probabilidade entre zero e um.

Ela será um **baseline**, isto é, uma referência de comparação. Não é um modelo feito para perder: deve ser implementado e ajustado com o mesmo cuidado metodológico.

| Modelo | O que recebe | O que produz |
|---|---|---|
| Regressão logística | Características do caso | Probabilidade de classe ruim |
| Rede bayesiana | Evidências do caso | Probabilidade de classe ruim |

Não confunda probabilidade com classificação. Uma saída `p = 0,30` é uma probabilidade. Transformá-la em “aprovar” ou “rejeitar” exige uma regra de decisão.

## 6. Utilidade esperada e next best action

**Utilidade** é um valor que representa a preferência por uma consequência. Pode expressar benefícios e perdas, sem necessariamente corresponder a reais.

Uma **matriz de utilidade** atribui um valor a cada combinação de ação e resultado. Exemplo exclusivamente didático:

| Ação | Caso bom | Caso ruim |
|---|---:|---:|
| Aprovar | +100 | −400 |
| Rejeitar | 0 | 0 |

Rejeitar ter valor zero é uma hipótese deste exemplo, não uma verdade sobre operações de crédito.

**Utilidade esperada** é a média dos valores possíveis, ponderada por suas probabilidades. Neste exemplo:

```text
EU(aprovar) = (1 − p) × 100 + p × (−400)
EU(rejeitar) = 0
```

| Risco estimado | EU de aprovar | EU de rejeitar | Recomendação |
|---|---:|---:|---|
| 10% | 0,90 × 100 − 0,10 × 400 = 50 | 0 | Aprovar |
| 20% | 0,80 × 100 − 0,20 × 400 = 0 | 0 | Empate |
| 40% | 0,60 × 100 − 0,40 × 400 = −100 | 0 | Rejeitar |

**Next best action**, neste trabalho, é a escolha da ação admissível com maior utilidade esperada. “Melhor” significa melhor segundo os valores e hipóteses definidos, não melhor em qualquer contexto. Empates precisam de uma regra documentada.

Neste exemplo, `EU(aprovar) = 100 − 500p`. Logo, aprovar é preferível quando `p < 0,20`. Isso mostra que maximizar utilidade pode equivaler a aplicar um limiar. Uma política de limiar não é necessariamente inferior; custos explícitos ajudam a justificar o limiar.

O projeto menciona ações intermediárias, como pedir informação ou encaminhar para análise manual. Para representá-las, será preciso definir suas consequências e custos. A base não mostra automaticamente o que ocorreria após cada uma dessas ações.

## 7. O que a simulação permite concluir

Na simulação inicial, usamos `P(y|x)` e uma matriz `U(a,y)`. Assumimos explicitamente que o estado de risco usado no cálculo não muda com a ação. A formulação mais geral do projeto, `P(y|a,x)`, envolveria probabilidades condicionadas também à ação; a base não permite estimar seus efeitos apenas com os registros disponíveis.

Podemos avaliar o comportamento das políticas sob hipóteses declaradas. Não podemos concluir que uma garantia reduziria o risco em determinado percentual ou que um banco obteria o lucro simulado na prática.

Uma conclusão adequada seria:

> Sob a matriz de utilidade e o protocolo adotados, a política apresentou maior utilidade média na avaliação simulada.

Também precisamos distinguir:

- **Utilidade esperada prevista:** calculada com as probabilidades do modelo.
- **Utilidade atribuída aos resultados observados:** calculada aplicando a matriz à ação escolhida e ao rótulo conhecido de cada caso.

A segunda evita avaliar a política somente com as próprias expectativas do modelo, mas continua sendo uma avaliação sob utilidades hipotéticas, sem observar consequências reais de ações alternativas.

## 8. Treino, validação e teste

| Função | Para que serve | Analogia |
|---|---|---|
| Treino | Ajustar o modelo aos dados | Resolver exercícios para aprender |
| Validação | Escolher configurações e comparar alternativas | Fazer simulados e ajustar a preparação |
| Teste | Avaliar o resultado depois das escolhas | Fazer a prova final |

**Parâmetros** são aprendidos no treinamento, como coeficientes e probabilidades condicionais. **Hiperparâmetros** controlam o ajuste ou a complexidade, como intensidade de regularização ou limite de pais por nó. Suas escolhas usam o desenvolvimento, não o teste final.

A proposta inicial é separar 80% para desenvolvimento e 20% para teste. Com 1.000 registros sem exclusões, isso corresponde a 800 e 200 casos.

Dentro dos 800, propomos **validação cruzada em cinco partes**:

1. Dividir os casos em cinco grupos de aproximadamente 160.
2. Treinar em quatro grupos, aproximadamente 640 casos.
3. Validar no grupo restante.
4. Repetir cinco vezes, alternando o grupo de validação.
5. Comparar os resultados das configurações nas mesmas divisões.

Cada rodada ajusta um modelo novamente. A proposta não consiste em treinar uma vez e continuar reaproveitando o modelo nas cinco rodadas.

Depois da seleção, o modelo é reajustado no conjunto de desenvolvimento, respeitando divisões internas necessárias à calibração. O teste final é usado após fechar as escolhas.

**Estratificação** procura preservar as proporções das classes nas divisões. **Semente aleatória** permite reproduzir uma divisão aleatória; guardar os índices utilizados torna o registro ainda mais claro.

## 9. Pré-processamento e vazamento de informação

**Pré-processamento** prepara as entradas para o modelo. Pode incluir codificar categorias, padronizar números, tratar ausências e discretizar variáveis.

**Discretizar** significa transformar números em faixas. Por exemplo, representar uma duração por intervalos. Os limites precisam ser justificados e, quando aprendidos a partir dos dados, ajustados somente no treino.

Um **pipeline** organiza essas transformações e o modelo em uma sequência reproduzível.

**Vazamento de informação** acontece quando informações que deveriam estar reservadas influenciam o ajuste ou as escolhas. Exemplos:

- Calcular faixas com a base inteira antes da divisão.
- Selecionar variáveis usando os resultados do teste.
- Aprender a estrutura da rede com todos os dados e só depois validar.
- Consultar repetidamente o teste para escolher a versão que parece melhor.

Na validação cruzada, as transformações aprendidas também precisam ser reajustadas no treino de cada rodada. Isso evita que a validação participe indiretamente da aprendizagem.

## 10. Como avaliar as previsões

**Desempenho preditivo** é a qualidade das previsões em casos que não orientaram aquele ajuste. Acurácia, sozinha, não descreve a qualidade das probabilidades necessárias ao seu decisor.

### Discriminação e ROC-AUC

Discriminação é a capacidade de atribuir riscos maiores aos casos ruins. ROC-AUC resume essa ordenação: 1 representa separação perfeita e 0,5 corresponde ao nível de ordenação aleatória. Valores abaixo de 0,5 também são possíveis.

**AUC de 0,80 não significa 80% de acertos.** A métrica não utiliza um único limiar nem garante probabilidades calibradas.

### Brier score

Para classificação binária, o Brier score é a média de `(p − y)²` nos casos avaliados. Quanto menor, melhor.

| Resultado observado | Probabilidade de classe ruim | Erro quadrático |
|---|---:|---:|
| Ruim, y = 1 | 0,90 | 0,01 |
| Ruim, y = 1 | 0,20 | 0,64 |
| Bom, y = 0 | 0,10 | 0,01 |

Nos três exemplos, a média é `(0,01 + 0,64 + 0,01) / 3 = 0,22`.

Uma previsão de 20% não está automaticamente errada porque o evento ocorreu em um caso: eventos pouco prováveis também acontecem. A qualidade probabilística é avaliada sobre um conjunto de casos.

### Calibração

Entre muitos casos com risco previsto próximo de 20%, esperamos uma frequência de classe ruim próxima de 20% se o modelo estiver bem calibrado nesse grupo.

O diagrama de calibração compara probabilidades médias previstas e frequências observadas em grupos de casos. Com poucos casos, as frequências oscilam; o gráfico não deve ser interpretado como uma medida exata sem incerteza.

Brier score e log loss não isolam calibração: também refletem outros aspectos da qualidade probabilística. Por isso, devem ser interpretados junto ao diagrama. A [documentação do scikit-learn](https://scikit-learn.org/stable/modules/calibration.html) explica essa distinção.

### Outras medidas previstas

| Medida | O que você precisa saber agora |
|---|---|
| Log loss | Penaliza previsões probabilísticas erradas, especialmente erros muito confiantes; menor é melhor |
| Precisão | Entre os casos classificados como positivos, quantos realmente eram positivos |
| Revocação ou recall | Entre os positivos reais, quantos foram identificados |
| Curva precisão e revocação | Mostra a relação entre essas duas medidas ao variar o limiar |
| Average precision | Resume essa curva por uma convenção específica; não é necessariamente igual à área trapezoidal chamada PR-AUC |

Aqui, “positivo” significa classe ruim, pela convenção adotada. O protocolo propõe Brier como critério principal de seleção; essa escolha operacional ainda deve ser consolidada antes dos experimentos.

## 11. Como avaliar as decisões

A avaliação da política considera ações e consequências atribuídas pela matriz, não apenas a qualidade das previsões.

- **Utilidade média:** média dos valores associados às decisões no cenário avaliado.
- **Custo médio:** média dos custos, quando houver uma definição explícita deles.
- **Distribuição das ações:** quantos casos foram aprovados, rejeitados ou encaminhados para cada alternativa.
- **Margem de utilidade:** diferença entre a melhor e a segunda melhor ação; uma margem pequena indica proximidade entre alternativas, não necessariamente baixa confiança estatística.

Para distinguir o efeito do modelo do efeito da política, o protocolo propõe comparar combinações de regressão logística e rede bayesiana com limiar e com utilidade esperada. As comparações precisam usar os mesmos casos e cenários; conjuntos diferentes de ações devem ser identificados.

**Análise de sensibilidade:** variar custos e benefícios e observar quanto as recomendações mudam. **Robustez a evidências incompletas:** retirar algumas informações de entrada de forma controlada e verificar o comportamento. Uma rede bayesiana pode inferir sem observar todas as variáveis, mas isso não garante desempenho superior com dados incompletos.

## 12. O que precisa ficar documentado

O **protocolo experimental** é o plano escrito antes dos experimentos. Ele registra o que comparar, como dividir os dados, quais métricas calcular e como escolher configurações.

A **reprodutibilidade** permite executar novamente o trabalho seguindo as mesmas instruções. Para isso, guardaremos:

- Fonte e versão da base, dicionário e transformações.
- Divisões dos dados e sementes.
- Código, versões de bibliotecas e configurações.
- Matriz de utilidade e hipóteses de cada cenário.
- Previsões, métricas, tabelas e figuras.
- Alterações no protocolo e suas justificativas.

Você não precisa implementar tudo nesta semana. Precisa compreender por que cada item existe e registrar as decisões iniciais.

## 13. Roteiro de estudo e entregas da semana

### Sessão 1 — Compreender o problema

Leia as seções 1 a 7. Escreva cinco a oito linhas respondendo: o que meu sistema prevê, como escolhe uma ação e o que a simulação não permite concluir?

### Sessão 2 — Compreender a avaliação

Leia as seções 8 a 11. Explique, sem copiar, a diferença entre treino, validação e teste. Refaça o exemplo de utilidade com risco de 30% e registre a recomendação.

### Sessão 3 — Organizar a execução

Leia o [protocolo preliminar](Protocolo_experimental.md). Marque termos que ainda geram dúvida, registre os prazos e sua disponibilidade e liste somente os detalhes de execução que precisam de alinhamento com Fabio.

### Checklist de conclusão

- [ ] Consigo explicar a proposta em um minuto.
- [ ] Distingo previsão de risco e escolha de ação.
- [ ] Entendo evidência, alvo, probabilidade e baseline.
- [ ] Sei calcular o exemplo de utilidade esperada.
- [ ] Entendo por que o resultado é uma avaliação simulada.
- [ ] Consigo explicar treino, validação, teste e vazamento.
- [ ] Distingo discriminação e calibração.
- [ ] Sei o que ROC-AUC e Brier medem, sem precisar decorar fórmulas avançadas.
- [ ] Registrei dúvidas e decisões operacionais pendentes.
- [ ] Registrei prazo de entrega e horas disponíveis, quando confirmados.

Não é necessário dominar BIC, algoritmos de busca de estrutura, calibração sigmoidal ou bootstrap nesta semana. Eles aparecerão quando forem necessários à implementação.

## 14. Perguntas para conferir seu entendimento

1. Um risco estimado de 10% significa aprovação automática?
2. Um modelo com AUC maior necessariamente tem probabilidades mais bem calibradas?
3. Posso escolher a estrutura da rede usando os resultados do teste?
4. Por que usar regressão logística se o tema é rede bayesiana?
5. No exemplo de +100 e −400, qual ação tem maior utilidade com risco de 30%?
6. Maior utilidade simulada comprova maior lucro em uma operação real?
7. Se a rede perder para o baseline, o TCC deixa de ter resultado?

### Respostas comentadas

1. Não. A ação depende das alternativas, custos, benefícios e restrições definidos.
2. Não. Ordenar os riscos e atribuir probabilidades adequadas são qualidades distintas.
3. Não. Isso faria o teste influenciar a construção. A seleção usa o desenvolvimento.
4. Para ter uma referência séria que permita avaliar a contribuição da rede.
5. Aprovar produz `0,70 × 100 − 0,30 × 400 = −50`; rejeitar produz zero. Rejeitar é preferível nesse cenário.
6. Não. As utilidades e hipóteses são demonstrativas, e os efeitos reais das ações não foram observados.
7. Não. Uma comparação correta também pode mostrar equivalência ou limitações da proposta.

## 15. Glossário para consulta rápida

| Termo | Definição curta |
|---|---|
| Inferência | Calcular probabilidades a partir do modelo e das evidências |
| Baseline | Modelo ou política de referência |
| Política de decisão | Regra que seleciona ações |
| Limiar | Valor de corte usado por uma regra |
| Utilidade | Valor atribuído a uma consequência |
| NBA | Next best action, a ação selecionada pelo critério definido |
| Discretização | Transformação de valores em faixas |
| Calibração | Correspondência entre probabilidades previstas e frequências observadas |
| Overfitting ou sobreajuste | Ajuste excessivo às particularidades do treino, com pior generalização |
| Generalização | Capacidade de funcionar em casos novos da distribuição de interesse |
| Contrafactual | Resultado que ocorreria sob uma alternativa à ação observada |
| Influence diagram | Representação que inclui incertezas, decisões e utilidades |
| Suavização | Uso de ajustes ou priores para evitar probabilidades extremas baseadas em poucas observações |

## 16. Materiais de referência

- Documento de projeto enviado e submetido por Fabio, conforme informado por Rodrigo: referência para objetivos e etapas.
- [Agenda semanal](../Agenda_semanal_TCC.md).
- [Resumo e acompanhamento da semana 1](Semana_01.md).
- [Protocolo experimental preliminar](Protocolo_experimental.md).
- [UCI — Statlog German Credit Data](https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data).
- [UCI — South German Credit](https://archive.ics.uci.edu/dataset/573/south+german+credit+update).
- [scikit-learn — Calibração de probabilidades](https://scikit-learn.org/stable/modules/calibration.html).

Para aprofundamento posterior, o projeto já cita Pearl, Jensen e Nielsen, Koller e Friedman e Russell e Norvig. Não é necessário ler esses livros integralmente para concluir a semana 1.

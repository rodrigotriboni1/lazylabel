# Semana 1 do TCC

Período proposto: 28/09 a 04/10/2026. Meta: compreender o projeto já submetido e detalhar seu protocolo de execução. Rodrigo informou que Fabio já submeteu o documento; não é necessário reiniciar a aprovação do tema. Os detalhes operacionais abaixo permanecem propostas a alinhar durante a orientação.

Comece pelo [guia de estudo da semana 1](Guia_de_estudo_Semana_01.md), com conceitos, exemplos e exercícios.

## Resumo para discutir com o orientador

**Tema:** redes bayesianas e utilidade esperada aplicadas à seleção de next best action.

**Pergunta proposta:** no estudo de caso German Credit, como uma rede bayesiana se compara à regressão logística na estimação probabilística de risco e como políticas de utilidade esperada se comparam a regras de limiar em utilidade obtida e estabilidade das recomendações, sob cenários de custos e benefícios explícitos?

**Objetivo geral:** desenvolver e avaliar um sistema que estime o risco de crédito e selecione uma ação demonstrativa por utilidade esperada, distinguindo a avaliação da previsão da avaliação da política de decisão.

**Hipótese de trabalho:** probabilidades adequadas e custos explícitos podem apoiar decisões consistentes com o critério escolhido. A pesquisa não pressupõe que a rede bayesiana superará a regressão logística. Resultados equivalentes ou inferiores também respondem à pergunta.

**Escopo mínimo:** uma base pública; regressão logística; rede com estrutura definida por conhecimento e rede com estrutura aprendida; avaliação probabilística; matriz de utilidade demonstrativa; comparação com política de limiar; sensibilidade aos custos; evidências incompletas; protótipo simples após a validação; monografia e código reproduzível.

**Limites:** a base não permite estimar o efeito causal de conceder crédito, pedir garantias ou encaminhar para análise. As ações são uma simulação metodológica. Não haverá implantação de política real nem uso de dados proprietários. O protótipo demonstra a metodologia e não é a contribuição principal.

**Protocolo proposto:** separar 20% para teste final e usar os 80% restantes para desenvolvimento, com validação cruzada estratificada em cinco partes. Ajustar transformações, estruturas, hiperparâmetros, calibração e limiares apenas no desenvolvimento. Congelar as escolhas antes do teste. Comparar modelos e políticas sobre os mesmos casos e cenários.

**Entregas finais:** relatório de comparação dos modelos; avaliação da política simulada e sua sensibilidade; protótipo; monografia; instruções de reprodução.

## Três sessões para esta semana

| Sessão | Tempo inicial | Atividade | Resultado esperado |
|---|---|---|---|
| 1 | 1h30 | Ler este resumo e conferir se consegue explicar a pergunta com suas palavras | Pergunta revisada e dúvidas anotadas |
| 2 | 2h | Ler o protocolo e discutir base, escopo e avaliação com o orientador, conforme disponibilidade | Decisões ou pontos pendentes registrados |
| 3 | 1h30 | Incorporar o retorno e confirmar datas e rotina de trabalho | Plano da semana 2 e protocolo atualizado |

Os tempos são provisórios. Se a reunião não ocorrer nesta semana, registrar as dúvidas e continuar as leituras; não marcar a validação como concluída.

## Checklist de acompanhamento

- [x] Organizar as pastas do projeto.
- [x] Preparar a pergunta e o escopo para discussão.
- [x] Preparar o protocolo experimental preliminar.
- [x] Identificar a fonte oficial da base e uma pendência sobre sua documentação.
- [ ] Rodrigo revisar a pergunta e explicar o objetivo com suas palavras.
- [x] Identificar o orientador: Fabio Vincenzi, informado por Rodrigo.
- [ ] Confirmar disponibilidade de acompanhamento com o orientador.
- [ ] Confirmar prazo oficial de entrega, defesa e requisitos do curso.
- [ ] Confirmar horas disponíveis por semana.
- [ ] Discutir com o orientador a versão da base e o protocolo.
- [ ] Registrar decisões e ajustar a agenda.

## Pauta para a orientação

1. Quais detalhes de execução precisam ser fechados para seguir a metodologia submetida?
2. Manter Statlog German Credit com documentação corrigida ou atualizar o projeto para South German Credit?
3. O desenho de 80% desenvolvimento e 20% teste atende ao trabalho?
4. Quais ações demonstrativas e hipóteses de utilidade fazem sentido? Aprovar e rejeitar podem formar o caso inicial; ações intermediárias exigem hipóteses adicionais.
5. Qual o prazo para entregar o texto ao orientador, antes do prazo oficial?

## Decisões ainda não confirmadas

- Orientador: Fabio Vincenzi (informado por Rodrigo).
- Prazo do texto para revisão:
- Prazo oficial de entrega:
- Data e duração da defesa:
- Horas semanais disponíveis:
- Versão da base escolhida:
- Alterações solicitadas no protocolo:

Concluir a preparação dos arquivos não significa concluir as validações acadêmicas da semana.

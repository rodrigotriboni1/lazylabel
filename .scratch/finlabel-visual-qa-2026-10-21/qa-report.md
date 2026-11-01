# FinLabel — QA visual do painel local

**Data:** 2026-10-21  
**Base inspecionada:** `codex/finlabel-lifecycle` em `59f6205`  
**Correções:** branch `codex/visual-qa-overview`, commit `c2e9a85`  
**Projeto de demonstração:** `/tmp/finlabel-visual-qa-project` (vazio, sem dados de usuário)  
**Servidor para revisão:** `http://127.0.0.1:8765` (loopback; serviço deixado ativo)

## Resultado

- Inspecionei `/`, `/analysis`, `/monitor`, `/labeling`, `/review` e `/training` em 1440×900 e 390×844. As rotas abriram diretamente e após atualização; todas ficaram sem overflow horizontal.
- A navegação móvel abriu Análises; os atalhos da visão geral abriram Análises e Monitoramento.
- No ciclo de treinamento, as sete etapas aparecem na ordem aprovada. A lista acessível contém sete itens e marca “Verificar dados” como atual. Sem dataset ou autorização configurada, o painel mantém o estado pendente e não oferece início de treino.
- O console do navegador não registrou erros durante a revisão.
- Corrigi dois problemas na visão geral: cabeçalho repetido e cartão de fontes vazio esticado à altura da coluna de atalhos. A revisão independente aprovou o diff; confirmei também a apresentação em viewport móvel.
- `npm ci` e `npm run build` concluídos para gerar os assets empacotados. `git diff --check` passou. Não executei testes automatizados, treinamento, inferência nem carregamento de modelos.

## Evidências

Capturas completas por rota e viewport estão na pasta `evidence/`:

- Visão geral: [desktop](evidence/overview-1440x900.png), [celular](evidence/overview-390x844.png)
- Análise: [desktop](evidence/analysis-1440x900.png), [celular](evidence/analysis-390x844.png)
- Monitoramento: [desktop](evidence/monitor-1440x900.png), [celular](evidence/monitor-390x844.png)
- Rotulagem: [desktop](evidence/labeling-1440x900.png), [celular](evidence/labeling-390x844.png)
- Revisão: [desktop](evidence/review-1440x900.png), [celular](evidence/review-390x844.png)
- Treinamento: [desktop](evidence/training-1440x900.png), [celular](evidence/training-390x844.png)
- Diagrama móvel em rolagem: [parte superior](evidence/training-mobile-flow-top.png), [sete etapas visíveis](evidence/training-mobile-flow-middle.png)

## Limites

A revisão usou estados vazios com projeto sintético. Não cobre aparência com fontes, rótulos, avaliações ou versões reais; também não avalia desempenho nem compatibilidade de pesos. A branch de correção está disponível para revisão e permanece separada da branch de integração. O serviço ativo usa somente `/tmp/finlabel-visual-qa-project` e pode ser encerrado com Ctrl+C no processo local.

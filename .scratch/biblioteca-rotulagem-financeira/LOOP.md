# Loop local de desenvolvimento

Este loop usa o issue tracker Markdown local do repositório. Cada ciclo resolve um ticket pequeno, deixa o resultado revisável e atualiza o estado antes de avançar.

## Ciclo

1. Ler `AGENTS.md`, `2026-10-19-design-mvp.md` (especificação aprovada/canônica), este arquivo, o estado do Git e o primeiro ticket `ready-for-agent` sem bloqueadores. `spec.md` mantém o histórico do primeiro incremento e não substitui a especificação aprovada.
2. Se o ticket não estiver especificado o bastante, fazer pesquisa técnica/read-only quando possível. Se uma decisão do usuário ou orientador for necessária, registrar a pergunta no ticket como `needs-info` e parar esse item.
3. Implementar somente o escopo do ticket; manter processamento de dados financeiros local e não introduzir chamadas externas sem uma decisão explícita de arquitetura.
4. Revisar as mudanças e atualizar o ticket para `ready-for-human`, registrando arquivos alterados, comportamento entregue, limitações e comandos que não foram executados.
5. Atualizar `spec.md` e o mapa do TCC somente quando o escopo ou uma decisão mudar.
6. Parar para revisão humana ao final de cada ticket; após direção/feedback do usuário, iniciar o próximo ticket não bloqueado.

## Guardrails

- Não fazer fine-tuning ou carregar bases do usuário até haver modelo, licença, hardware, política de dados e protocolo de avaliação definidos.
- Não afirmar que a biblioteca garante compliance, privacidade absoluta ou qualidade dos rótulos.
- Distinguir previsões do modelo, decisões humanas e rótulos de referência.
- Para esta conclusão do FinLabel, o usuário autorizou explicitamente a implementação completa e os testes automatizados; essa autorização é específica desta campanha e não transforma testes em execução automática nos ciclos futuros.
- Não buscar, instalar ou executar um loop de agente indefinido. O avanço ocorre por tickets locais revisáveis, um ciclo por vez.

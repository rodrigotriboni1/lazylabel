# Design: ciclo local de rotulagem e fine-tuning supervisionado

**Data:** 2026-10-20  
**Estado:** proposta escrita para revisão do autor; não iniciar implementação desta especificação antes da aprovação escrita e de um plano de execução aprovado.

## Objetivo

Especificar o ciclo que transforma sugestões de rótulos revisadas por uma pessoa em um adapter local avaliado, rastreável e reversível. O objetivo acadêmico e de produto é demonstrar que o fluxo configurável da biblioteca pode ser reutilizado em tarefas financeiras distintas, preservando supervisão humana, proveniência e limites explícitos para dados locais.

Esta especificação detalha o ciclo de rotulagem e treinamento do MVP. A visão geral de análise exploratória, perguntas em linguagem natural, tendências e composição/participação continua descrita em `.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`.

## Usuários e sucesso

O usuário principal é um desenvolvedor que integra a biblioteca Python ou CLI à própria tarefa. O painel web local fornece uma segunda interface para o mesmo estado e serviços.

O fluxo será demonstrável quando a pessoa conseguir conectar CSV ou SQLite em modo somente leitura, obter sugestões para uma tarefa configurável, revisar exemplos, preparar explicitamente um dataset, executar fine-tuning local, comparar base e adapter em exemplos reservados, decidir se ativa o adapter e voltar a uma versão anterior. A mesma interface e os mesmos contratos devem aceitar mais de uma tarefa financeira sem impor uma taxonomia financeira fixa.

## Decisões aprovadas

- Fonte original: CSV e SQLite no MVP, por conectores extensíveis e somente leitura.
- Operação: fluxo completo disponível pela CLI e por painel web local; ambas as interfaces usam os mesmos serviços Python.
- Tarefa: instruções, campos de entrada e rótulos configuráveis, com validação de saída estruturada.
- Revisão humana: aceitar, editar, rejeitar ou ignorar sugestões; manter registro local e preservar a saída original do modelo.
- Dataset: criar somente mediante ação explícita; incluir apenas campos escolhidos e decisões humanas aceitas/corrigidas.
- Monitoramento estrutural e de qualidade: regras determinísticas; a LLM não decide se a fonte está estruturalmente íntegra.
- Fine-tuning inicial: Transformers + PEFT/LoRA, sob comando/ação explícita e com pesos/dados locais. Compatibilidade só é declarada para combinações efetivamente suportadas.
- Gate do dataset: falhas de integridade bloqueiam o treino. Cobertura baixa ou desbalanceamento mostram ressalvas e podem permitir treino exploratório somente após confirmação explícita.
- Cobertura: mínimo por rótulo configurável. A ferramenta mostra contagens e desbalanceamento; um preset, se existir, é orientação e não garantia de qualidade.
- Avaliação: comparar modelo-base e adapter nos mesmos exemplos reservados que não participaram do ajuste; mostrar métricas gerais e por rótulo, ressalvas e erros inspecionáveis.
- Aprovação: pessoa decide entre ativar o adapter e manter o modelo-base; não há promoção automática.
- Versionamento: guardar versões locais imutáveis com proveniência; ativar explicitamente e permitir reversão para versão anterior.
- Interface aprovada visualmente: React + Vite + shadcn/ui no painel, servido localmente pelo FastAPI; CLI e painel acionam os mesmos serviços de domínio. A migração do painel existente em Jinja é parte do plano, não está presumida como concluída.
- Privacidade: fonte somente leitura; linhas não são enviadas a LLM externa. Uma LLM externa opcional no onboarding recebe somente metadados que a pessoa selecionou e aprovou explicitamente.

## Fluxo funcional

1. **Configurar fonte e tarefa.** A pessoa escolhe CSV ou SQLite, uma tarefa, as colunas de entrada e os rótulos válidos. Fontes são abertas em modo somente leitura. Fontes e revisões permanecem locais.
2. **Perfilhar e monitorar.** Regras determinísticas descrevem esquema, tipos, valores ausentes e mudanças estruturais configuradas. Problemas são apresentados com localização e contagens; o monitoramento não altera a fonte.
3. **Sugerir rótulos.** O backend local recebe apenas os campos selecionados para a tarefa. A resposta precisa seguir o formato configurado e usar um rótulo permitido. Respostas inválidas são sinalizadas, não viram sugestões válidas. Sugestões e conteúdo original do modelo são persistidos separados das decisões humanas.
4. **Revisar.** A pessoa aceita, corrige, rejeita ou ignora sugestões na CLI ou no painel. Cada decisão registra a sugestão associada, ação, rótulo final quando aplicável, timestamp e proveniência necessária para auditoria local.
5. **Preparar dataset explicitamente.** Uma ação explícita seleciona decisões aceitas/corrigidas e campos configurados. Rejeitados, ignorados, não revisados, inválidos, sem proveniência ou desatualizados são excluídos e contabilizados. A origem nunca é modificada. Um manifesto local identifica entradas, configuração, snapshot/hash e exclusões sem copiar campos não selecionados.
6. **Validar dataset.** Antes de carregar pesos, validar schema, exemplos vazios, integridade/proveniência, duplicidade e cobertura por rótulo. Falhas de integridade bloqueiam. Cobertura baixa ou desbalanceamento mostram contagens e avisos; a pessoa pode confirmar um treino exploratório. Os valores mínimos são configuração da tarefa, não um padrão universal nem evidência de desempenho.
7. **Separar treino e avaliação.** O conjunto reservado é definido antes do fine-tuning e jamais usado para ajustar pesos. A divisão, seed, IDs opacos/snapshot e contagens ficam no manifesto. A estratégia de divisão deve ser configurável para evitar vazamento temporal ou por entidade quando isso for relevante. O MVP não deve alegar que uma divisão aleatória serve a todos os problemas financeiros.
8. **Treinar explicitamente.** O comando/ação explícita executa o backend Transformers + PEFT/LoRA. O treino salva localmente adapter e metadados, incluindo base/revisão, parâmetros, dependências, hash do dataset, split/seed e versões. Sem sobrescrever artefatos existentes; sem upload, hub ou telemetria habilitados por padrão.
9. **Avaliar o candidato.** Base e adapter são avaliados no mesmo holdout e com o mesmo contrato de entrada/saída. Mostrar métricas por rótulo e agregadas, contagens e exemplos de erro. Uma ressalva deve acompanhar conjunto pequeno ou avaliação que não suporte conclusão firme. A biblioteca não escolhe uma versão vencedora por um único número.
10. **Decidir e versionar.** A pessoa revisa evidências e escolhe ativar o candidato ou manter o modelo-base/adapter atual. Ativação é explícita. Uma versão aprovada registra artefatos e proveniência; uma versão anterior pode ser reativada sem novo treino.
11. **Fechar o ciclo.** Novas sugestões usam somente a versão explicitamente ativa e retornam ao mesmo processo de revisão. A aceitação de uma sugestão não altera pesos imediatamente; um próximo ajuste exige preparar dataset e iniciar novo treino explicitamente.

## Gate e estados

O estado apresentado deve distinguir, no mínimo:

- **Bloqueado:** falha de integridade, schema inválido, dataset vazio, rótulo fora da tarefa, evento sem proveniência suficiente ou dados alterados desde a sugestão.
- **Pronto com ressalvas:** cobertura baixa ou classes desbalanceadas. Exibir o problema e permitir somente um treino exploratório após confirmação explícita.
- **Pronto:** critérios de integridade passam e mínimos configurados foram atingidos. “Pronto” não significa que o modelo terá bom desempenho.
- **Candidato aguardando avaliação/aprovação:** treino terminou, mas adapter não está ativo.
- **Ativo / rejeitado / substituído:** estados locais versionados. Rejeitar ou desativar não apaga métricas nem histórico.

Os controles devem informar razões concretas e ação corretiva. Nenhum erro de treino ou avaliação pode alterar a fonte, apagar decisões ou substituir silenciosamente uma versão ativa.

## Avaliação

A tabela comparativa deve apresentar pelo menos uma métrica global apropriada à tarefa e métricas por classe (por exemplo, precisão, recall e F1 para classificação), junto de suporte/contagem por classe. Métricas e nomes devem ser definidos pelo tipo de tarefa, não codificados como métricas universais para qualquer análise financeira. Para tarefas incompatíveis com essas métricas, o backend de avaliação deverá fornecer métricas adequadas explicitamente antes de declarar suporte.

A pessoa pode inspecionar erros por exemplo usando somente os campos selecionados/autorizados para a tarefa. Números de protótipos visuais são ilustrativos, nunca resultados publicados. Um holdout pequeno ou sem representação de um rótulo gera alerta e impede interpretação conclusiva; a especificação não fixa um limite amostral universal.

## Arquitetura e responsabilidades

- **CLI:** expõe configuração, perfil/monitoramento, sugestão, revisão, exportação, validação do dataset, treino, avaliação, aprovação/ativação e reversão por ações explícitas.
- **Painel web local:** expõe o mesmo ciclo com gráficos/tabelas de análise e revisão visual. React/Vite/shadcn/ui é a direção aprovada; FastAPI serve a aplicação local e chamadas para os serviços Python. Host/Origin, CSRF, cookies e limites de requisição seguem os controles definidos no plano existente.
- **Núcleo Python:** contratos de tarefa e rótulo, conectores somente leitura, regras estruturais, serviços de sugestão e revisão, preparação de dataset, treino, avaliação e registro/versionamento de adapters. CLI e painel não duplicam regras do domínio.
- **Persistência local:** configurações, runs, sugestões, decisões, manifestos, métricas e versões ficam no diretório local do projeto. Escritas ocorrem apenas nessa área de trabalho da biblioteca, após ações explícitas quando criam dataset, treinam ou ativam modelo.
- **Backend de modelo:** interface intercambiável com uma integração inicial Transformers + PEFT/LoRA. Modelo de rótulos, eventual planejador analítico e gerador de resumos são responsabilidades configuráveis separadas; não presumir que um adapter de rótulo seja bom para planejamento analítico.

## Falhas e recuperação

- Resposta do modelo malformada/desconhecida: marcar inválida e continuar processando registros independentes, sem gravar rótulo aceito.
- Fonte alterada ou digest divergente: impedir exportação da linha divergente, sinalizar stale e exigir nova sugestão/revisão.
- Gate bloqueado: não carregar pesos nem iniciar treino; exibir critério e como corrigir.
- Falha de dependência, download ou treino: manter fonte, revisão, manifesto prévio e modelo ativo intactos; registrar erro sanitizado localmente.
- Adapter sem melhoria ou com regressão relevante por classe: mantê-lo inativo até decisão humana; permitir rejeitar e revisar dados/configuração.
- Falha ao carregar adapter ativo: voltar ao modelo-base ou versão ativa anterior, reportando claramente a falha; nunca marcar versão quebrada como ativa.
- Reversão: trocar referência local da versão ativa para uma versão anterior íntegra, mantendo histórico.

## Segurança e privacidade

- Sem execução de código/SQL arbitrário criado pelo modelo.
- Sem mutação da fonte CSV/SQLite.
- Nenhuma linha de dados ou prompt com valores de registros segue para LLM externa, telemetria ou hub.
- O servidor escuta em localhost por padrão; revisão, exportação, treino e ativação exigem ações explícitas e proteções contra requests locais não originados pela aplicação.
- Exibir referência/licença/requisitos conhecidos do modelo antes de baixar ou treinar. Não distribuir pesos nem alegar compatibilidade universal.
- A biblioteca não afirma compliance regulatório, anonimização automática ou qualidade garantida.

## Fora do escopo desta etapa

- Aprendizado online ou alteração de pesos a cada clique de revisão.
- Promoção automática de adapter, deploy em nuvem ou compartilhamento multiusuário.
- Envio de registros para APIs de LLM, monitoramento contínuo agendado ou escrita na fonte.
- Um limiar amostral ou uma métrica universal que prometa qualidade.
- Suporte garantido a qualquer arquitetura/modelo, tarefa ou conector além dos caminhos implementados e demonstrados.
- Alegações de causalidade, ganho financeiro, risco de crédito real ou market share sem dados e definições validados.

## Critérios de aceite do ciclo

1. CLI e painel operam os mesmos serviços e persistência local para sugestão, revisão, exportação, treino e decisão de adapter.
2. Fonte original permanece byte a byte/logicamente inalterada; conectores expõem leitura somente.
3. Dataset é criado apenas sob pedido explícito, a partir de decisões aceitas/corrigidas e campos selecionados; stale, rejeitados, ignorados e inválidos não entram.
4. Falhas de integridade bloqueiam o treino antes de carregar pesos. Cobertura baixa exibe advertências e só permite treino exploratório após confirmação explícita.
5. Mínimos por rótulo são configuráveis e aparecem junto das contagens e do desbalanceamento.
6. O holdout é separado antes do treino, fica fora do ajuste e é idêntico ao usado na comparação base/adapter; split, seed e contagens são registradas.
7. Métricas agregadas e por rótulo, suporte, avisos e erros podem ser inspecionados antes da aprovação.
8. Treino produz artefato local versionado sem substituir o modelo ativo; falhas deixam artefatos ativos e históricos intactos.
9. Só uma decisão explícita ativa o adapter; novas sugestões indicam versão ativa e continuam exigindo revisão humana.
10. É possível reativar uma versão local anterior sem novo treino.
11. Não ocorre envio externo de valores de registros; painel local tem controles de origem/CSRF e limites de requisição.

## Questões para o plano de implementação e validação acadêmica

- Definir critério operacional de integridade e comportamento para linhas/duplicatas, sem impor limites universais de amostra.
- Escolher split apropriado para o dataset financeiro acadêmico (temporal, por entidade ou estratificado), antes de avaliar resultados.
- Selecionar métricas primárias e secundárias para a tarefa demonstrativa com o orientador; considerar custo assimétrico dos erros sem afirmar lucro causal.
- Fixar modelo/revisão, licença, hardware, dependências e limite de memória antes de baixar pesos ou treinar.
- Definir como persistir o registro imutável de modelos e qual estratégia protege contra ativação de diretório incompleto/corrompido.
- Integrar este ciclo com a visão de análise local já registrada na especificação de MVP; manter o modelo de rótulos separado de planejamento/resumo analítico.
- O plano anterior menciona Jinja2, enquanto a direção visual aprovada agora é React/Vite/shadcn/ui. O plano de execução deverá reconciliar essa diferença e não manter dois painéis concorrentes.

## Revisão de consistência

- **Placeholders:** não há TODO/TBD. As questões dependentes de contexto acadêmico ou hardware estão explicitamente listadas como decisões do plano, sem bloquear o contrato de produto.
- **Consistência:** cobertura baixa é aviso com confirmação exploratória; falha de integridade continua bloqueio. Treino nunca promove ou altera pesos automaticamente. A preparação de dataset continua explícita e a reversão conserva histórico.
- **Escopo:** esta especificação cobre um único ciclo coeso de rotulagem e adapter. A exploração analítica segue a especificação MVP existente e compartilha o núcleo/configuração, sem obrigar que o adapter de rotulagem realize análise.
- **Ambiguidades:** “pronto” significa somente que critérios configurados foram satisfeitos, não qualidade garantida. Compatibilidade fica restrita aos backends/tarefas realmente demonstrados. A estratégia de split e as métricas exatas dependem do protocolo da tarefa e devem ser fixadas antes do experimento.

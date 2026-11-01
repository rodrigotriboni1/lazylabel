# Fontes institucionais de dados de crédito

**Data da pesquisa:** 19/10/2026  
**Objetivo:** identificar fontes nacionais e internacionais para análise de crédito, tendências da carteira e contextualização do protótipo do TCC.

## Resumo executivo

Para uma demonstração com séries temporais reais no Brasil, a fonte pública mais útil encontrada é o **SCR.data do Banco Central do Brasil**. Ele publica dados mensais agregados de carteira ativa, inadimplência e ativos problemáticos, com cortes por tipo de cliente, modalidade, estado e outros segmentos. O histórico começa em junho de 2012, os dados têm defasagem de aproximadamente 30 dias e há downloads anuais em CSV compactado. Portanto, ele permite exibir tendências de mercado por segmento, mas não revela uma carteira individual nem observações identificáveis de tomadores. [BCB — SCR.data](https://dadosabertos.bcb.gov.br/pt_BR/dataset/scr_data), [Metodologia SCR.data v2](https://www.bcb.gov.br/pda/desig/metodologia_versao2.pdf)

Para o TCC, isso permite separar três níveis: **(1)** South German Credit para comparação de modelos individuais em dados transversais; **(2)** SCR.data para tendências agregadas reais no mercado de crédito brasileiro; **(3)** eventual cenário sintético para demonstrar uma carteira fictícia com snapshots mensais. Não se deve apresentar os dados agregados do BCB como se fossem a carteira individual monitorada por um analista.

## Fontes brasileiras

| Fonte | O que fornece | Frequência/escopo | Adequação ao projeto |
|---|---|---|---|
| **Banco Central — SCR.data** | Carteira ativa, inadimplência e ativo problemático, agregados e segmentáveis por PF/PJ, modalidade, UF, CNAE, porte/rendimento, origem de recursos, indexador e segmento institucional. | Mensal; Brasil; UF como granularidade geográfica; histórico desde jun/2012; publicação cerca de 30 dias após o fim do período. | **Alta** para gráficos de tendência reais de mercado e comparação por segmento; não é dado cliente-a-cliente nem carteira de uma instituição específica. [BCB](https://dadosabertos.bcb.gov.br/pt_BR/dataset/scr_data) |
| **BCB — SGS (Sistema Gerenciador de Séries Temporais)** | Séries econômicas e financeiras, incluindo indicadores de crédito e inadimplência. Há séries mensais de inadimplência de modalidades específicas. | Periodicidade depende da série; consulta pública e catálogo por código/tema. | **Alta** para selecionar poucas séries para contexto temporal e compor gráficos simples. É importante registrar o código da série, unidade e definição usada. [SGS](https://www3.bcb.gov.br/sgspub/) |
| **BCB — Estatísticas Monetárias e de Crédito** | Publicações analíticas periódicas sobre saldo de crédito, concessões, inadimplência, custo do crédito e endividamento/comprometimento de renda. | Publicação mensal com análise e séries oficiais relacionadas. | **Alta** para contexto macroeconômico e interpretação dos movimentos; os dados brutos estruturados são mais convenientes via SGS/SCR.data. [Estatísticas de crédito](https://www.bcb.gov.br/estatisticas/estatisticasmonetariascredito) |
| **Serasa Experian — Indicadores de inadimplência** | Indicadores de empresas inadimplentes, dívidas e outros levantamentos; algumas publicações segmentam por UF, setor e porte. | Publicações mensais; séries históricas públicas variam por indicador. | **Média** para contexto de mercado e comparação de tendências. A inadimplência baseada em registros negativos de bureau não é idêntica à inadimplência de operações bancárias do SCR. Verificar disponibilidade, metodologia e licença da série antes de integrar. [Indicadores econômicos](https://www.serasaexperian.com.br/conteudos/indicadores-economicos/), [metodologia do indicador empresarial](https://www.serasaexperian.com.br/sala-de-imprensa/indicadores/). |
| **SPC Brasil — Cadastro Positivo** | Histórico de pagamentos e informações usadas na formação do histórico/score, em contexto de base cadastral. | Acesso sujeito às regras do Cadastro Positivo e aos direitos do titular; não equivale a uma base pública de microdados. | **Baixa** como fonte pública diretamente baixável para o protótipo; útil para entender o ecossistema de dados de crédito, consentimento e direitos. [SPC Brasil](https://www.spcbrasil.org.br/cadastropositivo/consumidor/seus-direitos) |

### Limitação importante do SCR.data

O SCR.data foi elaborado a partir de informações detalhadas de operações reportadas ao SCR, mas a divulgação pública encontrada é **agregada**. Os dados são publicados por dimensões de segmento e geografia, não como histórico de cada contrato ou de cada consumidor/empresa. Ele permite responder “como evoluiu a inadimplência de crédito pessoal PF no Brasil/UF?”; não permite responder “como evoluiu a carteira de clientes do Banco X ou a conta de um tomador específico?”. A própria página do conjunto informa que a divulgação é agregada, mensal e pode divergir de outras publicações do BCB por diferenças na base e metodologia. [BCB — SCR.data](https://dadosabertos.bcb.gov.br/pt_BR/dataset/scr_data)

## Fontes internacionais

| Órgão | Dados e indicadores | Frequência/uso | Adequação ao projeto |
|---|---|---|---|
| **Bank for International Settlements (BIS)** | Crédito total e bancário ao setor privado não financeiro, hiato crédito/PIB e debt service ratios (parcela da renda usada para serviço da dívida). | Crédito publicado trimestralmente; DSR também trimestral, séries agregadas de vários países. | **Alta** para comparar contexto macro/pressão de endividamento entre países e estudar tendências; não substitui monitoramento de carteira individual. A BIS alerta que DSR agregado aproxima a dinâmica temporal, mas pode não medir precisamente o nível frente a microdados. [BIS Statistics](https://www.bis.org/statistics), [BIS DSR](https://data.bis.org/topics/DSR) |
| **International Monetary Fund (IMF) — Financial Soundness Indicators (FSI)** | Qualidade de ativos, NPL sobre empréstimos brutos, NPL líquido de provisões sobre capital, distribuição setorial de crédito, capital, rentabilidade e liquidez. | Dados reportados por países; periodicidade e comparabilidade variam, com metadados nacionais. | **Alta** para indicadores agregados de solidez bancária e comparações internacionais, com atenção a definições locais e cobertura. Não oferece a carteira de uma instituição ou microdados de tomadores. [IMF FSI](https://data.imf.org/en/datasets/IMF.STA:FSI) |
| **World Bank — Global Findex** | Acesso e uso de serviços financeiros por pessoas e empresas domiciliares, incluindo crédito formal/informal e inclusão financeira. | Pesquisas periódicas, não dados transacionais mensais de empréstimos. | **Média** para motivação, acesso a crédito e recorte de inclusão; **baixa** para tendências de inadimplência ou saúde de carteira. [World Bank Global Findex](https://www.worldbank.org/en/publication/globalfindex) |
| **World Bank — Global Financial Development Database** | Indicadores estruturais de instituições e mercados financeiros: profundidade, acesso, eficiência e estabilidade. | Série multi-país com frequência definida pelo indicador e disponibilidade histórica. | **Média** para contexto macro/financeiro e comparação entre países; não é base de pagamentos de empréstimos. [World Bank GFDD](https://www.worldbank.org/en/publication/gfdr/data/global-financial-development-database) |
| **TransUnion (bureau, EUA)** | Relatórios de tendências de crédito ao consumidor por produto, saldos, originações e desempenho de carteira. | Relatórios mensais/trimestrais publicados; dados mais detalhados podem depender de produto comercial. | **Média** como referência de mercado e inspiração de métricas; o foco é EUA e o material não deve ser misturado ao dado brasileiro sem explicar diferenças. [Consumer Credit Insights](https://www.transunion.com/lp/consumer-credit-insights) |

## O que essas fontes permitem desenhar

Com SCR.data, um painel acadêmico pode exibir:

- série mensal da inadimplência ou ativo problemático por modalidade, PF/PJ, UF ou porte;
- saldo/carteira ativa junto da taxa de inadimplência, para não analisar apenas percentuais;
- comparação entre segmentos ou entre a tendência brasileira e a de um segmento selecionado;
- filtros temporais e descrição da data-base, fonte, periodicidade, unidade e definição;
- contextualização com medidas BIS/IMF, se houver uma pergunta internacional comparativa bem delimitada.

Esses gráficos descreveriam o **mercado agregado** e não demonstrariam a eficácia preditiva de um modelo treinado no South German Credit. Para comparar modelos, a área experimental ainda deve usar dados de teste separados e métricas como discriminação, calibração e utilidade decisória. A proposta anterior de dashboard permanece válida, agora com a possibilidade de acrescentar um painel de contexto brasileiro observado.

## Recomendação para o recorte do TCC

1. **Fonte primária para gráfico temporal:** avaliar primeiro SCR.data v2, pois combina frequência mensal, histórico longo e cortes relevantes para risco de crédito.
2. **Fonte para narrativa e validação de conceito:** usar a metodologia do BCB para definir carteira ativa, inadimplência e ativo problemático corretamente. Não assumir que conceitos ou regras contábeis permaneceram invariáveis durante toda a série; documentar mudanças metodológicas.
3. **Fonte de benchmark internacional:** escolher BIS DSR/crédito ou IMF FSI apenas se o TCC formular uma pergunta comparativa internacional; caso contrário, pode aumentar o escopo sem ajudar a avaliação dos modelos.
4. **Interface:** manter visualmente separadas as abas “Mercado de crédito (BCB)” e “Comparação dos modelos (South German Credit)”. Se houver uma demonstração de carteira individual com curvas, rotular explicitamente “dados sintéticos” e informar como a série foi gerada.
5. **Antes de implementar:** baixar um ano de SCR.data v2, conferir dicionário/metodologia, testar quais cortes realmente estão disponíveis e selecionar duas ou três métricas. Não assumir que cada indicador tem todos os mesmos segmentos nem que arquivos da Versão 1 e Versão 2 são diretamente comparáveis.

## Referências oficiais

- Banco Central do Brasil. [SCR.data — conjunto de dados, arquivos e metadados](https://dadosabertos.bcb.gov.br/pt_BR/dataset/scr_data).
- Banco Central do Brasil. [Metodologia do SCR.data, Versão 2](https://www.bcb.gov.br/pda/desig/metodologia_versao2.pdf).
- Banco Central do Brasil. [Sistema Gerenciador de Séries Temporais — SGS](https://www3.bcb.gov.br/sgspub/).
- Banco Central do Brasil. [Estatísticas Monetárias e de Crédito](https://www.bcb.gov.br/estatisticas/estatisticasmonetariascredito).
- BIS. [Statistics](https://www.bis.org/statistics), [Credit to the non-financial sector](https://data.bis.org/topics/TOTAL_CREDIT), [Debt service ratios](https://data.bis.org/topics/DSR).
- IMF. [Financial Soundness Indicators dataset](https://data.imf.org/en/datasets/IMF.STA:FSI).
- World Bank. [Global Findex](https://www.worldbank.org/en/publication/globalfindex), [Global Financial Development Database](https://www.worldbank.org/en/publication/gfdr/data/global-financial-development-database).
- Serasa Experian. [Indicadores Econômicos](https://www.serasaexperian.com.br/conteudos/indicadores-economicos/).
- SPC Brasil. [Cadastro Positivo e direitos do consumidor](https://www.spcbrasil.org.br/cadastropositivo/consumidor/seus-direitos).
- TransUnion. [Consumer Credit Insights](https://www.transunion.com/lp/consumer-credit-insights).

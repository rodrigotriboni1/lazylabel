# Experimento local de fine-tuning LazyLabel (dados sintéticos)

## Objetivo e limites

Demonstrar que o fluxo LazyLabel consegue exportar exemplos revisados e treinar um adapter LoRA local, e observar a diferença de classificação em um conjunto sintético reservado. Este experimento não mede risco de crédito, desempenho em dados reais, robustez em produção nem eficácia geral de LLMs.

## Modelo e ambiente

- Modelo: `Qwen/Qwen2.5-0.5B-Instruct`
- Revisão imutável: `7ae557604adf67be50417f59c2c2f167def9a775`
- Licença declarada no model card: Apache-2.0
- Hardware observado: MacBook Apple M4, 16 GB de memória unificada, macOS 26.6.2; treino direcionado ao backend MPS quando disponível.
- O download de dependências e pesos usa PyPI/Hugging Face; linhas de dados sintéticos e resultados ficam neste diretório local. Telemetria do Hub desabilitada e nenhum upload do adapter.

## Tarefa

Classificar descrições financeiras sintéticas em `receita`, `despesa_operacional` ou `custo_financeiro`. O classificador recebe somente a coluna `historico`; a coluna `referencia_interna` é deliberadamente excluída.

## Dados e revisão

O script `scripts/generate_data.py` gera CSV de treino e conjunto reservado com rótulos de referência determinísticos. O CSV de treino passa pela geração de sugestões do modelo-base. Cada sugestão válida é revisada automaticamente contra o rótulo-oráculo conhecido: igual é registrada como aceita; divergente é corrigida para o rótulo-oráculo. Isso simula revisão assistida em dados sintéticos e não equivale a revisão humana independente. Só decisões aceitas/corrigidas entram no export explícito do LazyLabel.

## Avaliação

- Separação: treino e avaliação usam famílias de templates escritas separadamente, sem descrições exatamente iguais. Ainda compartilham vocabulário e conceitos; portanto, o conjunto reservado não é independente de padrões semânticos do treino e não representa generalização para dados reais.
- Baseline: modelo-base, antes de treinar.
- Modelo ajustado: mesmo modelo-base e revisão, com adapter LoRA.
- Métricas: acurácia exata e macro-F1 nas 24 observações reservadas, além de matriz de confusão e saídas brutas; inferência gulosa, limite de 64 tokens, prompt textual idêntico no baseline e pós-treino.
- Sem seleção de hiperparâmetros pelo conjunto de avaliação; 3 épocas, batch 1, learning rate `2e-4`, LoRA rank 8, seed 42.
- O dataset LazyLabel é exportado com provenance de revisões; em seguida, uma etapa derivada aplica o chat template do tokenizer Qwen ao campo `prompt`. Baseline e modelo ajustado são avaliados com o mesmo chat template. O formato textual sem chat template é mantido como diagnóstico separado, não usado na comparação principal.
- Uma amostra pequena e construída manualmente serve apenas como prova de fluxo; as métricas não sustentam conclusões estatísticas nem validade para casos reais.

## Proveniência e integridade

Guardar neste diretório: hashes dos CSVs e dataset JSONL, manifesto LazyLabel, hash da revisão do modelo, versões das dependências, métricas e logs redigidos. Não copiar dados ou credenciais do usuário. O adapter resultante permanece local e não será publicado.

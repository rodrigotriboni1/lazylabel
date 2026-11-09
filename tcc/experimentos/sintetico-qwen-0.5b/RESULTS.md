# Resultado do treino local sintético

**Estado:** treino concluído e adapter recarregado para avaliação. Este é um experimento demonstrativo; não é validação para dados financeiros reais nem uma recomendação de modelo para produto.

## Ambiente e modelo

- Base: `Qwen/Qwen2.5-0.5B-Instruct`, revisão `7ae557604adf67be50417f59c2c2f167def9a775`.
- Model card registra 0,49 bilhão de parâmetros e suporte multilíngue; a licença publicada no repositório é Apache-2.0 ([model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), [LICENSE](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/raw/main/LICENSE)).
- Máquina: Apple M4, 16 GB de memória unificada, macOS 26.6.2. `torch.backends.mps.is_available()` retornou `True`; treino e inferência foram executados em MPS. A documentação do Transformers descreve detecção automática de MPS pelo Trainer e ressalva que algumas operações podem precisar de fallback ([Apple Silicon](https://huggingface.co/docs/transformers/en/perf_train_special)).
- Ambiente isolado: Python 3.12.14, PyTorch 2.14.1, Transformers 5.20.2, TRL 1.16.0, PEFT 0.21.2, Datasets 5.1.0, Accelerate 1.15.0, Safetensors 0.8.0. A lista completa está em `results/requirements-frozen.txt`.

## Dados e procedimento

- Gerados localmente: 72 exemplos de treino (24 por rótulo) e 24 exemplos reservados (8 por rótulo), usando famílias de templates escritas separadamente. Não há descrições exatamente iguais entre treino e avaliação, mas os conjuntos compartilham vocabulário e padrões semânticos; isso não constitui evidência de generalização para descrições reais ou independentes.
- Tarefa: `receita`, `despesa_operacional` ou `custo_financeiro`, usando somente `historico`. `referencia_interna` foi excluída e a verificação confirmou que seus marcadores não aparecem nas sugestões nem nos prompts de treino.
- O Qwen sugeriu 72 rótulos; 38 coincidiram com o oráculo sintético e 34 foram corrigidos. O script comparou automaticamente cada sugestão com a regra usada para gerar os dados. Isso **não é revisão humana independente**.
- O export do LazyLabel incluiu 72 revisões aceitas/corrigidas, sem itens inválidos, rejeitados ou desatualizados. O manifesto mantém IDs, hashes, colunas selecionadas e referência do modelo.
- A etapa de formatação aplicou o chat template oficial do tokenizer Qwen ao prompt e registrou o hash do dataset derivado. Baseline e modelo treinado usaram o mesmo chat template, geração gulosa e limite de 64 tokens.
- Ajuste: SFT + PEFT/LoRA, rank 8, 3 épocas, batch 1, learning rate `2e-4`, seed 42; 216 passos em 143,6 segundos. Perda final reportada: `0.03175`. O teste reservado não foi usado para escolher hiperparâmetros.

## Avaliação reservada

| Métrica | Base | LoRA | Diferença |
|---|---:|---:|---:|
| Acurácia exata | 9/24 (37,5%) | 17/24 (70,8%) | +33,3 p.p. |
| Macro-F1 | 0,300 | 0,706 | +0,406 |
| Saídas válidas | 23/24 (95,8%) | 24/24 (100%) | +1 exemplo |

No pareamento das 24 descrições, 10 previsões erradas do modelo-base passaram a corretas e 2 corretas passaram a erradas; o saldo foi de 8 acertos a mais. A matriz registra linhas como rótulo de referência e colunas como previsão:

| Referência | Base: receita | Base: operacional | Base: financeira | Base: inválida | LoRA: receita | LoRA: operacional | LoRA: financeira |
|---|---:|---:|---:|---:|---:|---:|---:|
| receita | 2 | 0 | 6 | 0 | 4 | 3 | 1 |
| operacional | 0 | 0 | 7 | 1 | 0 | 7 | 1 |
| financeira | 0 | 1 | 7 | 0 | 0 | 2 | 6 |

O adapter foi recarregado sobre a mesma revisão-base e avaliado em MPS. Ele está em `adapter/adapter_model.safetensors` (17.640.136 bytes; SHA-256 `05edf565c2e86bd846b62bc92fa1f726b6f9fab407819ffc93af5c523304f018`). O arquivo `adapter/finlabel-training.json` registra revisão-base, parâmetros, hash do dataset e versões. Upload para Hub foi desabilitado; a variável `HF_HUB_DISABLE_TELEMETRY=1` foi usada.

A implementação LazyLabel usada estava no checkout local `codigo/finlabel/.worktrees/integration`, commit `ec8d3c4f5619e21e73b05ef3c315c72710fe917a`. O arquivo `results/requirements-frozen.txt` aponta para esse checkout por caminho editável; assim, a reprodução exige recuperar esse commit nesse caminho ou ajustar a referência local. A linha de comando completa usada para cada etapa não foi registrada durante a execução.

## Limitações e próximos passos do TCC

1. São somente 24 exemplos artificiais no conjunto reservado; descrições foram criadas por templates e rótulos por regras. O resultado mostra que a cadeia técnica funciona, mas não permite concluir que o ajuste melhora rótulos em dados reais.
2. Perda de treino baixa em uma amostra minúscula é compatível com memorização. Será necessário um conjunto real autorizado, anonimizado conforme política, com anotação humana revisada e separação por tempo/entidade para evitar vazamento.
3. Um ensaio inicial com prompt textual cru do LazyLabel produziu saída fora do JSON. O uso do chat template do Qwen passou a produzir sugestões válidas e foi necessário para a avaliação alinhada. O backend genérico atual do LazyLabel não aplica o chat template do modelo; a integração de inferência precisa ser tratada antes de afirmar que a CLI genérica reproduz este experimento.
4. Próxima análise acadêmica: comparar modelo-base, regras determinísticas e adapter; medir precisão/recall/F1 por rótulo, taxa de saída inválida e tempo/custo de revisão; repetir com diferentes seeds e uma amostra de avaliação maior. O modelo não decide crédito nem substitui revisão humana.

## Arquivos para inspeção

- `PROTOCOL.md`: protocolo e limites aprovados.
- `data/generation-manifest.json`: hashes e contagens de dados.
- `data/reviewed-training.jsonl.manifest.json` e `data/qwen-chat-training.jsonl.manifest.json`: proveniência e hashes.
- `results/base-heldout-chat.json` e `results/finetuned-heldout-chat.json`: previsões e métricas por exemplo.
- `results/training.log` e `results/training-summary.json`: saída e resumo do ajuste.
- `results/verification.json`: verificações de integridade e isolamento.
- `scripts/`: geração de dados, sugestões, revisão sintética, formatação, avaliação e verificação.

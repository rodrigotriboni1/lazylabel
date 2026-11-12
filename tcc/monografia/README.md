# Monografia do TCC (rascunho)

Rascunho em LaTeX (classe abnTeX2, citações autor-data com `abntex2cite`), gerado com assistência de IA em 10/11/2026 a partir dos documentos do repositório. **É um rascunho para o autor revisar e reescrever com a própria voz.** Nenhum resultado foi inventado: o que falta está marcado com `[PENDENTE: ...]` no PDF (`\pendente{...}` no fonte).

## Compilar

```bash
cd tcc/monografia
tectonic main.tex        # gera main.pdf (tectonic em /opt/homebrew/bin/tectonic)
```

A primeira compilação baixa os pacotes. `main.pdf` não vai para o git (`.gitignore`).

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `main.tex` | Preâmbulo, capa, folha de rosto, folha de aprovação, resumo, abstract, listas, sumário |
| `capitulos/01-introducao.tex` | Contexto, problema, pergunta (decisão 7), objetivos, justificativa, organização |
| `capitulos/02-fundamentacao.tex` | Conceitos: supervisão fraca, LLM por verossimilhança, LoRA, calibração, classificação seletiva, regressão logística, arquitetura, vazamento |
| `capitulos/03-metodologia.tex` | Protocolo v0.2, hipóteses refinadas, limiares, bases, divisão, métricas, E1/E2, bootstrap |
| `capitulos/04-desenvolvimento.tex` | O LazyLabel: requisitos, camadas, fluxo de uso, painel, decisões 1–9, testes |
| `capitulos/05-resultados.tex` | **Só estrutura**, mais os números já registrados (sintético, fumaça, baseline no dev) |
| `capitulos/06-conclusao.tex` | **Só estrutura** |
| `apendices/a-uso-de-ia.tex` | Declaração de uso de IA |
| `referencias.bib` | Referências; entradas com `% VERIFICAR` têm dados a conferir |

## O que está pendente

Procure por `\pendente` nos `.tex` (`grep -rn pendente .`). Os principais:

- **Pré-textuais:** nome do orientador, unidade acadêmica, banca, data da defesa, ficha catalográfica (comentário em `main.tex`), frases de resultado no resumo e no abstract.
- **Tema:** a decisão 7 ainda depende do orientador; se a pergunta mudar, os capítulos 1 e 3 mudam junto.
- **Capítulo 3:** checagem de vazamento temporal na segunda base; roteiro do bootstrap (não existe em `codigo/experimento/`); commit e versões das bibliotecas; terceiro sistema (modelo-base calibrado), se o orientador pedir.
- **Capítulo 4:** capturas de tela do painel; contagem de testes no commit final.
- **Capítulo 5:** todos os resultados do E1 e do E2 (ciclo, teste final, intervalos, curva risco-cobertura, matriz de confusão, quarentenas por motivo, tabela de alterações e tempos do E2).
- **Capítulo 6:** síntese, atendimento aos objetivos, limitações observadas.
- **Apêndice A:** confirmação do orientador sobre uso de IA, ferramentas e versões, registro de uso, conferência da portaria da UFU.

## Checklist de revisão do autor

- [ ] Ler tudo e reescrever com a própria voz; cortar o que não reconhece como seu.
- [ ] Conferir cada número contra o arquivo citado na "Fonte" da tabela.
- [ ] Conferir cada referência na fonte original, começando pelas marcadas `% VERIFICAR` em `referencias.bib` (Platt, Qwen, Geifman, Grömping, Wolf, Cockburn, Kaufman, páginas da UCI). Ler o que for citar.
- [ ] Ampliar a revisão de literatura do capítulo 2 com trabalhos relacionados lidos pelo autor.
- [ ] Confirmar com o orientador: tema (decisão 7), baseline e métricas, segunda base, modelo-base como terceiro sistema.
- [ ] Conferir o título (é uma proposta do rascunho) e as palavras-chave.
- [ ] Conferir o parágrafo da justificativa que liga o tema a Controle e Automação.
- [ ] Conferir as regras do curso para o TCC (modelo da UFU, fonte, margens, elementos obrigatórios, ficha catalográfica); o rascunho usa os padrões do abnTeX2 e a fonte Latin Modern.
- [ ] Conferir se quadros e tabelas seguem o que o curso exige (o rascunho usa "Quadro" para conteúdo textual e "Tabela" para números).
- [ ] Preencher todos os `\pendente` e confirmar que `grep -rn pendente capitulos apendices main.tex` só retorna a definição do comando.
- [ ] Revisar o Apêndice A para que descreva o uso real de IA, com ferramentas e versões.
- [ ] Recompilar e conferir sumário, listas e referências cruzadas.

## Notas técnicas

- As opções da classe estão como `english,brazil` (e não `brazil,english`): o babel usa a última língua como principal, e o documento é em português.
- `\cod{...}` escreve caminhos e comandos em fonte monoespaçada, com quebra de linha.
- Acentos em `referencias.bib` usam comandos LaTeX (`{\"o}`), porque o BibTeX não converte UTF-8 para maiúsculas.

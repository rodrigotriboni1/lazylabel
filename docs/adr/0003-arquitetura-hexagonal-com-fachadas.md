# ADR-0003: Clean Architecture / hexagonal com fachadas de compatibilidade

- **Status:** Aceita
- **Data:** 2026-10-31 (refatoração concluída em 2026-10-26)
- **Escopo:** FinLabel

## Contexto

O pacote cresceu por incrementos (perfil, revisão, análise, rotulagem, treino, painel) com lógica de negócio espalhada entre CLI, rotas HTTP e módulos de treino. Era preciso trocar modelos, fontes e interface sem duplicar regras.

## Decisão

Camadas com dependências apontando para dentro:

`domain` (puro) ← `application` (casos de uso + portas) ← `adapters` (inbound CLI/HTTP; outbound fontes, persistência, modelos, treino) ← `bootstrap` (única composição).

- Imports novos usam o caminho canônico (`finlabel.domain|application|adapters|bootstrap`).
- Módulos legados (`finlabel.project`, `finlabel.training.*`, `finlabel.cli:main`, `finlabel.web.app:create_app`…) permanecem como **fachadas** sem lógica.
- Regras são executáveis: `tests/architecture/test_layer_dependencies.py` (direção de dependência, sem I/O/rede nas camadas internas, fachadas sem lógica) e `tests/compatibility/` (símbolos públicos).
- Frontend espelha o desenho: porta `FinLabelClient`, adapter HTTP e adapter em memória; só o adapter HTTP faz requests.
- Imports de Transformers/PEFT/TRL são lazy para o pacote e a CLI não exigirem os extras.

## Consequências

- (+) Regras de negócio em um só lugar; adapters trocáveis; testes rápidos com fakes.
- (+) Violações de camada quebram o teste.
- (−) Mais arquivos e indireção para um projeto de uma pessoa.
- (−) Fachadas legadas precisam de decisão de versão/depreciação antes de serem removidas (ainda não tomada).

## Evidência

`docs/architecture/clean-hexagonal.md` e `clean-hexagonal-module-map.md` na branch `codex/finlabel-autonomous-mvp`. O relatório final cita 407 testes Python e 51 de frontend passando nesse commit; **não reexecutei** os testes ao escrever este ADR.

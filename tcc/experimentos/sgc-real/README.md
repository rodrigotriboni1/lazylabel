# Experimento E1 — South German Credit

Segue [../../plano-experimento-real.md](../../plano-experimento-real.md).

- `dados/brutos/`: original da UCI, com SHA-256.
- `dados/processados/`:
  - `sgc.csv`: gerado por `codigo/experimento/preparar_sgc.py`, com SHA-256 `8e24b426…8658`;
  - `dev.csv` (800) e `teste.csv` (200): divisão do baseline, semente 42.
- `config/`: tarefa, política de rotulagem, política de promoção e training gate, **congelados** no commit que adiciona este arquivo, antes de abrir o teste.
- `resultados/baseline/`: validação cruzada só no dev; o teste final é aberto uma única vez com `--final`.
- `fumaca-2026-11-10.md`: taxa de saídas válidas do modelo-base.

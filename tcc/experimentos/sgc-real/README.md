# Experimento E1 — South German Credit

Segue [../../plano-experimento-real.md](../../plano-experimento-real.md).

- `dados/brutos/`: original da UCI, com SHA-256.
- `dados/processados/`:
  - `sgc.csv`: gerado por `codigo/experimento/preparar_sgc.py`, com SHA-256 `8e24b426…8658`;
  - `dev.csv` (800) e `teste.csv` (200): divisão do baseline, semente 42.
- `config/`: tarefa, política de rotulagem, política de promoção e training gate, **congelados** no commit que adiciona este arquivo, antes de abrir o teste.
- `resultados/baseline/`: validação cruzada só no dev; o teste final é aberto uma única vez com `--final`.
- `fumaca-2026-11-10.md`: taxa de saídas válidas do modelo-base.

## Ocorrências

- **10/11/2026, 21:42.** A primeira execução de `lazylabel run` rotulou os 800 registros de dev em 8 min 43 s e terminou bloqueada com `task_calibration_ref_missing`: a política tinha `calibration_ref: null`. Não houve treino nem métrica. Corrigi `calibration_ref` para `risco-cal-v1` nas duas configurações.
- Por engano, uma segunda execução rodou ao mesmo tempo no mesmo projeto. O projeto foi descartado, e a execução válida começa num projeto novo. O teste final não foi tocado.

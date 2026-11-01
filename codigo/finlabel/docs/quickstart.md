# FinLabel Local quickstart

This guide takes you from a fresh checkout to a chart and the local web panel, using a tiny sample CSV. Everything runs locally.

## Prerequisites

- Python 3.10 or newer (`requires-python = ">=3.10"`). Check with:

  ```bash
  python3 --version
  ```

  The macOS system `python3` may be 3.9, which is too old. Use a newer interpreter, for example from python.org, Homebrew or [`uv`](https://docs.astral.sh/uv/).
- Node.js is optional. It is only needed for frontend development, because the built panel assets are already in the repo.

## Install

Run one of the following from `codigo/finlabel` (the directory that contains `pyproject.toml`).

Extras you may need:

| Extra | Needed for |
| --- | --- |
| `web` | `finlabel analyze` (offline chart rendering) and `finlabel serve` |
| `models` | local model labeling or analysis planning |
| `train` | fine-tuning |

`models` and `train` pull in torch and are large. This quickstart only needs `web`.

### (a) Project-local virtual environment

Replace `python3.12` with any interpreter that is 3.10 or newer.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web]'
```

### (b) pipx

```bash
pipx install '.[web]'
```

### (c) uv

```bash
uv tool install '.[web]'
```

## First run

These steps assume `finlabel` is on your `PATH` (activate the venv in (a), or use the binary installed by (b) or (c)). Work in a directory outside the repo checkout:

```bash
mkdir -p ~/finlabel-demo && cd ~/finlabel-demo
```

Create a sample CSV and an analysis plan:

```bash
cat > sales.csv <<'CSV'
period,product,amount
2024-01-01,alpha,100.50
2024-01-15,beta,40.00
2024-02-01,alpha,120.00
2024-02-10,beta,55.25
2024-03-01,alpha,130.75
2024-03-12,beta,60.00
CSV

cat > analysis-plan.json <<'JSON'
{
  "version": 1,
  "metric": {"operation": "sum", "column": "amount"},
  "dimensions": ["product"],
  "time_axis": {"column": "period", "grain": "month"},
  "filters": [],
  "chart": "line"
}
JSON
```

Initialize a project, register the CSV and map the non-string columns the plan uses:

```bash
finlabel project init .
finlabel source add-csv sales ./sales.csv
finlabel source set-type sales period date
finlabel source set-type sales amount decimal
```

Run the analysis. This needs the `web` extra:

```bash
finlabel analyze sales --question "How did sales change by month?" --plan ./analysis-plan.json
```

`analyze` prints a JSON summary. Its `artifact_dir` points to a directory containing `chart.html`; open that file in a browser.

Start the local panel (also needs `web`):

```bash
finlabel serve
```

The panel is served at <http://127.0.0.1:8765>. Press Ctrl+C to stop it.

## Next steps (labeling and training)

Labeling (`task add`, `label`) and training (`supervision add`, `run`, `train`) need extra setup that this quickstart does not cover: a task, a labeling policy, trusted labels, a training gate and the `models` / `train` extras. See [verified-training-cycle.md](verified-training-cycle.md) for the prerequisites and the full cycle.

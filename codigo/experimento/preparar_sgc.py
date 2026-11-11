"""Converte o SouthGermanCredit.asc original em CSV com record_id e alvo nomeado.

Não altera o arquivo bruto. Uso:
  python3 codigo/experimento/preparar_sgc.py tcc/experimentos/sgc-real/dados/brutos/SouthGermanCredit.asc \
      tcc/experimentos/sgc-real/dados/processados/sgc.csv
"""
import csv
import hashlib
import sys
from pathlib import Path


def main(src, dst):
    rows = [line.split() for line in Path(src).read_text(encoding="ascii").splitlines() if line.strip()]
    header, body = rows[0], rows[1:]
    assert len(body) == 1000 and all(len(r) == len(header) for r in body), "base inesperada"
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["record_id"] + header)
        for i, r in enumerate(body):
            w.writerow(["sgc-{:04d}".format(i)] + r)
    print(hashlib.sha256(Path(dst).read_bytes()).hexdigest(), dst)


if __name__ == "__main__":
    main(*sys.argv[1:3])

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("receita", "despesa_operacional", "custo_financeiro")

TRAIN_TEMPLATES = {
    "receita": [
        "Pix recebido de cliente {name} pela fatura {code}",
        "Crédito de venda no cartão referente ao pedido {code}",
        "Boleto recebido da empresa {name}, pedido {code}",
        "Transferência recebida de {name} por serviços prestados",
        "Recebimento de mensalidade do cliente {name}, contrato {code}",
        "Valor recebido por venda de mercadorias, pedido {code}",
        "Depósito de cliente {name} para quitação da nota {code}",
        "Receita de consultoria recebida da empresa {name}",
    ],
    "despesa_operacional": [
        "Pagamento do aluguel do escritório {name}, referência {code}",
        "Conta de energia elétrica da unidade {name}",
        "Compra de material de escritório na loja {name}, pedido {code}",
        "Pagamento da folha salarial da equipe {name}",
        "Fatura de internet e telefonia da filial {name}",
        "Reembolso de viagem de trabalho para {name}, relatório {code}",
        "Serviço de limpeza mensal contratado da empresa {name}",
        "Compra de insumos para a operação com fornecedor {name}",
    ],
    "custo_financeiro": [
        "Tarifa de manutenção da conta empresarial {name}",
        "Juros do empréstimo de capital de giro contrato {code}",
        "Taxa de processamento da adquirente {name}, lote {code}",
        "Encargo por atraso de parcela do financiamento {code}",
        "Tarifa bancária de transferência para {name}",
        "Juros sobre saldo utilizado no limite da conta {name}",
        "Custo de antecipação de recebíveis contrato {code}",
        "Taxa de administração financeira cobrada por {name}",
    ],
}
TEST_TEMPLATES = {
    "receita": [
        "Entrada via transferência do comprador {name}, documento {code}",
        "Valor de fatura comercial recebido do pagador {name}",
        "Crédito de venda à vista registrado no caixa {code}",
        "Cliente {name} liquidou a cobrança do serviço {code}",
        "Recebimento de parcela de venda realizada ao cliente {name}",
        "Depósito referente a mercadorias entregues, nota {code}",
        "Pagamento recebido pela prestação de serviço para {name}",
        "Liquidação de duplicata de cliente {name}, título {code}",
    ],
    "despesa_operacional": [
        "Quitação do contrato mensal de locação do espaço {name}",
        "Consumo de água e luz no centro operacional {name}",
        "Aquisição de papelaria para o departamento {name}, pedido {code}",
        "Salários mensais pagos aos funcionários da unidade {name}",
        "Plano corporativo de dados e telefone da equipe {name}",
        "Diária de hospedagem em viagem a trabalho para {name}",
        "Manutenção preventiva dos equipamentos da unidade {name}",
        "Material de embalagem comprado para expedição, fornecedor {name}",
    ],
    "custo_financeiro": [
        "Cobrança de pacote de serviços pelo banco {name}",
        "Encargos de juros do crédito empresarial número {code}",
        "Desconto de tarifa sobre vendas processadas na rede {name}",
        "Multa e juros de mora da prestação do contrato {code}",
        "Custo cobrado para transferir recursos pelo banco {name}",
        "Encargos de utilização do cheque especial da conta {name}",
        "Deságio pago pela antecipação do título {code}",
        "Despesa de intermediação financeira da instituição {name}",
    ],
}
NAMES = ("Aurora", "Cedro", "Horizonte", "Ipê", "Nascente", "Pioneira", "Raiz", "Solare")


def build(split, templates, repeats):
    rows = []
    for label in LABELS:
        for template_index, template in enumerate(templates[label]):
            for repeat in range(repeats):
                index = template_index * repeats + repeat
                name = NAMES[(template_index * 3 + repeat + (0 if split == "train" else 4)) % len(NAMES)]
                code = "S{:02d}{:02d}".format(template_index + 1, repeat + 1 + (0 if split == "train" else 4))
                rows.append({
                    "historico": template.format(name=name, code=code),
                    "referencia_interna": "SYNTH-{}-{:04d}".format(split.upper(), index),
                    "label": label,
                })
    return rows


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("historico", "referencia_interna"))
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in rows)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    train = build("train", TRAIN_TEMPLATES, repeats=3)
    test = build("test", TEST_TEMPLATES, repeats=1)
    write_csv(data_dir / "train.csv", train)
    write_csv(data_dir / "heldout.csv", test)
    (data_dir / "reference.jsonl").write_text(
        "".join(json.dumps({"split": split, "index": index, "label": row["label"]}, ensure_ascii=False) + "\n"
                 for split, rows in (("train", train), ("heldout", test)) for index, row in enumerate(rows)),
        encoding="utf-8",
    )
    summary = {
        "labels": list(LABELS), "train_rows": len(train), "heldout_rows": len(test),
        "train_sha256": sha256(data_dir / "train.csv"), "heldout_sha256": sha256(data_dir / "heldout.csv"),
        "ground_truth_sha256": sha256(data_dir / "reference.jsonl"),
        "train_templates_per_label": len(next(iter(TRAIN_TEMPLATES.values()))),
        "heldout_templates_per_label": len(next(iter(TEST_TEMPLATES.values()))),
        "overlapping_description_count": 0,
    }
    (data_dir / "generation-manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

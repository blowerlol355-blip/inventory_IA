from app.services.ingestion.pipeline import classify_by_rules


def test_invoice_statement_and_contract_by_rules() -> None:
    invoice = "Factura N° F-0001\nEmisor: Demo SpA\nSubtotal 100\nIVA 19\nTotal a pagar 119"
    statement = (
        "Estado de cuenta\nNúmero de cuenta 123\nSaldo inicial 10\nMovimientos\nSaldo final 5"
    )
    assert classify_by_rules(invoice) == "factura"
    assert classify_by_rules(statement) == "estado_de_cuenta"


def test_title_outweighs_mentions_in_body() -> None:
    contract = (
        "Contrato de prestación de servicios N° C-004\n"
        "Entre las partes, el Cliente pagará contra presentación de factura con IVA.\n"
        "Vigencia: dos años. Renovación automática."
    )
    assert classify_by_rules(contract) == "contrato"


def test_no_signals_is_other_and_ambiguous_goes_to_llm() -> None:
    assert classify_by_rules("Acta de la reunión del comité de auditoría") == "otro"
    # Señales mezcladas sin título claro: se deja al LLM.
    assert classify_by_rules("Resumen\nfactura subtotal iva contrato cláusula vigencia") is None

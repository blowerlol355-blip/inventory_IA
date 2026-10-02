"""Genera documentos financieros SINTÉTICOS (nunca datos reales) y su verdad de referencia.

Uso (desde la raíz del repo):
    uv run --project apps/api python data/generator/generate.py --out data/samples

Produce PDFs de facturas, contratos y un estado de cuenta, documentos de Word, Excel,
PowerPoint, CSV, TXT, una factura en JPG, archivos vacíos de cada formato, una factura escaneada (solo
imagen, para probar OCR) y `ground_truth.json` con los datos exactos de cada documento,
que se usarán para evaluar extracción y respuestas (Fases 2 y 3).
"""

import argparse
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any

import pymupdf
from office_samples import generate_office_samples

SEED = 42
PAGE = pymupdf.paper_rect("a4")
MARGIN = 50
CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; color: #222; }
h1 { font-size: 18pt; margin: 0 0 6px 0; }
h2 { font-size: 12pt; margin: 14px 0 4px 0; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
th, td { border: 1px solid #999; padding: 4px; }
th { background-color: #eee; }
.right { text-align: right; }
.muted { color: #666; font-size: 9pt; }
"""

VENDORS = [
    ("Suministros Andinos SpA", "76.123.456-7"),
    ("TecnoRed Soluciones Ltda.", "77.234.567-8"),
    ("Papelería Central S.A.", "96.345.678-9"),
    ("Logística del Pacífico SpA", "76.456.789-0"),
    ("Consultora Horizonte Ltda.", "78.567.890-1"),
    ("Energía Austral S.A.", "96.678.901-2"),
]
CLIENT = ("Comercial Demo SpA", "76.999.888-K")
PRODUCTS = [
    ("Resma papel carta", 4.5),
    ("Licencia software contable (mensual)", 120.0),
    ("Servicio de transporte", 350.0),
    ("Mantenimiento de servidores", 800.0),
    ("Tóner impresora láser", 65.0),
    ("Horas de consultoría", 90.0),
    ("Silla ergonómica", 210.0),
    ("Servicio de electricidad (mensual)", 640.0),
    ("Cable de red Cat6 (caja 305 m)", 150.0),
]
TAX_RATE = 0.19


def money(value: float) -> str:
    """Formato 12.345,67 (separador de miles con punto)."""
    whole, dec = f"{value:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{dec}"


@dataclass
class InvoiceLine:
    description: str
    quantity: int
    unit_price: float
    amount: float


@dataclass
class Invoice:
    filename: str
    invoice_number: str
    vendor_name: str
    vendor_tax_id: str
    issue_date: str
    due_date: str
    currency: str
    subtotal: float
    tax: float
    total: float
    purchase_order: str | None
    lines: list[InvoiceLine] = field(default_factory=list)
    scanned: bool = False


@dataclass
class Contract:
    filename: str
    title: str
    parties: list[str]
    start_date: str
    end_date: str
    amount: float
    currency: str
    auto_renewal: bool
    penalty_clause: str


@dataclass
class StatementMovement:
    date: str
    description: str
    amount: float


@dataclass
class BankStatement:
    filename: str
    bank: str
    account: str
    period: str
    opening_balance: float
    closing_balance: float
    movements: list[StatementMovement]


def render_html(path: Path, pages_html: list[str]) -> None:
    """Escribe un PDF con una página por bloque HTML."""
    doc = pymupdf.open()
    for html in pages_html:
        page = doc.new_page(width=PAGE.width, height=PAGE.height)
        rect = pymupdf.Rect(MARGIN, MARGIN, PAGE.width - MARGIN, PAGE.height - MARGIN)
        page.insert_htmlbox(rect, html, css=CSS)
    doc.save(path)
    doc.close()


def to_scanned(path: Path) -> None:
    """Convierte un PDF en uno 'escaneado': cada página pasa a ser solo una imagen."""
    src = pymupdf.open(path)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=150)
        new_page = out.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, pixmap=pix)
    src.close()
    out.save(path)
    out.close()


def make_invoice(rng: random.Random, number: int, issue: date) -> Invoice:
    vendor, tax_id = rng.choice(VENDORS)
    lines = []
    for description, base_price in rng.sample(PRODUCTS, rng.randint(2, 6)):
        qty = rng.randint(1, 20)
        price = round(base_price * rng.uniform(0.9, 1.3), 2)
        lines.append(InvoiceLine(description, qty, price, round(qty * price, 2)))
    subtotal = round(sum(line.amount for line in lines), 2)
    tax = round(subtotal * TAX_RATE, 2)
    has_po = rng.random() > 0.25
    return Invoice(
        filename=f"factura_{number:04d}.pdf",
        invoice_number=f"F-{number:06d}",
        vendor_name=vendor,
        vendor_tax_id=tax_id,
        issue_date=issue.isoformat(),
        due_date=(issue + timedelta(days=rng.choice([15, 30, 45, 60]))).isoformat(),
        currency="USD",
        subtotal=subtotal,
        tax=tax,
        total=round(subtotal + tax, 2),
        purchase_order=f"OC-{rng.randint(1000, 9999)}" if has_po else None,
        lines=lines,
    )


def invoice_pages(inv: Invoice, rng: random.Random) -> list[str]:
    rows = "".join(
        f"<tr><td>{escape(line.description)}</td><td class='right'>{line.quantity}</td>"
        f"<td class='right'>{money(line.unit_price)}</td>"
        f"<td class='right'>{money(line.amount)}</td></tr>"
        for line in inv.lines
    )
    po = inv.purchase_order or "Sin orden de compra"
    header = f"""
    <h1>FACTURA N° {inv.invoice_number}</h1>
    <p><b>Proveedor:</b> {escape(inv.vendor_name)} — RUT {inv.vendor_tax_id}<br>
    <b>Cliente:</b> {CLIENT[0]} — RUT {CLIENT[1]}<br>
    <b>Fecha de emisión:</b> {inv.issue_date}<br>
    <b>Fecha de vencimiento:</b> {inv.due_date}<br>
    <b>Orden de compra:</b> {po}<br>
    <b>Moneda:</b> {inv.currency}</p>
    """
    detail = f"""
    <h2>Detalle</h2>
    <table><tr><th>Descripción</th><th>Cantidad</th><th>Precio unitario</th><th>Monto</th></tr>
    {rows}</table>
    """
    totals = f"""
    <h2>Totales</h2>
    <table>
    <tr><td>Subtotal</td><td class='right'>{money(inv.subtotal)}</td></tr>
    <tr><td>IVA (19%)</td><td class='right'>{money(inv.tax)}</td></tr>
    <tr><td><b>Total a pagar</b></td><td class='right'><b>{money(inv.total)}</b></td></tr>
    </table>
    <p class='muted'>Pago por transferencia dentro del plazo indicado. Documento sintético
    generado para pruebas; no corresponde a una transacción real.</p>
    """
    if rng.random() < 0.3:  # algunas facturas ocupan dos páginas
        conditions = """
        <h2>Condiciones generales</h2>
        <p>1. Los reclamos sobre los productos o servicios facturados deben realizarse dentro
        de los 8 días siguientes a la recepción.</p>
        <p>2. El pago fuera de plazo devenga un interés moratorio del 1,5% mensual.</p>
        <p>3. Esta factura se rige por las condiciones comerciales acordadas entre las partes.</p>
        """
        return [header + detail, totals + conditions]
    return [header + detail + totals]


def make_contract(rng: random.Random, number: int, today: date) -> Contract:
    vendor, _ = rng.choice(VENDORS)
    start = today - timedelta(days=rng.randint(60, 700))
    # Algunos contratos vencen pronto, para probar preguntas de vencimientos.
    end = today + timedelta(days=rng.choice([20, 45, 75, 120, 200, 400]))
    amount = round(rng.uniform(5_000, 80_000), 2)
    penalty = rng.choice([5, 10, 15])
    return Contract(
        filename=f"contrato_{number:03d}.pdf",
        title=f"Contrato de prestación de servicios N° C-{number:03d}",
        parties=[CLIENT[0], vendor],
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        amount=amount,
        currency="USD",
        auto_renewal=rng.random() > 0.5,
        penalty_clause=(
            f"En caso de término anticipado sin causa justificada, la parte que ponga término "
            f"pagará una multa equivalente al {penalty}% del monto total del contrato."
        ),
    )


def contract_pages(c: Contract) -> list[str]:
    renewal = (
        "El contrato se renovará automáticamente por períodos iguales y sucesivos, salvo que "
        "una de las partes comunique su voluntad de no renovar con 30 días de anticipación."
        if c.auto_renewal
        else "El contrato NO se renueva automáticamente. Cualquier extensión requerirá un "
        "nuevo acuerdo por escrito firmado por ambas partes."
    )
    page1 = f"""
    <h1>{escape(c.title)}</h1>
    <p>Entre <b>{escape(c.parties[0])}</b> (en adelante, "el Cliente") y
    <b>{escape(c.parties[1])}</b> (en adelante, "el Proveedor"), se acuerda lo siguiente:</p>
    <h2>Primera: Objeto</h2>
    <p>El Proveedor prestará al Cliente los servicios descritos en el Anexo A, con los niveles
    de servicio indicados en dicho anexo.</p>
    <h2>Segunda: Vigencia</h2>
    <p>El presente contrato entra en vigor el {c.start_date} y termina el {c.end_date}.</p>
    <h2>Tercera: Precio</h2>
    <p>El precio total del contrato es de {money(c.amount)} {c.currency}, pagadero en cuotas
    mensuales iguales contra presentación de factura.</p>
    """
    page2 = f"""
    <h2>Cuarta: Renovación</h2>
    <p>{renewal}</p>
    <h2>Quinta: Penalización</h2>
    <p>{escape(c.penalty_clause)}</p>
    <h2>Sexta: Confidencialidad</h2>
    <p>Las partes mantendrán en reserva toda la información a la que tengan acceso con
    motivo de este contrato, durante su vigencia y por dos años después de su término.</p>
    """
    page3 = """
    <h2>Séptima: Jurisdicción</h2>
    <p>Para todos los efectos legales, las partes fijan domicilio en la ciudad de Santiago.</p>
    <h2>Anexo A: Servicios</h2>
    <p>Soporte técnico en horario hábil, mantenimiento preventivo trimestral e informe
    mensual de actividades.</p>
    <p class='muted'>Documento sintético generado para pruebas.</p>
    """
    return [page1, page2, page3]


def make_statement(
    rng: random.Random, today: date, months_back: int = 1
) -> BankStatement:
    month_start = today.replace(day=1)
    for _ in range(months_back):
        month_start = (month_start - timedelta(days=1)).replace(day=1)
    opening = round(rng.uniform(20_000, 60_000), 2)
    balance = opening
    movements = []
    for _ in range(14):
        day = month_start + timedelta(days=rng.randint(0, 27))
        if rng.random() < 0.35:
            amount = round(rng.uniform(1_000, 9_000), 2)
            desc = "Abono transferencia cliente"
        else:
            vendor, _ = rng.choice(VENDORS)
            amount = -round(rng.uniform(200, 4_000), 2)
            desc = f"Pago a {vendor}"
        movements.append(StatementMovement(day.isoformat(), desc, amount))
        balance += amount
    movements.sort(key=lambda m: m.date)
    return BankStatement(
        filename=f"estado_de_cuenta_banco_sur_{month_start:%Y_%m}.pdf",
        bank="Banco del Sur",
        account="00-123-45678-9",
        period=month_start.strftime("%Y-%m"),
        opening_balance=opening,
        closing_balance=round(balance, 2),
        movements=movements,
    )


def statement_pages(s: BankStatement) -> list[str]:
    rows = "".join(
        f"<tr><td>{m.date}</td><td>{escape(m.description)}</td>"
        f"<td class='right'>{money(m.amount)}</td></tr>"
        for m in s.movements
    )
    return [
        f"""
        <h1>Estado de cuenta — {s.bank}</h1>
        <p><b>Titular:</b> {CLIENT[0]}<br><b>Cuenta corriente:</b> {s.account}<br>
        <b>Período:</b> {s.period}</p>
        <table>
        <tr><td>Saldo inicial</td><td class='right'>{money(s.opening_balance)}</td></tr>
        <tr><td>Saldo final</td><td class='right'>{money(s.closing_balance)}</td></tr>
        </table>
        <h2>Movimientos</h2>
        <table><tr><th>Fecha</th><th>Descripción</th><th>Monto</th></tr>{rows}</table>
        """
    ]


def generate(
    out: Path,
    invoices_count: int = 12,
    contracts_count: int = 4,
    statements_count: int = 1,
    scanned_count: int = 1,
    today: date = date(2026, 10, 1),
    extended: bool = False,
) -> dict[str, Any]:
    """Genera los documentos en `out` y devuelve la verdad de referencia (también en JSON)."""
    rng = random.Random(SEED)
    out.mkdir(parents=True, exist_ok=True)

    invoices = []
    for i in range(1, invoices_count + 1):
        issue = today - timedelta(days=rng.randint(5, 270))
        inv = make_invoice(rng, i, issue)
        render_html(out / inv.filename, invoice_pages(inv, rng))
        invoices.append(inv)
    # Las últimas facturas se "escanean" para ejercitar el OCR.
    for inv in invoices[-scanned_count:] if scanned_count else []:
        inv.scanned = True
        to_scanned(out / inv.filename)

    contracts = []
    for i in range(1, contracts_count + 1):
        c = make_contract(rng, i, today)
        render_html(out / c.filename, contract_pages(c))
        contracts.append(c)

    statements = []
    for months_back in range(1, statements_count + 1):
        statement = make_statement(rng, today, months_back)
        render_html(out / statement.filename, statement_pages(statement))
        statements.append(statement)

    truth = {
        "generated_for_date": today.isoformat(),
        "seed": SEED,
        "invoices": [asdict(i) for i in invoices],
        "contracts": [asdict(c) for c in contracts],
        "bank_statements": [asdict(s) for s in statements],
        # Generador aparte, con su propio RNG para no alterar los documentos de arriba.
        "office": generate_office_samples(
            out, random.Random(SEED + 1), today, extended
        ),
    }
    (out / "ground_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/samples"))
    parser.add_argument("--invoices", type=int, default=12)
    parser.add_argument("--contracts", type=int, default=4)
    parser.add_argument("--statements", type=int, default=1)
    parser.add_argument(
        "--scanned", type=int, default=1, help="Facturas escaneadas (OCR)"
    )
    parser.add_argument(
        "--extended", action="store_true", help="Más documentos de oficina"
    )
    parser.add_argument("--today", type=date.fromisoformat, default=date(2026, 10, 1))
    args = parser.parse_args()

    truth = generate(
        args.out,
        args.invoices,
        args.contracts,
        args.statements,
        args.scanned,
        args.today,
        args.extended,
    )
    files = [
        p
        for p in args.out.iterdir()
        if p.is_file() and p.suffix not in (".json", ".md")
    ]
    empty = len(truth["office"]["empty_files"])
    print(
        f"Generados {len(files)} documentos en {args.out} + {empty} vacíos en {args.out / 'vacios'}"
    )


if __name__ == "__main__":
    main()

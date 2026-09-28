"""Generate six synthetic holdout PDFs; never read or write expected labels."""

import argparse
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = A4
INK = "#24364A"


def text(c, x, top, value, size=11, font="Helvetica", color=INK):
    c.setFillColor(HexColor(color))
    c.setFont(font, size)
    c.drawString(x, HEIGHT - top, value)


def panel(c, top, height, color):
    c.setFillColor(HexColor(color))
    c.rect(42, HEIGHT - top - height, WIDTH - 84, height, fill=1, stroke=0)


def money(quantity, rate):
    return (Decimal(quantity) * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def new_bill(root, number):
    path = root / f"holdout_{number:03}" / "bill.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(path), pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"Synthetic electricity bill HOLDOUT-{number:03}")
    c.setAuthor("Bill Lens synthetic holdout dataset")
    c.setSubject("Fictional sample; not payable; no customer information")
    panel(c, 10, 26, INK)
    text(c, 54, 28, "SYNTHETIC SAMPLE - NOT PAYABLE", 10, "Helvetica-Bold", "#FFFFFF")
    text(c, 42, 791, f"HOLDOUT-{number:03} | AUD | All organisations are fictional | 1 / 1", 9)
    text(c, 42, 809, "No customer, address, meter or payment details. Bill Lens test fixture.", 9)
    return c


def period(c, top, start, end, days, usage, *, x=54):
    text(c, x, top, f"Billing period (inclusive): {start} to {end}")
    text(c, x, top + 27, f"Billing days: {days}")
    text(c, x, top + 54, f"Total imported usage: {usage} kWh")


def charges(c, top, usage, usage_rate, days, supply_rate):
    # Amounts originate here, independently of the handwritten label files.
    used, supply = money(usage, usage_rate), money(days, supply_rate)
    panel(c, top - 22, 32, "#ECF1F5")
    text(c, 54, top, "CURRENT-PERIOD CHARGES", 11, "Helvetica-Bold")
    text(c, 54, top + 44, f"Usage: {usage} kWh at AUD {usage_rate}/kWh = AUD {used}")
    text(c, 54, top + 77, f"Supply: {days} days at AUD {supply_rate}/day = AUD {supply}")
    text(c, 54, top + 109, "All rates and charges are GST inclusive.", 10)
    return used + supply


def total(c, top, amount, *, color=INK):
    text(c, 54, top, f"Current bill amount: AUD {amount}", 16, "Helvetica-Bold", color)
    text(c, 54, top + 29, f"Amount due: AUD {amount}", 11)


def holdout_001(root):
    c = new_bill(root, 1)
    text(c, 54, 82, "Your electricity account", 25, "Helvetica-Bold")
    period(c, 133, "2026-01-01", "2026-01-31", "31", "180")
    amount = charges(c, 270, "180", "0.32", "31", "1.05")
    total(c, 442, amount)
    panel(c, 567, 90, "#EAF3EE")
    text(c, 54, 592, "Retailer and billing contact", 10, "Helvetica-Bold")
    text(c, 54, 627, "Quillstone Sample Power", 21, "Helvetica-Bold", "#28664C")
    # A separate footer logo, not the logo-then-name header used by dev bill_003.
    text(c, 438, 731, "QSP", 31, "Helvetica-Bold", "#28664C")
    c.save()


def holdout_002(root):
    c = new_bill(root, 2)
    text(c, 244, 92, "QVX", 36, "Helvetica-Bold", "#743C59")
    text(c, 182, 125, "ELECTRICITY STATEMENT", 12)
    panel(c, 151, 116, "#F8EDF2")
    period(c, 180, "2026-02-01", "2026-02-28", "28", "210")
    total(c, 319, Decimal("87.78"), color="#743C59")
    amount = charges(c, 443, "210", "0.29", "28", "0.96")
    assert amount == Decimal("87.78")
    text(c, 54, 643, "This statement covers household electricity imports and supply.", 10)
    c.save()


def holdout_003(root):
    c = new_bill(root, 3)
    text(c, 54, 85, "Vellum Kite Sample Energy", 23, "Helvetica-Bold")
    text(c, 54, 119, "Electricity bill / service information", 12)
    panel(c, 152, 72, "#EAF1FA")
    text(c, 54, 178, "Your distributor: Glass Orchard Sample Networks", 12, "Helvetica-Bold")
    text(c, 54, 205, "Network faults are handled by your distributor.", 10)
    period(c, 269, "2026-03-01", "2026-03-31", "31", "275")
    amount = charges(c, 402, "275", "0.31", "31", "1.10")
    total(c, 588, amount)
    c.save()


def holdout_004(root):
    c = new_bill(root, 4)
    panel(c, 61, 89, "#315D65")
    text(c, 54, 99, "Mosaic Finch Sample Power", 23, "Helvetica-Bold", "#FFFFFF")
    text(c, 54, 128, "Your household electricity statement", 11, color="#FFFFFF")
    period(c, 198, "2026-04-01", "2026-04-30", "30", "160")
    amount = charges(c, 334, "160", "0.35", "30", "1.02")
    total(c, 510, amount, color="#315D65")
    text(c, 54, 699, "Legal notice", 9, "Helvetica-Bold")
    text(c, 54, 719, "Issued by Mosaic Finch Sample Retail Pty Ltd | ABN 00 000 000 000", 8)
    text(c, 54, 737, "ABN is an intentionally invalid synthetic placeholder.", 8)
    c.save()


def holdout_005(root):
    c = new_bill(root, 5)
    text(c, 54, 85, "Electricity tax invoice", 26, "Times-Bold")
    text(c, 54, 130, "Issued by Parchment Vale Sample Retail Pty Ltd", 14, "Times-Roman")
    text(c, 54, 154, "ABN 00 000 000 000 (invalid synthetic placeholder)", 9)
    period(c, 223, "2026-05-01", "2026-05-31", "31", "240")
    amount = charges(c, 363, "240", "0.28", "31", "0.99")
    panel(c, 526, 96, "#F3F0E8")
    total(c, 564, amount)
    text(c, 54, 699, "Charges apply to the inclusive service period stated above.", 10, "Times-Roman")
    c.save()


def holdout_006(root):
    c = new_bill(root, 6)
    text(c, 54, 84, "Copper Wren Sample Electricity", 22, "Helvetica-Bold", "#875027")
    text(c, 54, 115, "MONTHLY ACCOUNT", 11, "Helvetica-Bold")
    amount = charges(c, 180, "195", "0.33", "30", "1.08")
    panel(c, 329, 124, "#FAF0E8")
    period(c, 357, "2026-06-01", "2026-06-30", "30", "195")
    total(c, 518, amount, color="#875027")
    text(c, 54, 681, "Copper Wren Sample Electricity is part of", 10)
    text(c, 54, 703, "Cobalt Loom Sample Group", 12, "Helvetica-Bold")
    text(c, 54, 728, "Group information only; electricity is supplied by the brand above.", 9)
    c.save()


BUILDERS = (holdout_001, holdout_002, holdout_003, holdout_004, holdout_005, holdout_006)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dataset/holdout")
    args = parser.parse_args(argv)
    for build in BUILDERS:
        build(args.output)
        print(f"Generated {args.output / build.__name__ / 'bill.pdf'}")


if __name__ == "__main__":
    main()

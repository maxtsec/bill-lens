"""Rebuild only the synthetic PDFs; never read or generate expected labels."""

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = A4
INK = "#172B3A"


def charge(quantity: str, rate: str) -> str:
    return str((Decimal(quantity) * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def text(c: Canvas, x: float, top: float, value: str, size: int = 11,
         font: str = "Helvetica", color: str = INK) -> None:
    c.setFillColor(HexColor(color))
    c.setFont(font, size)
    c.drawString(x, HEIGHT - top, value)


def box(c: Canvas, x: float, top: float, width: float, height: float, color: str) -> None:
    c.setFillColor(HexColor(color))
    c.rect(x, HEIGHT - top - height, width, height, fill=1, stroke=0)


def rule(c: Canvas, top: float) -> None:
    c.setStrokeColor(HexColor("#CBD5DC"))
    c.line(42, HEIGHT - top, WIDTH - 42, HEIGHT - top)


def new_bill(number: int) -> Canvas:
    path = ROOT / "dataset" / f"bill_{number:03}" / "bill.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Fixed metadata and stable drawing order make rebuilds byte-for-byte repeatable.
    c = Canvas(str(path), pagesize=A4, invariant=1, pageCompression=1)
    c.setTitle(f"Synthetic electricity bill TEST-{number:03}")
    c.setAuthor("Bill Lens synthetic dataset")
    c.setSubject("Fictional sample; not payable; no customer information")
    box(c, 0, 0, WIDTH, 28, INK)
    text(c, 42, 19, "SYNTHETIC SAMPLE - NOT PAYABLE", 10, "Helvetica-Bold", "#FFFFFF")
    rule(c, 775)
    text(c, 42, 795, f"Fictional retailer | TEST-{number:03} | Currency: AUD", 9)
    text(c, 42, 812, "No customer, address, meter or payment details. Bill Lens test fixture.", 9)
    text(c, WIDTH - 67, 795, "1 / 1", 9)
    return c


def bill_001() -> None:
    c = new_bill(1)
    text(c, 42, 78, "Example Energy", 26, "Helvetica-Bold")
    text(c, 42, 107, "Electricity statement", 14)
    text(c, 42, 152, "Billing period: 1 April 2026 to 30 April 2026")
    text(c, 42, 178, "Billing days: 30")
    text(c, 42, 204, "Total imported usage: 250 kWh")
    box(c, 42, 242, 511, 30, "#E8EFF4")
    text(c, 54, 262, "Current-period charges", 12, "Helvetica-Bold")
    text(c, 54, 303, "Usage: 250 kWh at AUD 0.30/kWh")
    text(c, 452, 303, f"AUD {charge('250', '0.30')}")
    text(c, 54, 342, "Supply: 30 days at 110.23 c/day")
    text(c, 452, 342, f"AUD {charge('30', '1.1023')}")
    text(c, 54, 379, "All rates and charges are GST inclusive.", 10)
    rule(c, 410)
    text(c, 54, 453, "Current bill amount", 14, "Helvetica-Bold")
    text(c, 435, 453, "AUD 108.07", 14, "Helvetica-Bold")
    text(c, 54, 489, "Amount due: AUD 108.07", 12)
    c.save()


def bill_002() -> None:
    c = new_bill(2)
    text(c, 42, 78, "Harbour Sample Power", 24, "Helvetica-Bold")
    text(c, 42, 106, "ACCOUNT NOTICE", 12, "Helvetica-Bold", "#8C3B20")
    box(c, 42, 131, 511, 108, "#FFF0E8")
    text(c, 58, 163, "AMOUNT DUE", 14, "Helvetica-Bold", "#8C3B20")
    text(c, 58, 212, "AUD 162.66", 32, "Helvetica-Bold", "#8C3B20")
    text(c, 42, 276, "Service period: 01 May 2026 - 31 May 2026")
    text(c, 42, 300, "Billing days: 31   |   Total imported usage: 320 kWh")
    rule(c, 322)
    text(c, 42, 350, "CHARGE DETAILS", 12, "Helvetica-Bold")
    text(c, 42, 378, "Printed usage and supply rates exclude GST.", 10)
    text(c, 42, 416, f"AUD {charge('320', '0.28')}", 12, "Helvetica-Bold")
    text(c, 170, 416, "Usage: 320 kWh at AUD 0.28/kWh, ex GST")
    text(c, 42, 452, f"AUD {charge('31', '1.00')}", 12, "Helvetica-Bold")
    text(c, 170, 452, "Supply: 31 days at $1.00/day, ex GST")
    text(c, 42, 488, "AUD 12.06", 12, "Helvetica-Bold")
    text(c, 170, 488, "GST on this period's charges")
    rule(c, 518)
    text(c, 42, 552, "Previous balance: AUD 40.00")
    text(c, 42, 582, "Payment received: AUD 10.00")
    text(c, 42, 636, "Account amounts include charges, balances and received payments.", 10)
    c.save()


def bill_003() -> None:
    c = new_bill(3)
    text(c, 42, 75, "LANTERN", 29, "Helvetica-Bold", "#12645C")
    text(c, 42, 101, "Lantern Sample Electricity", 14)
    text(c, 42, 136, "Time-of-use electricity statement", 12)
    box(c, 42, 160, 511, 84, "#E9F3EF")
    text(c, 54, 182, "Billing period (DD/MM/YYYY)", 10, "Helvetica-Bold")
    text(c, 54, 209, "05/06/2026 - 04/07/2026", 15)
    text(c, 398, 209, "Billing days: 30", 12)
    text(c, 42, 290, "Tariff", 11, "Helvetica-Bold")
    text(c, 174, 290, "Quantity", 11, "Helvetica-Bold")
    text(c, 286, 290, "Unit rate", 11, "Helvetica-Bold")
    text(c, 460, 290, "Charge", 11, "Helvetica-Bold")
    for top, name, quantity, rate, amount in [
        (332, "Peak", "120 kWh", "AUD 0.40/kWh", charge("120", "0.40")),
        (377, "Off-peak", "180 kWh", "AUD 0.20/kWh", charge("180", "0.20")),
        (422, "Supply", "30 days", "98 c per day", charge("30", "0.98")),
    ]:
        rule(c, top - 26)
        for x, value in [(42, name), (174, quantity), (286, rate), (460, f"AUD {amount}")]:
            text(c, x, top, value)
    text(c, 42, 463, "GST inclusive: all printed rates and charges.", 10)
    text(c, 42, 502, "Total imported usage: 300 kWh", 13, "Helvetica-Bold")
    text(c, 42, 557, "Current bill amount: AUD 113.40", 16, "Helvetica-Bold", "#12645C")
    text(c, 42, 608, "Previous unpaid balance: AUD 50.00")
    text(c, 42, 646, "Amount due: AUD 163.40", 14)
    c.save()


def bill_004() -> None:
    c = new_bill(4)
    text(c, 42, 84, "Mallee Sample Energy", 27, "Times-Bold", "#4D5E34")
    text(c, 42, 119, "SOLAR HOUSEHOLD STATEMENT", 12, "Times-Roman")
    rule(c, 144)
    text(c, 42, 178, "Billing period: 1 November 2026 to 30 November 2026")
    text(c, 42, 207, "Billing days: 30")
    text(c, 42, 260, "1. Grid imports", 17, "Times-Bold")
    text(c, 58, 294, "Total imported usage: 100 kWh")
    text(c, 58, 327, f"Usage: 100 kWh at AUD 0.30/kWh = AUD {charge('100', '0.30')}")
    text(c, 58, 360, f"Supply: 30 days at AUD 1.00/day = AUD {charge('30', '1.00')}")
    text(c, 58, 391, "Import and supply rates are GST inclusive.", 10)
    text(c, 42, 444, "2. Solar exports", 17, "Times-Bold")
    text(c, 58, 478, "Exported energy: 800 kWh")
    text(c, 58, 511, f"Feed-in: 800 kWh at AUD 0.08/kWh = AUD {charge('800', '0.08')} credit")
    text(c, 58, 542, "All printed rates and amounts are GST inclusive.", 10)
    box(c, 42, 580, 511, 114, "#EDF1E6")
    text(c, 58, 614, "Current bill amount", 15, "Times-Bold")
    text(c, 58, 655, "AUD 4.00 CR", 28, "Times-Bold", "#4D5E34")
    text(c, 347, 655, "CR indicates credit", 12)
    c.save()


def bill_005() -> None:
    c = new_bill(5)
    text(c, 42, 77, "Bluegum Sample Electric", 23, "Helvetica-Bold", "#39537B")
    text(c, 42, 108, "Electricity account summary", 13)
    box(c, 42, 151, 241, 40, "#39537B")
    box(c, 309, 151, 244, 40, "#E8EDF4")
    text(c, 54, 177, "ACCOUNT SUMMARY", 12, "Helvetica-Bold", "#FFFFFF")
    text(c, 321, 177, "CHARGE DETAILS", 12, "Helvetica-Bold")
    # Matched y coordinates deliberately interleave the two independent columns
    # in pdfplumber's default plain-text reading order.
    text(c, 54, 230, "Billing period", 12, "Helvetica-Bold")
    text(c, 321, 230, "Total imported usage: 0 kWh", 11)
    text(c, 54, 263, "1 August 2026 to")
    text(c, 321, 263, "Usage: 0 kWh at AUD 0.30/kWh", 10)
    text(c, 54, 296, "31 August 2026")
    text(c, 321, 296, "Usage charge: AUD 0.00")
    text(c, 54, 343, "Billing days: 30", 12)
    text(c, 321, 343, "Supply: 31 days at 95¢/day", 11)
    text(c, 54, 383, "Current bill amount", 12, "Helvetica-Bold")
    text(c, 321, 383, f"Supply charge: AUD {charge('31', '0.95')}")
    text(c, 54, 424, "AUD 29.45", 24, "Helvetica-Bold", "#39537B")
    text(c, 321, 424, "All rates are GST inclusive.", 10)
    text(c, 54, 493, "Amount due: AUD 29.45")
    text(c, 321, 493, "Charges are GST inclusive.", 10)
    rule(c, 548)
    text(c, 42, 588, "Statement amounts are shown in Australian dollars.", 10)
    c.save()


if __name__ == "__main__":
    for build in (bill_001, bill_002, bill_003, bill_004, bill_005):
        build()
        print(f"Generated {build.__name__}/bill.pdf")

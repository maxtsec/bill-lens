"""Build ten fictional role-holdout PDFs without reading any answer files.

This is layout/source generation only. In particular, it never invokes review
logic, reads labels, or measures whether any role trap succeeds.
"""

import argparse
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = A4
NAVY, GREY = "#223246", "#536578"


@dataclass(frozen=True)
class Figures:
    retailer: str
    start: str
    end: str
    days: int
    usage: int
    usage_rate: str
    supply_rate: str
    previous: str
    payments: str
    credits: str

    @property
    def usage_charge(self):
        return (Decimal(self.usage) * Decimal(self.usage_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def supply_charge(self):
        return (Decimal(self.days) * Decimal(self.supply_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def current(self):
        return self.usage_charge + self.supply_charge

    @property
    def due(self):
        return self.current + Decimal(self.previous) - Decimal(self.payments) - Decimal(self.credits)


FIGURES = (
    Figures("Cedar Arc Sample Energy", "2026-07-01", "2026-07-31", 31, 245, "0.30", "1.05", "55.00", "20.00", "3.00"),
    Figures("Cloud Ember Sample Electric", "2026-08-01", "2026-08-31", 31, 180, "0.34", "0.98", "42.00", "12.00", "5.00"),
    Figures("Fenwick Grove Sample Power", "2026-09-01", "2026-09-30", 30, 260, "0.27", "1.10", "25.00", "10.00", "2.00"),
    Figures("Quartz Cove Sample Energy", "2026-10-01", "2026-10-31", 31, 198, "0.32", "1.04", "30.00", "7.00", "10.00"),
    Figures("Paper Lantern Sample Power", "2026-11-01", "2026-11-30", 30, 225, "0.31", "1.06", "20.00", "8.00", "5.00"),
    Figures("Spruce Wattle Sample Electricity", "2026-12-01", "2026-12-31", 31, 310, "0.29", "1.00", "40.00", "85.00", "0.00"),
    Figures("Juniper Vale Sample Power", "2027-01-01", "2027-01-31", 31, 175, "0.33", "0.95", "40.00", "10.00", "5.00"),
    Figures("Indigo Meadow Sample Energy", "2027-02-01", "2027-02-28", 28, 205, "0.35", "1.12", "60.00", "20.00", "5.00"),
    Figures("Marsh Silver Sample Power", "2027-03-01", "2027-03-31", 31, 190, "0.28", "1.03", "27.00", "9.00", "4.00"),
    Figures("Copper Rain Sample Electric", "2027-04-01", "2027-04-30", 30, 240, "0.36", "0.97", "32.00", "11.00", "6.00"),
)


def money(value):
    return f"{Decimal(value):.2f}"


def ink(canvas, color):
    canvas.setFillColor(HexColor(color))


def text(canvas, x, top, value, size=11, font="Helvetica", color=NAVY):
    ink(canvas, color)
    canvas.setFont(font, size)
    canvas.drawString(x, HEIGHT - top, value)


def box(canvas, x, top, width, height, color):
    ink(canvas, color)
    canvas.rect(x, HEIGHT - top - height, width, height, fill=1, stroke=0)


def rule(canvas, x, top, width, color="#CCD4DB"):
    canvas.setStrokeColor(HexColor(color))
    canvas.line(x, HEIGHT - top, x + width, HEIGHT - top)


def page_head(canvas, n, retailer, *, accent="#23647C", page=1, pages=1):
    box(canvas, 0, 0, WIDTH, 36, accent)
    text(canvas, 42, 24, "SYNTHETIC SAMPLE - NOT PAYABLE", 10, "Helvetica-Bold", "#FFFFFF")
    text(canvas, 42, 69, retailer, 20, "Helvetica-Bold", accent)
    rule(canvas, 42, 84, WIDTH - 84)
    text(canvas, 42, 805, f"ROLE-R{n:02} | Fictional electricity statement | Page {page} of {pages}", 8, color=GREY)


def period(canvas, f, top, *, x=50):
    text(canvas, x, top, f"Service period: {f.start} to {f.end} (inclusive)")
    text(canvas, x, top + 23, f"Billing days: {f.days}")
    text(canvas, x, top + 46, f"Imported usage total: {f.usage} kWh")
    text(canvas, x, top + 69, f"Daily supply rate: AUD {f.supply_rate}/day (GST inclusive)")


def charges(canvas, f, top, *, x=50):
    text(canvas, x, top, "Electricity charge details", 12, "Helvetica-Bold")
    text(canvas, x, top + 28, f"Usage: {f.usage} kWh x AUD {f.usage_rate}/kWh = AUD {money(f.usage_charge)}")
    text(canvas, x, top + 54, f"Supply: {f.days} days x AUD {f.supply_rate}/day = AUD {money(f.supply_charge)}")
    text(canvas, x, top + 79, "Rates and charge lines are GST inclusive.", 9, color=GREY)


def new_bill(root, n):
    path = root / f"holdout_r{n:02}" / "bill.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=A4, invariant=1, pageCompression=1)
    canvas.setTitle(f"Role holdout R{n:02} - synthetic electricity bill")
    canvas.setAuthor("Bill Lens synthetic dataset")
    canvas.setSubject("Fictional sample; not payable; no customer details")
    return canvas


def holdout_r01(root):
    f = FIGURES[0]
    c = new_bill(root, 1)
    page_head(c, 1, f.retailer, accent="#23647C")
    text(c, 50, 119, "MONTHLY ELECTRICITY ACCOUNT", 12, "Helvetica-Bold")
    period(c, f, 148)
    charges(c, f, 265)
    rule(c, 50, 378, 495)
    text(c, 50, 413, f"Opening balance: AUD {f.previous}")
    text(c, 50, 439, f"Payments received: AUD {f.payments}")
    text(c, 50, 465, f"Account credit: AUD {f.credits}")
    text(c, 50, 508, f"Current charges: AUD {money(f.current)}", 15, "Helvetica-Bold")
    box(c, 42, 538, WIDTH - 84, 59, "#E6F2F5")
    text(c, 55, 574, f"Amount due: AUD {money(f.due)}", 17, "Helvetica-Bold")
    text(c, 50, 643, "Please pay the total amount due shown above by 21 August 2026.", 10)
    c.save()


def holdout_r02(root):
    f = FIGURES[1]
    c = new_bill(root, 2)
    page_head(c, 2, f.retailer, accent="#80508F")
    box(c, 42, 108, WIDTH - 84, 111, "#F5EFF8")
    period(c, f, 134, x=55)
    charges(c, f, 257)
    text(c, 50, 397, "Account summary", 15, "Helvetica-Bold")
    # Table: every heading is on one row, with the corresponding values below.
    xs = (96, 194, 291, 394, 497)
    headers = ("Previous balance", "Payment", "Account credit", "Current charges", "Amount Due")
    values = (f.previous, f.payments, f.credits, money(f.current), money(f.due))
    box(c, 47, 413, 502, 81, "#F0F2F7")
    for x, header, value in zip(xs, headers, values, strict=True):
        c.setFont("Helvetica-Bold", 8)
        ink(c, NAVY)
        c.drawCentredString(x, HEIGHT - 438, header)
        c.setFont("Helvetica", 12)
        c.drawCentredString(x, HEIGHT - 475, f"{value}")
    text(c, 50, 535, "AUD amounts; credits and payments reduce the payable balance.", 10, color=GREY)
    c.save()


def holdout_r03(root):
    f = FIGURES[2]
    c = new_bill(root, 3)
    page_head(c, 3, f.retailer, accent="#315E4C")
    text(c, 50, 121, "Electricity statement | September 2026", 16, "Times-Bold")
    period(c, f, 159)
    charges(c, f, 274)
    # Summary boxes deliberately put large amounts above their captions.
    box(c, 47, 410, 240, 104, "#EAF3EC")
    box(c, 306, 410, 240, 104, "#F3EEE8")
    text(c, 62, 454, f"AUD {money(f.current)}", 24, "Helvetica-Bold", "#315E4C")
    text(c, 321, 454, f"AUD {money(f.due)}", 24, "Helvetica-Bold", "#80512C")
    text(c, 62, 490, "Total current charges", 11, "Helvetica-Bold")
    text(c, 321, 490, "Total amount due", 11, "Helvetica-Bold")
    text(c, 50, 563, f"Previous balance: AUD {f.previous}")
    text(c, 50, 588, f"Payment: AUD {f.payments}")
    text(c, 50, 613, f"Account credit: AUD {f.credits}")
    c.save()


def holdout_r04(root):
    f = FIGURES[3]
    c = new_bill(root, 4)
    page_head(c, 4, f.retailer, accent="#935A2C")
    text(c, 50, 120, "SERVICE AND TAX SUMMARY", 14, "Helvetica-Bold")
    charges(c, f, 163)
    period(c, f, 289)
    rule(c, 50, 410, 495)
    text(c, 50, 448, f"Current charges (incl. 10% GST): AUD {money(f.current)}", 14, "Helvetica-Bold")
    text(c, 50, 502, f"Previous balance: AUD {f.previous}")
    text(c, 50, 527, f"Payment: AUD {f.payments}")
    text(c, 50, 552, f"Account credit: AUD {f.credits}")
    text(c, 50, 608, f"Amount Due: AUD {money(f.due)}", 17, "Helvetica-Bold", "#935A2C")
    c.save()


def holdout_r05(root):
    f = FIGURES[4]
    c = new_bill(root, 5)
    page_head(c, 5, f.retailer, accent="#426A8F")
    text(c, 50, 122, "November electricity invoice", 18, "Times-Bold")
    period(c, f, 163)
    box(c, 43, 277, WIDTH - 86, 114, "#EDF3FA")
    charges(c, f, 305, x=54)
    text(c, 50, 456, "Current service", 10, "Helvetica-Bold", color=GREY)
    text(c, 50, 490, f"Electricity charges: AUD {money(f.current)}", 18, "Helvetica-Bold")
    text(c, 50, 552, f"Previous balance: AUD {f.previous}")
    text(c, 50, 578, f"Payment: AUD {f.payments}")
    text(c, 50, 604, f"Account credit: AUD {f.credits}")
    box(c, 43, 636, WIDTH - 86, 59, "#DBE9F6")
    text(c, 55, 674, f"Amount due: AUD {money(f.due)}", 17, "Helvetica-Bold")
    c.save()


def holdout_r06(root):
    f = FIGURES[5]
    carried_forward = Decimal(f.previous) - Decimal(f.payments)
    assert carried_forward < 0
    c = new_bill(root, 6)
    page_head(c, 6, f.retailer, accent="#55743D")
    text(c, 50, 119, "Electricity charges and account credit", 16, "Helvetica-Bold")
    charges(c, f, 153)
    period(c, f, 283)
    text(c, 50, 412, f"Current charges: AUD {money(f.current)}", 17, "Helvetica-Bold")
    text(c, 50, 473, f"Opening balance: AUD {f.previous}")
    text(c, 50, 498, f"Payments received: AUD {f.payments}")
    box(c, 43, 517, WIDTH - 86, 51, "#EFF5E9")
    text(c, 54, 551, f"Balance carried forward: AUD {money(-carried_forward)} CR", 13, "Helvetica-Bold", "#55743D")
    text(c, 50, 620, f"Amount due: AUD {money(f.due)}", 18, "Helvetica-Bold")
    c.save()


def holdout_r07(root):
    f = FIGURES[6]
    c = new_bill(root, 7)
    page_head(c, 7, f.retailer, accent="#645484")
    text(c, 50, 120, "Household electricity | January 2027", 17, "Helvetica-Bold")
    period(c, f, 159)
    charges(c, f, 281)
    text(c, 50, 419, "Account activity", 14, "Helvetica-Bold")
    text(c, 50, 451, f"Opening balance: AUD {f.previous}")
    text(c, 50, 478, f"Payments received: AUD {f.payments}")
    text(c, 50, 505, f"Account credit: AUD {f.credits}")
    box(c, 43, 542, WIDTH - 86, 65, "#F1EDF7")
    text(c, 55, 582, f"Total amount due: AUD {money(f.due)}", 18, "Helvetica-Bold")
    text(c, 50, 649, "The usage and supply lines above are shown individually.", 10, color=GREY)
    # No current-period aggregate is printed, even though the two line items reconcile.
    c.save()


def holdout_r08(root):
    f = FIGURES[7]
    c = new_bill(root, 8)
    page_head(c, 8, f.retailer, accent="#386678", page=1, pages=2)
    text(c, 50, 125, "Account summary", 20, "Helvetica-Bold")
    period(c, f, 174)
    box(c, 43, 320, WIDTH - 86, 226, "#EAF0F2")
    text(c, 55, 358, f"Previous balance: AUD {f.previous}")
    text(c, 55, 392, f"Payment: AUD {f.payments}")
    text(c, 55, 426, f"Account credit: AUD {f.credits}")
    text(c, 55, 500, f"Amount due: AUD {money(f.due)}", 19, "Helvetica-Bold")
    text(c, 50, 591, "Charge details and this period's total continue on page 2.", 11)
    c.showPage()
    page_head(c, 8, f.retailer, accent="#386678", page=2, pages=2)
    text(c, 50, 126, "Electricity charges", 20, "Helvetica-Bold")
    charges(c, f, 184)
    rule(c, 50, 326, 495)
    text(c, 50, 375, f"Current charges: AUD {money(f.current)}", 16, "Helvetica-Bold")
    text(c, 50, 433, "This page shows the charges for the service period on page 1.", 10, color=GREY)
    c.save()


def holdout_r09(root):
    """Ordinary one-column summary with an out-of-vocabulary total label."""
    f = FIGURES[8]
    c = new_bill(root, 9)
    page_head(c, 9, f.retailer, accent="#58724B")
    text(c, 50, 123, "Electricity account | March 2027", 16, "Helvetica-Bold")
    period(c, f, 160)
    charges(c, f, 288)
    rule(c, 50, 408, 495)
    text(c, 50, 453, f"Total charges: AUD {money(f.current)}", 16, "Helvetica-Bold")
    text(c, 50, 508, f"Previous balance: AUD {f.previous}")
    text(c, 50, 535, f"Payment: AUD {f.payments}")
    text(c, 50, 562, f"Account credit: AUD {f.credits}")
    text(c, 50, 622, f"Amount due: AUD {money(f.due)}", 18, "Helvetica-Bold")
    c.save()


def holdout_r10(root):
    """Second ordinary summary with a different out-of-vocabulary label."""
    f = FIGURES[9]
    c = new_bill(root, 10)
    page_head(c, 10, f.retailer, accent="#705D9A")
    text(c, 50, 121, "April electricity statement", 17, "Times-Bold")
    period(c, f, 161)
    charges(c, f, 286)
    text(c, 50, 429, f"Total electricity charges: AUD {money(f.current)}", 16, "Helvetica-Bold")
    rule(c, 50, 454, 495)
    text(c, 50, 505, f"Previous balance: AUD {f.previous}")
    text(c, 50, 533, f"Payment: AUD {f.payments}")
    text(c, 50, 561, f"Account credit: AUD {f.credits}")
    box(c, 43, 605, WIDTH - 86, 63, "#F0EBF7")
    text(c, 55, 644, f"Amount due: AUD {money(f.due)}", 17, "Helvetica-Bold")
    c.save()


BUILDERS = (holdout_r01, holdout_r02, holdout_r03, holdout_r04,
            holdout_r05, holdout_r06, holdout_r07, holdout_r08,
            holdout_r09, holdout_r10)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dataset/role-holdout")
    args = parser.parse_args(argv)
    for builder in BUILDERS:
        builder(args.output)
        print(f"Generated {args.output / builder.__name__ / 'bill.pdf'}")


if __name__ == "__main__":
    main()

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

path = Path("data/sample/beacon-quickstart.pdf")
c = canvas.Canvas(str(path), pagesize=A4, invariant=True)
w, h = A4
for page, title, lines in [
    (
        1,
        "Beacon B200 quick start",
        [
            "Connect Beacon to a stable 5 V USB power supply.",
            "Choose a 2.4 GHz Wi-Fi network for pairing.",
            "Hold the reset button for 12 seconds to clear saved credentials.",
            "The amber light flashes when reset is complete.",
            "A reset retains installed firmware.",
        ],
    ),
    (
        2,
        "Pairing and escalation",
        [
            "For error E17, check the Wi-Fi password and MAC filtering.",
            "Repeat pairing within 3 metres of the router.",
            "After a failed reset, contact support with the device serial number,",
            "firmware version, and router model.",
            "Never send your Wi-Fi password to support.",
        ],
    ),
]:
    c.setFillColor(colors.HexColor("#235d4e"))
    c.rect(0, h - 12, w, 12, fill=1, stroke=0)
    c.setFont("Helvetica", 10)
    c.drawString(52, h - 58, "DOCULENS / FICTIONAL SAMPLE DOCUMENT")
    c.setFont("Helvetica-Bold", 23)
    c.drawString(52, h - 110, title)
    c.setFillColor(colors.HexColor("#233c38"))
    c.setFont("Helvetica", 12)
    for i, line in enumerate(lines):
        c.drawString(52, h - 166 - i * 27, line)
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#6d7c77"))
    c.drawString(52, 40, f"Version 2026.1 | AI-authored fixture, not human-reviewed | Page {page}")
    c.showPage()
c.save()
print(path)

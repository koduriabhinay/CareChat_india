"""Write a synthetic lab report PDF for testing. All values are made up.

  python samples/make_sample_report.py samples/sample_lab_report.pdf
"""

import sys

LINES = [
    ("Helvetica-Bold", 16, "Sample Clinical Laboratory - TEST DATA ONLY"),
    ("Helvetica", 10, "Patient: Test Patient (synthetic)    Collected: 2026-10-01"),
    ("Helvetica-Bold", 12, "Comprehensive Metabolic Panel and Hemoglobin A1c"),
    ("Courier-Bold", 10, "TEST                 RESULT   UNIT      REFERENCE RANGE   FLAG"),
    ("Courier", 10, "Glucose, fasting     112      mg/dL     70-99             H"),
    ("Courier", 10, "Hemoglobin A1c       6.1      %         4.0-5.6           H"),
    ("Courier", 10, "Sodium               139      mmol/L    135-145"),
    ("Courier", 10, "Potassium            4.2      mmol/L    3.5-5.1"),
    ("Courier", 10, "Creatinine           0.9      mg/dL     0.6-1.2"),
    ("Courier", 10, "eGFR                 92       mL/min    >60"),
    ("Courier", 10, "ALT                  48       U/L       7-40              H"),
    ("Courier", 10, "AST                  31       U/L       8-40"),
    ("Courier", 10, "Total cholesterol    214      mg/dL     <200              H"),
    ("Courier", 10, "Vitamin D, 25-OH     18       ng/mL     30-100            L"),
    ("Helvetica", 10, "Comment: Results reviewed. Follow up with your provider."),
]
FONTS = {"Helvetica": "F1", "Helvetica-Bold": "F2", "Courier": "F3", "Courier-Bold": "F4"}


def build() -> bytes:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y = 760
    ops = []
    for font, size, text in LINES:
        ops.append(f"BT /{FONTS[font]} {size} Tf 50 {y} Td ({esc(text)}) Tj ET")
        y -= size + 12
    content = "\n".join(ops).encode("latin-1")
    font_objs = [f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} >>" for name in FONTS]
    font_refs = " ".join(f"/{ref} {5 + i} 0 R" for i, ref in enumerate(FONTS.values()))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << {font_refs} >> >> >>".encode(),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        *[f.encode() for f in font_objs],
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "sample_lab_report.pdf"
    with open(path, "wb") as f:
        f.write(build())
    print(f"Wrote {path}")

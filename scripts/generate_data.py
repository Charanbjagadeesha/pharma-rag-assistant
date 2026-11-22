import os
import sqlite3
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Ensure output folders exist before creating files
os.makedirs("data/sops", exist_ok=True)


def create_sop_pdf(filename, doc_id, title, version, department, effective_date, sections):
    """Generates a multi-section pharmaceutical SOP PDF using ReportLab."""
    filepath = os.path.join("data", "sops", filename)
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    # Draw official SOP header block on Page 1
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, f"STANDARD OPERATING PROCEDURE: {doc_id}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 70, f"Title: {title}")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 90, f"Version: {version} | Department: {department} | Effective Date: {effective_date}")
    c.line(50, height - 100, width - 50, height - 100)

    y = height - 125
    for heading, paragraphs in sections:
        # Start a fresh page if near the bottom margin
        if y < 120:
            c.showPage()
            y = height - 60

        # Draw section heading
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, heading)
        y -= 18

        # Draw wrapped paragraph lines under each heading
        c.setFont("Helvetica", 10)
        for para in paragraphs:
            words = para.split(" ")
            line = ""
            for word in words:
                if len(line + word) < 88:
                    line += word + " "
                else:
                    if y < 70:
                        c.showPage()
                        c.setFont("Helvetica", 10)
                        y = height - 60
                    c.drawString(60, y, line.strip())
                    y -= 14
                    line = word + " "
            if line:
                c.drawString(60, y, line.strip())
                y -= 18
        y -= 6

    c.save()
    print(f"[OK] Created PDF: {filepath}")


# --- 1. Define 3 Pharma Manufacturing SOP Rulebooks ---
sops = [
    (
        "SOP-001_Cleaning_Validation.pdf",
        "SOP-001",
        "Equipment Cleaning and Line Clearance Validation",
        "v3.2",
        "Manufacturing & QA",
        "2026-01-15",
        [
            ("1.0 Purpose & Scope", [
                "This SOP defines mandatory cleaning procedures for Tablet Compression Machine TC-04 and Fluid Bed Dryer FBD-02 to prevent cross-contamination between drug products in accordance with FDA 21 CFR Part 211.67 and EU GMP Annex 15."
            ]),
            ("2.0 Cleaning Hold Times", [
                "Dirty Equipment Hold Time (DEHT) must not exceed 24 hours after batch completion. If DEHT exceeds 24 hours, a full CIP (Clean-In-Place) cycle plus manual scrubbing with 0.5% Sodium Lauryl Sulfate (SLS) is mandatory.",
                "Clean Equipment Hold Time (CEHT) is strictly limited to 72 hours. Any equipment idle beyond 72 hours requires re-sanitization using 70% Isopropyl Alcohol (IPA) before batch startup."
            ]),
            ("3.0 Acceptance Criteria & Swab Limits", [
                "Total Organic Carbon (TOC) in final WFI (Water for Injection) rinse samples must be below 500 ppb. Visual inspection under 500 lux lighting must show zero visible residue. Microbial swab count must not exceed 10 CFU per 25 cm2."
            ]),
            ("4.0 Line Clearance & QA Sign-Off", [
                "Before starting a new batch, Production Supervisor and QA Officer must verify zero leftover labels, empty hoppers, and calibrated differential pressure gauges (15 to 25 Pa). Production cannot start without dual digital sign-off."
            ])
        ]
    ),
    (
        "SOP-002_Batch_Release_QA.pdf",
        "SOP-002",
        "Finished Product Batch Release and Certificate of Analysis Review",
        "v4.0",
        "Quality Assurance (QA)",
        "2026-03-01",
        [
            ("1.0 Purpose & Regulatory Reference", [
                "Establishes rules for Qualified Person (QP) and QA Manager review prior to releasing finished oral solid dosage batches to commercial distribution under ICH Q7 and FDA 21 CFR 211.192."
            ]),
            ("2.0 Mandatory Batch Release Checklist", [
                "Every batch file must contain: (a) Executed Batch Manufacturing Record (BMR) with zero unapproved deviations, (b) Analytical Certificate of Analysis (CoA) passing Assay (95.0% to 105.0%), Dissolution (not less than 80% in 30 mins), and Water Content (below 3.0% w/w), (c) Environmental monitoring logs, and (d) Yield reconciliation within 97.0% to 101.5%."
            ]),
            ("3.0 Out-of-Specification (OOS) Quarantine Rule", [
                "Any batch failing Dissolution, Assay, Microbial Limit, or Impurity thresholds must be immediately placed in physical and ERP QUARANTINE status within 2 hours. Re-testing without an approved Phase I laboratory investigation is strictly prohibited."
            ]),
            ("4.0 Release Authorization", [
                "Only QA Manager or Qualified Person holds system permission to change batch status from HOLD to RELEASED. QC Analysts may enter lab results but cannot approve commercial release."
            ])
        ]
    ),
    (
        "SOP-003_Deviation_CAPA.pdf",
        "SOP-003",
        "Manufacturing Deviation Management and CAPA Execution",
        "v2.5",
        "Quality Compliance",
        "2026-02-10",
        [
            ("1.0 Deviation Classification", [
                "Critical Deviation: Direct impact on patient safety, sterility, or regulatory compliance (e.g., wrong active ingredient weight, failed sterility, uncalibrated sensor). Must be escalated to QA Head within 4 hours.",
                "Major Deviation: Significant departure from approved SOP affecting product quality attributes (e.g., HVAC excursion above 25 C for over 30 minutes, yield outside 97.0%-101.5%). Escalate within 24 hours.",
                "Minor Deviation: Isolated clerical or documentation error with zero product quality impact (e.g., missing date corrected via single-line strike-through)."
            ]),
            ("2.0 Root Cause Analysis & CAPA Timelines", [
                "Root Cause Analysis (RCA) using 5-Whys or Fishbone diagram must conclude within 15 calendar days. Corrective and Preventive Actions (CAPA) must be implemented within 30 calendar days, followed by a 60-day effectiveness check."
            ])
        ]
    )
]

for item in sops:
    create_sop_pdf(*item)


# --- 2. Create SQLite Batch & QC Database (data/pharma.db) ---
db_path = os.path.join("data", "pharma.db")
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create table storing factory batch manufacturing and QC test outcomes
cursor.execute("""
CREATE TABLE batch_records (
    batch_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    mfg_date TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    assay_pct REAL NOT NULL,
    dissolution_pct REAL NOT NULL,
    yield_pct REAL NOT NULL,
    qc_status TEXT NOT NULL,
    deviation_id TEXT,
    failure_reason TEXT
)
""")

# Insert 12 realistic pharma batch rows (passed, failed, and quarantined)
sample_batches = [
    ("B-2026-101", "Paracetamol 500mg Tablets", "2026-09-02", "TC-04", 99.4, 91.2, 99.1, "RELEASED", None, None),
    ("B-2026-102", "Paracetamol 500mg Tablets", "2026-09-05", "TC-04", 98.8, 89.5, 98.7, "RELEASED", None, None),
    ("B-2026-103", "Amoxicillin 250mg Capsules", "2026-09-10", "FBD-02", 92.1, 74.0, 95.4, "FAILED", "DEV-2026-014", "Assay below 95.0% and Dissolution below 80%"),
    ("B-2026-104", "Metformin 500mg Tablets", "2026-09-14", "TC-04", 100.2, 88.0, 99.5, "RELEASED", None, None),
    ("B-2026-105", "Atorvastatin 10mg Tablets", "2026-09-19", "TC-04", 97.6, 85.4, 98.2, "RELEASED", None, None),
    ("B-2026-106", "Amoxicillin 250mg Capsules", "2026-09-24", "FBD-02", 96.5, 76.8, 96.1, "FAILED", "DEV-2026-019", "Dissolution failed (76.8% < 80% limit) due to moisture excursion"),
    ("B-2026-107", "Paracetamol 500mg Tablets", "2026-10-03", "TC-04", 99.9, 92.0, 99.8, "RELEASED", None, None),
    ("B-2026-108", "Metformin 500mg Tablets", "2026-10-08", "TC-04", 98.1, 86.7, 94.8, "QUARANTINE", "DEV-2026-022", "Batch yield 94.8% outside 97.0%-101.5% SOP limit"),
    ("B-2026-109", "Azithromycin 500mg Tablets", "2026-10-15", "FBD-02", 101.0, 90.4, 99.0, "RELEASED", None, None),
    ("B-2026-110", "Atorvastatin 10mg Tablets", "2026-10-21", "TC-04", 93.4, 81.2, 97.9, "FAILED", "DEV-2026-027", "Assay 93.4% out of specification (95.0%-105.0%)"),
    ("B-2026-111", "Azithromycin 500mg Tablets", "2026-11-02", "FBD-02", 99.2, 89.8, 99.3, "RELEASED", None, None),
    ("B-2026-112", "Paracetamol 500mg Tablets", "2026-11-10", "TC-04", 98.5, 87.9, 98.9, "RELEASED", None, None),
]

cursor.executemany("INSERT INTO batch_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sample_batches)
conn.commit()
conn.close()
print(f"[OK] Created SQLite database with {len(sample_batches)} batch records: {db_path}")
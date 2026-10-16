"""Generate the bundled sample protocol, PHX-401-201.

Synthetic. Written to look like a real Phase II protocol so the pipeline
has something realistic to chew on without any confidential material.

Two things are planted on purpose:
  - Section 7.3.2 says 5 minutes of rest; Appendix B says 10 minutes.
    The model should flag this as conflicting rather than pick one.
  - There is NO heart rate requirement anywhere. The mock extractor
    fabricates one, and the grounding check should delete it.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

OUT = Path(__file__).parent / "PHX-401-201_protocol.pdf"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Normal"], fontName="Helvetica-Bold",
                    fontSize=13, spaceBefore=18, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Normal"], fontName="Helvetica-Bold",
                    fontSize=11, spaceBefore=12, spaceAfter=6)
B = ParagraphStyle("B", parent=ss["Normal"], fontName="Times-Roman",
                   fontSize=10, leading=14, spaceAfter=6)
T = ParagraphStyle("T", parent=ss["Normal"], fontName="Helvetica-Bold",
                   fontSize=18, spaceAfter=4)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontName="Helvetica",
                     fontSize=10, textColor=colors.grey, spaceAfter=24)

s = []
p = lambda t, st=B: s.append(Paragraph(t, st))

# ---------------------------------------------------------------- cover
p("Clinical Study Protocol PHX-401-201", T)
p("A Phase II, Randomised, Double-Blind, Placebo-Controlled Study of PHX-401 "
  "in Adults with Stage 1 Hypertension", SUB)
p("Sponsor: Phoenix Clinical (synthetic sample)  |  Protocol version 2.0  |  "
  "This document is a synthetic example generated for software testing and "
  "does not describe a real trial.", SUB)

# ------------------------------------------------------------ section 1
p("1 Study Objectives", H1)
p("1.1 Primary Objective", H2)
p("To evaluate the effect of PHX-401 compared with placebo on the change from "
  "baseline in seated systolic blood pressure at Week 12.")
p("1.2 Secondary Objectives", H2)
p("To evaluate the change from baseline in seated diastolic blood pressure at "
  "Week 4 and Week 12, and to characterise the safety and tolerability of "
  "PHX-401 over 12 weeks of treatment.")

# ------------------------------------------------------------ section 2
p("2 Study Design", H1)
p("This is a multicentre, randomised, double-blind, placebo-controlled, "
  "parallel-group study. Approximately 120 subjects will be randomised 1:1 "
  "to PHX-401 10 mg once daily or matching placebo for 12 weeks. The study "
  "consists of a Screening period of up to 14 days, a 12-week double-blind "
  "Treatment period, and a safety follow-up contact.")

# ------------------------------------------------------------ section 5
p("5 Study Population", H1)
p("5.1 Inclusion Criteria", H2)
p("Subjects aged 18 to 75 years inclusive with a seated systolic blood "
  "pressure of 140 to 159 mmHg at Screening, who provide written informed "
  "consent.")

# ------------------------------------------------------------ section 6
p("6 Schedule of Activities", H1)
p("The assessments to be performed at each study visit are summarised in "
  "Table 6-1. Visit windows are +/- 3 days for Week 4 and Week 12.")

rows = [
    ["Assessment", "Screening\n(Day -14 to -1)", "Day 1\n(Baseline)", "Week 4", "Week 12", "Early\nTermination"],
    ["Informed consent", "X", "", "", "", ""],
    ["Demographics", "X", "", "", "", ""],
    ["Seated blood pressure", "X", "X", "X", "X", "X"],
    ["Body weight", "X", "X", "", "X", "X"],
    ["Height", "X", "", "", "", ""],
    ["12-lead ECG", "X", "", "", "X", "X"],
    ["Clinical laboratory tests", "X", "", "X", "X", "X"],
    ["Adverse event review", "", "X", "X", "X", "X"],
    ["Study drug dispensing", "", "X", "X", "", ""],
]
t = Table(rows, colWidths=[1.9 * inch, 1.05 * inch, 0.95 * inch, 0.8 * inch, 0.8 * inch, 0.95 * inch])
t.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
s.append(Spacer(1, 6))
s.append(t)
s.append(Spacer(1, 6))
p("Table 6-1. Schedule of Activities. X indicates the assessment is performed "
  "at that visit.", SUB)

s.append(PageBreak())

# ------------------------------------------------------------ section 7
p("7 Study Assessments and Procedures", H1)

p("7.1 Demographics", H2)
p("Date of birth and sex will be recorded at Screening. Age will be derived "
  "from date of birth at the time of informed consent.")

p("7.2 Body Measurements", H2)
p("Body weight will be recorded in kilograms to one decimal place at each "
  "visit where it is scheduled, with the subject in light indoor clothing and "
  "without shoes. Height will be measured in centimetres at Screening only.")

p("7.3 Vital Signs", H2)
p("7.3.1 General", H2)
p("Vital signs will be assessed at every study visit as indicated in the "
  "Schedule of Activities. All measurements must be recorded on the "
  "electronic case report form on the day they are taken.")

p("7.3.2 Blood Pressure Measurement", H2)
p("Seated systolic and diastolic blood pressure will be measured in triplicate "
  "using a calibrated automated device, after the subject has rested in the "
  "seated position for 5 minutes. The three readings will be taken at "
  "intervals of 1 to 2 minutes and each reading recorded individually. "
  "Systolic values outside 60 to 250 mmHg and diastolic values outside 30 to "
  "150 mmHg must be re-confirmed before the visit is closed. The position of "
  "the subject during measurement must be recorded as seated or supine.")

p("7.4 Electrocardiogram", H2)
p("A standard 12-lead ECG will be performed at Screening, Week 12 and Early "
  "Termination after the subject has rested supine for at least 5 minutes. "
  "The investigator will record whether the ECG was performed, the overall "
  "interpretation as normal, abnormal not clinically significant, or abnormal "
  "clinically significant, and the QTcF interval in milliseconds.")

p("7.5 Clinical Laboratory Tests", H2)
p("Blood samples for haematology and clinical chemistry will be collected at "
  "the visits specified in the Schedule of Activities. Fasting plasma glucose "
  "will be measured in mmol/L and HbA1c as a percentage. Samples should be "
  "collected after an overnight fast of at least 8 hours where feasible, and "
  "the date and time of collection recorded.")

p("7.6 Adverse Events", H2)
p("Adverse events will be collected from the time of first dose of study drug "
  "until the final study contact. For each adverse event the investigator "
  "will record the event term, the start date, and the severity graded as "
  "mild, moderate or severe.")

# ------------------------------------------------------------ section 9
p("9 Statistical Considerations", H1)
p("9.1 Primary Analysis", H2)
p("The primary endpoint is the change from baseline in seated systolic blood "
  "pressure at Week 12. Baseline is defined as the Day 1 pre-dose measurement. "
  "The mean of the triplicate readings at each visit will be used as the "
  "visit value. Subjects with no post-baseline measurement will be excluded "
  "from the primary analysis.")

s.append(PageBreak())

# ------------------------------------------------------------ appendix
p("Appendix B Blood Pressure Measurement Procedure", H1)
p("Site staff should ensure the subject is seated comfortably with back "
  "supported and feet flat on the floor. The subject should rest quietly for "
  "10 minutes before the first reading is taken. The arm should be supported "
  "at heart level. Use the same arm for all measurements throughout the study.")

doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.9 * inch,
                        rightMargin=0.9 * inch, topMargin=0.9 * inch,
                        bottomMargin=0.9 * inch,
                        title="PHX-401-201 Clinical Study Protocol (synthetic)")
doc.build(s)
print(f"wrote {OUT}")

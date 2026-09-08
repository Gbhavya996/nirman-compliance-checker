"""
notice_service.py
─────────────────
Generates official Legal Metrology Statutory Enforcement Notice PDFs
under the Legal Metrology Act, 2009 and LM-PC Rules, 2011.

Supports:
  1. Case A: Platform Show-Cause Notice under Rule 6(10) & Section 36(1)
             (Over-MRP sale on e-commerce platforms).
  2. Case B: Retailer Compounding Offence Notice under Section 36
             (Price smudging / Dual MRP tampering on retail store physical samples).
"""

import io
import datetime
import logging
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)

logger = logging.getLogger(__name__)


def generate_enforcement_notice_pdf(
    case_type: str,  # 'CASE_A' | 'CASE_B' | 'RULE_6_VIOLATION'
    product_title: Optional[str] = None,
    physical_mrp: Optional[float] = None,
    online_price: Optional[float] = None,
    delta_rupees: Optional[float] = None,
    delta_pct: Optional[float] = None,
    domain_or_seller: Optional[str] = None,
    retailer_name: Optional[str] = None,
    manufacturer: Optional[str] = None,
    reference_no: Optional[str] = None,
    breaches: Optional[List[str]] = None,
) -> bytes:
    """
    Generate an official statutory PDF enforcement notice.
    
    Args:
        case_type: The type of enforcement notice ('CASE_A', 'CASE_B', 'RULE_6_VIOLATION').
        product_title: Name of the commodity inspected.
        physical_mrp: MRP printed on the physical package.
        online_price: Price observed on the digital/retail listing.
        delta_rupees: The absolute difference in currency.
        delta_pct: Percentage increase over allowed MRP.
        domain_or_seller: Entity name for online violations.
        retailer_name: Entity name for physical retail violations.
        manufacturer: Identified manufacturer of the commodity.
        reference_no: Unique tracking ID for the notice.
        breaches: List of specific legal rule violations found.

    Returns:
        bytes: The raw PDF file content.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'NoticeTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        alignment=1, # Center
        textColor=colors.HexColor('#0f172a'),
    )
    subtitle_style = ParagraphStyle(
        'NoticeSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        alignment=1,
        textColor=colors.HexColor('#1e3a8a'),
    )
    dept_style = ParagraphStyle(
        'NoticeDept',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#475569'),
    )
    subject_style = ParagraphStyle(
        'NoticeSubject',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#991b1b'),
    )
    body_style = ParagraphStyle(
        'NoticeBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
    )
    body_bold = ParagraphStyle(
        'NoticeBodyBold',
        parent=body_style,
        fontName='Helvetica-Bold',
    )
    table_hdr_style = ParagraphStyle(
        'TableHdr',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
    )
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a'),
    )

    now = datetime.datetime.now()
    date_str = now.strftime('%d-%m-%Y')
    timestamp_str = now.strftime('%d-%m-%Y %H:%M:%S IST')
    ref_code = reference_no or f"LM-ENF/{now.year}/{now.strftime('%m%d%H%M')}"

    p_title = product_title or "Packaged Commodity Sample"
    p_mrp_str = f"₹ {physical_mrp:.2f}" if physical_mrp is not None else "N/A"
    o_price_str = f"₹ {online_price:.2f}" if online_price is not None else "N/A"
    d_rup_str = f"₹ {abs(delta_rupees):.2f}" if delta_rupees is not None else "N/A"
    d_pct_str = f"{abs(delta_pct):.1f}%" if delta_pct is not None else ""
    mfg_str = manufacturer or "Not Declared / Under Investigation"

    # Determine default breaches if not explicitly supplied
    if not breaches:
        if case_type == 'CASE_B':
            breach_list = [
                "Rule 18(2) LM-PC Rules (Alteration of Price / Dual MRP Tampering)",
                "Rule 6(1)(e) LM-PC Rules (Statutory Retail Sale Price Declaration)",
                "Section 36 & Section 48 LM Act, 2009 (Compounding of Offences)",
            ]
        elif case_type == 'RULE_6_VIOLATION':
            breach_list = [
                "Rule 6(1) LM-PC Rules (Omission of Mandatory Declarations)",
                "Rule 6(10) LM-PC Rules (Incomplete E-Commerce Digital Disclosures)",
                "Section 36(1) LM Act, 2009 (Penalty for Statutory Non-Compliance)",
            ]
        else:
            breach_list = [
                "Rule 18(2) LM-PC Rules (Sale above declared Maximum Retail Price)",
                "Rule 6(1)(e) LM-PC Rules (Mandatory Maximum Retail Price)",
                "Rule 6(10) LM-PC Rules (E-Commerce Mandatory Pricing & Disclosures)",
                "Section 36(1) LM Act, 2009 (Penalty for Non-Compliant Retail Sale)",
            ]
    else:
        breach_list = breaches

    story = []

    # 1. Header Emblem & Titles
    story.append(Paragraph("GOVERNMENT OF INDIA", title_style))
    story.append(Paragraph("MINISTRY OF CONSUMER AFFAIRS, FOOD AND PUBLIC DISTRIBUTION", subtitle_style))
    story.append(Paragraph("DEPARTMENT OF CONSUMER AFFAIRS · LEGAL METROLOGY DIVISION", dept_style))
    story.append(Paragraph("STATUTORY ENFORCEMENT & COMPLIANCE DIRECTORATE", dept_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1e3a8a'), spaceAfter=10))

    # 2. Reference & Date Line
    ref_table_data = [
        [
            Paragraph(f"<b>Inspection Ref ID:</b> {ref_code}", body_style),
            Paragraph(f"<b>Date & Timestamp:</b> {timestamp_str}", ParagraphStyle('RightText', parent=body_style, alignment=2)),
        ],
        [
            Paragraph("<b>Issuing Authority:</b> Enforcement Officer, Legal Metrology", body_style),
            Paragraph("<b>Jurisdiction:</b> Central / State Metrology Wing", ParagraphStyle('RightText2', parent=body_style, alignment=2)),
        ]
    ]
    ref_table = Table(ref_table_data, colWidths=[260, 255])
    ref_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 10))

    # 3. Addressee & Subject depending on Case A vs Case B
    if case_type == 'CASE_B':
        subject_entity = retailer_name or "M/s Retail Enterprise / Store In-charge"
        story.append(Paragraph(f"<b>TO (Subject Entity):</b><br/>{subject_entity}<br/>Physical Retail Store Premise<br/>(Identified during Market Surveillance Sample Inspection)", body_style))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "<b>SUBJECT: STATUTORY NOTICE FOR COMPOUNDING OF OFFENCE UNDER SECTION 36 & 48 OF THE LEGAL METROLOGY ACT, 2009 — "
            "TAMPERING, PRICE SMUDGING, AND SALE AT DUAL / EXORBITANT MRP.</b>",
            subject_style
        ))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "WHEREAS, an authorized inspection of packaged commodities was conducted at your retail premise under Section 15 of the Legal Metrology Act, 2009. "
            "During physical sample examination and laboratory verification against the canonical manufacturer declaration and verified brand price catalog, "
            "it was established that the physical sample offered for sale bears an inflated / smudged MRP exceeding the lawful maximum retail price.",
            body_style
        ))
    elif case_type == 'RULE_6_VIOLATION':
        subject_entity = domain_or_seller or manufacturer or "Designated Commercial Entity / Packer"
        story.append(Paragraph(f"<b>TO (Subject Entity):</b><br/>{subject_entity}<br/>E-Commerce Marketplace Platform / Manufacturer Premise<br/>Metrology Compliance Desk", body_style))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "<b>SUBJECT: SHOW-CAUSE NOTICE UNDER RULE 6(1) & 6(10) OF LEGAL METROLOGY (PACKAGED COMMODITIES) RULES, 2011 "
            "READ WITH SECTION 36 OF THE LEGAL METROLOGY ACT, 2009 — OMISSION OF MANDATORY STATUTORY DECLARATIONS.</b>",
            subject_style
        ))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "WHEREAS, statutory audit and compliance examination conducted under the Legal Metrology Act, 2009 revealed that mandatory "
            "statutory declarations mandated under Rule 6 of the LM-PC Rules, 2011 are omitted or deficient on the subject packaged commodity.",
            body_style
        ))
    else:  # CASE_A default
        subject_entity = domain_or_seller or "E-Commerce Entity / Designated Marketplace Seller"
        story.append(Paragraph(f"<b>TO (Subject Entity):</b><br/>{subject_entity}<br/>E-Commerce Marketplace Platform & Registered Entity<br/>Grievance Officer / Metrology Compliance Desk", body_style))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "<b>SUBJECT: SHOW-CAUSE NOTICE UNDER RULE 6(10) & 18 OF LEGAL METROLOGY (PACKAGED COMMODITIES) RULES, 2011 "
            "READ WITH SECTION 36(1) OF THE LEGAL METROLOGY ACT, 2009 — OVER-MRP SALE ON DIGITAL PLATFORM.</b>",
            subject_style
        ))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "WHEREAS, digital market surveillance and technical inspection conducted by the Nirman Metrology Automated Compliance Checker "
            "detected that the packaged commodity listed and offered for retail sale on your e-commerce platform is priced higher than the "
            "physical Maximum Retail Price (MRP) mandated and stamped on the manufacturer's packaging label.",
            body_style
        ))

    story.append(Spacer(1, 10))

    # 4. Evidence Comparison Table
    story.append(Paragraph("<b>SCHEDULE OF INSPECTION & EVIDENCE MATRIX</b>", subtitle_style))
    story.append(Spacer(1, 4))

    table_data = [
        [
            Paragraph("<b>Parameter</b>", table_hdr_style),
            Paragraph("<b>Inspected Finding</b>", table_hdr_style),
            Paragraph("<b>Statutory Baseline / Reference</b>", table_hdr_style),
        ],
        [
            Paragraph("Product Description", table_cell_style),
            Paragraph(p_title[:75], table_cell_style),
            Paragraph("Commodity verification", table_cell_style),
        ],
        [
            Paragraph("Manufacturer / Brand", table_cell_style),
            Paragraph(mfg_str[:60], table_cell_style),
            Paragraph("Rule 6(1)(a) Mandatory Name & Address", table_cell_style),
        ],
        [
            Paragraph("Physical Label MRP", table_cell_style),
            Paragraph(f"<b>{p_mrp_str}</b>", table_cell_style),
            Paragraph("Rule 6(1)(e) Declared MRP (Inclusive of all taxes)", table_cell_style),
        ],
        [
            Paragraph(
                "Retail Store Offering Price" if case_type == 'CASE_B' else "Online Platform Listing Price",
                table_cell_style
            ),
            Paragraph(f"<b>{p_mrp_str if case_type == 'CASE_B' else o_price_str}</b>", table_cell_style),
            Paragraph(
                f"Canonical Brand Online MRP: {o_price_str}" if case_type == 'CASE_B' else f"Physical Package Label MRP: {p_mrp_str}",
                table_cell_style
            ),
        ],
        [
            Paragraph("Calculated Price Discrepancy", table_cell_style),
            Paragraph(f"<font color='#dc2626'><b>+{d_rup_str} per unit ({d_pct_str})</b></font>", table_cell_style),
            Paragraph("Section 36(1) Overcharging Margin (Delta per unit)", table_cell_style),
        ],
        [
            Paragraph("Specific Statutory Breaches", table_cell_style),
            Paragraph("<br/>".join(f"• {b}" for b in breach_list), table_cell_style),
            Paragraph("Contravention of Statutory Mandates under LM Act, 2009", table_cell_style),
        ],
    ]

    evidence_table = Table(table_data, colWidths=[150, 185, 180])
    evidence_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3a8a')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(evidence_table)
    story.append(Spacer(1, 10))

    # 5. Directives & Penalty Fine Bracket
    story.append(Paragraph("<b>STATUTORY PENALTY & DIRECTIVES</b>", subtitle_style))
    story.append(Spacer(1, 4))

    penalties_text = (
        "1. <b>Statutory Compounding Fine Range (₹25,000 – ₹1,00,000):</b> Under Section 36 read with Section 48 "
        "of the Legal Metrology Act, 2009, manufacturing, packaging, distributing, or selling commodities in "
        "contravention of LM-PC Rules attracts a statutory compounding fine range of <b>₹25,000 (Twenty-Five Thousand Rupees)</b> "
        "for the first offence, extending up to <b>₹50,000</b> for second offence, and up to <b>₹1,00,000 (One Lakh Rupees)</b> "
        "for repeated or continued contraventions.<br/>"
        "2. <b>Production of Records / Response:</b> The Subject Entity is directed to respond in writing within "
        "<b>7 (Seven) working days</b> of receipt of this notice, presenting purchase invoices, supplier manifests, and relevant declarations.<br/>"
        "3. <b>Compounding Option & Rectification:</b> If electing to compound this offence without court prosecution, submit Form LM-CP-1 "
        "along with the prescribed statutory fee and immediately rectify all packaging / listing declarations."
    )

    story.append(Paragraph(penalties_text, body_style))
    story.append(Spacer(1, 14))

    # 6. Signature Block
    sign_block = [
        Paragraph("<b>Digitally Issued by:</b><br/>Inspectorate of Legal Metrology<br/>Automated Compliance Directorate (NIRMAN)<br/>Department of Consumer Affairs, Govt. of India", body_style),
        Paragraph(f"<b>Official Seal / Stamp:</b><br/>[ SEAL OF LEGAL METROLOGY ]<br/><b>Verified:</b> {date_str}", ParagraphStyle('RightSign', parent=body_style, alignment=2)),
    ]
    sign_table = Table([sign_block], colWidths=[260, 255])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(KeepTogether([sign_table]))

    doc.build(story)
    return buffer.getvalue()

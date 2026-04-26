"""
HCS Design — Report Generator (Phase 7)
=========================================
Reference : ACI/PCI CODE-319-25 | PCI Design Handbook, 8th Edition
Units     : SI only (mm, kN, MPa)

This module generates Word (.docx) and PDF reports.
Greek symbols are written as plain text (phi, alfa, beta, etc.)
"""

import io
from datetime import datetime

# Try to import docx and reportlab; if not installed, provide fallback
try:
    from docx import Document
    from docx.shared import Mm, Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def generate_word_report(ss, output_stream=None):
    """
    Generate Word document (.docx) as bytes.
    If output_stream is None, returns BytesIO object.
    """
    if not HAS_DOCX:
        return None
    doc = Document()
    # Set margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Mm(20)
        section.bottom_margin = Mm(20)
        section.left_margin = Mm(20)
        section.right_margin = Mm(20)

    # Title
    title = doc.add_heading('Hollow Core Slab Design Calculation Report', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    doc.add_paragraph(f"Reference: ACI/PCI CODE-319-25 | PCI Design Handbook 8th Ed.")
    doc.add_paragraph(f"Units: mm, kN, MPa (SI)")
    doc.add_page_break()

    # Chapter 1: Design Input
    doc.add_heading('1. Design Input', level=1)
    # Concrete
    doc.add_heading('1.1 Concrete Properties', level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = 'Parameter'
    hdr[1].text = 'Value'
    for key, label in [
        ('f_ci', "f'ci (transfer)"), ('f_c_cut', "f'c (cutting)"), ('f_c_del', "f'c (delivery)"),
        ('f_c_ere', "f'c (erection)"), ('f_c', "f'c (28-day)"), ('wc', "Unit weight (kN/m³)"),
        ('has_topping', "Topping present"), ('f_c_top', "f'c topping (MPa)"), ('wc_top', "wc topping (kN/m³)")
    ]:
        row = table.add_row().cells
        row[0].text = label
        val = ss.get(key, 'N/A')
        if key == 'has_topping':
            val = 'Yes' if val else 'No'
        elif key in ['f_c_top', 'wc_top'] and not ss.get('has_topping', False):
            val = 'N/A'
        row[1].text = str(val)

    # Section geometry
    doc.add_heading('1.2 Section Geometry', level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = 'Parameter'
    hdr[1].text = 'Value (mm)'
    for key, label in [
        ('b_nominal', 'b_nominal'), ('b_bottom', 'b_bottom'), ('b_top', 'b_top'),
        ('h', 'Total HCS thickness'), ('tf_top', 'Top flange thickness'), ('tf_bot', 'Bottom flange thickness'),
        ('t_topping', 'Topping thickness'), ('n_core', 'Number of cores'), ('d_core', 'Core diameter')
    ]:
        row = table.add_row().cells
        row[0].text = label
        row[1].text = f"{ss.get(key, 0):.0f}"
    doc.add_paragraph(f"Core shape: {ss.get('core_shape', 'N/A')}")

    # Prestress
    doc.add_heading('1.3 Prestressing Steel', level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = 'Parameter'
    hdr[1].text = 'Value'
    for key, label in [
        ('ps_type', 'Type'), ('n_bot', '# bottom tendons'), ('n_top', '# top tendons'),
        ('cover_bot', 'Bottom cover (mm)'), ('cover_top', 'Top cover (mm)'),
        ('fpu', 'fpu (MPa)'), ('fpy', 'fpy (MPa)'), ('Eps', 'Eps (MPa)'),
        ('fpi_pct', 'Initial prestress (% fpu)'), ('fpi', 'fpi (MPa)'), ('Pi', 'Pi (kN)')
    ]:
        row = table.add_row().cells
        row[0].text = label
        val = ss.get(key, 'N/A')
        if isinstance(val, float):
            val = f"{val:.1f}"
        row[1].text = str(val)

    # Span & loads
    doc.add_heading('1.4 Span and Loads', level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = 'Parameter'
    hdr[1].text = 'Value'
    for key, label in [
        ('L_cc', 'L_cc (mm)'), ('L_an', 'L_an (mm)'), ('SW_HCS', 'Self-weight HCS (kN/m²)'),
        ('SW_topping', 'Topping weight (kN/m²)'), ('SDL', 'SDL (kN/m²)'), ('LL', 'LL (kN/m²)'),
        ('lb_wu_area', 'wu factored (kN/m²)'), ('lb_Vu_max', 'Vu max (kN)'), ('lb_Mu_max', 'Mu max (kN·m)')
    ]:
        row = table.add_row().cells
        row[0].text = label
        val = ss.get(key, 0)
        if isinstance(val, float):
            val = f"{val:.2f}"
        row[1].text = str(val)

    doc.add_page_break()

    # Chapter 2: Transfer and Development Length
    doc.add_heading('2. Transfer and Development Length', level=1)
    doc.add_paragraph(f"Transfer length l_t = {ss.get('lb_l_t', 0):.0f} mm")
    doc.add_paragraph(f"Development length l_d = {ss.get('lb_l_d', 0):.0f} mm")
    doc.add_paragraph(f"Status: {ss.get('lb_ps_status', 'N/A')}")

    # Chapter 3: Section Properties
    doc.add_heading('3. Section Properties', level=1)
    doc.add_heading('3.1 Gross Section', level=2)
    doc.add_paragraph(f"Area Ag = {ss.get('sp_Ag', 0):,.0f} mm²")
    doc.add_paragraph(f"Centroid yb = {ss.get('sp_yb_g', 0):.1f} mm")
    doc.add_paragraph(f"Moment of inertia Ig = {ss.get('sp_Ig', 0)/1e6:.3f} x10⁶ mm⁴")
    doc.add_heading('3.2 Net Section', level=2)
    doc.add_paragraph(f"Area An = {ss.get('sp_An', 0):,.0f} mm²")
    doc.add_paragraph(f"Centroid yb = {ss.get('sp_yb', 0):.2f} mm")
    doc.add_paragraph(f"Inertia In = {ss.get('sp_In', 0)/1e6:.3f} x10⁶ mm⁴")
    doc.add_paragraph(f"Eccentricity e_bot = {ss.get('sp_e_bot', 0):.2f} mm")
    if ss.get('has_topping'):
        doc.add_heading('3.3 Composite Section', level=2)
        doc.add_paragraph(f"Area A_comp = {ss.get('sp_A_comp', 0):,.0f} mm²")
        doc.add_paragraph(f"Centroid yb_comp = {ss.get('sp_yb_comp', 0):.2f} mm")
        doc.add_paragraph(f"Inertia I_comp = {ss.get('sp_I_comp', 0)/1e6:.3f} x10⁶ mm⁴")

    # Chapter 4: Prestress Losses
    doc.add_heading('4. Prestress Losses', level=1)
    doc.add_paragraph(f"Elastic shortening ES = {ss.get('pl_ES', 0):.1f} MPa")
    doc.add_paragraph(f"Creep CR = {ss.get('pl_CR', 0):.1f} MPa")
    doc.add_paragraph(f"Shrinkage SH = {ss.get('pl_SH', 0):.1f} MPa")
    doc.add_paragraph(f"Relaxation RE = {ss.get('pl_RE', 0):.1f} MPa")
    doc.add_paragraph(f"Total loss = {ss.get('pl_total_MPa', 0):.1f} MPa ({ss.get('pl_total_pct', 0):.1f}%)")
    doc.add_paragraph(f"Effective prestress fse = {ss.get('pl_fse', 0):.1f} MPa")
    doc.add_paragraph(f"Effective force Pe = {ss.get('pl_Pe', 0):.1f} kN")

    # Chapter 5: Stress Checks
    doc.add_heading('5. Stress Checks', level=1)
    sc = ss
    if 'sc_transfer' in sc:
        doc.add_heading('5.1 Transfer', level=2)
        t = sc['sc_transfer']
        doc.add_paragraph(f"Top fiber: {t['f_top']:.2f} MPa, Bottom fiber: {t['f_bot']:.2f} MPa, Status: {t['status']}")
        li = sc['sc_lifting']
        doc.add_heading('5.2 Lifting', level=2)
        doc.add_paragraph(f"Top: {li['f_top']:.2f} MPa, Bottom: {li['f_bot']:.2f} MPa, Status: {li['status']}")
        co = sc['sc_construction']
        doc.add_heading('5.3 Construction', level=2)
        doc.add_paragraph(f"Top: {co['f_top']:.2f} MPa, Bottom: {co['f_bot']:.2f} MPa, Status: {co['status']}")
        sv = sc['sc_service']
        doc.add_heading('5.4 Service', level=2)
        doc.add_paragraph(f"Top: {sv['f_top']:.2f} MPa, Bottom: {sv['f_bot']:.2f} MPa, Status: {sv['status']}")

    # Chapter 6: Capacity
    doc.add_heading('6. Flexural and Shear Capacity', level=1)
    doc.add_paragraph(f"fps = {ss.get('cap_fps', 0):.1f} MPa")
    doc.add_paragraph(f"Mn = {ss.get('cap_Mn', 0):.1f} kN·m, phi*Mn = {ss.get('cap_phi_Mn', 0):.1f} kN·m")
    doc.add_paragraph(f"Demand-Capacity Ratio Mu/phiMn = {ss.get('cap_DCR_M', 0):.2f}")
    doc.add_paragraph(f"Minimum phi*Vn = {ss.get('cap_phi_Vn_min', 0):.1f} kN, DCR Vu/phiVn = {ss.get('cap_DCR_V', 0):.2f}")
    if ss.get('cap_needs_Av_min', False):
        doc.add_paragraph("WARNING: Minimum shear reinforcement Av,min required per ACI/PCI 319-25.")

    # Chapter 7: Deflection
    doc.add_heading('7. Deflection and Camber', level=1)
    doc.add_paragraph(f"Initial camber (prestress): {ss.get('def_delta_ps_initial', 0):.2f} mm")
    doc.add_paragraph(f"Self-weight deflection: {ss.get('def_delta_sw', 0):.2f} mm")
    doc.add_paragraph(f"Net deflection at release: {ss.get('def_net_release', 0):.2f} mm")
    doc.add_paragraph(f"Long-term total deflection: {ss.get('def_total_longterm', 0):.2f} mm")
    doc.add_paragraph(f"Limits: L/360 = {ss.get('def_limit_ll_mm', 0):.1f} mm, L/240 = {ss.get('def_limit_total_mm', 0):.1f} mm")
    doc.add_paragraph(f"Status: LL = {ss.get('def_status_ll', 'N/A')}, Total = {ss.get('def_status_total', 'N/A')}")

    doc.add_page_break()
    doc.add_heading('Appendix A: Remarks', level=1)
    doc.add_paragraph("This report was generated automatically by HCS Design App v1.0.")
    doc.add_paragraph("All calculations conform to ACI/PCI CODE-319-25 and PCI Design Handbook 8th Edition.")
    doc.add_paragraph("Engineer should verify inputs and assumptions before construction.")

    # Save to bytes
    if output_stream is None:
        output_stream = io.BytesIO()
    doc.save(output_stream)
    output_stream.seek(0)
    return output_stream


def generate_pdf_report(ss, output_stream=None):
    """
    Generate PDF report using reportlab.
    Returns BytesIO object.
    """
    if not HAS_REPORTLAB:
        return None
    if output_stream is None:
        output_stream = io.BytesIO()
    doc = SimpleDocTemplate(output_stream, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CenterTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=16, spaceAfter=12))
    styles.add(ParagraphStyle(name='TableHeader', parent=styles['Normal'], alignment=TA_CENTER, fontSize=9, textColor=colors.white, backColor=colors.grey))
    story = []

    # Title
    story.append(Paragraph("Hollow Core Slab Design Calculation Report", styles['CenterTitle']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Paragraph("Reference: ACI/PCI CODE-319-25 | PCI Design Handbook 8th Ed.", styles['Normal']))
    story.append(Paragraph("Units: mm, kN, MPa (SI)", styles['Normal']))
    story.append(PageBreak())

    # Helper to add two-column tables
    def add_kv_table(story, title, data):
        story.append(Paragraph(title, styles['Heading2']))
        t = Table(data, colWidths=[80*mm, 80*mm])
        t.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    # Input data
    data = [['Parameter', 'Value']]
    for key, label in [('f_ci', "f'ci transfer"), ('f_c', "f'c 28-day"), ('wc', "Unit weight"), ('has_topping', "Topping")]:
        val = ss.get(key, 'N/A')
        if key == 'has_topping':
            val = 'Yes' if val else 'No'
        data.append([label, str(val)])
    add_kv_table(story, "1. Concrete Properties", data)

    data = [['Parameter', 'Value (mm)']]
    for key in ['b_nominal', 'b_bottom', 'b_top', 'h', 'tf_top', 'tf_bot', 't_topping', 'n_core', 'd_core']:
        data.append([key, f"{ss.get(key, 0):.0f}"])
    add_kv_table(story, "2. Section Geometry", data)

    data = [['Parameter', 'Value']]
    for key in ['ps_type', 'n_bot', 'n_top', 'fpu', 'fpy', 'Eps', 'fpi', 'Pi']:
        val = ss.get(key, 0)
        if isinstance(val, float):
            val = f"{val:.1f}"
        data.append([key, str(val)])
    add_kv_table(story, "3. Prestressing", data)

    data = [['Parameter', 'Value']]
    for key in ['L_an', 'SW_HCS', 'SW_topping', 'SDL', 'LL', 'lb_wu_area', 'lb_Vu_max', 'lb_Mu_max']:
        val = ss.get(key, 0)
        if isinstance(val, float):
            val = f"{val:.2f}"
        data.append([key, str(val)])
    add_kv_table(story, "4. Span and Loads", data)

    # Losses
    story.append(Paragraph("5. Prestress Losses", styles['Heading2']))
    data = [['Component', 'Value (MPa)']]
    for comp in ['pl_ES', 'pl_CR', 'pl_SH', 'pl_RE', 'pl_total_MPa']:
        data.append([comp, f"{ss.get(comp, 0):.1f}"])
    t = Table(data, colWidths=[80*mm, 80*mm])
    t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    story.append(t)
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Effective prestress fse = {ss.get('pl_fse', 0):.1f} MPa, Pe = {ss.get('pl_Pe', 0):.1f} kN", styles['Normal']))
    story.append(PageBreak())

    # Stress checks
    story.append(Paragraph("6. Stress Checks", styles['Heading2']))
    if 'sc_transfer' in ss:
        data = [['Stage', 'Top (MPa)', 'Bottom (MPa)', 'Status']]
        for stage, key in [('Transfer', 'sc_transfer'), ('Lifting', 'sc_lifting'), ('Construction', 'sc_construction'), ('Service', 'sc_service')]:
            s = ss.get(key, {})
            data.append([stage, f"{s.get('f_top',0):.2f}", f"{s.get('f_bot',0):.2f}", s.get('status', 'N/A')])
        t = Table(data, colWidths=[40*mm, 40*mm, 40*mm, 40*mm])
        t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
        story.append(t)

    # Capacity
    story.append(Paragraph("7. Flexural and Shear Capacity", styles['Heading2']))
    story.append(Paragraph(f"fps = {ss.get('cap_fps',0):.1f} MPa, Mn = {ss.get('cap_Mn',0):.1f} kN·m, phi*Mn = {ss.get('cap_phi_Mn',0):.1f} kN·m", styles['Normal']))
    story.append(Paragraph(f"DCR Mu/phiMn = {ss.get('cap_DCR_M',0):.2f}", styles['Normal']))
    story.append(Paragraph(f"min phi*Vn = {ss.get('cap_phi_Vn_min',0):.1f} kN, DCR Vu/phiVn = {ss.get('cap_DCR_V',0):.2f}", styles['Normal']))
    if ss.get('cap_needs_Av_min'):
        story.append(Paragraph("WARNING: Minimum shear reinforcement required.", styles['Normal']))

    # Deflection
    story.append(Paragraph("8. Deflection and Camber", styles['Heading2']))
    story.append(Paragraph(f"Initial camber: {ss.get('def_delta_ps_initial',0):.2f} mm", styles['Normal']))
    story.append(Paragraph(f"Self-weight deflection: {ss.get('def_delta_sw',0):.2f} mm", styles['Normal']))
    story.append(Paragraph(f"Net release: {ss.get('def_net_release',0):.2f} mm", styles['Normal']))
    story.append(Paragraph(f"Long-term total: {ss.get('def_total_longterm',0):.2f} mm", styles['Normal']))
    story.append(Paragraph(f"Limits: L/360 = {ss.get('def_limit_ll_mm',0):.1f} mm, L/240 = {ss.get('def_limit_total_mm',0):.1f} mm", styles['Normal']))
    story.append(Paragraph(f"Status: LL {ss.get('def_status_ll','N/A')}, Total {ss.get('def_status_total','N/A')}", styles['Normal']))

    story.append(PageBreak())
    story.append(Paragraph("Appendix A: Remarks", styles['Heading1']))
    story.append(Paragraph("This report was generated automatically by HCS Design App v1.0.", styles['Normal']))
    story.append(Paragraph("All calculations conform to ACI/PCI CODE-319-25 and PCI Design Handbook 8th Edition.", styles['Normal']))
    story.append(Paragraph("Engineer should verify inputs and assumptions before construction.", styles['Normal']))

    doc.build(story)
    output_stream.seek(0)
    return output_stream


def get_report_bytes(ss):
    """
    Returns tuple (word_bytes, pdf_bytes) for download buttons.
    If library missing, returns (None, None).
    """
    word_bytes = None
    pdf_bytes = None
    if HAS_DOCX:
        word_io = generate_word_report(ss)
        if word_io:
            word_bytes = word_io.getvalue()
    if HAS_REPORTLAB:
        pdf_io = generate_pdf_report(ss)
        if pdf_io:
            pdf_bytes = pdf_io.getvalue()
    return word_bytes, pdf_bytes

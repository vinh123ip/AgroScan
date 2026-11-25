"""PDF Inspection Certificate & Excel Summary Export Service (T3.1, T3.2).

Uses ``reportlab`` to generate tamper-evident PDF inspection certificates
(with embedded evidence photographs and 64-character SHA-256 digests) and
``openpyxl`` to generate multi-sheet Excel workbooks for order KPIs,
session history, and evidence hashes.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Optional, Sequence, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agroscan.models.inspection_models import (
    InspectionRecord,
    OrderSummary,
)
from agroscan.services.app_settings import AppSettings, ConnectionSettings
from agroscan.services.evidence_service import resolve_evidence_path
from agroscan.ui.formatting import final_result_text, fmt_datetime, fmt_percent

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXPORTS_DIR = REPO_ROOT / "exports"

_FONT_REGISTERED = False
_BODY_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"


def _ensure_unicode_font() -> tuple[str, str]:
    """Register a Unicode TTF font (Arial or bundled Inter) so Vietnamese renders cleanly."""
    global _FONT_REGISTERED, _BODY_FONT, _BOLD_FONT
    if _FONT_REGISTERED:
        return _BODY_FONT, _BOLD_FONT

    candidates = [
        (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
        (
            REPO_ROOT / "src" / "agroscan" / "ui" / "resources" / "fonts" / "Inter-Variable.ttf",
            REPO_ROOT / "src" / "agroscan" / "ui" / "resources" / "fonts" / "Inter-Variable.ttf",
        ),
    ]
    for regular_path, bold_path in candidates:
        if regular_path.is_file():
            try:
                pdfmetrics.registerFont(TTFont("AgroSans", str(regular_path)))
                if bold_path.is_file():
                    pdfmetrics.registerFont(TTFont("AgroSans-Bold", str(bold_path)))
                else:
                    pdfmetrics.registerFont(TTFont("AgroSans-Bold", str(regular_path)))
                _BODY_FONT = "AgroSans"
                _BOLD_FONT = "AgroSans-Bold"
                break
            except Exception:
                continue

    _FONT_REGISTERED = True
    return _BODY_FONT, _BOLD_FONT


def _styles() -> dict[str, ParagraphStyle]:
    body_font, bold_font = _ensure_unicode_font()
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AgroTitle",
            parent=sample["Heading1"],
            fontName=bold_font,
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "AgroSubtitle",
            parent=sample["Normal"],
            fontName=body_font,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#475569"),
            spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "AgroSection",
            parent=sample["Heading2"],
            fontName=bold_font,
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "AgroBody",
            parent=sample["Normal"],
            fontName=body_font,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
        ),
        "mono": ParagraphStyle(
            "AgroMono",
            parent=sample["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#334155"),
        ),
    }


def _default_table_style(body_font: str, bold_font: str) -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), bold_font),
            ("FONTSIZE", (0, 0), (-1, 0), 9.5),
            ("FONTNAME", (0, 1), (-1, -1), body_font),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]
    )


def _compute_record_digest(record: InspectionRecord) -> str:
    """Compute a deterministic SHA-256 certificate seal over the inspection record."""
    parts = [
        record.session.session_id,
        record.session.box_code.text,
        record.session.order.order_code,
        record.session.product.code,
        record.assessment.recommendation.value,
        record.review.decision.value if record.review else "PENDING",
        *(ev.sha256 for ev in record.evidence if ev.sha256),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def export_inspection_record_pdf(
    record: InspectionRecord,
    output_path: Optional[Union[Path, str]] = None,
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
) -> Path:
    """Generate a single-session PDF Inspection Certificate (T3.1)."""
    body_font, bold_font = _ensure_unicode_font()
    st = _styles()

    if output_path is None:
        DEFAULT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = record.session.session_id.replace(":", "_")
        target = DEFAULT_EXPORTS_DIR / f"Certificate_{safe_id}.pdf"
    else:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"AgroScan Certificate - {record.session.session_id}",
    )

    story = []
    session = record.session
    order = session.order
    product = session.product
    det = record.detection
    ass = record.assessment
    cert_sha256 = _compute_record_digest(record)

    # 1. Header
    story.append(Paragraph("AGROSCAN — QUALITY INSPECTION CERTIFICATE", st["title"]))
    story.append(
        Paragraph(
            f"Generated: {fmt_datetime(datetime.now())}   |   "
            f"Session ID: {session.session_id}   |   Final Outcome: {final_result_text(record)}",
            st["subtitle"],
        )
    )

    # 2. Order & Session metadata table
    story.append(Paragraph("1. Order & Inspection Session Metadata", st["section"]))
    meta_rows = [
        ["Field", "Value", "Field", "Value"],
        ["Order Code", order.order_code, "Box QR Code", session.box_code.text],
        ["Product", f"{product.name} ({product.code})", "Supplier", order.supplier],
        [
            "Lot Size",
            f"{order.total_boxes} boxes"
            + (f" ({order.expected_quantity} units)" if order.expected_quantity is not None else ""),
            "Station / Inspector",
            f"{session.station} / {session.inspector}",
        ],
        [
            "Started At",
            fmt_datetime(session.started_at),
            "Session Status",
            session.status.value,
        ],
        [
            "AI Recommendation",
            ass.recommendation.value,
            "Reviewer Decision",
            record.review.decision.value if record.review else "Pending Review",
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[35 * mm, 54 * mm, 35 * mm, 54 * mm])
    meta_table.setStyle(_default_table_style(body_font, bold_font))
    story.append(meta_table)

    # 3. YOLO Detection & Defect Criteria Table
    story.append(
        Paragraph(
            f"2. Defect Analysis & Rule Engine Evaluation "
            f"(Objects: {det.total_objects}, Mean Confidence: {fmt_percent(det.mean_confidence)})",
            st["section"],
        )
    )
    criteria_map = {c.defect_class: c for c in product.criteria}
    defect_rows = [["Class", "Count", "Measured Ratio", "Max Allowed", "Critical?", "Evaluation"]]
    for cls in product.detect_classes:
        cnt = det.class_counts.get(cls, 0)
        ratio = det.ratio(cls)
        crit = criteria_map.get(cls)
        if crit is None:
            limit_str, crit_str, status_str = "—", "No", "OK (Normal)"
        else:
            limit_str = fmt_percent(crit.max_ratio)
            crit_str = "YES" if crit.is_critical else "No"
            failed = (crit.is_critical and cnt > 0) or (ratio > crit.max_ratio)
            status_str = "EXCEEDED" if failed else "Within Limit"
        defect_rows.append(
            [cls.capitalize(), str(cnt), fmt_percent(ratio), limit_str, crit_str, status_str]
        )
    det_table = Table(
        defect_rows, colWidths=[30 * mm, 22 * mm, 30 * mm, 30 * mm, 24 * mm, 42 * mm]
    )
    det_table.setStyle(_default_table_style(body_font, bold_font))
    story.append(det_table)
    story.append(Spacer(1, 2 * mm))
    for reason in ass.reasons:
        story.append(Paragraph(f"• {reason}", st["body"]))

    # 4. Qwen-VL Deep Analysis (if performed)
    if record.deep_analysis is not None and not record.deep_analysis.is_error:
        vlm = record.deep_analysis
        story.append(Paragraph(f"3. Qwen-VL Deep Analysis ({vlm.model or 'Qwen-VL'})", st["section"]))
        story.append(Paragraph(f"Assessment: {vlm.assessment}", st["body"]))
        if vlm.suggestion:
            story.append(Paragraph(f"Suggestion: {vlm.suggestion}", st["body"]))
        for obs in vlm.observations:
            story.append(Paragraph(f"  - {obs}", st["body"]))

    # 5. Reviewer Sign-off
    if record.review is not None:
        rev = record.review
        story.append(Paragraph("4. Human Reviewer Sign-Off", st["section"]))
        story.append(
            Paragraph(
                f"Decision: {rev.decision.value}   |   Reviewer: {rev.reviewer}   |   "
                f"Reviewed At: {fmt_datetime(rev.reviewed_at)}",
                st["body"],
            )
        )
        if rev.notes:
            story.append(Paragraph(f"Reviewer Notes: {rev.notes}", st["body"]))

    # 6. Evidence Images & SHA-256 Integrity Hashes
    story.append(Paragraph("5. Evidence Photographs & SHA-256 Integrity Hashes", st["section"]))
    if not record.evidence:
        story.append(Paragraph("No evidence images recorded for this session.", st["body"]))
    else:
        ev_rows = [["#", "Captured At", "Relative Path", "SHA-256 Digest (64 hex chars)"]]
        embedded_flowables = []
        for idx, ev in enumerate(record.evidence, start=1):
            sha_text = ev.sha256 or "(not hashed)"
            ev_rows.append(
                [
                    str(idx),
                    fmt_datetime(ev.captured_at),
                    ev.relative_path or "(in-memory)",
                    sha_text,
                ]
            )
            img_path = resolve_evidence_path(ev, settings=settings)
            if img_path is not None and img_path.is_file():
                try:
                    rl_img = RLImage(str(img_path), width=75 * mm, height=52 * mm, kind="proportional")
                    embedded_flowables.append(rl_img)
                except Exception:
                    pass

        ev_table = Table(ev_rows, colWidths=[10 * mm, 34 * mm, 52 * mm, 82 * mm])
        ev_table.setStyle(_default_table_style(body_font, bold_font))
        story.append(ev_table)

        if embedded_flowables:
            story.append(Spacer(1, 3 * mm))
            # Arrange up to 2 evidence images side by side
            pairs = [embedded_flowables[i : i + 2] for i in range(0, len(embedded_flowables), 2)]
            img_table = Table(pairs, colWidths=[88 * mm, 88 * mm])
            story.append(img_table)

    # 7. Certificate SHA-256 Seal
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            f"Certificate SHA-256 Seal: {cert_sha256}",
            st["mono"],
        )
    )

    doc.build(story)
    return target


def export_summary_report_pdf(
    records: Sequence[InspectionRecord],
    summaries: Sequence[OrderSummary],
    output_path: Optional[Union[Path, str]] = None,
    title: str = "AGROSCAN — INSPECTION SUMMARY & KPI REPORT",
    filter_description: str = "All Products & Dates",
) -> Path:
    """Generate an aggregate PDF report covering order summaries and filtered sessions (T3.1/T3.2)."""
    body_font, bold_font = _ensure_unicode_font()
    st = _styles()

    if output_path is None:
        DEFAULT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        target = DEFAULT_EXPORTS_DIR / f"AgroScan_Report_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    else:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=title,
    )

    story = [
        Paragraph(title, st["title"]),
        Paragraph(
            f"Generated: {fmt_datetime(datetime.now())}   |   Filter: {filter_description}   |   "
            f"Sessions: {len(records)}",
            st["subtitle"],
        ),
    ]

    # Order-level KPI table
    story.append(Paragraph("1. Order-Level Quality Summary (D-022)", st["section"]))
    order_rows = [["Order Code", "Product", "Supplier", "Boxes", "Passed", "Failed", "Pending", "Remaining"]]
    for s in summaries:
        order_rows.append(
            [
                s.order.order_code,
                s.order.product.name,
                s.order.supplier,
                str(s.order.total_boxes),
                str(s.passed),
                str(s.failed),
                str(s.pending),
                str(s.remaining),
            ]
        )
    if len(order_rows) == 1:
        order_rows.append(["—", "No orders matched", "—", "0", "0", "0", "0", "0"])

    order_table = Table(
        order_rows,
        colWidths=[23 * mm, 35 * mm, 42 * mm, 16 * mm, 16 * mm, 16 * mm, 16 * mm, 16 * mm],
    )
    order_table.setStyle(_default_table_style(body_font, bold_font))
    story.append(order_table)

    # Session list table
    story.append(Paragraph("2. Inspection Sessions & Evidence Digest", st["section"]))
    rec_rows = [["Session ID", "Box Code", "Product", "AI Rec.", "Outcome", "Started", "Primary SHA-256"]]
    for r in records:
        first_sha = (r.evidence[0].sha256[:16] + "…") if (r.evidence and r.evidence[0].sha256) else "—"
        rec_rows.append(
            [
                r.session_id,
                r.session.box_code.text,
                r.session.product.code,
                r.assessment.recommendation.value,
                final_result_text(r),
                fmt_datetime(r.session.started_at),
                first_sha,
            ]
        )
    if len(rec_rows) == 1:
        rec_rows.append(["—", "No sessions matched", "—", "—", "—", "—", "—"])

    rec_table = Table(
        rec_rows,
        colWidths=[32 * mm, 32 * mm, 20 * mm, 22 * mm, 24 * mm, 26 * mm, 24 * mm],
    )
    rec_table.setStyle(_default_table_style(body_font, bold_font))
    story.append(rec_table)

    report_digest = hashlib.sha256(
        "|".join(r.session_id for r in records).encode("utf-8")
    ).hexdigest()
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(f"Report Batch SHA-256 Digest: {report_digest}", st["mono"]))

    doc.build(story)
    return target


def export_report_excel(
    records: Sequence[InspectionRecord],
    summaries: Sequence[OrderSummary],
    output_path: Optional[Union[Path, str]] = None,
) -> Path:
    """Export order KPIs, inspection sessions, and evidence SHA-256 hashes to Excel (.xlsx) (T3.2)."""
    if output_path is None:
        DEFAULT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        target = DEFAULT_EXPORTS_DIR / f"AgroScan_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    else:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    body_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    def _style_sheet(ws, headers: list[str], rows: list[list[object]]) -> None:
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left", vertical="center")
            cell.border = thin_border
        for row_data in rows:
            ws.append(row_data)
            r_idx = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=r_idx, column=col_idx)
                c.font = body_font
                c.border = thin_border
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = max(
                len(str(ws.cell(row=r, column=col_idx).value or ""))
                for r in range(1, ws.max_row + 1)
            )
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 52)

    # Sheet 1: Order Summary
    ws_orders = wb.active
    ws_orders.title = "Order Summary"
    order_rows: list[list[object]] = []
    for s in summaries:
        inspected = s.passed + s.failed
        pass_rate = f"{(s.passed / inspected * 100):.1f}%" if inspected > 0 else "0.0%"
        order_rows.append(
            [
                s.order.order_code,
                s.order.product.code,
                s.order.product.name,
                s.order.supplier,
                s.order.total_boxes,
                s.order.expected_quantity,
                s.passed,
                s.failed,
                s.pending,
                s.remaining,
                pass_rate,
                s.text,
            ]
        )
    _style_sheet(
        ws_orders,
        [
            "Order Code",
            "Product Code",
            "Product Name",
            "Supplier",
            "Total Boxes",
            "Expected Qty",
            "Passed",
            "Failed",
            "Pending",
            "Remaining",
            "Pass Rate",
            "Summary Text",
        ],
        order_rows,
    )

    # Sheet 2: Inspection Sessions
    ws_sessions = wb.create_sheet("Inspection Sessions")
    session_rows: list[list[object]] = []
    for r in records:
        primary_sha = r.evidence[0].sha256 if r.evidence else ""
        session_rows.append(
            [
                r.session_id,
                r.session.box_code.text,
                r.session.order.order_code,
                r.session.product.code,
                r.session.product.name,
                r.session.order.supplier,
                r.session.inspector,
                r.session.station,
                r.status.value,
                fmt_datetime(r.session.started_at),
                r.detection.total_objects,
                round(r.detection.mean_confidence, 3),
                r.assessment.recommendation.value,
                final_result_text(r),
                r.review.reviewer if r.review else "",
                r.review.notes if r.review else "",
                len(r.evidence),
                primary_sha,
            ]
        )
    _style_sheet(
        ws_sessions,
        [
            "Session ID",
            "Box Code",
            "Order Code",
            "Product Code",
            "Product Name",
            "Supplier",
            "Inspector",
            "Station",
            "Status",
            "Started At",
            "Objects Detected",
            "Mean Confidence",
            "AI Recommendation",
            "Final Outcome",
            "Reviewer",
            "Review Notes",
            "Evidence Count",
            "Primary SHA-256",
        ],
        session_rows,
    )

    # Sheet 3: Evidence Integrity
    ws_ev = wb.create_sheet("Evidence Integrity")
    ev_rows: list[list[object]] = []
    for r in records:
        for idx, ev in enumerate(r.evidence, start=1):
            ev_rows.append(
                [
                    r.session_id,
                    r.session.box_code.text,
                    idx,
                    fmt_datetime(ev.captured_at),
                    "Yes" if ev.is_auto_capture else "No",
                    ev.relative_path,
                    ev.sha256,
                ]
            )
    _style_sheet(
        ws_ev,
        [
            "Session ID",
            "Box Code",
            "Sequence",
            "Captured At",
            "Auto Capture",
            "Relative Path",
            "SHA-256 Hash",
        ],
        ev_rows,
    )

    wb.save(str(target))
    return target


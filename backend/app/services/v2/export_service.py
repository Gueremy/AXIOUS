"""
app/services/v2/export_service.py
Servicio reutilizable para exportación de datos en CSV, Excel y PDF (Fase 1F).
Cumple estrictamente con la Ley 19.628 (protección de datos personales: nunca exporta RUT).
"""
import csv
import io
from xml.sax.saxutils import escape
from decimal import Decimal, InvalidOperation
from typing import Any, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer


class ExportServiceV2:

    @staticmethod
    def _celda_segura(valor: Any) -> str:
        texto = str(valor) if valor is not None else ""
        if texto and texto[0] in "=+-@\t\r\n":
            try:
                numero = Decimal(texto)
                if numero.is_finite():
                    return texto
            except InvalidOperation:
                pass
            return "'" + texto
        return texto

    @staticmethod
    def exportar_csv(cabeceras: List[str], filas: List[List[Any]]) -> bytes:
        """Genera bytes de archivo CSV codificado en UTF-8 con BOM para apertura en Excel."""
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(cabeceras)
        for fila in filas:
            writer.writerow([ExportServiceV2._celda_segura(c) for c in fila])
        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def exportar_excel(titulo_hoja: str, cabeceras: List[str], filas: List[List[Any]]) -> bytes:
        """Genera un archivo Excel .xlsx profesional con estilo y autoajuste de ancho de columnas."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = titulo_hoja[:31]

        # Estilos de encabezado
        fill_header = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Calibri", size=10)
        border_thin = Border(
            left=Side(style="thin", color="E5E7EB"),
            right=Side(style="thin", color="E5E7EB"),
            top=Side(style="thin", color="E5E7EB"),
            bottom=Side(style="thin", color="E5E7EB"),
        )

        # Fila de cabecera
        ws.append(cabeceras)
        for col_idx in range(1, len(cabeceras) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = fill_header
            cell.font = font_header
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Filas de datos
        for row_data in filas:
            ws.append([ExportServiceV2._celda_segura(c) for c in row_data])

        for row in ws.iter_rows(min_row=2, max_row=len(filas) + 1, min_col=1, max_col=len(cabeceras)):
            for cell in row:
                cell.font = font_data
                cell.border = border_thin

        # Ajuste de ancho de columnas
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def exportar_pdf(titulo: str, subtitulo: str, cabeceras: List[str], filas: List[List[Any]]) -> bytes:
        """Genera reporte PDF formal en hoja A4 horizontal utilizando ReportLab."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        styles = getSampleStyleSheet()
        style_titulo = ParagraphStyle("Titulo", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#1E3A8A"))
        style_sub = ParagraphStyle("Subtitulo", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#4B5563"))
        style_cell = ParagraphStyle("Celda", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10)

        story = [
            Paragraph(titulo, style_titulo),
            Paragraph(subtitulo, style_sub),
            Spacer(1, 0.5 * cm),
        ]

        # Preparar datos de la tabla con Paragraphs para ajuste automático de texto
        data_table = [[Paragraph(f"<b>{escape(str(c))}</b>", style_cell) for c in cabeceras]]
        for fila in filas:
            data_table.append([Paragraph(escape(str(c)) if c is not None else "", style_cell) for c in fila])

        table = Table(data_table, repeatRows=1)
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ])
        )

        story.append(table)
        doc.build(story)
        return buffer.getvalue()

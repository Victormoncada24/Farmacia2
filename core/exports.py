"""Exportación de reportes a Excel (openpyxl) y PDF (reportlab)."""
from datetime import date, datetime
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone


def _limpiar(valor):
    if valor is None:
        return ''
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    return valor


def respuesta_excel(titulo, encabezados, filas, nombre_archivo, subtitulo=''):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    hoja = libro.active
    hoja.title = ''.join(c for c in titulo if c not in '[]:*?/\\')[:31] or 'Reporte'
    hoja.append([titulo])
    hoja['A1'].font = Font(bold=True, size=14)
    hoja.append([subtitulo or f'Generado el {timezone.localtime():%d/%m/%Y %H:%M}'])
    hoja.append([])
    hoja.append(list(encabezados))
    fila_encabezado = 4
    for celda in hoja[fila_encabezado]:
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = PatternFill('solid', fgColor='C8102E')
        celda.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    anchos = [len(str(e)) for e in encabezados]
    for fila in filas:
        limpia = [_limpiar(v) for v in fila]
        hoja.append(limpia)
        for i, v in enumerate(limpia):
            anchos[i] = max(anchos[i], min(len(str(v)), 60))
    for i, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho + 3
    hoja.freeze_panes = hoja.cell(row=fila_encabezado + 1, column=1)
    memoria = BytesIO()
    libro.save(memoria)
    respuesta = HttpResponse(
        memoria.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.xlsx"'
    return respuesta


def respuesta_pdf(titulo, encabezados, filas, nombre_archivo, subtitulo=''):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    memoria = BytesIO()
    documento = SimpleDocTemplate(
        memoria, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm, title=titulo,
    )
    estilos = getSampleStyleSheet()
    celda = ParagraphStyle('celda', parent=estilos['Normal'], fontSize=7.5, leading=9)
    celda_enc = ParagraphStyle('celda_enc', parent=celda, textColor=colors.white, fontName='Helvetica-Bold')

    def texto(valor):
        valor = str(_limpiar(valor))
        return valor.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    elementos = [
        Paragraph(f'<b>{texto(titulo)}</b>', estilos['Title']),
        Paragraph(texto(subtitulo or f'Generado el {timezone.localtime():%d/%m/%Y %H:%M}'), estilos['Normal']),
        Spacer(1, 0.4 * cm),
    ]
    filas = list(filas)
    if not filas:
        elementos.append(Paragraph('Sin registros para los filtros seleccionados.', estilos['Normal']))
    else:
        datos = [[Paragraph(texto(e), celda_enc) for e in encabezados]]
        for fila in filas:
            datos.append([Paragraph(texto(v), celda) for v in fila])
        ancho_util = landscape(A4)[0] - 2.4 * cm
        tabla = Table(datos, colWidths=[ancho_util / len(encabezados)] * len(encabezados), repeatRows=1)
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C8102E')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F3F3')]),
        ]))
        elementos.append(tabla)
    documento.build(elementos)
    respuesta = HttpResponse(memoria.getvalue(), content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.pdf"'
    return respuesta

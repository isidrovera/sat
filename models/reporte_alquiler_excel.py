# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import xlwt
import base64
from io import BytesIO
import logging
import re

_logger = logging.getLogger(__name__)


class ReporteEstadoMaquinaExcelExporter(models.TransientModel):
    _name = 'reporte.estado.maquina.excel.exporter'
    _description = 'Exportador Excel para Reporte Estado Máquinas'

    name = fields.Char(
        string='Nombre del Archivo',
        default='Estado_Maq.xls'
    )

    excel_file = fields.Binary(
        string='Archivo Excel'
    )

    filename = fields.Char(
        string='Nombre de Archivo'
    )

    state = fields.Selection([
        ('init', 'Inicial'),
        ('done', 'Completado')
    ], default='init')

    # ==========================================================
    # GENERADOR PRINCIPAL
    # ==========================================================

    def generar_excel(self, reportes_ids):
        """
        Genera un Excel de una sola hoja.

        Gerencia requiere ver todo en una única hoja:
        - Datos de máquina.
        - Estado.
        - Contadores.
        - Último ticket.
        - Informe técnico.
        - Componentes evaluados.
        - Accesorios evaluados.
        - Intervenciones / subpartes.
        - Partes retiradas para otras máquinas o reparaciones SAT.

        No se crean hojas adicionales.
        """
        if not reportes_ids:
            raise UserError(_('No hay reportes para exportar.'))

        reportes = self.env['reporte.estado.maquina'].browse(reportes_ids).exists()

        if not reportes:
            raise UserError(_('No se encontraron reportes válidos para exportar.'))

        workbook = xlwt.Workbook(encoding='utf-8')

        self._crear_hoja_unica(workbook, reportes)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        excel_data = base64.b64encode(output.read())

        fecha_actual = fields.Date.context_today(self).strftime('%Y%m%d')
        filename = f'Estado_Maq_{fecha_actual}.xls'

        self.write({
            'excel_file': excel_data,
            'filename': filename,
            'name': filename,
            'state': 'done',
        })

        _logger.info(
            "[ReporteEstadoMaquinaExcelExporter] Excel generado en una hoja | filename=%s | reportes=%s",
            filename,
            len(reportes),
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Descargar Excel',
            'res_model': 'reporte.estado.maquina.excel.exporter',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'},
        }

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _get_selection_label(self, record, field_name):
        """
        Devuelve la etiqueta legible de un campo selection.
        """
        if not record or field_name not in record._fields:
            return ''

        value = getattr(record, field_name, False)

        if not value:
            return ''

        field = record._fields[field_name]

        if field.type == 'selection':
            selection = field.selection
            if callable(selection):
                selection = selection(record)
            return dict(selection).get(value, value)

        return str(value or '')

    def _html_to_text(self, html):
        """
        Convierte HTML simple a texto plano para Excel.
        """
        if not html:
            return ''

        text = str(html)

        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
        text = re.sub(r'</p>', '\n', text, flags=re.I)
        text = re.sub(r'</div>', '\n', text, flags=re.I)
        text = re.sub(r'</li>', '\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>', '• ', text, flags=re.I)
        text = re.sub(r'<[^>]+>', '', text)

        text = (
            text.replace('&nbsp;', ' ')
                .replace('&amp;', '&')
                .replace('&lt;', '<')
                .replace('&gt;', '>')
        )

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return '\n'.join(lines)

    def _fecha_txt(self, value):
        """
        Devuelve fecha como texto dd/mm/yyyy para mantener una lectura simple.
        """
        if not value:
            return ''

        try:
            return value.strftime('%d/%m/%Y')
        except Exception:
            return str(value)

    def _datetime_txt(self, value):
        """
        Devuelve fecha/hora como texto dd/mm/yyyy hh:mm.
        """
        if not value:
            return ''

        try:
            return value.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return str(value)

    def _crear_estilos(self):
        """
        Estilos reutilizables.
        """
        return {
            'title': xlwt.easyxf(
                'font: bold 1, height 360;'
                'align: horiz center, vert center;'
                'pattern: pattern solid, fore_colour gray25;'
                'borders: all thin'
            ),
            'header': xlwt.easyxf(
                'font: bold 1;'
                'align: horiz center, vert center, wrap 1;'
                'pattern: pattern solid, fore_colour gray25;'
                'borders: all thin'
            ),
            'data': xlwt.easyxf(
                'borders: all thin;'
                'align: vert top'
            ),
            'wrap': xlwt.easyxf(
                'borders: all thin;'
                'align: vert top, wrap 1'
            ),
            'number': xlwt.easyxf(
                'borders: all thin;'
                'align: horiz right, vert top',
                num_format_str='#,##0'
            ),
            'estado_ok': xlwt.easyxf(
                'borders: all thin;'
                'align: vert top;'
                'pattern: pattern solid, fore_colour light_green'
            ),
            'estado_warn': xlwt.easyxf(
                'borders: all thin;'
                'align: vert top;'
                'pattern: pattern solid, fore_colour light_yellow'
            ),
            'estado_bad': xlwt.easyxf(
                'borders: all thin;'
                'align: vert top;'
                'pattern: pattern solid, fore_colour rose'
            ),
        }

    def _estado_style(self, estado, styles):
        """
        Estilo simple según estado de máquina.
        """
        if estado in ('lista', 'revisada', 'alquilada'):
            return styles['estado_ok']

        if estado in ('sin_revisar', 'con_problemas'):
            return styles['estado_warn']

        if estado in ('partes',):
            return styles['estado_bad']

        return styles['data']

    def _build_partes_detalle_texto(self, reporte):
        """
        Devuelve las partes retiradas como texto detallado para una sola celda.

        Se separa por origen:
        - Bodega / Alquiler: partes retiradas para otras máquinas de alquiler.
        - Reparación / SAT: partes retiradas para reparaciones SAT.

        Todo queda en una sola celda, porque gerencia quiere una sola hoja.
        """
        partes = reporte.partes_retiradas_ids

        if not partes:
            return ''

        lineas_bodega = []
        lineas_sat = []

        partes_ordenadas = partes.sorted(
            key=lambda p: (
                p.fecha_solicitud or fields.Date.context_today(self),
                p.solicitud_partes_id.name if p.solicitud_partes_id else '',
                p.nombre_parte or '',
            )
        )

        for parte in partes_ordenadas:
            fecha = self._fecha_txt(parte.fecha_solicitud)
            estado = self._get_selection_label(parte, 'estado_parte') or parte.estado_parte or ''
            condicion = self._get_selection_label(parte, 'condicion') or parte.condicion or ''
            destino = parte.maquina_destino or ''
            solicitud = parte.solicitud_partes_id.name if parte.solicitud_partes_id else ''
            descripcion = parte.descripcion or ''

            linea = ""

            if fecha:
                linea += f"{fecha} | "

            if solicitud:
                linea += f"{solicitud} | "

            linea += parte.nombre_parte or ''

            if estado:
                linea += f" | {estado}"

            if condicion:
                linea += f" | Condición: {condicion}"

            if destino:
                linea += f" | Destino: {destino}"

            if descripcion:
                linea += f" | Obs: {descripcion}"

            if parte.solicitud_partes_id:
                lineas_bodega.append(linea)
            else:
                lineas_sat.append(linea)

        bloques = []

        if lineas_bodega:
            bloques.append(
                "PARTES RETIRADAS PARA OTRAS MÁQUINAS:\n" +
                "\n".join([f"• {l}" for l in lineas_bodega])
            )

        if lineas_sat:
            bloques.append(
                "PARTES RETIRADAS PARA REPARACIÓN / SAT:\n" +
                "\n".join([f"• {l}" for l in lineas_sat])
            )

        return "\n\n".join(bloques)

    def _set_widths(self, worksheet):
        """
        Ajusta anchos de columnas de la hoja única.
        """
        widths = [
            2800,   # Fecha
            4000,   # Serie
            5200,   # Modelo
            3500,   # Marca
            3000,   # Tipo
            3500,   # Estado
            3500,   # Ubicación
            3000,   # Cont B/N
            3000,   # Cont Color
            3000,   # Cont Total
            3000,   # Cont Scanner
            3500,   # Último Ticket
            4200,   # Fecha Ticket
            4000,   # Tipo Servicio
            4500,   # Técnico
            5200,   # Cliente Anterior
            4200,   # Fecha Retiro
            9000,   # Informe
            10000,  # Componentes
            10000,  # Accesorios
            10000,  # Intervenciones
            12000,  # Partes retiradas
        ]

        for col, width in enumerate(widths):
            worksheet.col(col).width = width

    # ==========================================================
    # HOJA ÚNICA
    # ==========================================================

    def _crear_hoja_unica(self, workbook, reportes):
        """
        Crea una sola hoja con todo el detalle por equipo.

        No crea hojas adicionales porque gerencia requiere revisar todo
        en una sola vista.
        """
        worksheet = workbook.add_sheet('Estado')
        styles = self._crear_estilos()

        headers = [
            'Fecha',
            'Serie',
            'Modelo',
            'Marca',
            'Tipo',
            'Estado',
            'Ubicación',
            'Cont. B/N',
            'Cont. Color',
            'Cont. Total',
            'Cont. Scanner',
            'Último Ticket',
            'Fecha Ticket',
            'Tipo Servicio',
            'Técnico',
            'Cliente Anterior',
            'Fecha Último Retiro',
            'Informe Técnico',
            'Componentes Evaluados',
            'Accesorios Evaluados',
            'Intervenciones / Subpartes',
            'Partes Retiradas',
        ]

        worksheet.write_merge(
            0, 0, 0, len(headers) - 1,
            'REPORTE DE ESTADO DE MÁQUINAS',
            styles['title']
        )

        worksheet.write_merge(
            1, 1, 0, len(headers) - 1,
            f'Generado: {fields.Date.context_today(self).strftime("%d/%m/%Y")}',
            styles['data']
        )

        header_row = 3

        for col, header in enumerate(headers):
            worksheet.write(header_row, col, header, styles['header'])

        row = header_row + 1

        reportes_ordenados = reportes.sorted(
            key=lambda r: (
                r.estado_maquina or '',
                r.serie or '',
            )
        )

        for reporte in reportes_ordenados:
            tipo_maquina = self._get_selection_label(reporte, 'tipo_maquina')
            estado_maquina = self._get_selection_label(reporte, 'estado_maquina')
            ubicacion = self._get_selection_label(reporte, 'ubicacion_fisica')

            informe_txt = self._html_to_text(reporte.informe_tecnico or '')
            componentes_txt = self._html_to_text(reporte.componentes_resumen or '')
            accesorios_txt = self._html_to_text(reporte.accesorios_resumen or '')
            intervenciones_txt = self._html_to_text(reporte.intervenciones_resumen or '')
            partes_txt = self._build_partes_detalle_texto(reporte)

            estado_style = self._estado_style(reporte.estado_maquina, styles)

            col = 0

            worksheet.write(row, col, self._fecha_txt(reporte.fecha_generacion), styles['data'])
            col += 1

            worksheet.write(row, col, reporte.serie or '', styles['data'])
            col += 1

            worksheet.write(row, col, reporte.modelo or '', styles['data'])
            col += 1

            worksheet.write(row, col, reporte.marca or '', styles['data'])
            col += 1

            worksheet.write(row, col, tipo_maquina, styles['data'])
            col += 1

            worksheet.write(row, col, estado_maquina, estado_style)
            col += 1

            worksheet.write(row, col, ubicacion, styles['data'])
            col += 1

            worksheet.write(row, col, reporte.contador_bn or 0, styles['number'])
            col += 1

            worksheet.write(row, col, reporte.contador_color or 0, styles['number'])
            col += 1

            worksheet.write(row, col, reporte.contador_total or 0, styles['number'])
            col += 1

            worksheet.write(row, col, reporte.contador_scanner or 0, styles['number'])
            col += 1

            worksheet.write(
                row,
                col,
                reporte.ultimo_ticket_id.name if reporte.ultimo_ticket_id else '',
                styles['data']
            )
            col += 1

            worksheet.write(row, col, self._datetime_txt(reporte.ultimo_ticket_fecha), styles['data'])
            col += 1

            worksheet.write(row, col, reporte.ultimo_ticket_tipo or '', styles['data'])
            col += 1

            worksheet.write(row, col, reporte.tecnico_responsable or '', styles['data'])
            col += 1

            worksheet.write(
                row,
                col,
                reporte.cliente_anterior_id.name if reporte.cliente_anterior_id else '',
                styles['data']
            )
            col += 1

            worksheet.write(row, col, self._fecha_txt(reporte.fecha_ultimo_retiro), styles['data'])
            col += 1

            worksheet.write(row, col, informe_txt, styles['wrap'])
            col += 1

            worksheet.write(row, col, componentes_txt, styles['wrap'])
            col += 1

            worksheet.write(row, col, accesorios_txt, styles['wrap'])
            col += 1

            worksheet.write(row, col, intervenciones_txt, styles['wrap'])
            col += 1

            worksheet.write(row, col, partes_txt, styles['wrap'])
            col += 1

            max_lines = max(
                1,
                len(informe_txt.splitlines()) if informe_txt else 1,
                len(componentes_txt.splitlines()) if componentes_txt else 1,
                len(accesorios_txt.splitlines()) if accesorios_txt else 1,
                len(intervenciones_txt.splitlines()) if intervenciones_txt else 1,
                len(partes_txt.splitlines()) if partes_txt else 1,
            )

            worksheet.row(row).height = max(400, min(max_lines * 320, 7000))

            row += 1

        self._set_widths(worksheet)

        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(header_row + 1)
        worksheet.set_vert_split_pos(4)

        _logger.info(
            "[ReporteEstadoMaquinaExcelExporter] Hoja única creada | filas=%s",
            row - header_row - 1,
        )

    # ==========================================================
    # DESCARGA
    # ==========================================================

    def action_download_excel(self):
        """
        Acción para descargar el archivo Excel.
        """
        self.ensure_one()

        if not self.excel_file:
            raise UserError(_('No hay archivo Excel generado para descargar.'))

        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/reporte.estado.maquina.excel.exporter/'
                f'{self.id}/excel_file/{self.filename}?download=true'
            ),
            'target': 'self',
        }
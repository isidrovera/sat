# -*- coding: utf-8 -*-

import logging
import re
import base64
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import quote

import xlwt

from odoo import models, fields, api, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class ReporteEstadoMaquina(models.Model):
    _name = 'reporte.estado.maquina'
    _description = 'Reporte de Estado de Máquinas'
    _order = 'fecha_generacion desc, estado_maquina, serie'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ==========================================================
    # Campos de identificación del reporte
    # ==========================================================

    fecha_generacion = fields.Date(
        string='Fecha de Generación',
        default=fields.Date.context_today,
        required=True,
        index=True
    )

    semana_reporte = fields.Char(
        string='Semana del Reporte',
        compute='_compute_semana_reporte',
        store=True,
        help='Semana del año en formato YYYY-WXX'
    )

    # ==========================================================
    # Datos básicos de la máquina
    # ==========================================================

    maquina_id = fields.Many2one(
        'alquiler',
        string='Máquina',
        required=True,
        ondelete='cascade'
    )

    serie = fields.Char(
        string='Serie',
        required=True,
        index=True
    )

    modelo = fields.Char(
        string='Modelo',
        required=True
    )

    marca = fields.Char(
        string='Marca',
        required=True
    )

    tipo_maquina = fields.Selection([
        ('color', 'Color'),
        ('monocromatica', 'Monocromática')
    ], string='Tipo de Máquina')

    estado_maquina = fields.Selection([
        ('sin_revisar', 'Sin Revisar'),
        ('revisada', 'Revisada'),
        ('lista', 'Lista'),
        ('alquilada', 'Alquilada'),
        ('con_problemas', 'Con Problemas'),
        ('partes', 'De Partes'),
        ('externo', 'Externo'),
        ('vendida', 'Vendida')
    ], string='Estado de Máquina', required=True, index=True)

    ubicacion_fisica = fields.Selection([
        ('primer_piso', 'Primer Piso'),
        ('tercer_piso', 'Tercer Piso'),
        ('segundo_local', 'Segundo Local'),
        ('covida', 'Covida')
    ], string='Ubicación Física')

    # ==========================================================
    # Datos del último ticket
    # ==========================================================

    ultimo_ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Último Ticket',
        help='Último ticket finalizado registrado para esta máquina'
    )

    ultimo_ticket_fecha = fields.Datetime(
        string='Fecha Último Ticket'
    )

    ultimo_ticket_tipo = fields.Char(
        string='Tipo de Servicio'
    )

    tecnico_responsable = fields.Char(
        string='Técnico Responsable'
    )

    informe_tecnico = fields.Html(
        string='Informe Técnico'
    )

    componentes_resumen = fields.Html(
        string='Resumen Componentes',
        help='Resumen dinámico de componentes evaluados en el último ticket.'
    )

    accesorios_resumen = fields.Html(
        string='Resumen Accesorios',
        help='Resumen dinámico de accesorios evaluados en el último ticket.'
    )

    intervenciones_resumen = fields.Html(
        string='Intervenciones / Subpartes',
        help='Resumen de componentes/accesorios intervenidos y sus subpartes.'
    )

    # ==========================================================
    # Contómetros
    # ==========================================================

    contador_bn = fields.Integer(
        string='Contador B/N',
        default=0
    )

    contador_color = fields.Integer(
        string='Contador Color',
        default=0
    )

    contador_total = fields.Integer(
        string='Contador Total (B/N + Color)',
        compute='_compute_contador_total',
        store=True
    )

    contador_scanner = fields.Integer(
        string='Contador Scanner',
        default=0
    )

    # ==========================================================
    # Cliente anterior
    # ==========================================================

    cliente_anterior_id = fields.Many2one(
        'res.partner',
        string='Cliente Anterior',
        help='Último cliente donde estuvo alquilada la máquina'
    )

    direccion_anterior = fields.Text(
        string='Dirección Anterior'
    )

    fecha_ultimo_retiro = fields.Date(
        string='Fecha Último Retiro'
    )

    # ==========================================================
    # Partes retiradas / historial
    # ==========================================================

    partes_retiradas_ids = fields.One2many(
        'reporte.estado.maquina.parte',
        'reporte_id',
        string='Partes Retiradas/Reemplazadas'
    )

    historial_alquileres_ids = fields.One2many(
        'reporte.estado.maquina.alquiler',
        'reporte_id',
        string='Historial de Alquileres'
    )

    display_name = fields.Char(
        string='Nombre del Reporte',
        compute='_compute_display_name',
        store=True
    )

    # ==========================================================
    # Computes
    # ==========================================================

    @api.depends('fecha_generacion')
    def _compute_semana_reporte(self):
        for record in self:
            if record.fecha_generacion:
                anio, semana, _ = record.fecha_generacion.isocalendar()
                record.semana_reporte = f"{anio}-W{semana:02d}"
            else:
                record.semana_reporte = False

    @api.depends('contador_bn', 'contador_color')
    def _compute_contador_total(self):
        for record in self:
            record.contador_total = (record.contador_bn or 0) + (record.contador_color or 0)

    @api.depends('serie', 'modelo', 'estado_maquina', 'fecha_generacion')
    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"{record.serie or ''} - {record.modelo or ''} "
                f"({record.estado_maquina or ''}) - {record.fecha_generacion or ''}"
            )

    # ==========================================================
    # Generación principal
    # ==========================================================

    @api.model
    def generar_reporte_semanal(self):
        """
        Genera el reporte semanal de estado de máquinas.
        """
        _logger.info("[ReporteEstadoMaquina] Iniciando generación de reporte semanal")

        fecha_reporte = fields.Date.context_today(self)

        reportes_existentes = self.search([
            ('fecha_generacion', '=', fecha_reporte)
        ])

        if reportes_existentes:
            cantidad = len(reportes_existentes)
            reportes_existentes.unlink()
            _logger.info(
                "[ReporteEstadoMaquina] Eliminados %s reportes existentes de fecha %s",
                cantidad,
                fecha_reporte
            )

        estados_incluir = [
            'sin_revisar',
            'revisada',
            'lista',
            'con_problemas',
            'partes'
        ]

        maquinas = self.env['alquiler'].search([
            ('estado_alquiler_id', 'in', estados_incluir)
        ])

        reportes_creados = 0

        for maquina in maquinas:
            try:
                self._crear_reporte_maquina(maquina, fecha_reporte)
                reportes_creados += 1
            except Exception as e:
                _logger.exception(
                    "[ReporteEstadoMaquina] Error creando reporte para máquina %s: %s",
                    getattr(maquina, 'serie', ''),
                    str(e)
                )
                continue

        _logger.info(
            "[ReporteEstadoMaquina] Reporte semanal generado. Máquinas procesadas: %s",
            reportes_creados
        )

        self._generar_pdf_reporte(fecha_reporte)

        return True

    def _crear_reporte_maquina(self, maquina, fecha_reporte):
        """
        Crea un registro de reporte para una máquina específica.
        """
        ultimo_ticket = self.env['ticket.alquiler'].search([
            ('product_alquiler', '=', maquina.id),
            ('estado', '=', 'finalizado')
        ], order='agenda desc, id desc', limit=1)

        cliente_anterior = self._obtener_cliente_anterior(maquina)

        valores_reporte = {
            'fecha_generacion': fecha_reporte,
            'maquina_id': maquina.id,
            'serie': maquina.serie or '',
            'modelo': maquina.name.name if maquina.name else '',
            'marca': maquina.marca or '',
            'tipo_maquina': maquina.tipo_maquina_id,
            'estado_maquina': maquina.estado_alquiler_id,
            'ubicacion_fisica': maquina.ubicacion_id,
        }

        if cliente_anterior:
            valores_reporte.update({
                'cliente_anterior_id': cliente_anterior.get('cliente_id'),
                'direccion_anterior': cliente_anterior.get('direccion'),
                'fecha_ultimo_retiro': cliente_anterior.get('fecha_retiro'),
            })

        if ultimo_ticket:
            valores_reporte.update(self._extraer_datos_ticket(ultimo_ticket))

        reporte = self.create(valores_reporte)

        self._crear_historial_alquileres(reporte, maquina)
        self._crear_registro_partes_retiradas(reporte, maquina)

        return reporte

    def _obtener_cliente_anterior(self, maquina):
        """
        Obtiene información del último cliente donde estuvo alquilada la máquina.
        """
        ticket_retiro = self.env['ticket.alquiler'].search([
            ('product_alquiler', '=', maquina.id),
            ('tipo_servicio_id', '=', 'retiro'),
            ('estado', '=', 'finalizado')
        ], order='agenda desc, id desc', limit=1)

        if ticket_retiro:
            return {
                'cliente_id': ticket_retiro.partner_id.id if ticket_retiro.partner_id else False,
                'direccion': ticket_retiro.direccion_id_r,
                'fecha_retiro': ticket_retiro.agenda.date() if ticket_retiro.agenda else False,
            }

        return False

    # ==========================================================
    # Extracción del último ticket
    # ==========================================================

    def _extraer_datos_ticket(self, ticket):
        """
        Extrae datos relevantes del último ticket finalizado.

        Ya no lee campos antiguos fijos como:
        - tray4_estado
        - bypass_estado
        - finalizador_estado
        - toner_black_nivel
        - transformador
        - estabilizador

        Ahora usa únicamente:
        - ticket_componente_eval_ids
        - ticket_accesorio_eval_ids
        - ticket_intervencion_ids
        """
        contador_bn = self._limpiar_contador(ticket.contometrok_id)
        contador_color = self._limpiar_contador(ticket.contometroc_id)
        contador_scanner = self._limpiar_contador(ticket.contometros_id)

        return {
            'ultimo_ticket_id': ticket.id,
            'ultimo_ticket_fecha': ticket.agenda,
            'ultimo_ticket_tipo': self._get_tipo_servicio_label(ticket),
            'tecnico_responsable': ticket.responsable.name if ticket.responsable else '',
            'informe_tecnico': ticket.informe_id,
            'contador_bn': contador_bn,
            'contador_color': contador_color,
            'contador_scanner': contador_scanner,
            'componentes_resumen': self._build_componentes_resumen_html(ticket),
            'accesorios_resumen': self._build_accesorios_resumen_html(ticket),
            'intervenciones_resumen': self._build_intervenciones_resumen_html(ticket),
        }

    def _get_tipo_servicio_label(self, ticket):
        """
        Devuelve la etiqueta legible del tipo de servicio.
        Soporta Selection y Many2one por seguridad.
        """
        field = ticket._fields.get('tipo_servicio_id')

        if not field:
            return ''

        value = ticket.tipo_servicio_id

        if field.type == 'selection':
            return dict(field.selection).get(value, value or '')

        if field.type == 'many2one':
            return value.display_name if value else ''

        return str(value or '')

    def _html_escape(self, value):
        """
        Escape básico para evitar HTML roto en los resúmenes.
        """
        if value is None:
            return ''

        value = str(value)

        return (
            value.replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;')
        )

    def _build_componentes_resumen_html(self, ticket):
        """
        Construye resumen HTML de componentes evaluados.

        Fuente:
            ticket.ticket_componente_eval_ids
        """
        evaluaciones = ticket.ticket_componente_eval_ids

        if not evaluaciones:
            return '<p><em>Sin evaluación de componentes registrada.</em></p>'

        rows = []

        for ev in evaluaciones:
            componente = ev.componente_tipo_id.name if ev.componente_tipo_id else 'Sin componente'
            color = ev.color_id.name if ev.color_id else ''
            estado = ev.estado_id.name if ev.estado_id else 'Sin estado'
            observaciones = ev.observaciones or ''

            nombre = componente

            if color:
                nombre = "%s (%s)" % (nombre, color)

            rows.append(
                "<li><strong>%s:</strong> %s%s</li>" % (
                    self._html_escape(nombre),
                    self._html_escape(estado),
                    (
                        "<br/><span>%s</span>" % self._html_escape(observaciones)
                        if observaciones else ""
                    )
                )
            )

        return "<ul>%s</ul>" % "".join(rows)

    def _build_accesorios_resumen_html(self, ticket):
        """
        Construye resumen HTML de accesorios evaluados.

        Fuente:
            ticket.ticket_accesorio_eval_ids
        """
        evaluaciones = ticket.ticket_accesorio_eval_ids

        if not evaluaciones:
            return '<p><em>Sin evaluación de accesorios registrada.</em></p>'

        rows = []

        for ev in evaluaciones:
            accesorio = ev.tipo_id.name if ev.tipo_id else 'Sin accesorio'
            estado = ev.estado_id.name if ev.estado_id else 'Sin estado'
            observaciones = ev.observaciones or ''

            rows.append(
                "<li><strong>%s:</strong> %s%s</li>" % (
                    self._html_escape(accesorio),
                    self._html_escape(estado),
                    (
                        "<br/><span>%s</span>" % self._html_escape(observaciones)
                        if observaciones else ""
                    )
                )
            )

        return "<ul>%s</ul>" % "".join(rows)

    def _build_intervenciones_resumen_html(self, ticket):
        """
        Construye resumen HTML de intervenciones y subpartes.

        Fuente:
            ticket.ticket_intervencion_ids
        """
        intervenciones = ticket.ticket_intervencion_ids

        if not intervenciones:
            return '<p><em>Sin intervenciones registradas.</em></p>'

        bloques = []

        for intervencion in intervenciones:
            nombre = (
                intervencion.componente_display
                or intervencion.componente_code
                or 'Intervención'
            )

            if not intervencion.detalle_ids:
                bloques.append(
                    "<li><strong>%s:</strong> Sin subpartes seleccionadas.</li>" %
                    self._html_escape(nombre)
                )
                continue

            subpartes = []

            for det in intervencion.detalle_ids:
                subparte = det.subparte_id.name if det.subparte_id else 'Sin subparte'
                cantidad = det.cantidad or 0
                observacion = det.observacion or ''

                texto = "%s x %s" % (
                    self._html_escape(subparte),
                    cantidad
                )

                if observacion:
                    texto += " - %s" % self._html_escape(observacion)

                subpartes.append("<li>%s</li>" % texto)

            bloques.append(
                "<li><strong>%s</strong><ul>%s</ul></li>" % (
                    self._html_escape(nombre),
                    "".join(subpartes)
                )
            )

        return "<ul>%s</ul>" % "".join(bloques)

    def _limpiar_contador(self, contador_str):
        """
        Limpia y convierte el valor del contador a entero.
        """
        if not contador_str:
            return 0

        try:
            cleaned = str(contador_str).replace(',', '').replace(' ', '')
            return int(float(cleaned))
        except (ValueError, TypeError):
            return 0

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

    # ==========================================================
    # Historial de alquileres
    # ==========================================================

    def _crear_historial_alquileres(self, reporte, maquina):
        """
        Crea registros del historial de alquileres para la máquina.
        """
        tickets_instalacion = self.env['ticket.alquiler'].search([
            ('product_alquiler', '=', maquina.id),
            ('tipo_servicio_id', '=', 'instalacion'),
            ('estado', '=', 'finalizado')
        ], order='agenda asc, id asc')

        for ticket in tickets_instalacion:
            if not ticket.partner_id:
                _logger.warning(
                    "[ReporteEstadoMaquina][Historial] Ticket=%s sin cliente, se omite historial.",
                    ticket.name
                )
                continue

            ticket_retiro = self.env['ticket.alquiler'].search([
                ('product_alquiler', '=', maquina.id),
                ('tipo_servicio_id', '=', 'retiro'),
                ('estado', '=', 'finalizado'),
                ('agenda', '>', ticket.agenda)
            ], order='agenda asc, id asc', limit=1)

            self.env['reporte.estado.maquina.alquiler'].create({
                'reporte_id': reporte.id,
                'cliente_id': ticket.partner_id.id,
                'direccion': ticket.direccion_id_r,
                'fecha_instalacion': ticket.agenda.date() if ticket.agenda else False,
                'fecha_retiro': (
                    ticket_retiro.agenda.date()
                    if ticket_retiro and ticket_retiro.agenda else False
                ),
                'contador_bn_instalacion': self._limpiar_contador(ticket.contometrok_id),
                'contador_color_instalacion': self._limpiar_contador(ticket.contometroc_id),
                'contador_bn_retiro': (
                    self._limpiar_contador(ticket_retiro.contometrok_id)
                    if ticket_retiro else 0
                ),
                'contador_color_retiro': (
                    self._limpiar_contador(ticket_retiro.contometroc_id)
                    if ticket_retiro else 0
                ),
            })

    # ==========================================================
    # Partes retiradas
    # ==========================================================

    def _crear_registro_partes_retiradas(self, reporte, maquina):
        """
        Crea registros de partes retiradas para el reporte de una máquina de alquiler.

        Fuentes:
        1) solicitud.partes.linea
           - Flujo alquiler -> alquiler.
           - Toma líneas reales retiradas o reemplazadas.

        2) solicitud.parte.tecnico.linea
           - Flujo reparación / SAT.
           - Toma líneas entregadas cuyo origen fue una máquina de alquiler.
        """
        CONDICION_MAP = {
            'bueno': 'bueno',
            'regular': 'regular',
            'malo': 'malo',
            'defectuoso': 'malo',
        }

        # ==========================================================
        # FUENTE 1: solicitud.partes.linea
        # ==========================================================
        lineas_partes = self.env['solicitud.partes.linea'].search([
            ('maquina_origen_id', '=', maquina.id),
            ('estado', 'in', ['retirado', 'reemplazado']),
        ])

        _logger.info(
            "[ReporteEstadoMaquina][Partes] Máquina=%s Serie=%s | líneas solicitud.partes.linea encontradas=%s",
            maquina.id,
            maquina.serie,
            len(lineas_partes),
        )

        for linea in lineas_partes:
            solicitud = linea.solicitud_id

            fecha_solicitud = (
                solicitud.fecha_solicitud.date()
                if solicitud and solicitud.fecha_solicitud
                else fields.Date.context_today(self)
            )

            maquina_destino = ''

            if solicitud and solicitud.maquina_destino_id:
                maquina_destino = solicitud.maquina_destino_id.serie or ''

            self.env['reporte.estado.maquina.parte'].create({
                'reporte_id': reporte.id,
                'solicitud_partes_id': solicitud.id if solicitud else False,
                'nombre_parte': linea.parte,
                'descripcion': linea.descripcion,
                'estado_parte': linea.estado,
                'condicion': CONDICION_MAP.get(linea.condicion or '', False),
                'fecha_solicitud': fecha_solicitud,
                'maquina_destino': maquina_destino,
            })

            _logger.info(
                "[ReporteEstadoMaquina][Partes] Agregada línea alquiler->alquiler | reporte=%s solicitud=%s parte=%s estado=%s destino=%s",
                reporte.id,
                solicitud.name if solicitud else '',
                linea.parte,
                linea.estado,
                maquina_destino,
            )

        # ==========================================================
        # FUENTE 2: solicitud.parte.tecnico.linea
        # ==========================================================
        lineas_tecnico = self.env['solicitud.parte.tecnico.linea'].search([
            ('tipo_origen', '=', 'alquiler'),
            ('maquina_origen_alquiler_id', '=', maquina.id),
            ('state', '=', 'entregada'),
        ])

        _logger.info(
            "[ReporteEstadoMaquina][PartesSAT] Máquina=%s Serie=%s | líneas solicitud.parte.tecnico.linea encontradas=%s",
            maquina.id,
            maquina.serie,
            len(lineas_tecnico),
        )

        for linea in lineas_tecnico:
            solicitud = linea.solicitud_id

            fecha_solicitud = (
                solicitud.fecha_solicitud.date()
                if solicitud and solicitud.fecha_solicitud
                else fields.Date.context_today(self)
            )

            maquina_destino_serie = ''

            if solicitud and solicitud.maquina_id:
                maquina_destino_serie = (
                    getattr(solicitud.maquina_id, 'serie_id', False)
                    or getattr(solicitud.maquina_id, 'serie', False)
                    or ''
                )

            descripcion = linea.descripcion or ''

            if solicitud and solicitud.reparacion_id:
                reparacion_name = solicitud.reparacion_id.name or ''
                if reparacion_name:
                    descripcion = (
                        "%s\nReparación: %s" % (descripcion, reparacion_name)
                    ).strip()

            self.env['reporte.estado.maquina.parte'].create({
                'reporte_id': reporte.id,
                'solicitud_partes_id': False,
                'nombre_parte': linea.parte,
                'descripcion': descripcion,
                'estado_parte': 'retirado',
                'condicion': False,
                'fecha_solicitud': fecha_solicitud,
                'maquina_destino': str(maquina_destino_serie),
            })

            _logger.info(
                "[ReporteEstadoMaquina][PartesSAT] Agregada línea alquiler->SAT | reporte=%s solicitud=%s parte=%s destino=%s",
                reporte.id,
                solicitud.name if solicitud else '',
                linea.parte,
                maquina_destino_serie,
            )

    # ==========================================================
    # PDF / limpieza
    # ==========================================================

    def _generar_pdf_reporte(self, fecha_reporte):
        """
        Genera el PDF del reporte semanal.
        """
        reportes = self.search([
            ('fecha_generacion', '=', fecha_reporte)
        ])

        _logger.info(
            "[ReporteEstadoMaquina] Generando PDF para %s máquinas del reporte %s",
            len(reportes),
            fecha_reporte
        )

        return True

    @api.model
    def limpiar_reportes_antiguos(self, dias_conservar=90):
        """
        Limpia reportes antiguos para no sobrecargar la base de datos.
        """
        fecha_limite = fields.Date.context_today(self) - timedelta(days=dias_conservar)

        reportes_antiguos = self.search([
            ('fecha_generacion', '<', fecha_limite)
        ])

        if reportes_antiguos:
            cantidad = len(reportes_antiguos)
            reportes_antiguos.unlink()

            _logger.info(
                "[ReporteEstadoMaquina] Eliminados %s reportes anteriores a %s",
                cantidad,
                fecha_limite
            )

        return True

    # ==========================================================
    # Excel - Una sola hoja para gerencia
    # ==========================================================

    def _exportar_excel(self, reportes):
        """
        Exporta el reporte en una sola hoja.

        Correcciones:
        - No usa self.fecha_desde ni self.fecha_hasta.
        - Las fechas vienen por contexto desde reporte.estado.maquina.wizard.
        - Se genera una sola hoja llamada Estado.
        - Se muestran componentes/accesorios/intervenciones dinámicas.
        - Se muestran partes retiradas detalladas en la misma fila.
        """
        reportes = reportes.exists()

        if not reportes:
            raise UserError(_('No hay reportes válidos para exportar.'))

        workbook = xlwt.Workbook(encoding='utf-8')

        self._crear_hoja_estado_unica(workbook, reportes)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        excel_data = base64.b64encode(output.read()).decode('utf-8')

        fecha_hasta = self.env.context.get('reporte_fecha_hasta')

        if not fecha_hasta:
            fechas = reportes.mapped('fecha_generacion')
            fecha_hasta = max(fechas) if fechas else fields.Date.context_today(self)

        fecha_hasta_date = fields.Date.to_date(fecha_hasta)
        safe_filename = f"Estado_Maq_{fecha_hasta_date.strftime('%Y%m%d')}.xls"
        quoted_filename = quote(safe_filename)

        attachment = self.env['ir.attachment'].create({
            'name': safe_filename,
            'type': 'binary',
            'datas': excel_data,
            'mimetype': 'application/octet-stream',
            'res_model': self._name,
            'res_id': reportes[:1].id if reportes else False,
        })

        token = getattr(attachment, 'access_token', False)

        if not token:
            if hasattr(attachment, 'generate_access_token'):
                attachment.generate_access_token()
                token = attachment.access_token

        if not token:
            token = uuid.uuid4().hex
            attachment.write({'access_token': token})

        url = f"/web/content/{attachment.id}/{quoted_filename}?download=1&access_token={token}"

        _logger.info(
            "[ReporteEstadoMaquina] Excel generado una sola hoja -> id=%s name=%s url=%s reportes=%s",
            attachment.id,
            safe_filename,
            url,
            len(reportes),
        )

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    def _excel_selection_label(self, record, field_name):
        """
        Devuelve etiqueta legible de un campo selection.
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

    def _excel_html_to_text(self, html):
        """
        Convierte HTML simple a texto plano para Excel.
        """
        return self._html_to_text(html)

    def _excel_clip_text(self, value, limit=30000):
        """
        Evita errores por textos demasiado largos en una celda XLS.
        """
        if not value:
            return ''

        value = str(value)

        if len(value) > limit:
            return value[:limit - 3] + '...'

        return value

    def _excel_fecha_txt(self, value):
        """
        Devuelve fecha como texto dd/mm/yyyy.
        """
        if not value:
            return ''

        try:
            return value.strftime('%d/%m/%Y')
        except Exception:
            return str(value)

    def _excel_datetime_txt(self, value):
        """
        Devuelve fecha/hora como texto dd/mm/yyyy hh:mm.
        """
        if not value:
            return ''

        try:
            return value.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return str(value)

    def _excel_crear_estilos(self):
        """
        Estilos simples para una sola hoja.

        IMPORTANTE:
        xlwt no soporta:
            borders: all thin

        Debe usarse:
            borders: left thin, right thin, top thin, bottom thin
        """
        border = 'borders: left thin, right thin, top thin, bottom thin;'

        return {
            'title': xlwt.easyxf(
                'font: bold 1, height 360;'
                'align: horiz center, vert center;'
                + border
            ),
            'subtitle': xlwt.easyxf(
                'font: bold 1;'
                'align: horiz left, vert center;'
                + border
            ),
            'header': xlwt.easyxf(
                'font: bold 1;'
                'align: horiz center, vert center, wrap 1;'
                + border
            ),
            'data': xlwt.easyxf(
                'align: vert top;'
                + border
            ),
            'wrap': xlwt.easyxf(
                'align: vert top, wrap 1;'
                + border
            ),
            'number': xlwt.easyxf(
                'align: horiz right, vert top;'
                + border,
                num_format_str='#,##0'
            ),
        }

    def _excel_build_partes_detalle_texto(self, reporte):
        """
        Devuelve las partes retiradas como texto detallado en una sola celda.

        Se separa por:
        - Partes retiradas para otras máquinas.
        - Partes retiradas para reparación / SAT.
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
            fecha = self._excel_fecha_txt(parte.fecha_solicitud)
            estado = self._excel_selection_label(parte, 'estado_parte') or parte.estado_parte or ''
            condicion = self._excel_selection_label(parte, 'condicion') or parte.condicion or ''
            destino = parte.maquina_destino or ''
            solicitud = parte.solicitud_partes_id.name if parte.solicitud_partes_id else ''
            descripcion = parte.descripcion or ''

            linea = ''

            if fecha:
                linea += f"{fecha} | "

            if solicitud:
                linea += f"{solicitud} | "

            linea += parte.nombre_parte or ''

            if estado:
                linea += f" | Estado: {estado}"

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
                "\n".join([f"• {linea}" for linea in lineas_bodega])
            )

        if lineas_sat:
            bloques.append(
                "PARTES RETIRADAS PARA REPARACIÓN / SAT:\n" +
                "\n".join([f"• {linea}" for linea in lineas_sat])
            )

        return "\n\n".join(bloques)

    def _crear_hoja_estado_unica(self, workbook, reportes):
        """
        Crea una sola hoja para gerencia.

        Cada fila representa una máquina y contiene todo el detalle.
        """
        worksheet = workbook.add_sheet('Estado')
        styles = self._excel_crear_estilos()

        headers = [
            'Fecha Reporte',
            'Serie',
            'Modelo',
            'Marca',
            'Tipo',
            'Estado',
            'Ubicación',
            'Contador B/N',
            'Contador Color',
            'Contador Total',
            'Contador Scanner',
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
            0,
            0,
            0,
            len(headers) - 1,
            'REPORTE DE ESTADO DE MÁQUINAS',
            styles['title']
        )

        fecha_desde = self.env.context.get('reporte_fecha_desde')
        fecha_hasta = self.env.context.get('reporte_fecha_hasta')

        fecha_desde_txt = self._excel_fecha_txt(fields.Date.to_date(fecha_desde)) if fecha_desde else ''
        fecha_hasta_txt = self._excel_fecha_txt(fields.Date.to_date(fecha_hasta)) if fecha_hasta else ''

        if fecha_desde_txt or fecha_hasta_txt:
            rango_txt = f"Rango: {fecha_desde_txt} - {fecha_hasta_txt}"
        else:
            rango_txt = f"Generado: {self._excel_fecha_txt(fields.Date.context_today(self))}"

        worksheet.write_merge(
            1,
            1,
            0,
            len(headers) - 1,
            rango_txt,
            styles['subtitle']
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
            tipo_maquina = self._excel_selection_label(reporte, 'tipo_maquina')
            estado_maquina = self._excel_selection_label(reporte, 'estado_maquina')
            ubicacion = self._excel_selection_label(reporte, 'ubicacion_fisica')

            informe_txt = self._excel_html_to_text(reporte.informe_tecnico or '')
            componentes_txt = self._excel_html_to_text(reporte.componentes_resumen or '')
            accesorios_txt = self._excel_html_to_text(reporte.accesorios_resumen or '')
            intervenciones_txt = self._excel_html_to_text(reporte.intervenciones_resumen or '')
            partes_txt = self._excel_build_partes_detalle_texto(reporte)

            informe_txt = self._excel_clip_text(informe_txt)
            componentes_txt = self._excel_clip_text(componentes_txt)
            accesorios_txt = self._excel_clip_text(accesorios_txt)
            intervenciones_txt = self._excel_clip_text(intervenciones_txt)
            partes_txt = self._excel_clip_text(partes_txt)

            col = 0

            worksheet.write(row, col, self._excel_fecha_txt(reporte.fecha_generacion), styles['data'])
            col += 1

            worksheet.write(row, col, reporte.serie or '', styles['data'])
            col += 1

            worksheet.write(row, col, reporte.modelo or '', styles['data'])
            col += 1

            worksheet.write(row, col, reporte.marca or '', styles['data'])
            col += 1

            worksheet.write(row, col, tipo_maquina, styles['data'])
            col += 1

            worksheet.write(row, col, estado_maquina, styles['data'])
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

            worksheet.write(row, col, self._excel_datetime_txt(reporte.ultimo_ticket_fecha), styles['data'])
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

            worksheet.write(row, col, self._excel_fecha_txt(reporte.fecha_ultimo_retiro), styles['data'])
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

        widths = [
            2800,
            4000,
            5200,
            3500,
            3000,
            3500,
            3500,
            3000,
            3000,
            3000,
            3000,
            3500,
            4200,
            4000,
            4500,
            5200,
            4200,
            9000,
            10000,
            10000,
            10000,
            12000,
        ]

        for col, width in enumerate(widths):
            worksheet.col(col).width = width

        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(header_row + 1)
        worksheet.set_vert_split_pos(4)

        _logger.info(
            "[ReporteEstadoMaquina] Hoja única Excel creada | filas=%s",
            row - header_row - 1,
        )


class ReporteEstadoMaquinaParte(models.Model):
    _name = 'reporte.estado.maquina.parte'
    _description = 'Partes Retiradas/Reemplazadas en Reporte de Máquinas'
    _order = 'fecha_solicitud desc'

    reporte_id = fields.Many2one(
        'reporte.estado.maquina',
        string='Reporte',
        required=True,
        ondelete='cascade'
    )

    solicitud_partes_id = fields.Many2one(
        'solicitud.partes',
        string='Solicitud de Partes',
        required=False
    )

    nombre_parte = fields.Char(
        string='Nombre de la Parte',
        required=True
    )

    descripcion = fields.Text(
        string='Descripción'
    )

    estado_parte = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('retirado', 'Retirado'),
        ('reemplazado', 'Reemplazado')
    ], string='Estado de la Parte')

    condicion = fields.Selection([
        ('bueno', 'Bueno'),
        ('regular', 'Regular'),
        ('malo', 'Malo')
    ], string='Condición')

    fecha_solicitud = fields.Date(
        string='Fecha de Solicitud',
        required=True
    )

    maquina_destino = fields.Char(
        string='Máquina Destino (Serie)'
    )


class ReporteEstadoMaquinaAlquiler(models.Model):
    _name = 'reporte.estado.maquina.alquiler'
    _description = 'Historial de Alquileres en Reporte de Máquinas'
    _order = 'fecha_instalacion desc'

    reporte_id = fields.Many2one(
        'reporte.estado.maquina',
        string='Reporte',
        required=True,
        ondelete='cascade'
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True
    )

    direccion = fields.Text(
        string='Dirección'
    )

    fecha_instalacion = fields.Date(
        string='Fecha de Instalación'
    )

    fecha_retiro = fields.Date(
        string='Fecha de Retiro'
    )

    contador_bn_instalacion = fields.Integer(
        string='Contador B/N Instalación',
        default=0
    )

    contador_color_instalacion = fields.Integer(
        string='Contador Color Instalación',
        default=0
    )

    contador_bn_retiro = fields.Integer(
        string='Contador B/N Retiro',
        default=0
    )

    contador_color_retiro = fields.Integer(
        string='Contador Color Retiro',
        default=0
    )

    copias_bn_periodo = fields.Integer(
        string='Copias B/N en el Período',
        compute='_compute_copias_periodo',
        store=True
    )

    copias_color_periodo = fields.Integer(
        string='Copias Color en el Período',
        compute='_compute_copias_periodo',
        store=True
    )

    copias_total_periodo = fields.Integer(
        string='Total Copias en el Período',
        compute='_compute_copias_periodo',
        store=True
    )

    dias_alquiler = fields.Integer(
        string='Días de Alquiler',
        compute='_compute_dias_alquiler',
        store=True
    )

    @api.depends(
        'contador_bn_instalacion',
        'contador_color_instalacion',
        'contador_bn_retiro',
        'contador_color_retiro'
    )
    def _compute_copias_periodo(self):
        for record in self:
            record.copias_bn_periodo = max(
                0,
                record.contador_bn_retiro - record.contador_bn_instalacion
            )

            record.copias_color_periodo = max(
                0,
                record.contador_color_retiro - record.contador_color_instalacion
            )

            record.copias_total_periodo = (
                record.copias_bn_periodo + record.copias_color_periodo
            )

    @api.depends('fecha_instalacion', 'fecha_retiro')
    def _compute_dias_alquiler(self):
        for record in self:
            if record.fecha_instalacion and record.fecha_retiro:
                delta = record.fecha_retiro - record.fecha_instalacion
                record.dias_alquiler = delta.days
            else:
                record.dias_alquiler = 0


class ReporteEstadoMaquinaWizard(models.TransientModel):
    _name = 'reporte.estado.maquina.wizard'
    _description = 'Wizard para Generar Reporte de Estado de Máquinas'

    fecha_desde = fields.Date(
        string='Fecha Desde',
        default=lambda self: fields.Date.context_today(self) - timedelta(days=30)
    )

    fecha_hasta = fields.Date(
        string='Fecha Hasta',
        default=fields.Date.context_today
    )

    estados_maquina = fields.Selection([
        ('todos', 'Todos los Estados Relevantes'),
        ('sin_revisar', 'Solo Sin Revisar'),
        ('revisada', 'Solo Revisadas'),
        ('lista', 'Solo Listas'),
        ('con_problemas', 'Solo Con Problemas'),
        ('partes', 'Solo De Partes'),
        ('personalizado', 'Selección Personalizada')
    ], string='Estados a Incluir', default='todos', required=True)

    estados_personalizados = fields.Selection([
        ('sin_revisar', 'Sin Revisar'),
        ('revisada', 'Revisada'),
        ('lista', 'Lista'),
        ('con_problemas', 'Con Problemas'),
        ('partes', 'De Partes'),
        ('alquilada', 'Alquilada'),
        ('externo', 'Externo'),
        ('vendida', 'Vendida')
    ], string='Estado Personalizado',
        help='Seleccionar estado específico cuando se elige "Selección Personalizada"'
    )

    incluir_historial = fields.Boolean(
        string='Incluir Historial de Alquileres',
        default=True
    )

    incluir_partes = fields.Boolean(
        string='Incluir Información de Partes',
        default=True
    )

    formato_salida = fields.Selection([
        ('pantalla', 'Ver en Pantalla'),
        ('pdf', 'Generar PDF'),
        ('excel', 'Exportar a Excel')
    ], string='Formato de Salida', default='pantalla', required=True)

    def action_generar_reporte(self):
        """
        Acción para generar el reporte según los filtros seleccionados.
        """
        self.ensure_one()

        domain = [
            ('fecha_generacion', '>=', self.fecha_desde),
            ('fecha_generacion', '<=', self.fecha_hasta),
        ]

        if self.estados_maquina != 'todos':
            if self.estados_maquina == 'personalizado':
                if self.estados_personalizados:
                    domain.append(('estado_maquina', '=', self.estados_personalizados))
                else:
                    raise UserError(_(
                        'Debe seleccionar un estado cuando elige "Selección Personalizada".'
                    ))
            else:
                domain.append(('estado_maquina', '=', self.estados_maquina))
        else:
            domain.append((
                'estado_maquina',
                'in',
                ['sin_revisar', 'revisada', 'lista', 'con_problemas', 'partes']
            ))

        reportes = self.env['reporte.estado.maquina'].search(
            domain,
            order='estado_maquina, serie'
        )

        if not reportes:
            raise UserError(_('No se encontraron datos para los filtros seleccionados.'))

        if self.formato_salida == 'pantalla':
            return self._mostrar_en_pantalla(reportes)

        if self.formato_salida == 'pdf':
            return self._generar_pdf(reportes)

        if self.formato_salida == 'excel':
            return self._exportar_excel(reportes)

        return False

    def _mostrar_en_pantalla(self, reportes):
        """
        Muestra los reportes en una vista de lista/formulario.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reporte de Estado de Máquinas',
            'res_model': 'reporte.estado.maquina',
            'view_mode': 'list,form',
            'view_type': 'form',
            'domain': [('id', 'in', reportes.ids)],
            'context': {
                'group_by': ['estado_maquina'],
            },
            'target': 'current',
        }

    def _generar_pdf(self, reportes):
        """
        Genera un PDF con el reporte.
        """
        try:
            report_ref = self.env.ref('sat.action_reporte_estado_maquinas_pdf')
            return report_ref.report_action(reportes)
        except ValueError:
            raise UserError(_(
                'El reporte PDF no está configurado. '
                'Por favor, configure el reporte PDF en el módulo.'
            ))

    def _exportar_excel(self, reportes):
        """
        Exporta el Excel pasando el rango de fechas del wizard por contexto.
        """
        self.ensure_one()

        return self.env['reporte.estado.maquina'].with_context(
            reporte_fecha_desde=self.fecha_desde,
            reporte_fecha_hasta=self.fecha_hasta,
        )._exportar_excel(reportes)

    def action_generar_reporte_ahora(self):
        """
        Genera el reporte semanal inmediatamente.
        """
        self.ensure_one()

        try:
            self.env['reporte.estado.maquina'].generar_reporte_semanal()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reporte Generado'),
                    'message': _('El reporte semanal se ha generado exitosamente.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.exception(
                "[ReporteEstadoMaquinaWizard] Error al generar reporte semanal: %s",
                str(e)
            )
            raise UserError(_('Error al generar el reporte: %s') % str(e))

    @api.onchange('estados_maquina')
    def _onchange_estados_maquina(self):
        """
        Limpia el estado personalizado cuando cambia la selección principal.
        """
        if self.estados_maquina != 'personalizado':
            self.estados_personalizados = False


class ReporteGestionPartesTecnico(models.Model):
    _name = 'reporte.gestion.partes.tecnico'
    _description = 'Reporte Gestión de Partes Técnicos'
    _order = 'fecha desc'

    fecha = fields.Datetime(
        string="Fecha"
    )

    solicitud_id = fields.Many2one(
        'solicitud.parte.tecnico',
        string="Solicitud"
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string="Técnico"
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string="Máquina"
    )

    parte = fields.Char(
        string="Parte"
    )

    estado = fields.Selection([
        ('buscando', 'Buscando'),
        ('encontrada', 'Encontrada'),
        ('por_conseguir', 'Por Conseguir'),
        ('en_stock_logistica', 'En Stock Logística'),
        ('compra_externa', 'Compra Externa'),
        ('entregada', 'Entregada'),
    ], string="Estado")

    origen = fields.Char(
        string="Origen"
    )

    @api.model
    def generar_reporte_partes_tecnicos(self):
        """
        Genera reporte auxiliar de gestión de partes técnicos.

        Este método pertenece a este modelo para no borrar registros de
        reporte.estado.maquina por error.
        """
        self.search([]).unlink()

        lineas = self.env['solicitud.parte.tecnico.linea'].search([])

        for linea in lineas:
            solicitud = linea.solicitud_id
            origen = ''

            if hasattr(linea, '_get_origen_display'):
                origen = linea._get_origen_display()

            self.create({
                'fecha': solicitud.fecha_solicitud if solicitud else False,
                'solicitud_id': solicitud.id if solicitud else False,
                'tecnico_id': solicitud.tecnico_id.id if solicitud and solicitud.tecnico_id else False,
                'maquina_id': solicitud.maquina_id.id if solicitud and solicitud.maquina_id else False,
                'parte': linea.parte,
                'estado': linea.state,
                'origen': origen,
            })

        return True
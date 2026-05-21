# -*- coding: utf-8 -*-

import logging
import re
import base64
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from unicodedata import normalize
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
        help='Último ticket de servicio registrado para esta máquina'
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
    # Campos antiguos de accesorios
    # Se mantienen para compatibilidad con reportes existentes.
    # ==========================================================

    transformador = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Transformador')

    estabilizador = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Estabilizador')

    adf_simple = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='ADF Simple')

    adf_dual = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='ADF Dual Scan')

    finalizador_interno = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Finalizador Interno')

    finalizador_externo = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Finalizador Externo')

    mueble = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Mueble')

    panel_smart = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Panel Smart')

    panel_normal = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Panel Normal')

    wifi = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Wi-Fi')

    bluetooth = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Bluetooth')

    cable_usb = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Cable USB de Impresión')

    cable_red = fields.Selection([
        ('si', 'Sí lo tiene'),
        ('no', 'No lo tiene'),
        ('no_aplica', 'No aplica')
    ], string='Cable de Red')

    numero_caseteras = fields.Char(
        string='Número de Caseteras'
    )

    # ==========================================================
    # Check List - Funciones antiguas
    # ==========================================================

    copia_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Función Copia')

    impresion_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Función Impresión')

    impresion_usb_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Impresión USB')

    scanner_smb_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner SMB')

    scanner_usb_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner USB')

    scanner_ftp_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner FTP')

    scanner_mail_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('no_aplica', 'No Aplica')
    ], string='Scanner Mail')

    # ==========================================================
    # Check List - Componentes antiguos
    # ==========================================================

    adf_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado ADF')

    tray1_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 1')

    tray2_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 2')

    tray3_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 3')

    tray4_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tray 4')

    bypass_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Bypass')

    finalizador_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Finalizador')

    # ==========================================================
    # Check List - Partes Críticas antiguas
    # ==========================================================

    tacho_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Tacho Residual')

    fusora_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Fusora')

    transfer_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Faja Transfer')

    optico_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Óptica')

    unidad_imagen_black_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Black')

    unidad_imagen_magenta_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Magenta')

    unidad_imagen_cyan_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Cyan')

    unidad_imagen_yellow_estado = fields.Selection([
        ('si', 'Funciona Correctamente'),
        ('no', 'No Funciona'),
        ('desgaste', 'Con Desgaste'),
        ('cambio', 'Requiere Cambio'),
        ('no_aplica', 'No Aplica')
    ], string='Estado Unidad Imagen Yellow')

    # ==========================================================
    # Toners antiguos
    # ==========================================================

    toner_black_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Black')

    toner_magenta_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Magenta')

    toner_cyan_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Cyan')

    toner_yellow_nivel = fields.Selection([
        ('lleno', 'Lleno'),
        ('medio', 'Medio'),
        ('vacio', 'Vacío'),
        ('sin_botella', 'Sin Botella'),
        ('no_aplica', 'No Aplica')
    ], string='Nivel Toner Yellow')

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
                f"{record.serie} - {record.modelo} "
                f"({record.estado_maquina}) - {record.fecha_generacion}"
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
            'serie': maquina.serie,
            'modelo': maquina.name.name if maquina.name else '',
            'marca': maquina.marca,
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
        Extrae todos los datos relevantes del último ticket.

        Mejora aplicada:
        - Mantiene datos generales, contómetros e informe técnico.
        - Mantiene compatibilidad con campos antiguos.
        - Agrega resumen de componentes, accesorios e intervenciones dinámicas.
        """
        contador_bn = self._limpiar_contador(ticket.contometrok_id)
        contador_color = self._limpiar_contador(ticket.contometroc_id)
        contador_scanner = self._limpiar_contador(ticket.contometros_id)

        datos = {
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

        datos.update(self._extraer_campos_antiguos_ticket(ticket))

        return datos

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

    def _extraer_campos_antiguos_ticket(self, ticket):
        """
        Mantiene compatibilidad con campos antiguos del ticket.
        Usa getattr() para no romper si algún campo ya no existe.
        """
        def val(field_name, default=False):
            return getattr(ticket, field_name, default)

        return {
            # Accesorios antiguos
            'transformador': val('transformador_id'),
            'estabilizador': val('estabilizador'),
            'adf_simple': val('adf_simple_id'),
            'adf_dual': val('adf_dual_id'),
            'finalizador_interno': val('finalizador_interno_id'),
            'finalizador_externo': val('finalizador_externo_id'),
            'mueble': val('mueble_id'),
            'panel_smart': val('panel_smart_id'),
            'panel_normal': val('panel_normal_id'),
            'wifi': val('wi_fi_id'),
            'bluetooth': val('bluetooth_id'),
            'cable_usb': val('cable_usb_id'),
            'cable_red': val('cable_red_id'),
            'numero_caseteras': val('tray_id'),

            # Check List - Funciones antiguas
            'copia_estado': val('copia_id'),
            'impresion_estado': val('impresion_id'),
            'impresion_usb_estado': val('impresion_usb_id'),
            'scanner_smb_estado': val('scaner_smb_id'),
            'scanner_usb_estado': val('scaner_usb_id'),
            'scanner_ftp_estado': val('scaner_ftp_id'),
            'scanner_mail_estado': val('scaner_mail_id'),

            # Check List - Componentes antiguos
            'adf_estado': val('adf_id'),
            'tray1_estado': val('tray1_id'),
            'tray2_estado': val('tray2_id'),
            'tray3_estado': val('tray3_id'),
            'tray4_estado': val('tray4_id'),
            'bypass_estado': val('bypass_id'),
            'finalizador_estado': val('finalizador_id'),

            # Partes Críticas antiguas
            'tacho_estado': val('tacho_id'),
            'fusora_estado': val('fusora_id'),
            'transfer_estado': val('transfer_id'),
            'optico_estado': val('optico_id'),
            'unidad_imagen_black_estado': val('black_id'),
            'unidad_imagen_magenta_estado': val('magenta_id'),
            'unidad_imagen_cyan_estado': val('cyan_id'),
            'unidad_imagen_yellow_estado': val('yellow_id'),

            # Toners antiguos
            'toner_black_nivel': val('toner_black_id'),
            'toner_magenta_nivel': val('toner_magenta_id'),
            'toner_cyan_nivel': val('toner_cyan_id'),
            'toner_yellow_nivel': val('toner_yellow_id'),
        }

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
            ticket_retiro = self.env['ticket.alquiler'].search([
                ('product_alquiler', '=', maquina.id),
                ('tipo_servicio_id', '=', 'retiro'),
                ('estado', '=', 'finalizado'),
                ('agenda', '>', ticket.agenda)
            ], order='agenda asc, id asc', limit=1)

            self.env['reporte.estado.maquina.alquiler'].create({
                'reporte_id': reporte.id,
                'cliente_id': ticket.partner_id.id if ticket.partner_id else False,
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
    # Se mantiene la lógica existente porque está funcionando.
    # ==========================================================

    def _crear_registro_partes_retiradas(self, reporte, maquina):
        """
        Crea registros de partes retiradas para el reporte de una máquina de alquiler.

        IMPORTANTE:
        No se debe depender solo del estado de la cabecera de solicitud.partes,
        porque una solicitud puede tener algunas líneas pendientes y otras ya
        retiradas/reemplazadas.

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
        # Partes retiradas desde una máquina de alquiler hacia otra
        # máquina de alquiler.
        #
        # Antes se buscaba por cabecera:
        # solicitud.partes state in ['completed', 'replaced']
        #
        # Ahora se busca por línea, porque el retiro real está en:
        # solicitud.partes.linea.estado
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
        # Partes retiradas desde una máquina de alquiler para una
        # reparación/SAT.
        #
        # Solo debe entrar cuando:
        # - tipo_origen = alquiler
        # - maquina_origen_alquiler_id = máquina del reporte
        # - state = entregada
        #
        # No se incluye en_stock_logistica porque eso representa stock
        # de logística, no retiro desde la máquina de alquiler.
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
    # Excel
    # ==========================================================

    def _setup_palette(self, workbook):
        """
        Define colores personalizados para xlwt.
        """
        xlwt.add_palette_colour("dark_header", 0x21)
        workbook.set_colour_RGB(0x21, 47, 79, 79)

        xlwt.add_palette_colour("light_header", 0x22)
        workbook.set_colour_RGB(0x22, 240, 248, 255)

        xlwt.add_palette_colour("lista_color", 0x23)
        workbook.set_colour_RGB(0x23, 212, 237, 218)

        xlwt.add_palette_colour("revisada_color", 0x24)
        workbook.set_colour_RGB(0x24, 217, 237, 247)

        xlwt.add_palette_colour("sin_revisar_color", 0x25)
        workbook.set_colour_RGB(0x25, 248, 249, 250)

        xlwt.add_palette_colour("con_problemas_color", 0x26)
        workbook.set_colour_RGB(0x26, 255, 243, 205)

        xlwt.add_palette_colour("partes_color", 0x27)
        workbook.set_colour_RGB(0x27, 248, 215, 218)

        xlwt.add_palette_colour("alquilada_color", 0x28)
        workbook.set_colour_RGB(0x28, 230, 247, 255)

    def _exportar_excel(self, reportes):
        def _mes_es(dt):
            return [
                'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
            ][dt.month - 1]

        def _slug_filename(text):
            text = normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
            text = re.sub(r'[^A-Za-z0-9._-]+', '_', text)
            text = re.sub(r'_{2,}', '_', text).strip('_')
            return text

        workbook = xlwt.Workbook(encoding='utf-8')

        self._setup_palette(workbook)
        self._crear_hoja_resumen(workbook, reportes)
        self._crear_hoja_detalle(workbook, reportes)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        excel_data = base64.b64encode(output.read()).decode('utf-8')

        fecha_desde = self.fecha_desde or fields.Date.context_today(self)
        fecha_hasta = self.fecha_hasta or fields.Date.context_today(self)

        mes_texto = _mes_es(fecha_hasta).capitalize()
        anio = fecha_hasta.year

        seq_raw = self.env['ir.sequence'].next_by_code('sat.reporte_estado_excel') or '0001'
        seq_safe = _slug_filename(seq_raw)

        human_name = (
            f"{seq_safe}_Reporte_Estado_Maquinas_"
            f"{mes_texto}-{anio}_{fecha_desde.strftime('%Y%m%d')}_a_{fecha_hasta.strftime('%Y%m%d')}.xls"
        )

        safe_filename = _slug_filename(human_name)
        quoted_filename = quote(safe_filename)

        attachment = self.env['ir.attachment'].create({
            'name': safe_filename,
            'type': 'binary',
            'datas': excel_data,
            'mimetype': 'application/octet-stream',
            'res_model': self._name,
            'res_id': self.id,
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
            "[ReporteEstadoMaquina] Descarga Excel -> id=%s name=%s url=%s",
            attachment.id,
            safe_filename,
            url
        )

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    def _crear_hoja_resumen(self, workbook, reportes):
        """
        Crea dashboard ejecutivo con métricas y KPIs.
        """
        worksheet = workbook.add_sheet('Dashboard Ejecutivo')

        title_style = xlwt.easyxf(
            'pattern: pattern solid, fore_colour dark_header;'
            'font: bold 1, height 500, colour white, name Arial;'
            'align: horiz center, vert center'
        )

        subtitle_style = xlwt.easyxf(
            'font: bold 1, height 320, colour dark_header, name Arial;'
            'align: horiz center, vert center'
        )

        card_header = xlwt.easyxf(
            'pattern: pattern solid, fore_colour light_header;'
            'font: bold 1, height 280, name Arial;'
            'align: horiz center, vert center;'
            'borders: left medium, right medium, top medium, bottom thin'
        )

        card_value = xlwt.easyxf(
            'pattern: pattern solid, fore_colour light_header;'
            'font: bold 1, height 400, colour dark_header, name Arial;'
            'align: horiz center, vert center;'
            'borders: left medium, right medium, top thin, bottom medium',
            num_format_str='#,##0'
        )

        status_excellent = xlwt.easyxf(
            'pattern: pattern solid, fore_colour lista_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        status_good = xlwt.easyxf(
            'pattern: pattern solid, fore_colour revisada_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        status_warning = xlwt.easyxf(
            'pattern: pattern solid, fore_colour con_problemas_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        status_critical = xlwt.easyxf(
            'pattern: pattern solid, fore_colour partes_color;'
            'font: bold 1, height 240, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")

        worksheet.write_merge(
            0, 1, 0, 8,
            'DASHBOARD EJECUTIVO - INVENTARIO DE EQUIPOS',
            title_style
        )
        worksheet.write_merge(
            2, 2, 0, 8,
            f'Actualizado: {fecha_actual}',
            subtitle_style
        )

        worksheet.row(0).height = 800
        worksheet.row(1).height = 400
        worksheet.row(2).height = 400

        total_maquinas = len(reportes)
        estados_data = {}

        for reporte in reportes:
            estado = reporte.estado_maquina

            if estado not in estados_data:
                estados_data[estado] = {
                    'cantidad': 0,
                    'contador_total': 0,
                }

            estados_data[estado]['cantidad'] += 1
            estados_data[estado]['contador_total'] += reporte.contador_total or 0

        row = 4
        worksheet.write_merge(row, row, 0, 8, 'MÉTRICAS CLAVE', subtitle_style)
        row += 2

        equipos_operativos = (
            estados_data.get('lista', {}).get('cantidad', 0) +
            estados_data.get('alquilada', {}).get('cantidad', 0)
        )

        equipos_problema = (
            estados_data.get('con_problemas', {}).get('cantidad', 0) +
            estados_data.get('partes', {}).get('cantidad', 0)
        )

        sin_revisar = estados_data.get('sin_revisar', {}).get('cantidad', 0)

        worksheet.write_merge(row, row, 0, 1, 'TOTAL EQUIPOS', card_header)
        worksheet.write_merge(row + 1, row + 1, 0, 1, total_maquinas, card_value)

        worksheet.write_merge(row, row, 2, 3, 'OPERATIVOS', card_header)
        worksheet.write_merge(row + 1, row + 1, 2, 3, equipos_operativos, card_value)

        worksheet.write_merge(row, row, 4, 5, 'CON PROBLEMAS', card_header)
        worksheet.write_merge(row + 1, row + 1, 4, 5, equipos_problema, card_value)

        worksheet.write_merge(row, row, 6, 7, 'SIN REVISAR', card_header)
        worksheet.write_merge(row + 1, row + 1, 6, 7, sin_revisar, card_value)

        row += 4

        worksheet.write_merge(row, row, 0, 8, 'INDICADOR DE SALUD', subtitle_style)
        row += 2

        pct_operativos = (
            equipos_operativos / total_maquinas * 100
            if total_maquinas > 0 else 0
        )

        if pct_operativos >= 80:
            estado_general = "EXCELENTE"
            semaforo_style = status_excellent
        elif pct_operativos >= 60:
            estado_general = "BUENO"
            semaforo_style = status_good
        elif pct_operativos >= 40:
            estado_general = "REGULAR"
            semaforo_style = status_warning
        else:
            estado_general = "CRÍTICO"
            semaforo_style = status_critical

        worksheet.write_merge(
            row,
            row + 1,
            0,
            8,
            f'{estado_general} ({pct_operativos:.1f}% Operativo)',
            semaforo_style
        )

        worksheet.row(row).height = 600
        worksheet.row(row + 1).height = 400

        row += 3

        worksheet.write_merge(row, row, 0, 8, 'DISTRIBUCIÓN POR ESTADOS', subtitle_style)
        row += 2

        modern_header = xlwt.easyxf(
            'pattern: pattern solid, fore_colour dark_header;'
            'font: bold 1, colour white, height 260, name Arial;'
            'align: horiz center, vert center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        headers_modernos = [
            'ESTADO',
            'CANTIDAD',
            '%',
            'CONTÓMETRO TOTAL',
            'ESTADO VISUAL',
            'ACCIÓN REQUERIDA'
        ]

        for col, header in enumerate(headers_modernos):
            worksheet.write(row, col, header, modern_header)

        row += 1

        estado_configs = {
            'lista': {
                'style': status_excellent,
                'visual': 'LISTO',
                'accion': 'Disponible para alquiler'
            },
            'revisada': {
                'style': status_good,
                'visual': 'REVISADO',
                'accion': 'Preparar para inventario'
            },
            'sin_revisar': {
                'style': status_warning,
                'visual': 'PENDIENTE',
                'accion': 'Revisar técnicamente'
            },
            'con_problemas': {
                'style': status_warning,
                'visual': 'ATENCIÓN',
                'accion': 'Reparación requerida'
            },
            'partes': {
                'style': status_critical,
                'visual': 'CRÍTICO',
                'accion': 'Solo para repuestos'
            },
            'alquilada': {
                'style': status_good,
                'visual': 'ACTIVO',
                'accion': 'En servicio'
            }
        }

        for estado, data in estados_data.items():
            config = estado_configs.get(estado, estado_configs['sin_revisar'])
            estado_label = dict(reportes._fields['estado_maquina'].selection).get(estado, estado)
            porcentaje = round((data['cantidad'] / total_maquinas) * 100, 1) if total_maquinas else 0

            worksheet.write(row, 0, estado_label, config['style'])
            worksheet.write(row, 1, data['cantidad'], config['style'])
            worksheet.write(row, 2, f"{porcentaje}%", config['style'])
            worksheet.write(row, 3, data['contador_total'], config['style'])
            worksheet.write(row, 4, config['visual'], config['style'])
            worksheet.write(row, 5, config['accion'], config['style'])

            row += 1

        row += 2
        worksheet.write_merge(row, row, 0, 8, 'RECOMENDACIONES', subtitle_style)
        row += 1

        recomendaciones = []

        if sin_revisar > total_maquinas * 0.3:
            recomendaciones.append("Priorizar revisión técnica de equipos pendientes")

        if equipos_problema > 0:
            recomendaciones.append("Programar mantenimiento para equipos con problemas")

        if pct_operativos < 50:
            recomendaciones.append("Nivel crítico: aumentar equipos operativos")

        if not recomendaciones:
            recomendaciones.append("Inventario en buen estado general")

        for recomendacion in recomendaciones:
            worksheet.write_merge(row, row, 0, 8, recomendacion, status_good)
            row += 1

        for col in range(0, 9):
            worksheet.col(col).width = 4500

    def _crear_hoja_detalle(self, workbook, reportes):
        """
        Crea hoja con detalles completos, incluyendo:
        - Informe técnico
        - Componentes dinámicos
        - Accesorios dinámicos
        - Intervenciones / subpartes
        - Partes retiradas
        """
        worksheet = workbook.add_sheet('Detalles Completos')

        def _build_partes_texto(reporte):
            partes = reporte.partes_retiradas_ids

            if not partes:
                return '', '', '', ''

            nombres = []
            fechas = []
            destinos = []
            fuentes = []

            for p in partes:
                nombres.append(p.nombre_parte or '-')
                fechas.append(
                    p.fecha_solicitud.strftime('%d/%m/%Y')
                    if p.fecha_solicitud else '-'
                )
                destinos.append(p.maquina_destino or '-')
                fuentes.append(
                    'Técnico'
                    if not p.solicitud_partes_id
                    else 'Bodega'
                )

            sep = '\n'

            return (
                sep.join(nombres),
                sep.join(fechas),
                sep.join(destinos),
                sep.join(fuentes),
            )

        header_main = xlwt.easyxf(
            'pattern: pattern solid, fore_colour dark_header;'
            'font: bold 1, colour white, height 240;'
            'align: horiz center;'
            'borders: left thin, right thin, top thin, bottom thin'
        )

        def get_row_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour lista_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                ),
                'revisada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour revisada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                ),
                'sin_revisar': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour sin_revisar_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                ),
                'con_problemas': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour con_problemas_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                ),
                'partes': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour partes_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                ),
                'alquilada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour alquilada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                ),
            }

            return estado_styles.get(
                estado_maquina,
                xlwt.easyxf(
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top'
                )
            )

        def get_number_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour lista_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                ),
                'revisada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour revisada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                ),
                'sin_revisar': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour sin_revisar_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                ),
                'con_problemas': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour con_problemas_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                ),
                'partes': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour partes_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                ),
                'alquilada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour alquilada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                ),
            }

            return estado_styles.get(
                estado_maquina,
                xlwt.easyxf(
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: horiz right, vert top',
                    num_format_str='#,##0'
                )
            )

        def get_date_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour lista_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                ),
                'revisada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour revisada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                ),
                'sin_revisar': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour sin_revisar_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                ),
                'con_problemas': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour con_problemas_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                ),
                'partes': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour partes_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                ),
                'alquilada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour alquilada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                ),
            }

            return estado_styles.get(
                estado_maquina,
                xlwt.easyxf(
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top',
                    num_format_str='DD/MM/YYYY'
                )
            )

        def get_wrap_style(estado_maquina):
            estado_styles = {
                'lista': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour lista_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                ),
                'revisada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour revisada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                ),
                'sin_revisar': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour sin_revisar_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                ),
                'con_problemas': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour con_problemas_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                ),
                'partes': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour partes_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                ),
                'alquilada': xlwt.easyxf(
                    'pattern: pattern solid, fore_colour alquilada_color;'
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                ),
            }

            return estado_styles.get(
                estado_maquina,
                xlwt.easyxf(
                    'borders: left thin, right thin, top thin, bottom thin;'
                    'align: vert top, wrap 1'
                )
            )

        headers = [
            'Fecha',
            'Marca',
            'Modelo',
            'Serie',
            'Estado',
            'Total Contómetro',
            'Informe Técnico',
            'Componentes Evaluados',
            'Accesorios Evaluados',
            'Intervenciones / Subpartes',
            'Partes Retiradas',
            'Fechas Solicitud',
            'Máquinas Destino',
            'Fuente',
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_main)

        row = 1

        for reporte in reportes:
            estado = reporte.estado_maquina

            row_style = get_row_style(estado)
            number_style = get_number_style(estado)
            date_style = get_date_style(estado)
            wrap_style = get_wrap_style(estado)

            col = 0

            worksheet.write(row, col, reporte.fecha_generacion or '', date_style)
            col += 1

            worksheet.write(row, col, reporte.marca or '', row_style)
            col += 1

            worksheet.write(row, col, reporte.modelo or '', row_style)
            col += 1

            worksheet.write(row, col, reporte.serie or '', row_style)
            col += 1

            estado_display = dict(reporte._fields['estado_maquina'].selection).get(
                estado,
                ''
            )
            worksheet.write(row, col, estado_display, row_style)
            col += 1

            worksheet.write(row, col, reporte.contador_total or 0, number_style)
            col += 1

            informe_txt = self._html_to_text(reporte.informe_tecnico or '')
            if len(informe_txt) > 1000:
                informe_txt = informe_txt[:997] + '...'

            worksheet.write(row, col, informe_txt, wrap_style)
            col += 1

            componentes_txt = self._html_to_text(reporte.componentes_resumen or '')
            accesorios_txt = self._html_to_text(reporte.accesorios_resumen or '')
            intervenciones_txt = self._html_to_text(reporte.intervenciones_resumen or '')

            worksheet.write(row, col, componentes_txt, wrap_style)
            col += 1

            worksheet.write(row, col, accesorios_txt, wrap_style)
            col += 1

            worksheet.write(row, col, intervenciones_txt, wrap_style)
            col += 1

            nombres_txt, fechas_txt, destinos_txt, fuentes_txt = _build_partes_texto(reporte)

            worksheet.write(row, col, nombres_txt, wrap_style)
            col += 1

            worksheet.write(row, col, fechas_txt, wrap_style)
            col += 1

            worksheet.write(row, col, destinos_txt, wrap_style)
            col += 1

            worksheet.write(row, col, fuentes_txt, wrap_style)

            num_lineas = max(
                len(nombres_txt.splitlines()) if nombres_txt else 1,
                len(componentes_txt.splitlines()) if componentes_txt else 1,
                len(accesorios_txt.splitlines()) if accesorios_txt else 1,
                len(intervenciones_txt.splitlines()) if intervenciones_txt else 1,
            )

            worksheet.row(row).height = max(400, min(num_lineas * 320, 5000))

            row += 1

        column_data = [[] for _ in range(len(headers))]

        for reporte in reportes:
            estado = reporte.estado_maquina

            nombres_txt, fechas_txt, destinos_txt, fuentes_txt = _build_partes_texto(reporte)

            column_data[0].append(str(reporte.fecha_generacion or ''))
            column_data[1].append(reporte.marca or '')
            column_data[2].append(reporte.modelo or '')
            column_data[3].append(reporte.serie or '')
            column_data[4].append(dict(reporte._fields['estado_maquina'].selection).get(estado, ''))
            column_data[5].append(str(reporte.contador_total or 0))
            column_data[6].append(self._html_to_text(reporte.informe_tecnico or ''))
            column_data[7].append(self._html_to_text(reporte.componentes_resumen or ''))
            column_data[8].append(self._html_to_text(reporte.accesorios_resumen or ''))
            column_data[9].append(self._html_to_text(reporte.intervenciones_resumen or ''))
            column_data[10].append(nombres_txt)
            column_data[11].append(fechas_txt)
            column_data[12].append(destinos_txt)
            column_data[13].append(fuentes_txt)

        def auto_adjust_column_width(header_text, data_values):
            header_width = len(header_text) * 256 + 500
            max_content_width = 0

            for value in data_values:
                if value:
                    if isinstance(value, str) and '\n' in value:
                        lines = value.split('\n')
                        content_width = max(len(line) for line in lines) * 256
                    else:
                        content_width = len(str(value)) * 256

                    max_content_width = max(max_content_width, content_width)

            optimal_width = max(header_width, max_content_width)

            return max(2000, min(optimal_width, 20000))

        for col_index, header in enumerate(headers):
            worksheet.col(col_index).width = auto_adjust_column_width(
                header,
                column_data[col_index]
            )

        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(1)
        worksheet.set_vert_split_pos(4)


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
        return self.env['reporte.estado.maquina']._exportar_excel(reportes)

    def action_generar_reporte_ahora(self):
        """
        Genera el reporte semanal inmediatamente.
        """
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

        Nota:
        Este método pertenece a este modelo, no a reporte.estado.maquina,
        para evitar borrar reportes de estado de máquinas por error.
        """
        self.search([]).unlink()

        lineas = self.env['solicitud.parte.tecnico.linea'].search([])

        for linea in lineas:
            origen = linea._get_origen_display() if hasattr(linea, '_get_origen_display') else ''

            solicitud = linea.solicitud_id

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
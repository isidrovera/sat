# -*- coding: utf-8 -*-
from odoo import _, models, fields, api, exceptions
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError, UserError
from odoo.http import request
from datetime import datetime, timedelta
from pytz import timezone, UTC
import requests
import json
import logging
import base64

_logger = logging.getLogger(__name__)


class TicketAlquiler(models.Model):
    _name = 'ticket.alquiler'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ticket.informe.mixin']

    name = fields.Char('TICKET N°', default='New', copy=False, required=True, readonly=True)

    url = fields.Char('URL', compute='_compute_url', store=True)
    calendar_event_id = fields.Many2one('calendar.event', string='Evento de Calendario')

    def _compute_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.url = f"{base_url}/web#id={record.id}&model=ticket.alquiler&view_type=form"

    # ============================================================
    # CAMPOS NUEVOS — EVALUACIONES DINÁMICAS
    # ============================================================

    ticket_componente_eval_ids = fields.One2many(
        'ticket.componente.evaluacion',
        'ticket_id',
        string='Evaluaciones de Componentes'
    )

    ticket_accesorio_eval_ids = fields.One2many(
        'ticket.accesorio.evaluacion',
        'ticket_id',
        string='Evaluaciones de Accesorios'
    )

    ticket_intervencion_ids = fields.One2many(
        'ticket.componente.intervencion',
        'ticket_id',
        string='Intervenciones'
    )

    ticket_pedido_ids = fields.One2many(
        'ticket.repuesto.pedido',
        'ticket_id',
        string='Pedidos de Repuestos'
    )

    ticket_componente_eval_count = fields.Integer(
        string='Componentes',
        compute='_compute_eval_counts'
    )

    ticket_accesorio_eval_count = fields.Integer(
        string='Accesorios',
        compute='_compute_eval_counts'
    )

    ticket_pedido_count = fields.Integer(
        string='Pedidos',
        compute='_compute_eval_counts'
    )

    @api.depends('ticket_componente_eval_ids', 'ticket_accesorio_eval_ids', 'ticket_pedido_ids')
    def _compute_eval_counts(self):
        for record in self:
            record.ticket_componente_eval_count = len(record.ticket_componente_eval_ids)
            record.ticket_accesorio_eval_count = len(record.ticket_accesorio_eval_ids)
            record.ticket_pedido_count = len(record.ticket_pedido_ids)

    # ============================================================
    # CAMPOS EXISTENTES — SIN CAMBIOS
    # ============================================================

    reporter_name = fields.Char(string="Nombre de quien reporta")
    reporter_phone = fields.Char(string="Numero de quien reporto")
    problem_photo = fields.Binary(string="Foto del problema")

    responsable = fields.Many2one("res.users", string="Técnico", tracking=True, index=True)
    nombre_responsable = fields.Char(string="Nombre del Técnico", related="responsable.name", store=True)

    priority = fields.Selection([("0", "Low"), ("1", "Medium"), ("2", "High"), ("3", "Very High")],
                                string="Prioridad", default="1")
    partner_id = fields.Many2one("res.partner", string="Empresa", tracking=True)
    nombre_cliente = fields.Char(related='partner_id.name', string='Nombre de cliente', store=True)

    description = fields.Text(tracking=True)
    informe_id = fields.Html(string='Notas de reparación')

    estado = fields.Selection([
        ('nuevo', 'Nuevo'),
        ('proceso', 'Asignado'),
        ('en_ruta', 'En Ruta'),
        ('en_sitio', 'En Sitio'),
        ('en_revision', 'En Revisión'),
        ('finalizado', 'Finalizado'),
    ], tracking=True, default='nuevo')

    product_alquiler = fields.Many2one('alquiler', string='Modelo', tracking=True)

    tipo_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')],
                               string='Tipo de maquina', related='product_alquiler.tipo_maquina_id')
    serie_id_r = fields.Char(related='product_alquiler.serie', string="Serie", store=True, readonly=False)
    marca_id_r = fields.Char(related='product_alquiler.marca', string="Marca", store=True)
    modelo_id_r = fields.Char(related='product_alquiler.name.name', string='Modelo', store=True)
    direccion_id_r = fields.Char(string="Dirección")
    contacto_id_r = fields.Char(string="Contacto")
    celular_id_r = fields.Char(string="Celular")
    corre_id_r = fields.Char(string="Correo")
    piso_id_r = fields.Char(string="Piso")
    oficina_id_r = fields.Char(string="Oficina")
    area_id_r = fields.Char(string="Área")
    estern_id_r = fields.Boolean(string="Cliente externo", tracking=True)
    tray_id = fields.Char("Caseteras N°", tracking=True)

    # Accesorios Selection (se mantienen como referencia visual, ya no se validan al cerrar)
    adf_simple_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="ADF Simple", tracking=True)
    transformador_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Transformador", tracking=True)
    estabilizador = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Estabilizador", tracking=True)
    adf_dual_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="ADF Dual scan", tracking=True)
    finalizador_interno_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Finalizador Interno", tracking=True)
    finalizador_externo_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Finalizador Externo", tracking=True)
    mueble_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Mueble", tracking=True)
    panel_smart_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Panel Smart", tracking=True)
    panel_normal_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Panel Normal", tracking=True)
    wi_fi_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Wi-Fi", tracking=True)
    bluetooth_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Bluetooth", tracking=True)
    cable_usb_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Cable USB de impresión", tracking=True)
    cable_red_id = fields.Selection([("si", "Sí lo tiene"), ("no", "No lo tiene"), ("no_aplica", "No aplica")], string="Cable de red", tracking=True)

    # Tóners Selection (se mantienen)
    toner_black_id = fields.Selection([("lleno", "Lleno"), ("medio", "Medio"), ("vacio", "Vacío"), ("sin_botella", "Sin botella")], string="Toner Black", tracking=True)
    toner_magenta_id = fields.Selection([("lleno", "Lleno"), ("medio", "Medio"), ("vacio", "Vacío"), ("sin_botella", "Sin botella"), ("no_aplica", "No aplica")], string="Toner Magenta", tracking=True)
    toner_cyan_id = fields.Selection([("lleno", "Lleno"), ("medio", "Medio"), ("vacio", "Vacío"), ("sin_botella", "Sin botella"), ("no_aplica", "No aplica")], string="Toner Cyan", tracking=True)
    toner_yellow_id = fields.Selection([("lleno", "Lleno"), ("medio", "Medio"), ("vacio", "Vacío"), ("sin_botella", "Sin botella"), ("no_aplica", "No aplica")], string="Toner Yellow", tracking=True)

    # Funciones Selection (se mantienen)
    copia_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Copia", tracking=True)
    impresion_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Impresión", tracking=True)
    impresion_usb_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Impresión USB", tracking=True)
    scaner_smb_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Scanner SMB", tracking=True)
    scaner_usb_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Scanner USB", tracking=True)
    scaner_ftp_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Scanner FTP", tracking=True)
    scaner_mail_id = fields.Selection([("si", "Revisado - Funciona Correctamente"), ("no", "Revisado - No Funciona"), ("no_aplica", "No Aplica")], string="Scanner Mail", tracking=True)

    # Componentes mecánicos Selection (se mantienen como legado visual)
    adf_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="ADF", tracking=True)
    tray1_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Tray 1", tracking=True)
    tray2_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Tray 2", tracking=True)
    tray3_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Tray 3", tracking=True)
    tray4_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Tray 4", tracking=True)
    bypass_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Bypass", tracking=True)
    finalizador_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Requiere cambio de repuestos"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Finalizador", tracking=True)
    tacho_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Tacho residual", tracking=True)
    fusora_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Unidad Fusora", tracking=True)
    transfer_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Faja de Transferencia", tracking=True)
    optico_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Unidad Optica", tracking=True)
    black_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Unidad Imagen Black", tracking=True)
    magenta_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Unidad Imagen Magenta", tracking=True)
    cyan_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Unidad Imagen Cyan", tracking=True)
    yellow_id = fields.Selection([("si", "Funciona Correctamente"), ("no", "No Funciona"), ("desgaste", "Con Desgaste"), ("cambio", "Requiere Cambio"), ("no_aplica", "No Aplica")], string="Unidad Imagen Yellow", tracking=True)

    codigo_id = fields.Char(string='Referencia id')
    contometros_id = fields.Char(string="Contometro Scanner", tracking=True)
    contometrok_id = fields.Char(string="Contometro K", tracking=True)
    contometroc_id = fields.Char(string="Contometro Color", tracking=True)
    total_copias_id = fields.Char(string="Contometro Total P+C", compute="sumar_field")

    tipo_servicio_id = fields.Selection([
        ("instalacion", "Instalación"),
        ("retiro", "Retiro de maquina"),
        ("mantenimiento_preventivo", "Mantenimiento preventivo"),
        ("mantenimiento_correctivo", "Mantenimiento correctivo"),
        ("cambio_repuestos", "Cambio de repuestos"),
        ("remoto", "Asistencia remoto"),
        ("revision", "Revisión"),
        ("alquiler", "Preparar para alquiler")
    ], string="Tipo de servicio", default="revision", tracking=True)

    retorno_id = fields.Selection([("si", "Si"), ("no", "No")], string="Retorno", default="si", tracking=True)
    asistencia_id = fields.Selection([("no", "No"), ("si", "Si")], string="Asistencia Directa", default="no", tracking=True)
    calidad_id = fields.Selection([("buena", "Buena"), ("regular", "Regular"), ("mala", "Mala")], string="Calidad", tracking=True)
    agenda = fields.Datetime(string='Fecha de visita', tracking=True)
    agenda_local = fields.Char(string='Fecha y Hora Local', compute='_compute_agenda_local')
    mensaje = fields.Text(default='Se le asigno un Ticket de servicio, lea atentamente se le indica todos los detalles del servicio.')
    last_pending_notification = fields.Datetime(string="Última notificación de pendiente", readonly=True)
    color = fields.Integer(string='Índice de Color', default=0)

    pedidos_count = fields.Integer(compute='compute_count_pedidos')
    repuestos_count_ticket = fields.Integer(compute='compute_count_repuestos_ticket')
    responsable_mobile_clean = fields.Char(string='Número de celular (limpio)', compute='_compute_responsable_mobile_clean', store=True)
    cliente_phones_clean = fields.Char(string='Números de contacto limpios', compute='_compute_cliente_phones_clean', store=True)

    sale_order_line_ids = fields.One2many('sale.order.line', 'ticket_ref_id', string='Productos Solicitados', tracking=True)
    line_ids = fields.One2many('ticket.alquiler.line', 'ticket_id', string='Líneas de Productos', copy=True, required=True)
    calendar_event_id = fields.Many2one('calendar.event', string='Evento de Calendario')

    # ============================================================
    # CRUD
    # ============================================================

    @api.model
    def create(self, vals):
        # Validar instalación
        if vals.get('tipo_servicio_id') == 'instalacion' and vals.get('product_alquiler'):
            equipo = self.env['alquiler'].browse(vals['product_alquiler'])
            if equipo.exists() and equipo.estado_alquiler_id != 'por_instalar':
                raise UserError(_(
                    "No se puede crear un ticket de instalación.\n"
                    "El equipo '%s' no está en estado 'Por instalar'.\n"
                    "Estado actual: %s\n\n"
                    "Primero debe completarse y aprobarse la inspección del sitio."
                ) % (
                    equipo.serie,
                    dict(equipo._fields['estado_alquiler_id'].selection).get(
                        equipo.estado_alquiler_id, equipo.estado_alquiler_id
                    )
                ))

        vals['name'] = self.env['ir.sequence'].next_by_code('ticket.alquiler') or 'New'
        if vals.get('name', 'New') == 'New':
            raise UserError(_("Error: No se pudo generar un número de ticket."))

        record = super(TicketAlquiler, self).create(vals)
        record._compute_url()

        # Auto-cargar evaluaciones dinámicas
        try:
            record._seed_evaluaciones_ticket()
            _logger.info("[ticket.alquiler] Evaluaciones auto-cargadas para ticket ID: %s", record.id)
        except Exception as e:
            _logger.warning("[ticket.alquiler] No se pudieron cargar evaluaciones para ticket ID %s: %s", record.id, str(e))

        return record

    # ============================================================
    # AUTO-CARGA DE EVALUACIONES
    # ============================================================

    def _seed_evaluaciones_ticket(self):
        """Carga automáticamente componentes y accesorios desde el catálogo del modelo."""
        self.ensure_one()

        if not self.product_alquiler or not self.product_alquiler.name:
            _logger.info("[_seed_evaluaciones_ticket] Ticket %s sin equipo o modelo asignado", self.id)
            return

        modelo = self.product_alquiler.name
        _logger.info("[_seed_evaluaciones_ticket] Cargando para ticket %s modelo %s", self.id, modelo.name)

        # ---- COMPONENTES ----
        componentes_modelo = self.env['modelo.maquina.componente'].search([
            ('modelo_id', '=', modelo.id)
        ])

        Color = self.env['color.tipo']
        Eval = self.env['ticket.componente.evaluacion']
        componentes_creados = 0

        for comp_line in componentes_modelo:
            color_id = False
            if comp_line.color:
                color_obj = Color.search([('code', '=', comp_line.color)], limit=1)
                if color_obj:
                    color_id = color_obj.id
                else:
                    _logger.warning("[_seed_evaluaciones_ticket] Color '%s' no encontrado en color.tipo", comp_line.color)

            dup_domain = [
                ('ticket_id', '=', self.id),
                ('componente_tipo_id', '=', comp_line.tipo_id.id),
            ]
            dup_domain.append(('color_id', '=', color_id) if color_id else ('color_id', '=', False))

            if Eval.search(dup_domain, limit=1):
                continue

            try:
                Eval.create({
                    'ticket_id': self.id,
                    'componente_tipo_id': comp_line.tipo_id.id,
                    'color_id': color_id,
                    'estado_id': comp_line.estado_sugerido_id.id if comp_line.estado_sugerido_id else False,
                    'observaciones': comp_line.frase_desgaste or '',
                })
                componentes_creados += 1
            except Exception as e:
                _logger.error("[_seed_evaluaciones_ticket] Error creando evaluación %s: %s", comp_line.tipo_id.name, e)

        _logger.info("[_seed_evaluaciones_ticket] %s componentes creados para ticket %s", componentes_creados, self.id)

        # ---- ACCESORIOS ----
        accesorios_modelo = self.env['modelo.maquina.accesorio'].search([
            ('modelo_id', '=', modelo.id)
        ])

        AccEval = self.env['ticket.accesorio.evaluacion']
        accesorios_creados = 0

        for acc_line in accesorios_modelo:
            if AccEval.search([('ticket_id', '=', self.id), ('tipo_id', '=', acc_line.tipo_id.id)], limit=1):
                continue
            try:
                AccEval.create({
                    'ticket_id': self.id,
                    'tipo_id': acc_line.tipo_id.id,
                    'estado_id': acc_line.estado_predeterminado_id.id if acc_line.estado_predeterminado_id else False,
                    'observaciones': acc_line.nota or '',
                })
                accesorios_creados += 1
            except Exception as e:
                _logger.error("[_seed_evaluaciones_ticket] Error creando accesorio %s: %s", acc_line.tipo_id.name, e)

        _logger.info("[_seed_evaluaciones_ticket] %s accesorios creados para ticket %s", accesorios_creados, self.id)
        _logger.info("[_seed_evaluaciones_ticket] Total: %s evaluaciones para ticket %s", componentes_creados + accesorios_creados, self.id)

    # ============================================================
    # DETECCIÓN DE PENDIENTES PARA WIZARD
    # ============================================================

    def _get_componentes_requieren_cambio_sin_subpartes(self):
        """
        Devuelve lista de dicts con componentes y accesorios que tienen
        estado requiere_cambio y NO tienen intervención con subpartes.
        """
        self.ensure_one()
        pendientes = []
        seen = set()

        # --- COMPONENTES ---
        for evaluacion in self.ticket_componente_eval_ids:
            if not evaluacion.estado_id or evaluacion.estado_id.code != 'requiere_cambio':
                continue

            tipo = evaluacion.componente_tipo_id
            if not tipo:
                continue

            # Construir componente_code dinámico
            base_code = f"t{tipo.id}"
            color_code = False

            if tipo.is_color_sensitive:
                if evaluacion.color_id and evaluacion.color_id.code:
                    color_code = evaluacion.color_id.code.lower()
                if not color_code:
                    _logger.warning("[_get_componentes_requieren_cambio_sin_subpartes] Tipo %s color-sensitive sin color en eval %s", tipo.name, evaluacion.id)
                    continue
                componente_code = f"{base_code}_{color_code}"
            else:
                componente_code = base_code

            if componente_code in seen:
                continue
            seen.add(componente_code)

            # Verificar si ya tiene intervención con subpartes
            intervencion = self.ticket_intervencion_ids.filtered(
                lambda x: x.componente_code == componente_code and x.detalle_ids
            )
            if not intervencion:
                pendientes.append({
                    'evaluacion_id': evaluacion.id,
                    'componente_code': componente_code,
                    'tipo_id': tipo.id,
                    'color_code': color_code,
                    'es_accesorio': False,
                })

        # --- ACCESORIOS ---
        for evaluacion in self.ticket_accesorio_eval_ids:
            if not evaluacion.estado_id or evaluacion.estado_id.code != 'requiere_cambio':
                continue

            tipo = evaluacion.tipo_id
            if not tipo:
                continue

            componente_code = f"a{tipo.id}"

            if componente_code in seen:
                continue
            seen.add(componente_code)

            intervencion = self.ticket_intervencion_ids.filtered(
                lambda x: x.componente_code == componente_code and x.detalle_ids
            )
            if not intervencion:
                pendientes.append({
                    'evaluacion_id': evaluacion.id,
                    'componente_code': componente_code,
                    'tipo_id': tipo.id,
                    'color_code': None,
                    'es_accesorio': True,
                })

        _logger.info(
            "[_get_componentes_requieren_cambio_sin_subpartes] ticket=%s pendientes=%s",
            self.id, len(pendientes)
        )
        return pendientes

    def _abrir_wizard_subpartes(self, pendientes):
        """Crea y abre el wizard de subpartes para los componentes pendientes."""
        self.ensure_one()

        wizard = self.env['ticket.subpartes.wizard'].create({'ticket_id': self.id})
        modelo = self.product_alquiler

        for comp_info in pendientes:
            componente_code = comp_info['componente_code']
            es_accesorio = comp_info['es_accesorio']

            # Crear o reutilizar intervención
            intervencion = self.env['ticket.componente.intervencion'].search([
                ('ticket_id', '=', self.id),
                ('componente_code', '=', componente_code),
            ], limit=1)
            if not intervencion:
                intervencion = self.env['ticket.componente.intervencion'].create({
                    'ticket_id': self.id,
                    'componente_code': componente_code,
                })

            ya_existentes = set(intervencion.detalle_ids.mapped('subparte_id').ids)
            agregadas = set()
            total_lineas = 0

            if not es_accesorio:
                # Buscar subpartes del catálogo del modelo para este componente
                color_code = comp_info.get('color_code')
                tipo_id = comp_info['tipo_id']

                mmc = self.env['modelo.maquina.componente']
                domain = [('modelo_id', '=', modelo.id), ('tipo_id', '=', tipo_id)]
                if color_code:
                    color_rec = self.env['color.tipo'].search([('code', '=', color_code)], limit=1)
                    if color_rec:
                        domain.append(('color_id', '=', color_rec.id))

                componentes_modelo = mmc.search(domain)
                if not componentes_modelo:
                    componentes_modelo = mmc.search([('modelo_id', '=', modelo.id), ('tipo_id', '=', tipo_id)])
                if not componentes_modelo:
                    componentes_modelo = mmc.search([('tipo_id', '=', tipo_id)])

                for comp_mod in componentes_modelo:
                    for detalle in getattr(comp_mod, 'detalle_ids', []):
                        sid = detalle.subparte_id.id
                        if not sid or sid in ya_existentes or sid in agregadas:
                            continue
                        self.env['ticket.subpartes.wizard.linea'].create({
                            'wizard_id': wizard.id,
                            'componente_code': componente_code,
                            'intervencion_id': intervencion.id,
                            'subparte_id': sid,
                            'selected': False,
                            'cantidad': detalle.cantidad or 1.0,
                        })
                        agregadas.add(sid)
                        total_lineas += 1
            else:
                # Accesorios: buscar subpartes por tipo en componente.subparte
                Subparte = self.env.get('componente.subparte')
                if Subparte and 'tipo_id' in Subparte._fields:
                    subpartes = Subparte.search([('tipo_id', '=', comp_info['tipo_id'])])
                    for sp in subpartes:
                        if sp.id in ya_existentes or sp.id in agregadas:
                            continue
                        self.env['ticket.subpartes.wizard.linea'].create({
                            'wizard_id': wizard.id,
                            'componente_code': componente_code,
                            'intervencion_id': intervencion.id,
                            'subparte_id': sp.id,
                            'selected': False,
                            'cantidad': 1.0,
                        })
                        agregadas.add(sp.id)
                        total_lineas += 1

            if total_lineas == 0:
                _logger.warning(
                    "[_abrir_wizard_subpartes] Sin subpartes para code=%s tipo_id=%s",
                    componente_code, comp_info['tipo_id']
                )
                self.message_post(body=_(
                    "⚠️ No se encontraron subpartes para <b>%s</b>. "
                    "Complete el catálogo en Configuración → Componentes por Modelo."
                ) % componente_code)

        # Título dinámico
        nombres = []
        for comp in pendientes:
            if comp['es_accesorio']:
                tipo = self.env['accesorio.tipo'].browse(comp['tipo_id'])
            else:
                tipo = self.env['componente.tipo'].browse(comp['tipo_id'])
            nombre = tipo.name if tipo.exists() else comp['componente_code']
            if comp.get('color_code'):
                nombre = f"{nombre} ({comp['color_code'].upper()})"
            nombres.append(nombre)

        titulo = f"Subpartes requeridas: {', '.join(nombres)}"

        return {
            'type': 'ir.actions.act_window',
            'name': titulo,
            'res_model': 'ticket.subpartes.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'from_ticket_finalizar': True},
        }

    # ============================================================
    # VALIDACIONES
    # ============================================================

    def _validar_evaluaciones_ticket(self):
        """Valida que todos los componentes y accesorios tengan estado completado."""
        self.ensure_one()

        # Componentes sin estado
        sin_estado_comp = self.ticket_componente_eval_ids.filtered(lambda e: not e.estado_id)
        if sin_estado_comp:
            nombres = []
            for e in sin_estado_comp:
                nombre = e.componente_tipo_id.name
                if e.color_id:
                    nombre += f" ({e.color_id.name})"
                nombres.append(nombre)
            raise ValidationError(_(
                "❗ Evaluación de Componentes Incompleta\n\n"
                "Completa el estado de los siguientes componentes:\n• %s"
            ) % "\n• ".join(nombres))

        # Accesorios sin estado
        sin_estado_acc = self.ticket_accesorio_eval_ids.filtered(lambda e: not e.estado_id)
        if sin_estado_acc:
            nombres = [e.tipo_id.name for e in sin_estado_acc]
            raise ValidationError(_(
                "❗ Evaluación de Accesorios Incompleta\n\n"
                "Completa el estado de los siguientes accesorios:\n• %s"
            ) % "\n• ".join(nombres))

    # ============================================================
    # CREAR PEDIDO AL CERRAR
    # ============================================================

    def _crear_pedido_repuestos(self):
        """Crea el pedido de repuestos desde las intervenciones con subpartes."""
        self.ensure_one()

        intervenciones_con_subpartes = self.ticket_intervencion_ids.filtered(lambda x: x.detalle_ids)
        if not intervenciones_con_subpartes:
            _logger.info("[_crear_pedido_repuestos] ticket=%s sin intervenciones con subpartes", self.id)
            return

        pedido = self.env['ticket.repuesto.pedido'].create({
            'ticket_id': self.id,
        })

        for intervencion in intervenciones_con_subpartes:
            # Determinar color_id desde el componente_code
            import re
            color_id = False
            m = re.match(r'^t\d+_([kcmy])$', intervencion.componente_code or '')
            if m:
                color_rec = self.env['color.tipo'].search([('code', '=', m.group(1))], limit=1)
                color_id = color_rec.id if color_rec else False

            for detalle in intervencion.detalle_ids:
                self.env['ticket.repuesto.pedido.linea'].create({
                    'pedido_id': pedido.id,
                    'componente_code': intervencion.componente_code,
                    'color_id': color_id,
                    'subparte_id': detalle.subparte_id.id,
                    'cantidad': detalle.cantidad,
                    'observacion': detalle.observacion or '',
                })

        _logger.info(
            "[_crear_pedido_repuestos] Pedido %s creado para ticket %s con %s líneas",
            pedido.name, self.id, pedido.total_lineas
        )

        self.message_post(body=_(
            "📦 <b>Pedido de repuestos generado:</b> %s<br/>"
            "Líneas: %s<br/>"
            "Estado: Pendiente de aprobación"
        ) % (pedido.name, pedido.total_lineas))

    # ============================================================
    # ACTION FINALIZAR — REEMPLAZA AL ANTERIOR
    # ============================================================

    def action_finalizar(self):
        _logger.info("=== Iniciando action_finalizar para tickets %s ===", self.ids)
        tickets = self.sudo()

        for ticket in tickets:
            _logger.info("Procesando ticket ID %s (estado=%s)", ticket.id, ticket.estado)

            # ---- VALIDAR ESTADO ----
            ESTADOS_FINALIZAR = ('proceso', 'en_revision', 'en_sitio', 'en_ruta')
            if ticket.estado not in ESTADOS_FINALIZAR:
                raise UserError(_(
                    "El ticket debe estar en uno de estos estados para finalizar: %s.\n"
                    "Estado actual: '%s'"
                ) % (', '.join(ESTADOS_FINALIZAR), ticket.estado))

            # ---- VALIDAR CAMPOS BÁSICOS ----
            errors = []
            if not ticket.contometrok_id:
                errors.append("• Contador K es requerido")
            if not ticket.contometros_id:
                errors.append("• Contador S es requerido")
            if ticket.tipo_id == 'color' and not ticket.contometroc_id:
                errors.append("• Contador Color es requerido para equipos a color")
            if not ticket.informe_id:
                errors.append("• Informe Técnico es requerido")
            if not ticket.calidad_id:
                errors.append("• Calidad es requerida")

            if errors:
                raise UserError(
                    "No se puede finalizar el ticket:\n\n" + "\n".join(errors) +
                    "\n\nComplete todos los campos requeridos."
                )

            # ---- VALIDAR CONTÓMETROS ----
            try:
                ticket._check_contometro_values()
            except Exception:
                raise

            # ---- VALIDAR EVALUACIONES DINÁMICAS ----
            ticket._validar_evaluaciones_ticket()

            # ---- VERIFICAR SUBPARTES PENDIENTES ----
            if not self.env.context.get('skip_subpartes_validation'):
                pendientes = ticket._get_componentes_requieren_cambio_sin_subpartes()
                if pendientes:
                    _logger.info(
                        "[action_finalizar] ticket=%s -> %s componentes pendientes, abriendo wizard",
                        ticket.id, len(pendientes)
                    )
                    return ticket._abrir_wizard_subpartes(pendientes)

            # ---- CREAR PEDIDO DE REPUESTOS ----
            ticket._crear_pedido_repuestos()

            # ---- ENVIAR CORREO DE FINALIZACIÓN ----
            try:
                tmpl_fin = ticket.env.ref('sat.email_template_ticket_cliente_finalizacion')
                tmpl_fin.send_mail(ticket.id, force_send=True)
            except Exception as e:
                _logger.error("[action_finalizar] Error enviando correo para ticket %s: %s", ticket.id, e)

            if ticket.retorno_id == 'no':
                try:
                    ticket.env.ref('sat.mail_template_retorno').send_mail(ticket.id, force_send=True)
                except Exception as e:
                    _logger.error("[action_finalizar] Error enviando correo retorno ticket %s: %s", ticket.id, e)

            # ---- ACTUALIZAR ESTADO DE LA UNIDAD ----
            unidad = ticket.product_alquiler
            if unidad:
                if ticket.tipo_servicio_id == 'alquiler' and unidad.estado_alquiler_id == 'sin_revisar':
                    unidad.write({'estado_alquiler_id': 'revisada'})

                elif ticket.tipo_servicio_id == 'cambio_repuestos' and unidad.estado_alquiler_id == 'revisada':
                    prev = ticket.search([
                        ('product_alquiler', '=', unidad.id),
                        ('tipo_servicio_id', '=', 'alquiler')
                    ], order="create_date desc", limit=1)
                    if prev:
                        unidad.write({'estado_alquiler_id': 'lista'})

                elif ticket.tipo_servicio_id == 'instalacion':
                    if unidad.estado_alquiler_id != 'por_instalar':
                        raise UserError(_(
                            "No se puede finalizar la instalación.\n"
                            "El equipo '%s' no está en estado 'Por instalar'.\n"
                            "Estado actual: %s"
                        ) % (
                            unidad.serie,
                            dict(unidad._fields['estado_alquiler_id'].selection).get(
                                unidad.estado_alquiler_id, unidad.estado_alquiler_id
                            )
                        ))
                    unidad.write({'estado_alquiler_id': 'alquilada'})
                    unidad.message_post(
                        body=_("🏗️ Equipo instalado exitosamente.\nTicket: %s\nTécnico: %s") % (
                            ticket.name, ticket.responsable.name or 'N/A'
                        ),
                        message_type='notification',
                    )

                elif ticket.tipo_servicio_id == 'retiro':
                    unidad.write({
                        'estado_alquiler_id': 'sin_revisar',
                        'direccion': 'AV Angelica Gamarra 2156',
                        'contacto_id': 'Isidro',
                        'celular': '975399303',
                        'correo_': 'soporte@andescopiers.com.pe',
                        'cliente_id': 1,
                        'fecha_inicio': False,
                    })

            # ---- MARCAR COMO FINALIZADO ----
            ticket.write({
                'estado': 'finalizado',
                'last_pending_notification': False,
            })
            _logger.info("[action_finalizar] Ticket %s finalizado correctamente", ticket.id)

        _logger.info("=== action_finalizar completado para tickets %s ===", self.ids)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'view_id': False,
            'target': 'main',
        }

    # ============================================================
    # SMART BUTTONS — VISTAS EVALUACIONES Y PEDIDOS
    # ============================================================

    def action_ver_componentes_ticket(self):
        self.ensure_one()
        return {
            'name': 'Evaluación de Componentes',
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.componente.evaluacion',
            'view_mode': 'list,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'default_ticket_id': self.id},
        }

    def action_ver_accesorios_ticket(self):
        self.ensure_one()
        return {
            'name': 'Evaluación de Accesorios',
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.accesorio.evaluacion',
            'view_mode': 'list,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'default_ticket_id': self.id},
        }

    def action_ver_pedidos_ticket(self):
        self.ensure_one()
        return {
            'name': 'Pedidos de Repuestos',
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.repuesto.pedido',
            'view_mode': 'list,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'default_ticket_id': self.id},
        }

    # ============================================================
    # MÉTODOS EXISTENTES SIN CAMBIOS
    # ============================================================

    def crear_evento_calendario(self):
        self.ensure_one()
        CalendarEvent = self.env['calendar.event']
        if not self.agenda:
            return False
        try:
            start_datetime = self.agenda
            stop_datetime = start_datetime + timedelta(hours=2)
            partner_ids = []
            if self.partner_id:
                partner_ids.append(self.partner_id.id)
            if self.responsable and self.responsable.partner_id:
                partner_ids.append(self.responsable.partner_id.id)
            event_vals = {
                'name': f"Visita Técnica - {self.name or 'NA'} - {self.partner_id.name or 'NA'}",
                'start': start_datetime,
                'stop': stop_datetime,
                'partner_ids': [(6, 0, partner_ids)],
                'user_id': self.responsable.id if self.responsable else None,
                'description': f"Ticket: {self.name}\nCliente: {self.partner_id.name or 'NA'}\nSerie: {self.serie_id_r or 'NA'}",
                'location': self.direccion_id_r or 'NA',
                'allday': False,
            }
            if self.calendar_event_id:
                self.calendar_event_id.write(event_vals)
            else:
                event = CalendarEvent.create(event_vals)
                self.calendar_event_id = event.id
            return True
        except Exception as e:
            _logger.error("Error creando evento calendario ticket %s: %s", self.id, str(e))
            self.message_post(body=f"Error al gestionar evento de calendario: {str(e)}")
            return False

    @api.depends('contometrok_id', 'contometroc_id')
    def sumar_field(self):
        for record in self:
            contometrok_value = int(record.contometrok_id) if record.contometrok_id else 0
            contometroc_value = int(record.contometroc_id) if record.contometroc_id else 0
            record.total_copias_id = str(contometrok_value + contometroc_value)

    @api.constrains('contometrok_id', 'contometroc_id', 'contometros_id')
    def _check_contometro_values(self):
        if self.env.context.get('skip_constraints'):
            return
        for record in self:
            previous_record = self.search(
                [('product_alquiler', '=', record.product_alquiler.id), ('id', '<', record.id)],
                limit=1, order='id desc'
            )

            def clean_and_convert(value_str):
                if not value_str:
                    return 0
                value_str = str(value_str).strip()
                try:
                    cleaned = value_str.replace(',', '')
                    if '.' in cleaned:
                        parts = cleaned.split('.')
                        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
                            cleaned = parts[0] + parts[1]
                        else:
                            cleaned = parts[0]
                    return int(float(cleaned))
                except (ValueError, TypeError):
                    return 0

            current_k = clean_and_convert(record.contometrok_id)
            current_color = clean_and_convert(record.contometroc_id)
            current_scanner = clean_and_convert(record.contometros_id)
            prev_k = clean_and_convert(previous_record.contometrok_id) if previous_record else 0
            prev_color = clean_and_convert(previous_record.contometroc_id) if previous_record else 0
            prev_scanner = clean_and_convert(previous_record.contometros_id) if previous_record else 0

            if previous_record and current_k <= prev_k:
                raise ValidationError(_(
                    "❗ El contómetro K debe ser mayor al último registrado.\n"
                    "Actual: %s | Anterior: %s | Ticket: %s"
                ) % (f"{current_k:,}", f"{prev_k:,}", previous_record.name))

            if record.tipo_id == 'color':
                if previous_record and current_color <= prev_color:
                    raise ValidationError(_(
                        "❗ El contómetro Color debe ser mayor al último registrado.\n"
                        "Actual: %s | Anterior: %s | Ticket: %s"
                    ) % (f"{current_color:,}", f"{prev_color:,}", previous_record.name))
                if current_color == 0:
                    raise ValidationError(_("❗ El contómetro Color no puede ser 0."))

            if previous_record and current_scanner < prev_scanner:
                raise ValidationError(_(
                    "❗ El contómetro Scanner debe ser igual o mayor al último registrado.\n"
                    "Actual: %s | Anterior: %s | Ticket: %s"
                ) % (f"{current_scanner:,}", f"{prev_scanner:,}", previous_record.name))

            if current_k == 0 and current_scanner == 0:
                raise ValidationError(_("❗ Los contómetros no pueden ser 0."))

    @api.depends('agenda')
    def _compute_agenda_local(self):
        user_tz = self.env.user.tz or 'UTC'
        local_tz = timezone(user_tz)
        for record in self:
            if record.agenda:
                utc_dt = UTC.localize(record.agenda)
                local_dt = utc_dt.astimezone(local_tz)
                record.agenda_local = local_dt.strftime('%d/%m/%Y %I:%M:%S %p')
            else:
                record.agenda_local = ''

    def compute_count_pedidos(self):
        for record in self:
            record.pedidos_count = self.env['sale.order'].search_count([('equipo_id', '=', record.product_alquiler.id)])

    def get_pedidos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedidos',
            'view_mode': 'list,form',
            'res_model': 'sale.order',
            'domain': [('equipo_id', '=', self.product_alquiler.id)],
            'context': "{'create': True}"
        }

    def compute_count_repuestos_ticket(self):
        for record in self:
            record.repuestos_count_ticket = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', self.product_alquiler.id)])

    def get_repuestos_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos_ticket',
            'view_mode': 'list,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.product_alquiler.id)],
            'context': "{'create': False}"
        }

    def action_view_lines(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Líneas de Productos',
            'res_model': 'ticket.alquiler.line',
            'view_mode': 'tree,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'create': False}
        }

    def action_add_product_line(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agregar Producto',
            'res_model': 'ticket.alquiler.line',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }

    def action_proceso(self):
        self.estado = 'proceso'

    def action_nuevo(self):
        self.estado = 'nuevo'

    @api.depends('responsable.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            if record.responsable.mobile_phone:
                phone = record.responsable.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_mobile_clean = phone
            else:
                record.responsable_mobile_clean = 'NA'

    @api.depends('product_alquiler.celular')
    def _compute_cliente_phones_clean(self):
        for record in self:
            if record.product_alquiler.celular:
                phones = record.product_alquiler.celular.split('/')
                cleaned_phones = []
                for phone in phones:
                    phone = ''.join(phone.split())
                    if not phone.startswith('51'):
                        phone = '51' + phone
                    cleaned_phones.append(phone)
                record.cliente_phones_clean = ','.join(cleaned_phones)
            else:
                record.cliente_phones_clean = 'NA'

    def _generate_report_url(self):
        report = self.env.ref('sat.report_template_id')
        pdf_content, _ = report.sudo().render_qweb_pdf([self.id])
        report_name = f'Informe_Tecnico_{self.name}.pdf'
        attachment = self.env['ir.attachment'].create({
            'name': report_name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'store_fname': report_name,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf'
        })
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/web/content/{attachment.id}?download=true'

    def get_selection_labels(self):
        selection_labels = {}
        for field_name, field in self._fields.items():
            if field.type == 'selection' and hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    selection = field.selection
                    if callable(selection):
                        selection = selection(self)
                    for option_value, option_label in selection:
                        if option_value == value:
                            selection_labels[field_name] = option_label
                            break
                else:
                    selection_labels[field_name] = 'NA'
        return selection_labels

    def create_ticket_wizard(self):
        return {
            'name': 'Crear ticket',
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.alquiler',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(self.env.ref('sat.view_ticket_wizard').id, 'form')],
            'target': 'new',
        }

    def action_crear_evaluacion(self):
        self.ensure_one()
        if self.estado != 'finalizado':
            raise ValidationError(_("El ticket no está finalizado. No se puede generar la evaluación."))
        evaluation_model = self.env['client.service.evaluation']
        existing_eval = evaluation_model.search([('ticket_id', '=', self.id)], limit=1)
        if existing_eval:
            raise ValidationError(_("Ya existe una evaluación para este ticket."))
        try:
            evaluation = evaluation_model.create({'ticket_id': self.id, 'state': 'draft'})
            template = self.env.ref('sat.email_template_service_evaluation', raise_if_not_found=False)
            if template:
                template.send_mail(evaluation.id, force_send=True)
            return {
                'type': 'ir.actions.act_window',
                'name': 'Evaluación',
                'view_mode': 'form',
                'res_model': 'client.service.evaluation',
                'res_id': evaluation.id,
                'target': 'current',
            }
        except Exception as e:
            raise ValidationError(_("Error al crear la evaluación: {}").format(str(e)))

    def action_asignar_masivo(self):
        _logger.info("🎯 [asignar_masivo] records=%s ids=%s", len(self), self.ids)
        tickets_no_nuevos = self.filtered(lambda t: t.estado != 'nuevo')
        if tickets_no_nuevos:
            raise UserError(
                "No se pueden asignar tickets que no están en estado 'nuevo'.\n"
                f"Diferentes: {', '.join(tickets_no_nuevos.mapped('name'))}"
            )
        Wizard = self.env['whatsapp.notification.wizard']
        view = self.env.ref('sat.view_whatsapp_notification_wizard_form_massive')
        wizard = Wizard.create({
            'es_asignacion_masiva': True,
            'tickets_masivos_ids': [(6, 0, self.ids)],
            'notificar_grupos': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': f'Asignación Masiva - {len(self)} Tickets',
            'res_model': 'whatsapp.notification.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': view.id,
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': {
                'default_es_asignacion_masiva': True,
                'default_tickets_masivos_ids': [(6, 0, self.ids)],
            },
        }

    def action_asignar_ticket(self):
        if len(self) > 1:
            return self.action_asignar_masivo()
        self.ensure_one()
        wizard = self.env['whatsapp.notification.wizard'].create({
            'ticket_id': self.id,
            'es_asignacion_masiva': False,
            'notificar_grupos': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmar Asignación de Ticket',
            'res_model': 'whatsapp.notification.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_es_asignacion_masiva': False,
                'default_notificar_grupos': False
            }
        }

    def _procesar_asignacion_masiva(self, wizard_data):
        valores_comunes = {
            'responsable': wizard_data.get('tecnico_asignado').id if wizard_data.get('tecnico_asignado') else False,
            'agenda': wizard_data.get('fecha_visita'),
            'asistencia_id': wizard_data.get('asistencia_directa', 'no'),
        }
        for ticket_data in wizard_data.get('ticket_lines', []):
            ticket = self.browse(ticket_data['ticket_id'])
            valores_ticket = valores_comunes.copy()
            valores_ticket['tipo_servicio_id'] = ticket_data['tipo_servicio_id']
            ticket.write(valores_ticket)
        grupos = {}
        for ticket in self:
            key = (ticket.partner_id.id if ticket.partner_id else 0,
                   ticket.responsable.id if ticket.responsable else 0)
            if key not in grupos:
                grupos[key] = {'cliente': ticket.partner_id, 'tecnico': ticket.responsable, 'tickets': self.env['ticket.alquiler']}
            grupos[key]['tickets'] |= ticket
        for grupo_data in grupos.values():
            self._procesar_grupo_tickets_consolidado(grupo_data, wizard_data)
        self.write({'estado': 'proceso'})
        return True

    def _procesar_grupo_tickets_consolidado(self, grupo_data, wizard_data):
        tickets = grupo_data['tickets']
        for ticket in tickets:
            try:
                ticket.crear_evento_calendario()
            except Exception as e:
                _logger.warning(f"Error creando evento para ticket {ticket.name}: {e}")
        if wizard_data.get('notificar_grupos') and wizard_data.get('grupo_seleccionado'):
            self._enviar_notificacion_grupo_consolidada(tickets, wizard_data)
        self._enviar_whatsapp_consolidado(tickets, grupo_data['cliente'], grupo_data['tecnico'])
        self._enviar_correos_consolidados(tickets, grupo_data['cliente'], grupo_data['tecnico'])
        tickets_directos = tickets.filtered(lambda t: t.asistencia_id == 'si')
        if tickets_directos:
            self._notificar_gerente_asistencia_directa_consolidada(tickets_directos)

    def _agrupar_tickets_por_tipo_servicio(self, tickets):
        agrupados = {}
        for ticket in tickets:
            tipo = ticket.tipo_servicio_id
            if tipo not in agrupados:
                agrupados[tipo] = []
            agrupados[tipo].append(ticket)
        return agrupados

    @api.model
    def _cron_notificar_tickets_pendientes(self):
        tickets_pendientes = self.search([
            ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
            ('agenda', '<', fields.Datetime.now())
        ])
        tecnicos_con_tickets = {}
        for ticket in tickets_pendientes:
            if not ticket.responsable:
                continue
            tech_id = ticket.responsable.id
            if tech_id not in tecnicos_con_tickets:
                tecnicos_con_tickets[tech_id] = {'tecnico': ticket.responsable, 'tickets': []}
            tecnicos_con_tickets[tech_id]['tickets'].append(ticket)
        for tech_data in tecnicos_con_tickets.values():
            self._enviar_notificacion_pendientes(tech_data['tecnico'], tech_data['tickets'])
        return True


class ReportTicketAlquiler(models.AbstractModel):
    _name = 'report.sat.ticket_alquiler'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['ticket.alquiler'].browse(docids)
        selection_labels = {}
        for doc in docs:
            selection_labels[doc.id] = doc.get_selection_labels() if doc else {}
        return {
            'doc_ids': docids,
            'doc_model': 'ticket.alquiler',
            'docs': docs,
            'selection_labels': selection_labels,
        }


class TicketAlquilerLine(models.Model):
    _name = 'ticket.alquiler.line'
    _description = 'Línea de Ticket de Alquiler'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket', required=True)
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    product_uom_qty = fields.Float(string='Cantidad', required=True, default=1.0)
    price_unit = fields.Float(string='Precio Unitario', required=True)
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_price_subtotal', store=True)

    @api.depends('product_uom_qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_uom_qty * line.price_unit

    def action_add_product_line(self):
        return self.env['ticket.alquiler'].browse(self.ticket_id.id).action_add_product_line()
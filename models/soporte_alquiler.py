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
import re

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
    def action_enviar_informe_administracion(self):
        """
        Envía el informe técnico al área de administración para que
        tomen la decisión sobre el destino del equipo (alquiler o venta).
        Adjunta automáticamente el reporte PDF del ticket.
        """
        self.ensure_one()

        # Validaciones mínimas
        errores = []
        if not self.informe_id:
            errores.append("• El Informe Técnico es requerido")
        if not self.product_alquiler:
            errores.append("• El equipo (modelo) es requerido")
        if not self.contometrok_id:
            errores.append("• El contómetro K es requerido")

        if errores:
            raise UserError(_(
                "No se puede enviar el informe a administración:\n\n%s"
            ) % "\n".join(errores))

        try:
            tmpl = self.env.ref('sat.email_template_ticket_admin_decision')
            tmpl.send_mail(self.id, force_send=True)

            self.message_post(body=_(
                "📤 <b>Informe técnico enviado a Administración</b><br/>"
                "Equipo: %s (Serie: %s)<br/>"
                "Pendiente de decisión: alquiler o venta."
            ) % (
                self.product_alquiler.name.name if self.product_alquiler.name else 'N/A',
                self.serie_id_r or 'N/A',
            ))

            _logger.info(
                "[action_enviar_informe_administracion] Informe enviado | ticket=%s | equipo=%s",
                self.name, self.serie_id_r
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Informe enviado'),
                    'message': _('El informe técnico fue enviado a Administración correctamente.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            _logger.error(
                "[action_enviar_informe_administracion] Error enviando informe | ticket=%s | error=%s",
                self.name, str(e)
            )
            raise UserError(_(
                "Error al enviar el informe a administración:\n%s"
            ) % str(e))
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
    
    
    codigo_id = fields.Char(string='Referencia id')
    contometros_id = fields.Char(string="Contometro Scanner", tracking=True)
    contometrok_id = fields.Char(string="Contometro K", tracking=True)
    contometroc_id = fields.Char(string="Contometro Color", tracking=True)
    total_copias_id = fields.Char(string="Contometro Total P+C", compute="sumar_field")
    pedido_origen_id = fields.Many2one(
        'ticket.repuesto.pedido',
        string='Pedido de repuestos origen',
        readonly=True,
        index=True,
        help="Pedido que originó este ticket de instalación."
    )
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
    pedido_especial = fields.Boolean(
        string='📦 Pedido Especial',
        default=False,
        tracking=True,
        help="Si está activo, el pedido se crea en borrador y NO se envía "
            "automáticamente a Gerencia. El técnico o aprobador agrega "
            "líneas libres y luego envía manualmente."
    )
    def _crear_pedido_repuestos(self):
        self.ensure_one()

        _logger.info(
            "[_crear_pedido_repuestos] INICIO ticket=%s | pedido_especial=%s",
            self.id, self.pedido_especial
        )

        # 1. Detectar pendientes SIN subpartes
        pendientes = self._get_componentes_requieren_cambio_sin_subpartes()

        if pendientes and not self.pedido_especial:
            _logger.warning(
                "[_crear_pedido_repuestos] ticket=%s requiere subpartes → abriendo wizard",
                self.id
            )
            return self._abrir_wizard_subpartes(pendientes)

        # 2. Intervenciones con subpartes
        intervenciones_con_subpartes = self.ticket_intervencion_ids.filtered(
            lambda x: x.detalle_ids
        )

        # 3. Validación final
        if not intervenciones_con_subpartes and not self.pedido_especial:
            raise UserError(_(
                "Debe seleccionar subpartes o activar 'Pedido Especial'."
            ))

        # 4. Crear pedido
        pedido = self.env['ticket.repuesto.pedido'].create({
            'ticket_id': self.id,
        })

        total_lineas = 0

        # 5. Crear líneas
        for intervencion in intervenciones_con_subpartes:
            color_id = False

            m = re.match(r'^t\d+_([kcmy])$', intervencion.componente_code or '')
            if m:
                color_rec = self.env['color.tipo'].search(
                    [('code', '=', m.group(1))], limit=1
                )
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
                total_lineas += 1

        # 6. Flujo
        if self.pedido_especial:
            _logger.info("Pedido especial creado: %s", pedido.name)

            self.message_post(body=_(
                "📦 <b>Pedido especial creado:</b> %s<br/>"
                "Puede agregar líneas manualmente."
            ) % pedido.name)

        else:
            try:
                pedido.action_enviar_a_gerencia()
                estado = "Enviado a Gerencia"
            except Exception as e:
                _logger.error("Error enviando pedido: %s", e)
                estado = "Error al enviar"

            self.message_post(body=_(
                "📦 <b>Pedido generado:</b> %s<br/>"
                "Líneas: %s<br/>"
                "Estado: %s"
            ) % (pedido.name, total_lineas, estado))

        _logger.info(
            "[_crear_pedido_repuestos] FIN pedido=%s | líneas=%s",
            pedido.name, total_lineas
        )
    
    def _seed_evaluaciones_ticket(self):
        """Carga automáticamente componentes y accesorios desde el catálogo del modelo.
        
        Para accesorios: si existe un ticket anterior del mismo equipo, copia los valores
        (estado_id y observaciones) de esa evaluación previa. Si es un accesorio nuevo
        o no hay ticket anterior, usa los valores predeterminados del catálogo.
        """
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

        # ============================================================
        # ---- ACCESORIOS ----
        # Si existe ticket anterior del mismo equipo con evaluaciones,
        # copiar valores de ese ticket. Si no, usar valores del catálogo.
        # ============================================================
        AccEval = self.env['ticket.accesorio.evaluacion']

        ticket_anterior = self.search([
            ('product_alquiler', '=', self.product_alquiler.id),
            ('id', '!=', self.id),
            ('ticket_accesorio_eval_ids', '!=', False),
        ], order='id desc', limit=1)

        # Construir diccionario {tipo_id: (estado_id, observaciones)}
        valores_anteriores = {}
        if ticket_anterior:
            _logger.info(
                "[_seed_evaluaciones_ticket] Ticket anterior encontrado: %s (id=%s) — copiando accesorios",
                ticket_anterior.name, ticket_anterior.id
            )
            for ev in ticket_anterior.ticket_accesorio_eval_ids:
                if ev.tipo_id:
                    valores_anteriores[ev.tipo_id.id] = (
                        ev.estado_id.id if ev.estado_id else False,
                        ev.observaciones or '',
                    )
            _logger.info(
                "[_seed_evaluaciones_ticket] Se copiarán %s accesorios del ticket anterior",
                len(valores_anteriores)
            )
        else:
            _logger.info(
                "[_seed_evaluaciones_ticket] No hay ticket anterior para equipo id=%s — usando valores del catálogo",
                self.product_alquiler.id
            )

        accesorios_modelo = self.env['modelo.maquina.accesorio'].search([
            ('modelo_id', '=', modelo.id)
        ])

        accesorios_creados = 0

        for acc_line in accesorios_modelo:
            if AccEval.search([('ticket_id', '=', self.id), ('tipo_id', '=', acc_line.tipo_id.id)], limit=1):
                continue

            # Decidir origen de valores: ticket anterior o catálogo
            if acc_line.tipo_id.id in valores_anteriores:
                estado_id, observaciones = valores_anteriores[acc_line.tipo_id.id]
                origen = "ticket anterior"
            else:
                estado_id = acc_line.estado_predeterminado_id.id if acc_line.estado_predeterminado_id else False
                observaciones = acc_line.nota or ''
                origen = "catálogo (accesorio nuevo o sin historial)"

            try:
                AccEval.create({
                    'ticket_id': self.id,
                    'tipo_id': acc_line.tipo_id.id,
                    'estado_id': estado_id,
                    'observaciones': observaciones,
                })
                accesorios_creados += 1
                _logger.info(
                    "[_seed_evaluaciones_ticket] Accesorio '%s' creado desde %s (estado_id=%s)",
                    acc_line.tipo_id.name, origen, estado_id
                )
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
        _logger.info(
            "[_abrir_wizard_subpartes] ticket=%s | pendientes=%s",
            self.id, [c.get('componente_code') for c in pendientes]
        )

        wizard = self.env['ticket.subpartes.wizard'].create({'ticket_id': self.id})
        modelo = self.product_alquiler.name
        _logger.info(
            "[_abrir_wizard_subpartes] ticket=%s | modelo=%s (id=%s)",
            self.id, modelo.name if modelo else 'None', modelo.id if modelo else 'None'
        )

        mmc_fields = self.env['modelo.maquina.componente']._fields
        _logger.info(
            "[_abrir_wizard_subpartes] campos disponibles en modelo.maquina.componente: %s",
            list(mmc_fields.keys())
        )

        for comp_info in pendientes:
            componente_code = comp_info['componente_code']
            es_accesorio = comp_info['es_accesorio']
            _logger.info(
                "[_abrir_wizard_subpartes] Procesando comp_info=%s | es_accesorio=%s",
                comp_info, es_accesorio
            )

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
            _logger.info(
                "[_abrir_wizard_subpartes] intervencion id=%s para code=%s",
                intervencion.id, componente_code
            )

            # Mapear sub-partes ya guardadas en la intervención -> sus datos previos
            # Esto permite re-abrir el wizard mostrando todas las sub-partes del catálogo,
            # pero pre-marcando las que ya estaban (con su cantidad y observación previas).
            detalles_previos = {
                d.subparte_id.id: d
                for d in intervencion.detalle_ids
                if d.subparte_id
            }
            agregadas = set()
            total_lineas = 0

            if not es_accesorio:
                color_code = comp_info.get('color_code')
                tipo_id = comp_info['tipo_id']
                _logger.info(
                    "[_abrir_wizard_subpartes] componente | tipo_id=%s | color_code=%s",
                    tipo_id, color_code
                )

                mmc = self.env['modelo.maquina.componente']
                domain = [('modelo_id', '=', modelo.id), ('tipo_id', '=', tipo_id)]

                if color_code:
                    if 'color_id' in mmc_fields:
                        color_rec = self.env['color.tipo'].search(
                            [('code', '=', color_code)], limit=1
                        )
                        if color_rec:
                            domain.append(('color_id', '=', color_rec.id))
                            _logger.info(
                                "[_abrir_wizard_subpartes] filtro color_id=%s (%s) agregado al domain",
                                color_rec.id, color_rec.name
                            )
                        else:
                            _logger.warning(
                                "[_abrir_wizard_subpartes] color_code=%s no encontrado en color.tipo, ignorando filtro",
                                color_code
                            )
                    else:
                        _logger.warning(
                            "[_abrir_wizard_subpartes] modelo.maquina.componente no tiene campo color_id, "
                            "ignorando filtro de color para code=%s",
                            componente_code
                        )

                _logger.info(
                    "[_abrir_wizard_subpartes] domain final para mmc.search: %s",
                    domain
                )
                componentes_modelo = mmc.search(domain)
                _logger.info(
                    "[_abrir_wizard_subpartes] resultado domain completo: %s registros",
                    len(componentes_modelo)
                )

                if not componentes_modelo:
                    domain_sin_color = [('modelo_id', '=', modelo.id), ('tipo_id', '=', tipo_id)]
                    componentes_modelo = mmc.search(domain_sin_color)
                    _logger.info(
                        "[_abrir_wizard_subpartes] fallback sin color: %s registros",
                        len(componentes_modelo)
                    )

                if not componentes_modelo:
                    domain_solo_tipo = [('tipo_id', '=', tipo_id)]
                    componentes_modelo = mmc.search(domain_solo_tipo)
                    _logger.info(
                        "[_abrir_wizard_subpartes] fallback solo tipo_id: %s registros",
                        len(componentes_modelo)
                    )

                for comp_mod in componentes_modelo:
                    detalles = getattr(comp_mod, 'detalle_ids', [])
                    _logger.info(
                        "[_abrir_wizard_subpartes] comp_mod id=%s | detalles=%s",
                        comp_mod.id, len(detalles)
                    )
                    for detalle in detalles:
                        sid = detalle.subparte_id.id
                        if not sid:
                            _logger.warning(
                                "[_abrir_wizard_subpartes] detalle id=%s sin subparte_id, ignorando",
                                detalle.id
                            )
                            continue
                        if sid in agregadas:
                            _logger.info(
                                "[_abrir_wizard_subpartes] subparte_id=%s ya agregada en este pase, ignorando",
                                sid
                            )
                            continue
                        prev = detalles_previos.get(sid)
                        self.env['ticket.subpartes.wizard.linea'].create({
                            'wizard_id': wizard.id,
                            'componente_code': componente_code,
                            'intervencion_id': intervencion.id,
                            'subparte_id': sid,
                            'selected': bool(prev),
                            'cantidad': prev.cantidad if prev else (detalle.cantidad or 1.0),
                            'observacion': prev.observacion if prev else False,
                        })
                        agregadas.add(sid)
                        total_lineas += 1
                        _logger.info(
                            "[_abrir_wizard_subpartes] linea creada: subparte_id=%s | preseleccionada=%s",
                            sid, bool(prev)
                        )

            else:
                # Accesorios: buscar subpartes por tipo en componente.subparte
                tipo_id = comp_info['tipo_id']
                _logger.info(
                    "[_abrir_wizard_subpartes] accesorio | tipo_id=%s",
                    tipo_id
                )
                Subparte = self.env.get('componente.subparte')
                if Subparte is None:
                    _logger.warning(
                        "[_abrir_wizard_subpartes] modelo componente.subparte no existe"
                    )
                elif 'tipo_id' not in Subparte._fields:
                    _logger.warning(
                        "[_abrir_wizard_subpartes] componente.subparte no tiene campo tipo_id"
                    )
                else:
                    subpartes = Subparte.search([('tipo_id', '=', tipo_id)])
                    _logger.info(
                        "[_abrir_wizard_subpartes] subpartes encontradas para accesorio tipo_id=%s: %s",
                        tipo_id, len(subpartes)
                    )
                    for sp in subpartes:
                        if sp.id in agregadas:
                            continue
                        prev = detalles_previos.get(sp.id)
                        self.env['ticket.subpartes.wizard.linea'].create({
                            'wizard_id': wizard.id,
                            'componente_code': componente_code,
                            'intervencion_id': intervencion.id,
                            'subparte_id': sp.id,
                            'selected': bool(prev),
                            'cantidad': prev.cantidad if prev else 1.0,
                            'observacion': prev.observacion if prev else False,
                        })
                        agregadas.add(sp.id)
                        total_lineas += 1
                        _logger.info(
                            "[_abrir_wizard_subpartes] linea accesorio creada: subparte_id=%s | preseleccionada=%s",
                            sp.id, bool(prev)
                        )

            _logger.info(
                "[_abrir_wizard_subpartes] code=%s | total_lineas agregadas=%s",
                componente_code, total_lineas
            )

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
        _logger.info(
            "[_abrir_wizard_subpartes] abriendo wizard id=%s | titulo=%s",
            wizard.id, titulo
        )

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

    
    # ============================================================
    # ACTION FINALIZAR — REEMPLAZA AL ANTERIOR
    # ============================================================

    def action_finalizar(self):
        _logger.info("=== Iniciando action_finalizar para tickets %s ===", self.ids)
        tickets = self.sudo()
    
        for ticket in tickets:
            _logger.info(
                "[action_finalizar] Procesando ticket=%s estado=%s "
                "tipo_servicio=%s pedido_origen=%s pedido_especial=%s",
                ticket.id,
                ticket.estado,
                ticket.tipo_servicio_id,
                ticket.pedido_origen_id.name if ticket.pedido_origen_id else 'N/A',
                ticket.pedido_especial,
            )
    
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
            
            if ticket.tipo_id == 'color' and not ticket.contometroc_id:
                errors.append("• Contador Color es requerido para equipos a color")
            if not ticket.informe_id:
                errors.append("• Informe Técnico es requerido")
    
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
    
            # ---- LOG DIAGNÓSTICO: COMPONENTES ----
            _logger.info(
                "[action_finalizar] ticket=%s | componentes eval=%s",
                ticket.id, len(ticket.ticket_componente_eval_ids)
            )
            for e in ticket.ticket_componente_eval_ids:
                nombre = e.componente_tipo_id.name if e.componente_tipo_id else "SIN_TIPO"
                if e.color_id:
                    nombre += f" ({e.color_id.name})"
                _logger.info(
                    "[action_finalizar] Componente: %s | estado_id: %r | "
                    "code: %s | requiere_cambio: %s",
                    nombre,
                    e.estado_id,
                    e.estado_id.code if e.estado_id else 'N/A',
                    e.estado_id.code == 'requiere_cambio' if e.estado_id else False,
                )
    
            # ---- LOG DIAGNÓSTICO: ACCESORIOS ----
            _logger.info(
                "[action_finalizar] ticket=%s | accesorios eval=%s",
                ticket.id, len(ticket.ticket_accesorio_eval_ids)
            )
            for e in ticket.ticket_accesorio_eval_ids:
                nombre = e.tipo_id.name if e.tipo_id else "SIN_TIPO"
                _logger.info(
                    "[action_finalizar] Accesorio: %s | estado_id: %r | "
                    "code: %s | requiere_cambio: %s",
                    nombre,
                    e.estado_id,
                    e.estado_id.code if e.estado_id else 'N/A',
                    e.estado_id.code == 'requiere_cambio' if e.estado_id else False,
                )
    
            # ---- VALIDAR EVALUACIONES DINÁMICAS ----
            ticket._validar_evaluaciones_ticket()
    
            # ================================================================
            # BIFURCACIÓN: ticket de instalación de repuestos vs ticket normal
            # ================================================================
    
            es_instalacion_repuestos = (
                ticket.tipo_servicio_id == 'cambio_repuestos'
                and bool(ticket.pedido_origen_id)
            )
    
            _logger.info(
                "[action_finalizar] ticket=%s | es_instalacion_repuestos=%s",
                ticket.id, es_instalacion_repuestos
            )
    
            if es_instalacion_repuestos:
                # ============================================================
                # FLUJO A — TICKET DE INSTALACIÓN DE REPUESTOS
                # No pasa por el wizard ni crea pedido nuevo.
                # Solo registra historial con contómetros reales.
                # ============================================================
                _logger.info(
                    "[action_finalizar] FLUJO A — instalación de repuestos | "
                    "ticket=%s pedido_origen=%s",
                    ticket.id, ticket.pedido_origen_id.name
                )
    
                ticket._registrar_historial_instalacion()
    
                try:
                    ticket.pedido_origen_id.action_marcar_instalado()
                    _logger.info(
                        "[action_finalizar] pedido_origen=%s marcado como instalado",
                        ticket.pedido_origen_id.name
                    )
                except Exception as e:
                    _logger.error(
                        "[action_finalizar] Error marcando pedido como instalado "
                        "ticket=%s pedido=%s error=%s",
                        ticket.id, ticket.pedido_origen_id.name, str(e)
                    )
    
            else:
                # ============================================================
                # FLUJO B — TICKET NORMAL
                #
                # Escenarios:
                # B1) sin requiere_cambio + sin pedido_especial
                #     → no hay wizard, no hay pedido, cierra normal
                #
                # B2) sin requiere_cambio + con pedido_especial
                #     → no hay wizard, crea pedido vacío en borrador
                #
                # B3) con requiere_cambio + sin pedido_especial
                #     → abre wizard → al confirmar regresa aquí con
                #       skip_subpartes_validation=True
                #     → crea pedido con subpartes y envía a gerencia
                #
                # B4) con requiere_cambio + con pedido_especial
                #     → abre wizard → al confirmar regresa aquí con
                #       skip_subpartes_validation=True
                #     → crea pedido con subpartes en borrador (no envía)
                #
                # B5) con requiere_cambio ya con subpartes (wizard ya procesado)
                #     → skip_subpartes_validation=True en contexto
                #     → crea pedido con subpartes (envía o no según pedido_especial)
                # ============================================================
    
                _logger.info(
                    "[action_finalizar] FLUJO B — ticket normal | "
                    "ticket=%s pedido_especial=%s skip_wizard=%s",
                    ticket.id,
                    ticket.pedido_especial,
                    self.env.context.get('skip_subpartes_validation', False),
                )
    
                # Verificar subpartes pendientes
                if not self.env.context.get('skip_subpartes_validation'):
                    pendientes = ticket._get_componentes_requieren_cambio_sin_subpartes()
                    _logger.info(
                        "[action_finalizar] ticket=%s | componentes pendientes "
                        "de subpartes=%s",
                        ticket.id, len(pendientes)
                    )
    
                    if pendientes:
                        _logger.info(
                            "[action_finalizar] ticket=%s → abriendo wizard "
                            "para %s componentes | pedido_especial=%s",
                            ticket.id, len(pendientes), ticket.pedido_especial
                        )
                        return ticket._abrir_wizard_subpartes(pendientes)
                else:
                    _logger.info(
                        "[action_finalizar] ticket=%s skip_subpartes_validation=True "
                        "— omitiendo verificación de wizard",
                        ticket.id
                    )
    
                # Determinar si crear pedido
                tiene_intervenciones = bool(
                    ticket.ticket_intervencion_ids.filtered(lambda x: x.detalle_ids)
                )
    
                _logger.info(
                    "[action_finalizar] ticket=%s | tiene_intervenciones=%s | "
                    "pedido_especial=%s",
                    ticket.id, tiene_intervenciones, ticket.pedido_especial
                )
    
                if tiene_intervenciones or ticket.pedido_especial:
                    _logger.info(
                        "[action_finalizar] ticket=%s → creando pedido de repuestos "
                        "(intervenciones=%s, especial=%s)",
                        ticket.id, tiene_intervenciones, ticket.pedido_especial
                    )
                    ticket._crear_pedido_repuestos()
                else:
                    _logger.info(
                        "[action_finalizar] ticket=%s → sin intervenciones y sin "
                        "pedido_especial — no se crea pedido",
                        ticket.id
                    )
    
            # ---- ENVIAR CORREO DE FINALIZACIÓN (todos los tickets) ----
            try:
                tmpl_fin = ticket.env.ref('sat.email_template_ticket_cliente_finalizacion')
                tmpl_fin.send_mail(ticket.id, force_send=True)
                _logger.info(
                    "[action_finalizar] correo finalización enviado ticket=%s",
                    ticket.id
                )
            except Exception as e:
                _logger.error(
                    "[action_finalizar] Error enviando correo finalización "
                    "ticket=%s: %s",
                    ticket.id, e
                )
    
            if ticket.retorno_id == 'no':
                try:
                    ticket.env.ref('sat.mail_template_retorno').send_mail(
                        ticket.id, force_send=True
                    )
                except Exception as e:
                    _logger.error(
                        "[action_finalizar] Error enviando correo retorno "
                        "ticket=%s: %s",
                        ticket.id, e
                    )
    
            # ---- ACTUALIZAR ESTADO DE LA UNIDAD ----
            unidad = ticket.product_alquiler
            if unidad:
                _logger.info(
                    "[action_finalizar] ticket=%s | tipo_servicio=%s | "
                    "estado_alquiler=%s | es_instalacion_repuestos=%s",
                    ticket.id,
                    ticket.tipo_servicio_id,
                    unidad.estado_alquiler_id,
                    es_instalacion_repuestos,
                )
    
                if ticket.tipo_servicio_id == 'alquiler' \
                        and unidad.estado_alquiler_id == 'sin_revisar':
                    unidad.write({'estado_alquiler_id': 'revisada'})
                    _logger.info(
                        "[action_finalizar] unidad=%s → revisada",
                        unidad.serie
                    )
    
                elif ticket.tipo_servicio_id == 'cambio_repuestos' \
                        and unidad.estado_alquiler_id == 'revisada':
                    prev = ticket.search([
                        ('product_alquiler', '=', unidad.id),
                        ('tipo_servicio_id', '=', 'alquiler')
                    ], order="create_date desc", limit=1)
                    if prev:
                        unidad.write({'estado_alquiler_id': 'lista'})
                        _logger.info(
                            "[action_finalizar] unidad=%s → lista",
                            unidad.serie
                        )
    
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
                        body=_(
                            "🏗️ Equipo instalado exitosamente.\n"
                            "Ticket: %s\nTécnico: %s"
                        ) % (ticket.name, ticket.responsable.name or 'N/A'),
                        message_type='notification',
                    )
                    _logger.info(
                        "[action_finalizar] unidad=%s → alquilada",
                        unidad.serie
                    )
    
                elif ticket.tipo_servicio_id == 'retiro':
                    unidad.write({
                        'estado_alquiler_id': 'sin_revisar',
                        'direccion':          'AV Angelica Gamarra 2156',
                        'contacto_id':        'Isidro',
                        'celular':            '975399303',
                        'correo_':            'soporte@andescopiers.com.pe',
                        'cliente_id':         1,
                        'fecha_inicio':       False,
                    })
                    _logger.info(
                        "[action_finalizar] unidad=%s → sin_revisar (retiro)",
                        unidad.serie
                    )
    
            # ---- MARCAR COMO FINALIZADO ----
            ticket.write({
                'estado':                    'finalizado',
                'last_pending_notification': False,
            })
    
            _logger.info(
                "[action_finalizar] ✅ Ticket %s finalizado correctamente | "
                "flujo=%s | pedido_especial=%s | es_instalacion=%s",
                ticket.id,
                'instalacion_repuestos' if es_instalacion_repuestos else 'normal',
                ticket.pedido_especial,
                es_instalacion_repuestos,
            )
    
        _logger.info("=== action_finalizar completado para tickets %s ===", self.ids)
    
        return {
            'type':      'ir.actions.act_window',
            'name':      'Tickets',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'view_id':   False,
            'target':    'main',
        }
    
    
    def _registrar_historial_instalacion(self):
        """
        Registra el historial de durabilidad usando los contómetros REALES
        del momento en que el técnico finaliza el ticket de instalación.
    
        Solo se llama desde action_finalizar cuando:
        - tipo_servicio == 'cambio_repuestos'
        - pedido_origen_id está definido
    
        Diferencia clave con el flujo anterior:
        - Antes: historial se creaba al aprobar el pedido (contómetros del ticket original)
        - Ahora: historial se crea al finalizar la instalación (contómetros reales)
    
        Lógica de tipo de contómetro:
        - color_id presente                  → tipo 'color'  (contómetro C)
        - color_id ausente + máquina color   → tipo 'total'  (K + C)
        - color_id ausente + máquina B/N     → tipo 'bn'     (contómetro K)
        """
        self.ensure_one()
    
        def _to_int(val):
            if not val:
                return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0
    
        pedido    = self.pedido_origen_id
        Historial = self.env['ticket.repuesto.historial']
    
        # Contómetros REALES del ticket de instalación
        contometro_k_real     = self.contometrok_id
        contometro_color_real = self.contometroc_id
        es_maquina_color      = (self.tipo_id == 'color')
    
        _logger.info(
            "[_registrar_historial_instalacion] ticket=%s | pedido=%s | "
            "contometro_k=%s | contometro_color=%s | es_color=%s | lineas=%s",
            self.name,
            pedido.name,
            contometro_k_real,
            contometro_color_real,
            es_maquina_color,
            len(pedido.linea_ids),
        )
    
        for linea in pedido.linea_ids:
    
            # ---- Determinar tipo y valor de contómetro ----
    
            if linea.color_id and contometro_color_real:
                # Componente de color (IU, drum, etc.) → contómetro Color
                contometro      = contometro_color_real
                tipo_contometro = 'color'
    
            elif not linea.color_id and es_maquina_color:
                # Sin color en máquina a color (fusor, ITB, faja) → K + C
                k     = _to_int(contometro_k_real)
                c     = _to_int(contometro_color_real)
                total = k + c
                if total > 0:
                    contometro = str(total)
                else:
                    contometro = contometro_k_real or '0'
                    _logger.warning(
                        "[_registrar_historial_instalacion] ticket=%s linea=%s "
                        "suma K+C=0, usando K como fallback",
                        self.name, linea.subparte_id.name
                    )
                tipo_contometro = 'total'
    
            else:
                # Máquina monocromática → solo K
                contometro      = contometro_k_real or '0'
                tipo_contometro = 'bn'
    
            _logger.info(
                "[_registrar_historial_instalacion] linea=%s | color=%s | "
                "tipo=%s | contometro=%s",
                linea.subparte_id.name,
                linea.color_id.name if linea.color_id else 'B/N',
                tipo_contometro,
                contometro,
            )
    
            historial = Historial.create({
                'pedido_id':         pedido.id,
                'ticket_id':         self.id,           # ticket de instalación (no el original)
                'equipo_id':         self.product_alquiler.id if self.product_alquiler else False,
                'subparte_id':       linea.subparte_id.id,
                'color_id':          linea.color_id.id if linea.color_id else False,
                'cantidad':          linea.cantidad,
                'contometro_cambio': contometro,
                'tipo_contometro':   tipo_contometro,
                'tecnico_id':        self.responsable.id if self.responsable else False,
                'fecha_cambio':      fields.Datetime.now(),
            })
    
            _logger.info(
                "[_registrar_historial_instalacion] historial creado — "
                "id=%s | subparte=%s | color=%s | tipo=%s | contometro=%s | "
                "copias=%s | meses=%s",
                historial.id,
                historial.subparte_id.name,
                historial.color_id.name if historial.color_id else 'B/N',
                historial.tipo_contometro,
                historial.contometro_cambio,
                historial.copias_duracion,
                historial.meses_duracion,
            )
    
        _logger.info(
            "[_registrar_historial_instalacion] completado — "
            "ticket=%s | pedido=%s | total_historiales=%s",
            self.name,
            pedido.name,
            len(pedido.linea_ids),
        )
    
    def action_ver_pedido_origen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedido de Repuestos',
            'res_model': 'ticket.repuesto.pedido',
            'res_id': self.pedido_origen_id.id,
            'view_mode': 'form',
            'target': 'current',
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
            start_datetime = fields.Datetime.to_datetime(self.agenda)
            duracion_horas = self._get_duracion_ticket_calendario()
            stop_datetime = start_datetime + timedelta(hours=duracion_horas)

            partner_ids = []

            if self.partner_id:
                partner_ids.append(self.partner_id.id)

            if self.responsable and self.responsable.partner_id:
                partner_ids.append(self.responsable.partner_id.id)

            tipo_servicio_label = dict(self._fields['tipo_servicio_id'].selection).get(
                self.tipo_servicio_id,
                self.tipo_servicio_id or 'NA'
            )

            event_vals = {
                'name': f"Visita Técnica - {self.name or 'NA'} - {self.partner_id.name or 'NA'}",
                'start': start_datetime,
                'stop': stop_datetime,
                'partner_ids': [(6, 0, partner_ids)],
                'user_id': self.responsable.id if self.responsable else None,
                'description': (
                    f"Ticket: {self.name}\n"
                    f"Cliente: {self.partner_id.name or 'NA'}\n"
                    f"Serie: {self.serie_id_r or 'NA'}\n"
                    f"Tipo de servicio: {tipo_servicio_label}\n"
                    f"Duración estimada: {duracion_horas} hora(s)"
                ),
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
            _logger.error(
                "Error creando evento calendario ticket %s: %s",
                self.id,
                str(e)
            )
            self.message_post(
                body=f"Error al gestionar evento de calendario: {str(e)}"
            )
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

            
            if current_k == 0:
                raise ValidationError(_("❗ El contómetro K no puede ser 0."))

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
        # ============================================================
    # ASIGNACIÓN MASIVA INTELIGENTE - HELPERS DE AGENDA
    # ============================================================

    def _get_duracion_servicio_masivo(self, tipo_servicio):
        """
        Devuelve la duración en horas para la asignación masiva.

        Regla principal:
        - Mantenimiento preventivo: 1 hora por máquina.
        - Otros servicios: 2 horas por defecto.
        """
        if tipo_servicio == 'mantenimiento_preventivo':
            return 1.0

        if tipo_servicio == 'remoto':
            return 1.0

        if tipo_servicio in ('revision', 'mantenimiento_correctivo', 'cambio_repuestos'):
            return 2.0

        if tipo_servicio in ('instalacion', 'retiro', 'alquiler'):
            return 2.0

        return 2.0

    def _get_duracion_ticket_calendario(self):
        """
        Devuelve la duración del ticket actual para crear/actualizar evento calendario.
        Se usa también para que el calendario no cree siempre eventos de 2 horas.
        """
        self.ensure_one()
        return self._get_duracion_servicio_masivo(self.tipo_servicio_id)

    def _get_horarios_laborales_masivo(self, fecha_dt):
        """
        Horarios de búsqueda para asignación masiva.

        Por ahora usamos jornada estándar:
        - Mañana: 09:00 a 13:00
        - Tarde: 14:00 a 18:00

        Si luego quieres usar el perfil del técnico, aquí se puede extender.
        """
        fecha = fecha_dt.date()

        return [
            (
                fecha_dt.replace(hour=9, minute=0, second=0, microsecond=0),
                fecha_dt.replace(hour=13, minute=0, second=0, microsecond=0),
            ),
            (
                fecha_dt.replace(hour=14, minute=0, second=0, microsecond=0),
                fecha_dt.replace(hour=18, minute=0, second=0, microsecond=0),
            ),
        ]

    def _normalizar_inicio_bloque_masivo(self, fecha_dt):
        """
        Normaliza la hora inicial.
        Si el usuario coloca 09:15, se redondea a 10:00.
        Si coloca 09:00, se mantiene 09:00.
        """
        fecha_dt = fields.Datetime.to_datetime(fecha_dt)

        if fecha_dt.minute == 0 and fecha_dt.second == 0:
            return fecha_dt.replace(second=0, microsecond=0)

        fecha_dt = fecha_dt.replace(second=0, microsecond=0)
        return fecha_dt.replace(minute=0) + timedelta(hours=1)

    def _ticket_cruza_horario_masivo(
        self,
        tecnico_id,
        inicio_dt,
        fin_dt,
        excluir_ticket_id=False,
        ocupaciones_temporales=None,
    ):
        """
        Valida si el técnico tiene un cruce real en ese rango.

        Revisa:
        1. Tickets existentes en BD.
        2. Tickets del mismo lote que aún no se han escrito, mediante ocupaciones_temporales.
        """
        ocupaciones_temporales = ocupaciones_temporales or []

        # 1. Revisar cruces temporales del mismo lote
        for ocupacion in ocupaciones_temporales:
            if ocupacion.get('tecnico_id') != tecnico_id:
                continue

            ocupado_inicio = ocupacion.get('inicio')
            ocupado_fin = ocupacion.get('fin')

            if ocupado_inicio and ocupado_fin:
                if ocupado_inicio < fin_dt and ocupado_fin > inicio_dt:
                    return True

        # 2. Revisar tickets existentes en BD
        domain = [
            ('responsable', '=', tecnico_id),
            ('agenda', '!=', False),
            ('estado', 'not in', ['finalizado']),
        ]

        if excluir_ticket_id:
            domain.append(('id', '!=', excluir_ticket_id))

        tickets = self.search(domain)

        for ticket in tickets:
            if not ticket.agenda:
                continue

            ticket_inicio = fields.Datetime.to_datetime(ticket.agenda)
            duracion = ticket._get_duracion_ticket_calendario()
            ticket_fin = ticket_inicio + timedelta(hours=duracion)

            if ticket_inicio < fin_dt and ticket_fin > inicio_dt:
                return True

        return False

    def _buscar_siguiente_agenda_libre_masiva(
        self,
        tecnico,
        fecha_inicio,
        duracion_horas,
        excluir_ticket_id=False,
        ocupaciones_temporales=None,
        dias_busqueda=10,
    ):
        """
        Busca el siguiente horario libre para el técnico.

        Ejemplo:
        - Si empieza 09:00 y mantenimiento dura 1 hora:
          09:00, 10:00, 11:00, 12:00, 14:00, 15:00...

        Si un bloque está ocupado, salta al siguiente.
        Si no alcanza el día, pasa al siguiente día.
        """
        if not tecnico:
            raise UserError(_("Debe indicar un técnico para buscar agenda libre."))

        if not fecha_inicio:
            raise UserError(_("Debe indicar fecha de visita para la asignación masiva."))

        fecha_inicio = self._normalizar_inicio_bloque_masivo(fecha_inicio)
        ocupaciones_temporales = ocupaciones_temporales or []

        paso_minutos = int(duracion_horas * 60)
        if paso_minutos <= 0:
            paso_minutos = 60

        for dia_offset in range(0, dias_busqueda + 1):
            fecha_base = fecha_inicio + timedelta(days=dia_offset)
            ventanas = self._get_horarios_laborales_masivo(fecha_base)

            for ventana_inicio, ventana_fin in ventanas:
                # El primer día respetamos la hora indicada por el usuario.
                # Los siguientes días empezamos desde la ventana laboral.
                if dia_offset == 0:
                    cursor = max(fecha_inicio, ventana_inicio)
                else:
                    cursor = ventana_inicio

                while cursor + timedelta(hours=duracion_horas) <= ventana_fin:
                    inicio_dt = cursor
                    fin_dt = cursor + timedelta(hours=duracion_horas)

                    ocupado = self._ticket_cruza_horario_masivo(
                        tecnico_id=tecnico.id,
                        inicio_dt=inicio_dt,
                        fin_dt=fin_dt,
                        excluir_ticket_id=excluir_ticket_id,
                        ocupaciones_temporales=ocupaciones_temporales,
                    )

                    if not ocupado:
                        return inicio_dt

                    cursor += timedelta(minutes=paso_minutos)

        raise UserError(_(
            "No se encontró horario libre para el técnico %s desde %s "
            "en los próximos %s días."
        ) % (
            tecnico.name,
            fecha_inicio.strftime('%d/%m/%Y %H:%M'),
            dias_busqueda,
        ))

    def _ordenar_ticket_lines_masivo(self, ticket_lines):
        """
        Ordena los tickets para que la ruta quede más lógica:
        1. Cliente
        2. Dirección
        3. Distrito aproximado desde el equipo
        4. Serie
        5. Ticket

        ticket_lines es una lista de diccionarios recibida desde wizard_data.
        """
        def _key(line_data):
            ticket = self.browse(line_data.get('ticket_id'))

            cliente = ticket.partner_id.name or ''
            direccion = ticket.direccion_id_r or ''

            distrito = ''
            if ticket.product_alquiler:
                distrito = getattr(ticket.product_alquiler, 'distrito', '') or ''

            serie = ticket.serie_id_r or ''
            name = ticket.name or ''

            return (
                cliente.lower(),
                direccion.lower(),
                distrito.lower(),
                serie.lower(),
                name.lower(),
            )

        return sorted(ticket_lines, key=_key)
    def _procesar_asignacion_masiva(self, wizard_data):
        """
        Procesa la asignación masiva con agenda inteligente y logs completos.

        Objetivo:
        - Evitar que todos los tickets reciban la misma hora.
        - Asignar horarios consecutivos.
        - Detectar exactamente dónde falla:
          cálculo de horarios, write del ticket, eventos, WhatsApp, correos o consolidado.
        """
        _logger.warning(
            "🟣 [ASIGNACION MASIVA][INICIO] self_ids=%s wizard_keys=%s",
            self.ids,
            list(wizard_data.keys()) if wizard_data else [],
        )

        tecnico = wizard_data.get('tecnico_asignado')
        fecha_visita = wizard_data.get('fecha_visita')
        asistencia_directa = wizard_data.get('asistencia_directa', 'no')
        ticket_lines = wizard_data.get('ticket_lines', [])

        _logger.warning(
            "🟣 [ASIGNACION MASIVA][DATA] tecnico=%s tecnico_id=%s fecha_visita=%s asistencia=%s total_ticket_lines=%s self_count=%s",
            tecnico.name if tecnico else False,
            tecnico.id if tecnico else False,
            fecha_visita,
            asistencia_directa,
            len(ticket_lines),
            len(self),
        )

        if not tecnico:
            _logger.error("🔴 [ASIGNACION MASIVA] No se recibió técnico.")
            raise UserError(_("Debe asignar un técnico responsable para todos los tickets."))

        if not fecha_visita:
            _logger.error("🔴 [ASIGNACION MASIVA] No se recibió fecha_visita.")
            raise UserError(_("Debe asignar una fecha de visita para todos los tickets."))

        if not ticket_lines:
            _logger.error("🔴 [ASIGNACION MASIVA] No se recibieron ticket_lines.")
            raise UserError(_("No se encontraron tickets para procesar."))

        # ============================================================
        # 1. ORDENAR TICKETS
        # ============================================================
        try:
            ticket_lines_ordenadas = self._ordenar_ticket_lines_masivo(ticket_lines)
            _logger.warning(
                "🟣 [ASIGNACION MASIVA][ORDEN] líneas ordenadas=%s",
                ticket_lines_ordenadas,
            )
        except Exception as e:
            _logger.error(
                "🔴 [ASIGNACION MASIVA][ORDEN] Error ordenando tickets: %s",
                str(e),
                exc_info=True,
            )
            raise

        ocupaciones_temporales = []
        asignaciones = []

        fecha_cursor = fields.Datetime.to_datetime(fecha_visita)

        _logger.warning(
            "🟣 [ASIGNACION MASIVA][CURSOR_INICIAL] fecha_cursor=%s",
            fecha_cursor,
        )

        # ============================================================
        # 2. CALCULAR AGENDA LIBRE POR TICKET
        # ============================================================
        for index, ticket_data in enumerate(ticket_lines_ordenadas, start=1):
            ticket = self.browse(ticket_data.get('ticket_id'))

            _logger.warning(
                "🟣 [ASIGNACION MASIVA][CALCULO][%s] ticket_data=%s ticket_exists=%s",
                index,
                ticket_data,
                ticket.exists(),
            )

            if not ticket.exists():
                _logger.warning(
                    "🟡 [ASIGNACION MASIVA][CALCULO][%s] Ticket no existe, se omite. data=%s",
                    index,
                    ticket_data,
                )
                continue

            tipo_servicio = ticket_data.get('tipo_servicio_id') or ticket.tipo_servicio_id or 'revision'
            duracion_horas = self._get_duracion_servicio_masivo(tipo_servicio)

            _logger.warning(
                "🟣 [ASIGNACION MASIVA][CALCULO][%s] ticket=%s tipo=%s duracion=%s fecha_cursor=%s responsable_actual=%s agenda_actual=%s estado_actual=%s",
                index,
                ticket.name,
                tipo_servicio,
                duracion_horas,
                fecha_cursor,
                ticket.responsable.name if ticket.responsable else False,
                ticket.agenda,
                ticket.estado,
            )

            try:
                agenda_libre = self._buscar_siguiente_agenda_libre_masiva(
                    tecnico=tecnico,
                    fecha_inicio=fecha_cursor,
                    duracion_horas=duracion_horas,
                    excluir_ticket_id=ticket.id,
                    ocupaciones_temporales=ocupaciones_temporales,
                    dias_busqueda=10,
                )
            except Exception as e:
                _logger.error(
                    "🔴 [ASIGNACION MASIVA][CALCULO][%s] Error buscando agenda libre para ticket=%s tecnico=%s fecha_cursor=%s duracion=%s error=%s",
                    index,
                    ticket.name,
                    tecnico.name,
                    fecha_cursor,
                    duracion_horas,
                    str(e),
                    exc_info=True,
                )
                raise

            agenda_fin = agenda_libre + timedelta(hours=duracion_horas)

            ocupaciones_temporales.append({
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'tecnico_id': tecnico.id,
                'inicio': agenda_libre,
                'fin': agenda_fin,
                'tipo_servicio_id': tipo_servicio,
                'duracion_horas': duracion_horas,
            })

            asignaciones.append({
                'ticket': ticket,
                'tipo_servicio_id': tipo_servicio,
                'agenda': agenda_libre,
                'agenda_fin': agenda_fin,
                'duracion_horas': duracion_horas,
                'observaciones': ticket_data.get('observaciones') or '',
            })

            fecha_cursor = agenda_fin

            _logger.warning(
                "🟢 [ASIGNACION MASIVA][SLOT][%s] ticket=%s tecnico=%s inicio=%s fin=%s tipo=%s duracion=%s",
                index,
                ticket.name,
                tecnico.name,
                agenda_libre.strftime('%d/%m/%Y %H:%M'),
                agenda_fin.strftime('%d/%m/%Y %H:%M'),
                tipo_servicio,
                duracion_horas,
            )

        _logger.warning(
            "🟣 [ASIGNACION MASIVA][RESUMEN_SLOTS] total_asignaciones=%s ocupaciones_temporales=%s",
            len(asignaciones),
            ocupaciones_temporales,
        )

        if not asignaciones:
            _logger.error("🔴 [ASIGNACION MASIVA] No se pudo preparar ninguna asignación.")
            raise UserError(_("No se pudo preparar ninguna asignación."))

        # ============================================================
        # 3. ESCRIBIR TICKETS UNO POR UNO
        # ============================================================
        tickets_escritos = self.env['ticket.alquiler']

        for index, item in enumerate(asignaciones, start=1):
            ticket = item['ticket']

            valores_ticket = {
                'responsable': tecnico.id,
                'agenda': item['agenda'],
                'asistencia_id': asistencia_directa,
                'tipo_servicio_id': item['tipo_servicio_id'],
                'estado': 'proceso',
            }

            _logger.warning(
                "🟣 [ASIGNACION MASIVA][WRITE][%s][ANTES] ticket=%s id=%s vals=%s",
                index,
                ticket.name,
                ticket.id,
                valores_ticket,
            )

            try:
                ticket.write(valores_ticket)
                tickets_escritos |= ticket

                _logger.warning(
                    "🟢 [ASIGNACION MASIVA][WRITE][%s][OK] ticket=%s nueva_agenda=%s responsable=%s estado=%s",
                    index,
                    ticket.name,
                    ticket.agenda,
                    ticket.responsable.name if ticket.responsable else False,
                    ticket.estado,
                )

            except Exception as e:
                _logger.error(
                    "🔴 [ASIGNACION MASIVA][WRITE][%s][ERROR] ticket=%s id=%s vals=%s error=%s",
                    index,
                    ticket.name,
                    ticket.id,
                    valores_ticket,
                    str(e),
                    exc_info=True,
                )
                raise

            # Chatter individual
            try:
                tipo_label = dict(ticket._fields['tipo_servicio_id'].selection).get(
                    item['tipo_servicio_id'],
                    item['tipo_servicio_id']
                )

                mensaje = _(
                    "📅 <b>Agenda asignada automáticamente por asignación masiva</b><br/>"
                    "👨‍🔧 <b>Técnico:</b> %s<br/>"
                    "🕒 <b>Horario:</b> %s - %s<br/>"
                    "🔧 <b>Tipo de servicio:</b> %s<br/>"
                    "⏱️ <b>Duración estimada:</b> %s hora(s)"
                ) % (
                    tecnico.name,
                    item['agenda'].strftime('%d/%m/%Y %H:%M'),
                    item['agenda_fin'].strftime('%H:%M'),
                    tipo_label,
                    item['duracion_horas'],
                )

                if item.get('observaciones'):
                    mensaje += _("<br/>📝 <b>Observaciones:</b> %s") % item['observaciones']

                ticket.message_post(
                    body=mensaje,
                    message_type='notification'
                )

                _logger.warning(
                    "🟢 [ASIGNACION MASIVA][CHATTER][%s][OK] ticket=%s",
                    index,
                    ticket.name,
                )

            except Exception as e:
                _logger.error(
                    "🔴 [ASIGNACION MASIVA][CHATTER][%s][ERROR] ticket=%s error=%s",
                    index,
                    ticket.name,
                    str(e),
                    exc_info=True,
                )
                # No detenemos el proceso solo por chatter.

        # ============================================================
        # 4. AGRUPAR TICKETS YA ESCRITOS
        # ============================================================
        grupos = {}

        _logger.warning(
            "🟣 [ASIGNACION MASIVA][AGRUPAR] tickets_escritos=%s",
            tickets_escritos.ids,
        )

        for ticket in tickets_escritos:
            key = (
                ticket.partner_id.id if ticket.partner_id else 0,
                ticket.responsable.id if ticket.responsable else 0,
            )

            if key not in grupos:
                grupos[key] = {
                    'cliente': ticket.partner_id,
                    'tecnico': ticket.responsable,
                    'tickets': self.env['ticket.alquiler'],
                }

            grupos[key]['tickets'] |= ticket

            _logger.warning(
                "🟣 [ASIGNACION MASIVA][AGRUPAR] ticket=%s key=%s cliente=%s tecnico=%s agenda=%s",
                ticket.name,
                key,
                ticket.partner_id.name if ticket.partner_id else False,
                ticket.responsable.name if ticket.responsable else False,
                ticket.agenda,
            )

        _logger.warning(
            "🟣 [ASIGNACION MASIVA][GRUPOS] total_grupos=%s keys=%s",
            len(grupos),
            list(grupos.keys()),
        )

        # ============================================================
        # 5. PROCESAR FLUJO CONSOLIDADO
        # Aquí puede entrar WhatsApp, correos, calendario, gerente, etc.
        # Si falla aquí, ya sabremos que los writes sí pasaron.
        # ============================================================
        for index, grupo_data in enumerate(grupos.values(), start=1):
            _logger.warning(
                "🟣 [ASIGNACION MASIVA][GRUPO][%s][ANTES] cliente=%s tecnico=%s tickets=%s",
                index,
                grupo_data['cliente'].name if grupo_data.get('cliente') else False,
                grupo_data['tecnico'].name if grupo_data.get('tecnico') else False,
                grupo_data['tickets'].ids,
            )

            try:
                self._procesar_grupo_tickets_consolidado(grupo_data, wizard_data)

                _logger.warning(
                    "🟢 [ASIGNACION MASIVA][GRUPO][%s][OK] tickets=%s",
                    index,
                    grupo_data['tickets'].ids,
                )

            except Exception as e:
                _logger.error(
                    "🔴 [ASIGNACION MASIVA][GRUPO][%s][ERROR] cliente=%s tecnico=%s tickets=%s error=%s",
                    index,
                    grupo_data['cliente'].name if grupo_data.get('cliente') else False,
                    grupo_data['tecnico'].name if grupo_data.get('tecnico') else False,
                    grupo_data['tickets'].ids,
                    str(e),
                    exc_info=True,
                )
                raise

        _logger.warning(
            "🟢 [ASIGNACION MASIVA][FIN] completado tecnico=%s tickets_escritos=%s total=%s",
            tecnico.name,
            tickets_escritos.ids,
            len(tickets_escritos),
        )

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
        # subpartes_por_eval: { eval_id: [{'nombre': str, 'cantidad': float}] }
        subpartes_por_eval = {}
 
        for doc in docs:
            selection_labels[doc.id] = doc.get_selection_labels() if doc else {}
 
            # Construir índice de intervenciones por componente_code para este ticket
            intervencion_por_code = {}
            for intervencion in doc.ticket_intervencion_ids:
                if intervencion.detalle_ids:
                    intervencion_por_code[intervencion.componente_code] = intervencion
 
            # Para cada evaluación de componente con estado requiere_cambio
            for eval_comp in doc.ticket_componente_eval_ids:
                if not eval_comp.estado_id or eval_comp.estado_id.code != 'requiere_cambio':
                    subpartes_por_eval[eval_comp.id] = []
                    continue
 
                tipo = eval_comp.componente_tipo_id
                if not tipo:
                    subpartes_por_eval[eval_comp.id] = []
                    continue
 
                # Construir el mismo código dinámico que usa el wizard
                base_code = f"t{tipo.id}"
                color_code = False
                if getattr(tipo, 'is_color_sensitive', False):
                    if eval_comp.color_id and eval_comp.color_id.code:
                        color_code = eval_comp.color_id.code.lower()
                componente_code = f"{base_code}_{color_code}" if color_code else base_code
 
                intervencion = intervencion_por_code.get(componente_code)
                if intervencion:
                    subpartes_por_eval[eval_comp.id] = [
                        {
                            'nombre': d.subparte_id.name,
                            'cantidad': d.cantidad,
                            'observacion': d.observacion or '',
                        }
                        for d in intervencion.detalle_ids
                        if d.subparte_id
                    ]
                else:
                    subpartes_por_eval[eval_comp.id] = []
 
            # Accesorios con requiere_cambio
            for eval_acc in doc.ticket_accesorio_eval_ids:
                if not eval_acc.estado_id or eval_acc.estado_id.code != 'requiere_cambio':
                    subpartes_por_eval[eval_acc.id] = []
                    continue
 
                tipo = eval_acc.tipo_id
                if not tipo:
                    subpartes_por_eval[eval_acc.id] = []
                    continue
 
                componente_code = f"a{tipo.id}"
                intervencion = intervencion_por_code.get(componente_code)
                if intervencion:
                    subpartes_por_eval[eval_acc.id] = [
                        {
                            'nombre': d.subparte_id.name,
                            'cantidad': d.cantidad,
                            'observacion': d.observacion or '',
                        }
                        for d in intervencion.detalle_ids
                        if d.subparte_id
                    ]
                else:
                    subpartes_por_eval[eval_acc.id] = []
 
        return {
            'doc_ids': docids,
            'doc_model': 'ticket.alquiler',
            'docs': docs,
            'selection_labels': selection_labels,
            'subpartes_por_eval': subpartes_por_eval,
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
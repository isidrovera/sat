# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import re
import uuid

_logger = logging.getLogger(__name__)

EMAIL_GERENCIA  = 'lincoln@corapsac.com'
EMAIL_COMERCIAL = 'comercial01@andescopiers.com.pe'
EMAIL_LOGISTICA = 'logistica@corapsac.com'
EMAIL_SOPORTE   = 'soporte@andescopiers.com.pe'


class TicketRepuestoPedido(models.Model):
    _name = 'ticket.repuesto.pedido'
    _description = 'Pedido de Repuestos generado desde Ticket de Servicio'
    _order = 'fecha desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Pedido N°', default=lambda self: _('New'), copy=False, readonly=True, required=True, tracking=True)
    token = fields.Char(string='Token de acceso', copy=False, readonly=True, index=True)
    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket origen', required=True, ondelete='restrict', index=True, tracking=True)
    cliente_id = fields.Many2one(related='ticket_id.partner_id', string='Cliente', store=True, readonly=True)
    equipo_id = fields.Many2one(related='ticket_id.product_alquiler', string='Equipo', store=True, readonly=True)
    modelo_nombre = fields.Char(related='ticket_id.modelo_id_r', string='Modelo', store=True, readonly=True)
    serie = fields.Char(related='ticket_id.serie_id_r', string='Serie', store=True, readonly=True)
    tecnico_id = fields.Many2one(related='ticket_id.responsable', string='Técnico', store=True, readonly=True)
    contometro_k = fields.Char(related='ticket_id.contometrok_id', string='Contómetro K (B/N)', store=True, readonly=True)
    contometro_color = fields.Char(related='ticket_id.contometroc_id', string='Contómetro Color', store=True, readonly=True)
    contometro_actual = fields.Char(related='ticket_id.contometrok_id', string='Contómetro actual', store=True, readonly=True)

    estado = fields.Selection([
        ('borrador',           'Borrador'),
        ('esperando_gerencia', 'Esperando Gerencia'),
        ('informe_solicitado', 'Informe solicitado a Comercial'),
        ('informe_recibido',   'Informe recibido — en revisión'),
        ('aprobado',           'Aprobado por Gerencia'),
        ('rechazado',          'Rechazado'),
        ('stock_en_revision',  'Comercial revisando stock'),
        ('stock_completo',     'Stock confirmado'),
        ('en_camino',          'Logística preparando entrega'),
        ('entregado',          'Entregado al técnico'),
        ('instalado',          'Instalado'),
        ('cancelado',          'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True)

    fecha = fields.Datetime(string='Fecha de creación', default=fields.Datetime.now, readonly=True)
    fecha_envio_gerencia = fields.Datetime(string='Enviado a Gerencia', readonly=True, tracking=True)
    gerente_id = fields.Many2one('res.users', string='Gestionado por Gerencia', readonly=True, tracking=True)
    fecha_aprobacion = fields.Datetime(string='Fecha de aprobación', readonly=True, tracking=True)
    motivo_rechazo = fields.Text(string='Motivo de rechazo', tracking=True)
    fecha_solicitud_informe = fields.Datetime(string='Informe solicitado el', readonly=True, tracking=True)
    informe_adjunto = fields.Binary(string='Informe adjunto', attachment=True)
    informe_adjunto_nombre = fields.Char(string='Nombre archivo informe')
    fecha_informe_recibido = fields.Datetime(string='Informe recibido el', readonly=True, tracking=True)
    nota_comercial = fields.Text(string='Nota de Comercial', tracking=True)
    fecha_stock_completo = fields.Datetime(string='Stock confirmado el', readonly=True, tracking=True)
    fecha_entrega = fields.Datetime(string='Entregado el', readonly=True, tracking=True)
    nota_logistica = fields.Text(string='Nota de Logística', tracking=True)
    ticket_instalacion_id = fields.Many2one('ticket.alquiler', string='Ticket de instalación', readonly=True, tracking=True)
    fecha_instalacion = fields.Datetime(string='Instalado el', readonly=True, tracking=True)
    aprobado_por = fields.Many2one(related='gerente_id', string='Aprobado por', store=True, readonly=True)
    observaciones = fields.Text(string='Observaciones', tracking=True)

    linea_ids = fields.One2many('ticket.repuesto.pedido.linea', 'pedido_id', string='Repuestos solicitados')
    total_lineas = fields.Integer(string='Total de líneas', compute='_compute_total_lineas', store=True)
    lineas_sin_stock = fields.Integer(string='Líneas sin stock', compute='_compute_stock_status', store=False)
    todas_disponibles = fields.Boolean(string='Todas disponibles', compute='_compute_stock_status', store=False)

    @api.depends('linea_ids')
    def _compute_total_lineas(self):
        for record in self:
            record.total_lineas = len(record.linea_ids)

    @api.depends('linea_ids.estado_stock')
    def _compute_stock_status(self):
        for record in self:
            sin_stock = record.linea_ids.filtered(lambda l: l.estado_stock not in ('disponible', 'recibido'))
            record.lineas_sin_stock  = len(sin_stock)
            record.todas_disponibles = len(record.linea_ids) > 0 and len(sin_stock) == 0

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code('ticket.repuesto.pedido') or '/'
        if not vals.get('token'):
            vals['token'] = str(uuid.uuid4()).replace('-', '')
        _logger.info("[ticket.repuesto.pedido] create() — ticket_id=%s | name=%s", vals.get('ticket_id'), vals.get('name'))
        return super().create(vals)

    # ============================================================
    # HELPERS
    # ============================================================

    def action_ver_ticket_instalacion(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Ticket de Instalación', 'res_model': 'ticket.alquiler', 'res_id': self.ticket_instalacion_id.id, 'view_mode': 'form', 'target': 'current'}

    def _get_base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')

    def _url_accion(self, accion):
        return f"{self._get_base_url()}/pedido/{self.token}/{accion}"

    def _lineas_html(self, con_historial=False):
        def _fmt_num(val):
            try:
                return f"{int(re.sub(r'[^\d]', '', str(val)) or 0):,}"
            except Exception:
                return str(val) if val else '—'

        def _cont_actual_linea(linea):
            def _to_int(v):
                if not v: return 0
                d = re.sub(r'[^\d]', '', str(v))
                return int(d) if d else 0
            k = _to_int(self.contometro_k)
            c = _to_int(self.contometro_color)
            es_color = bool(self.contometro_color)
            if linea.color_id: return self.contometro_color or '0'
            elif es_color: return str(k + c) if (k + c) > 0 else '0'
            else: return self.contometro_k or '0'

        filas = ''
        for i, l in enumerate(self.linea_ids, 1):
            color = l.color_id.name if l.color_id else 'B/N'
            bg    = '#f9fafb' if i % 2 == 0 else '#ffffff'
            color_bg = {'Black': '#374151', 'Cyan': '#0891b2', 'Magenta': '#db2777', 'Yellow': '#d97706', 'B/N': '#6b7280'}.get(color, '#6b7280')
            badge_color = f"<span style='background:{color_bg};color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:bold;'>{color}</span>"
            fila_base = (
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;color:#9ca3af;text-align:center;'>{i}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;'><b style='color:#1f2d3d;'>{l.componente_display or '—'}</b></td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;'>{l.subparte_id.name or '—'}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:center;'>{badge_color}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:center;'>{int(l.cantidad)}</td>"
            )
            if con_historial:
                cont_actual   = _cont_actual_linea(l)
                cont_anterior = l.ultimo_cambio_contometro or ''
                fecha_ult = meses_ult = diferencia = ''
                dif_color = '#374151'
                if l.ultimo_cambio_fecha:
                    fecha_ult = l.ultimo_cambio_fecha.strftime('%d/%m/%Y')
                    meses_ult = str(l.meses_desde_ultimo_cambio) + 'm'
                if cont_anterior:
                    try:
                        ca = int(re.sub(r'[^\d]', '', str(cont_actual)) or 0)
                        cp = int(re.sub(r'[^\d]', '', str(cont_anterior)) or 0)
                        df = ca - cp
                        diferencia = f"+{df:,}" if df >= 0 else f"{df:,}"
                        dif_color  = '#059669' if df >= 0 else '#DC2626'
                    except Exception:
                        diferencia = '—'
                else:
                    diferencia = '<i style="color:#9ca3af;">Primer cambio</i>'
                fila_base += (
                    f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:right;font-family:monospace;font-size:11px;'>{_fmt_num(cont_actual)}</td>"
                    f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:right;font-family:monospace;font-size:11px;color:#6b7280;'>{_fmt_num(cont_anterior) if cont_anterior else '<i style=\"color:#9ca3af;\">Sin registro</i>'}</td>"
                    f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:right;font-weight:bold;color:{dif_color};font-size:11px;'>{diferencia}</td>"
                    f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:center;font-size:11px;color:#6b7280;'>{fecha_ult or '<i style=\"color:#9ca3af;\">—</i>'}</td>"
                    f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:center;font-size:11px;'>{meses_ult or '<i style=\"color:#9ca3af;\">—</i>'}</td>"
                )
            filas += f"<tr style='background:{bg};'>{fila_base}</tr>"

        thead_base = (
            "<th style='padding:7px 8px;text-align:center;'>#</th>"
            "<th style='padding:7px 8px;text-align:left;'>Componente</th>"
            "<th style='padding:7px 8px;text-align:left;'>Subparte / Repuesto</th>"
            "<th style='padding:7px 8px;text-align:center;'>Color</th>"
            "<th style='padding:7px 8px;text-align:center;'>Cant.</th>"
        )
        if con_historial:
            thead_base += (
                "<th style='padding:7px 8px;text-align:right;'>Cont. Actual</th>"
                "<th style='padding:7px 8px;text-align:right;'>Cont. Anterior</th>"
                "<th style='padding:7px 8px;text-align:right;'>Diferencia</th>"
                "<th style='padding:7px 8px;text-align:center;'>Último Cambio</th>"
                "<th style='padding:7px 8px;text-align:center;'>Meses</th>"
            )
        return (
            "<table style='width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px;'>"
            f"<thead><tr style='background:#1B3A6B;color:#fff;'>{thead_base}</tr></thead>"
            f"<tbody>{filas}</tbody></table>"
        )

    def _boton_html(self, url, texto, color='#1B3A6B'):
        return (f"<a href='{url}' style='display:inline-block;padding:10px 22px;background:{color};color:#fff;text-decoration:none;border-radius:5px;font-weight:bold;font-size:13px;margin:5px;'>{texto}</a>")

    def _header_correo(self, titulo, subtitulo='', color='#1B3A6B'):
        return (f"<div style='background:{color};color:#fff;padding:16px 20px;border-radius:6px 6px 0 0;'><h2 style='margin:0;'>{titulo}</h2>{'<p style=margin:4px 0 0 0;opacity:0.85;>' + subtitulo + '</p>' if subtitulo else ''}</div>")

    def _footer_correo(self):
        return "<p style='font-size:11px;color:#9ca3af;text-align:center;margin-top:16px;'>Andes Copiers SAC — Sistema de Taller SAT</p>"

    def _info_pedido_html(self):
        return (f"<p><b>Pedido N°:</b> {self.name}<br/><b>Modelo:</b> {self.modelo_nombre or '—'} | <b>Serie:</b> {self.serie or '—'}<br/><b>Cliente:</b> {self.cliente_id.name or '—'}<br/><b>Técnico:</b> {self.tecnico_id.name or '—'}<br/><b>Total repuestos:</b> {self.total_lineas}</p>")

    def _get_smtp_server(self):
        """Obtiene el servidor SMTP por nombre 'SMTP' o el primero disponible."""
        IrMailServer = self.env['ir.mail_server'].sudo()
        server = IrMailServer.search([('name', '=', 'SMTP')], limit=1)
        if not server:
            server = IrMailServer.search([], order='id asc', limit=1)
        return server

    def _enviar_correo_simple(self, email_to, asunto, cuerpo_html):
        self.ensure_one()
        try:
            smtp_server = self._get_smtp_server()
            mail_vals = {
                'subject':    asunto,
                'email_to':   email_to,
                'email_from': 'soporte@andescopiers.com.pe',
                'body_html':  cuerpo_html,
                'auto_delete': True,
            }
            if smtp_server:
                mail_vals['mail_server_id'] = smtp_server.id
            mail = self.env['mail.mail'].sudo().create(mail_vals)
            mail.send()
            _logger.info("[correo] pedido=%s | to=%s | server=%s | asunto=%s",
                        self.name, email_to, smtp_server.name if smtp_server else 'default', asunto)
        except Exception as e:
            _logger.error("[correo] ERROR pedido=%s | to=%s | error=%s", self.name, email_to, str(e))
    def _wrap_correo(self, header_html, contenido_html):
        return (f"<div style='font-family:Arial,sans-serif;max-width:700px;margin:0 auto;'>{header_html}<div style='background:#f9fafb;border:1px solid #e5e7eb;padding:16px 20px;'>{contenido_html}{self._footer_correo()}</div></div>")

    def _guardar_snapshot_lineas(self):
        self.ensure_one()
        def _to_int(val):
            if not val: return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0
        es_color = (self.equipo_id.tipo_maquina_id == 'color')
        k = _to_int(self.contometro_k)
        c = _to_int(self.contometro_color)
        _logger.info("[_guardar_snapshot_lineas] pedido=%s | K=%s | C=%s | es_color=%s", self.name, k, c, es_color)
        for linea in self.linea_ids:
            if linea.color_id: cont_actual = self.contometro_color or '0'
            elif es_color: cont_actual = str(k + c) if (k + c) > 0 else '0'
            else: cont_actual = self.contometro_k or '0'
            domain = [('equipo_id', '=', self.equipo_id.id), ('subparte_id', '=', linea.subparte_id.id), ('pedido_id', '!=', self.id)]
            if linea.color_id: domain.append(('color_id', '=', linea.color_id.id))
            else: domain.append(('color_id', '=', False))
            ultimo = self.env['ticket.repuesto.historial'].sudo().search(domain, order='fecha_cambio desc', limit=1)
            cont_anterior = ultimo.contometro_cambio if ultimo else ''
            meses = copias = 0
            if ultimo and ultimo.fecha_cambio:
                diff = relativedelta(datetime.now(), ultimo.fecha_cambio)
                meses = diff.months + (diff.years * 12)
            if cont_anterior:
                copias = max(0, _to_int(cont_actual) - _to_int(cont_anterior))
            linea.write({'contometro_actual_snapshot': cont_actual, 'contometro_anterior_snapshot': cont_anterior, 'copias_snapshot': copias, 'meses_snapshot': meses})
            _logger.info("[snapshot] linea=%s | color=%s | actual=%s | anterior=%s | copias=%s | meses=%s", linea.subparte_id.name, linea.color_id.name if linea.color_id else 'B/N', cont_actual, cont_anterior, copias, meses)

    # ============================================================
    # PASO 1 — enviar a Gerencia
    # ============================================================

    def action_enviar_a_gerencia(self):
        self.ensure_one()
        if self.estado != 'borrador':
            raise UserError(_("Solo se puede enviar desde estado Borrador."))
        if not self.linea_ids:
            raise UserError(_("El pedido no tiene líneas de repuestos.\nAgregue los repuestos antes de enviar a Gerencia."))
        lineas_sin_descripcion = self.linea_ids.filtered(lambda l: not l.subparte_id and not l.nombre_libre)
        if lineas_sin_descripcion:
            raise UserError(_("Hay %s línea(s) sin subparte ni descripción.\nComplete todas las líneas antes de enviar.") % len(lineas_sin_descripcion))
        self.write({'estado': 'esperando_gerencia', 'fecha_envio_gerencia': fields.Datetime.now()})
        self._correo_gerencia_evaluacion()
        self.message_post(body=_("📤 <b>Pedido enviado a Gerencia</b><br/>Correo enviado a: %s") % EMAIL_GERENCIA)
        _logger.info("[action_enviar_a_gerencia] pedido=%s", self.name)

    def _correo_gerencia_evaluacion(self):
        self.ensure_one()
        header = self._header_correo('🔧 Nuevo Pedido de Repuestos', 'Requiere su evaluación y aprobación')
        cont_k     = self.contometro_k or '—'
        cont_color = self.contometro_color or '—'
        cont_bloque = (
            "<div style='display:table;width:100%;border-collapse:separate;border-spacing:8px 0;margin-bottom:12px;'>"
            "<div style='display:table-cell;vertical-align:top;width:50%;'>"
            "<div style='background:#EBF3FF;border-left:3px solid #2D5AA0;border-radius:4px;padding:8px 12px;'>"
            "<div style='font-size:10px;color:#6b7280;'>Contómetro K (B/N)</div>"
            f"<div style='font-size:16px;font-weight:bold;color:#1f2d3d;'>{cont_k}</div></div></div>"
        )
        if self.contometro_color:
            cont_bloque += (
                "<div style='display:table-cell;vertical-align:top;width:50%;'>"
                "<div style='background:#FFF3E8;border-left:3px solid #D85A30;border-radius:4px;padding:8px 12px;'>"
                "<div style='font-size:10px;color:#6b7280;'>Contómetro Color</div>"
                f"<div style='font-size:16px;font-weight:bold;color:#1f2d3d;'>{cont_color}</div></div></div>"
            )
        cont_bloque += "</div>"
        cuerpo = (
            self._info_pedido_html() + cont_bloque +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>"
            "<p style='font-size:12px;color:#6b7280;margin-bottom:6px;'>La columna <b>Diferencia</b> muestra las copias desde el último cambio de ese repuesto en este equipo.</p>" +
            self._lineas_html(con_historial=True) +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('aprobar'),       '✅ Aprobar',           '#059669') +
            self._boton_html(self._url_accion('pedir-informe'), '📋 Solicitar informe', '#D97706') +
            self._boton_html(self._url_accion('rechazar'),      '❌ Rechazar',          '#DC2626') +
            "</p>"
        )
        self._enviar_correo_simple(EMAIL_GERENCIA, f"[SAT] Pedido {self.name} requiere aprobación — {self.modelo_nombre} ({self.serie})", self._wrap_correo(header, cuerpo))

    # ============================================================
    # PASO 2a — aprobar
    # ============================================================

    def action_aprobar_gerencia(self, desde_token=False):
        self.ensure_one()
        if self.estado not in ('esperando_gerencia', 'informe_recibido'):
            raise UserError(_("No se puede aprobar desde estado: %s") % self.estado)
        if not self.linea_ids:
            raise UserError(_("El pedido no tiene líneas de repuestos."))
        self._guardar_snapshot_lineas()
        self.write({'estado': 'aprobado', 'fecha_aprobacion': fields.Datetime.now(), 'gerente_id': self.env.user.id if not desde_token else self.gerente_id.id})
        self._correo_aprobado_comercial()
        self._correo_aprobado_logistica()
        self.write({'estado': 'stock_en_revision'})
        self.message_post(body=_("✅ <b>Pedido aprobado por Gerencia</b><br/>Notificado a Comercial (%s) y Logística (%s)") % (EMAIL_COMERCIAL, EMAIL_LOGISTICA))
        _logger.info("[action_aprobar_gerencia] pedido=%s | desde_token=%s", self.name, desde_token)

    def _correo_aprobado_comercial(self):
        header = self._header_correo('✅ Pedido aprobado — Verificar stock', color='#059669')
        cuerpo = (
            "<p>El pedido fue <b>aprobado por Gerencia</b>. Verifique disponibilidad de cada item:</p>" +
            self._info_pedido_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html(con_historial=False) +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('stock'), '📦 Gestionar stock del pedido', '#059669') + "</p>"
        )
        self._enviar_correo_simple(EMAIL_COMERCIAL, f"[SAT] Pedido {self.name} aprobado — Verificar stock", self._wrap_correo(header, cuerpo))

    def _correo_aprobado_logistica(self):
        header = self._header_correo('📦 Pedido en preparación')
        cuerpo = (
            f"<p>El pedido <b>{self.name}</b> fue aprobado. Comercial está verificando stock. Recibirá notificación cuando todo esté listo para despachar.</p>" +
            self._info_pedido_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html()
        )
        self._enviar_correo_simple(EMAIL_LOGISTICA, f"[SAT] Pedido {self.name} aprobado — En preparación", self._wrap_correo(header, cuerpo))

    # ============================================================
    # PASO 2b — solicitar informe
    # ============================================================

    def action_solicitar_informe_comercial(self, desde_token=False):
        self.ensure_one()
        if self.estado != 'esperando_gerencia':
            raise UserError(_("Solo se puede solicitar informe desde 'Esperando Gerencia'."))
        self.write({'estado': 'informe_solicitado', 'fecha_solicitud_informe': fields.Datetime.now()})
        self._correo_informe_solicitado_comercial()
        self.message_post(body=_("📋 <b>Informe solicitado a Comercial</b> (%s)") % EMAIL_COMERCIAL)
        _logger.info("[action_solicitar_informe_comercial] pedido=%s | desde_token=%s", self.name, desde_token)

    def _correo_informe_solicitado_comercial(self):
        header = self._header_correo('📋 Gerencia solicita informe técnico', color='#D97706')
        cuerpo = (
            "<p>Gerencia requiere un informe previo para evaluar este pedido:</p>" +
            self._info_pedido_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('informe'), '📎 Completar informe técnico', '#D97706') + "</p>"
        )
        self._enviar_correo_simple(EMAIL_COMERCIAL, f"[SAT] Pedido {self.name} — Gerencia solicita informe", self._wrap_correo(header, cuerpo))

    def action_informe_recibido(self, nota=None, adjunto_vals=None):
        self.ensure_one()
        if self.estado != 'informe_solicitado':
            raise UserError(_("El pedido no está esperando un informe."))
        vals = {'estado': 'informe_recibido', 'fecha_informe_recibido': fields.Datetime.now()}
        if nota: vals['nota_comercial'] = nota
        self.write(vals)
        if adjunto_vals:
            self.env['ir.attachment'].sudo().create({'name': adjunto_vals.get('nombre', 'informe.pdf'), 'type': 'binary', 'datas': adjunto_vals.get('datos'), 'res_model': self._name, 'res_id': self.id})
        self._correo_informe_recibido_gerencia()
        self.message_post(body=_("📎 <b>Informe recibido de Comercial</b><br/>Nota: %s") % (nota or '—'))
        _logger.info("[action_informe_recibido] pedido=%s", self.name)

    def _correo_informe_recibido_gerencia(self):
        def _to_int(val):
            if not val: return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0

        def _fmt_num(val):
            try: return f"{int(re.sub(r'[^\d]', '', str(val)) or 0):,}"
            except Exception: return str(val) if val else '—'

        header  = self._header_correo('📎 Informe de Comercial disponible')
        url_odoo = f"{self._get_base_url()}/web#id={self.id}&model=ticket.repuesto.pedido&view_type=form"

        filas = ''
        for i, l in enumerate(self.linea_ids, 1):
            color    = l.color_id.name if l.color_id else 'B/N'
            bg       = '#f9fafb' if i % 2 == 0 else '#ffffff'
            color_bg = {'Black': '#374151', 'Cyan': '#0891b2', 'Magenta': '#db2777', 'Yellow': '#d97706', 'B/N': '#6b7280'}.get(color, '#6b7280')
            badge_color = f"<span style='background:{color_bg};color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:bold;'>{color}</span>"
            if l.color_id: cont_actual_raw = self.contometro_color or '0'
            else:
                k = _to_int(self.contometro_k); c = _to_int(self.contometro_color)
                cont_actual_raw = str(k + c) if bool(self.contometro_color) else (self.contometro_k or '0')
            cont_anterior_raw = l.contador_informe_anterior or ''
            cont_anterior_fmt = _fmt_num(cont_anterior_raw) if cont_anterior_raw else '<i style="color:#9ca3af;">Sin registro</i>'
            if cont_anterior_raw:
                duracion = max(0, _to_int(cont_actual_raw) - _to_int(cont_anterior_raw))
                dur_fmt  = f"<b style='color:#059669;'>+{duracion:,}</b>"
            else:
                dur_fmt = '<i style="color:#9ca3af;">—</i>'
            fecha_fmt = l.fecha_informe_cambio.strftime('%d/%m/%Y') if l.fecha_informe_cambio else '<i style="color:#9ca3af;">Sin registro</i>'
            filas += (
                f"<tr style='background:{bg};'>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;color:#9ca3af;text-align:center;'>{i}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;'><b style='color:#1f2d3d;'>{l.componente_display or '—'}</b></td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;'>{l.subparte_id.name or l.nombre_libre or '—'}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:center;'>{badge_color}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:right;font-family:monospace;font-size:11px;'>{_fmt_num(cont_actual_raw)}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:right;font-family:monospace;font-size:11px;color:#6b7280;'>{cont_anterior_fmt}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:right;font-size:11px;'>{dur_fmt}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;text-align:center;font-size:11px;color:#6b7280;'>{fecha_fmt}</td>"
                f"<td style='padding:5px 8px;border:1px solid #e5e7eb;font-size:11px;color:#374151;'>{l.observacion_informe or ''}</td>"
                f"</tr>"
            )
        tabla = (
            "<table style='width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px;'>"
            "<thead><tr style='background:#1B3A6B;color:#fff;'>"
            "<th style='padding:7px 8px;text-align:center;'>#</th><th style='padding:7px 8px;text-align:left;'>Componente</th>"
            "<th style='padding:7px 8px;text-align:left;'>Subparte / Repuesto</th><th style='padding:7px 8px;text-align:center;'>Color</th>"
            "<th style='padding:7px 8px;text-align:right;'>Cont. Actual</th><th style='padding:7px 8px;text-align:right;'>Cont. Anterior</th>"
            "<th style='padding:7px 8px;text-align:right;'>Duración</th><th style='padding:7px 8px;text-align:center;'>Último Cambio</th>"
            "<th style='padding:7px 8px;text-align:left;'>Observación</th></tr></thead>"
            f"<tbody>{filas}</tbody></table>"
        )
        cuerpo = (
            f"<p>Comercial completó el informe del pedido <b>{self.name}</b>.</p>" +
            self._info_pedido_html() +
            (f"<p><b>Nota general de Comercial:</b><br/><span style='color:#374151;'>{self.nota_comercial}</span></p>" if self.nota_comercial else '') +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>"
            "<p style='font-size:12px;color:#6b7280;margin-bottom:6px;'>Detalle de repuestos con contadores y duración estimada:</p>" +
            tabla +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('aprobar'),  '✅ Aprobar',           '#059669') +
            self._boton_html(self._url_accion('rechazar'), '❌ Rechazar',          '#DC2626') +
            self._boton_html(url_odoo,                     '🔗 Ver en el sistema', '#1B3A6B') + "</p>"
        )
        self._enviar_correo_simple(EMAIL_GERENCIA, f"[SAT] Pedido {self.name} — Informe de Comercial listo", self._wrap_correo(header, cuerpo))

    # ============================================================
    # PASO 2c — rechazar
    # ============================================================

    def action_rechazar_gerencia(self, motivo=None, desde_token=False):
        self.ensure_one()
        if self.estado not in ('esperando_gerencia', 'informe_recibido'):
            raise UserError(_("No se puede rechazar desde estado: %s") % self.estado)
        self.write({'estado': 'rechazado', 'gerente_id': self.env.user.id if not desde_token else self.gerente_id.id, 'motivo_rechazo': motivo or _('Sin motivo especificado')})
        self._correo_rechazado_tecnico()
        self.message_post(body=_("❌ <b>Pedido rechazado</b><br/>Motivo: %s") % (motivo or '—'))
        _logger.info("[action_rechazar_gerencia] pedido=%s | motivo=%s", self.name, motivo)

    def _correo_rechazado_tecnico(self):
        email_tecnico = self.tecnico_id.email or self.tecnico_id.partner_id.email or ''
        if not email_tecnico:
            _logger.warning("[_correo_rechazado_tecnico] pedido=%s técnico sin email", self.name)
            return
        header = self._header_correo('❌ Pedido rechazado por Gerencia', color='#DC2626')
        cuerpo = self._info_pedido_html() + f"<p><b>Motivo del rechazo:</b><br/><span style='color:#DC2626;'>{self.motivo_rechazo or 'Sin motivo especificado'}</span></p>"
        self._enviar_correo_simple(email_tecnico, f"[SAT] Pedido {self.name} rechazado — {self.modelo_nombre} ({self.serie})", self._wrap_correo(header, cuerpo))

    # ============================================================
    # PASO 3 — stock completo
    # Crea el ticket inmediatamente y notifica a Soporte + Logística.
    # NO notifica al técnico — Soporte asigna el ticket.
    # ============================================================

    def action_stock_completo(self):
        self.ensure_one()
        if self.estado != 'stock_en_revision':
            raise UserError(_("Solo se puede confirmar stock desde 'Comercial revisando stock'."))
        if not self.todas_disponibles:
            raise UserError(_("Aún hay %s línea(s) sin stock confirmado.") % self.lineas_sin_stock)

        self.write({'estado': 'stock_completo', 'fecha_stock_completo': fields.Datetime.now()})

        # Crear ticket inmediatamente
        ticket_instalacion = self._crear_ticket_instalacion()

        # Notificar a Logística con botón confirmar entrega
        self._correo_stock_completo_logistica()

        # Notificar a Soporte para que asigne el ticket al técnico
        self._correo_stock_completo_soporte(ticket_instalacion)

        self.message_post(body=_(
            "📦 <b>Stock confirmado por Comercial</b><br/>"
            "Ticket de instalación creado: <b>%s</b><br/>"
            "Notificaciones enviadas a Logística y Soporte."
        ) % (ticket_instalacion.name if ticket_instalacion else '—'))

        _logger.info("[action_stock_completo] pedido=%s | ticket=%s", self.name, ticket_instalacion.name if ticket_instalacion else 'N/A')

    def _correo_stock_completo_logistica(self):
        header = self._header_correo('📦 Stock listo — Preparar entrega', color='#059669')
        cont_k     = self.contometro_k or '—'
        cont_color = self.contometro_color or '—'
        cont_info  = (f"<p style='font-size:12px;color:#6b7280;'><b>Contómetro K:</b> {cont_k}" + (f" &nbsp;|&nbsp; <b>Contómetro Color:</b> {cont_color}" if self.contometro_color else '') + "</p>")
        cuerpo = (
            "<p>Comercial confirmó que <b>todos los repuestos están disponibles</b>.</p>" +
            self._info_pedido_html() + cont_info +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html(con_historial=False) +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p>Cuando entregue los repuestos al técnico, confirme aquí:</p>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('entregar'), '🚚 Confirmar entrega al técnico', '#059669') + "</p>"
        )
        self._enviar_correo_simple(EMAIL_LOGISTICA, f"[SAT] Pedido {self.name} — Stock listo, preparar entrega", self._wrap_correo(header, cuerpo))

    def _correo_stock_completo_soporte(self, ticket_instalacion=False):
        """
        Notifica a Soporte que el stock está listo y se creó el ticket.
        Soporte debe asignarlo al técnico correspondiente.
        """
        ticket_info = ''
        if ticket_instalacion:
            url_ticket = f"{self._get_base_url()}/web#id={ticket_instalacion.id}&model=ticket.alquiler&view_type=form"
            ticket_info = f"<p style='text-align:center;'>{self._boton_html(url_ticket, '🔧 Abrir ticket de instalación', '#1B3A6B')}</p>"

        header = self._header_correo('📦 Stock listo — Asignar ticket al técnico', color='#1B3A6B')
        cuerpo = (
            f"<p>El stock del pedido <b>{self.name}</b> fue confirmado. "
            f"Se creó el ticket de instalación <b>{ticket_instalacion.name if ticket_instalacion else '—'}</b>. "
            f"Por favor asígnelo al técnico correspondiente.</p>" +
            self._info_pedido_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            ticket_info
        )
        self._enviar_correo_simple(
            EMAIL_SOPORTE,
            f"[SAT] Pedido {self.name} — Asignar ticket {ticket_instalacion.name if ticket_instalacion else ''}",
            self._wrap_correo(header, cuerpo)
        )

    # ============================================================
    # PASO 4 — Logística confirma entrega física
    # Solo cambia estado. El ticket ya existe desde el paso 3.
    # ============================================================

    def action_confirmar_entrega(self, desde_token=False):
        self.ensure_one()
        if self.estado != 'stock_completo':
            raise UserError(_("Solo se puede confirmar entrega cuando el stock está confirmado."))
        self.write({'estado': 'entregado', 'fecha_entrega': fields.Datetime.now()})
        ticket_inst = self.ticket_instalacion_id
        self.message_post(body=_("🚚 <b>Entrega física confirmada por Logística</b><br/>Ticket: <b>%s</b>") % (ticket_inst.name if ticket_inst else '—'))
        _logger.info("[action_confirmar_entrega] pedido=%s | desde_token=%s", self.name, desde_token)

    def _crear_ticket_instalacion(self):
        self.ensure_one()
        lineas_desc = "\n".join([
            f"- {l.componente_display or '?'} → {l.subparte_id.name} ({'Color: ' + l.color_id.name if l.color_id else 'B/N'}) x{int(l.cantidad)}"
            for l in self.linea_ids
        ])
        descripcion = f"Instalación de repuestos del pedido {self.name}\n\nRepuestos a instalar:\n{lineas_desc}\n\nEquipo: {self.modelo_nombre} — Serie: {self.serie}"
        try:
            ticket = self.env['ticket.alquiler'].sudo().create({
                'tipo_servicio_id': 'cambio_repuestos',
                'product_alquiler': self.equipo_id.id if self.equipo_id else False,
                'partner_id':       self.cliente_id.id if self.cliente_id else False,                
                'description':      descripcion,
                'estado':           'nuevo',
                'pedido_origen_id': self.id,
            })
            self.write({'ticket_instalacion_id': ticket.id})
            _logger.info("[_crear_ticket_instalacion] pedido=%s → ticket=%s", self.name, ticket.name)
            return ticket
        except Exception as e:
            _logger.error("[_crear_ticket_instalacion] ERROR pedido=%s | %s", self.name, str(e))
            return False

    # ============================================================
    # PASO 5 — marcar instalado
    # ============================================================

    def action_marcar_instalado(self):
        self.ensure_one()
        self.write({'estado': 'instalado', 'fecha_instalacion': fields.Datetime.now()})
        self.message_post(body=_("✅ <b>Repuestos instalados</b><br/>Historial de durabilidad actualizado con contómetros reales."))
        _logger.info("[action_marcar_instalado] pedido=%s instalado", self.name)

    # ============================================================
    # LEGACY
    # ============================================================

    def action_aprobar(self):
        return self.action_aprobar_gerencia()

    def action_cancelar(self):
        self.ensure_one()
        if self.estado in ('instalado', 'entregado', 'en_camino'):
            raise UserError(_("No se puede cancelar un pedido en estado '%s'.") % self.estado)
        self.write({'estado': 'cancelado'})
        self.message_post(body=_("❌ <b>Pedido cancelado</b> por %s") % self.env.user.name)
        _logger.info("[action_cancelar] pedido=%s cancelado", self.name)

    def action_volver_pendiente(self):
        self.ensure_one()
        if self.estado not in ('cancelado', 'rechazado'):
            raise UserError(_("Solo se puede reactivar un pedido cancelado o rechazado."))
        self.write({'estado': 'borrador'})
        self.message_post(body=_("🔄 <b>Pedido reactivado</b> a borrador por %s") % self.env.user.name)
        _logger.info("[action_volver_pendiente] pedido=%s reactivado", self.name)

    def _registrar_historial(self):
        """DEPRECATED — usar ticket_alquiler.action_finalizar"""
        _logger.warning("[_registrar_historial] DEPRECATED pedido=%s — usar ticket_alquiler.action_finalizar", self.name)

    @api.model
    def get_pedido_dashboard_values(self, domain=None):
        domain = domain or []
        def count(extra_domain):
            return self.search_count(domain + extra_domain)
        return {
            'total_pedidos':            count([]),
            'total_borrador':           count([['estado', '=', 'borrador']]),
            'total_esperando_gerencia': count([['estado', '=', 'esperando_gerencia']]),
            'total_informe_solicitado': count([['estado', '=', 'informe_solicitado']]),
            'total_informe_recibido':   count([['estado', '=', 'informe_recibido']]),
            'total_aprobado':           count([['estado', '=', 'aprobado']]),
            'total_rechazado':          count([['estado', '=', 'rechazado']]),
            'total_stock_en_revision':  count([['estado', '=', 'stock_en_revision']]),
            'total_stock_completo':     count([['estado', '=', 'stock_completo']]),
            'total_en_camino':          count([['estado', '=', 'en_camino']]),
            'total_entregado':          count([['estado', '=', 'entregado']]),
            'total_instalado':          count([['estado', '=', 'instalado']]),
            'total_cancelado':          count([['estado', '=', 'cancelado']]),
        }


# ============================================================
# LÍNEA DE PEDIDO
# ============================================================

class TicketRepuestoPedidoLinea(models.Model):
    _name = 'ticket.repuesto.pedido.linea'
    _description = 'Línea de Pedido de Repuestos de Ticket'
    _order = 'pedido_id, id'

    pedido_id = fields.Many2one('ticket.repuesto.pedido', string='Pedido', required=True, ondelete='cascade', index=True)
    componente_code = fields.Char(string='Código de Componente')
    componente_display = fields.Char(string='Componente', compute='_compute_componente_display', store=True)
    color_id = fields.Many2one('color.tipo', string='Color', ondelete='restrict')
    subparte_id = fields.Many2one('componente.subparte', string='Subparte / Repuesto', required=False, ondelete='restrict')
    nombre_libre = fields.Char(string='Descripción libre')

    @api.constrains('subparte_id', 'nombre_libre')
    def _check_linea_repuesto(self):
        for rec in self:
            if not rec.subparte_id and not rec.nombre_libre:
                raise ValidationError("Debe seleccionar una subparte o ingresar una descripción manual.")

    cantidad = fields.Float(string='Cantidad', default=1.0, required=True)
    observacion = fields.Char(string='Observación')

    # STOCK
    estado_stock = fields.Selection([('pendiente', 'Pendiente verificación'), ('disponible', 'En stock'), ('sin_stock', 'Sin stock — en compra'), ('recibido', 'Recibido de proveedor')], string='Estado de stock', default='pendiente', tracking=True)
    fecha_disponible = fields.Date(string='Fecha estimada disponibilidad')
    observacion_stock = fields.Char(string='Nota de stock')

    # INFORME COMERCIAL
    contador_informe_anterior = fields.Char(string='Contador anterior (informe)')
    fecha_informe_cambio = fields.Date(string='Fecha último cambio (informe)')
    observacion_informe = fields.Char(string='Observación (informe)')
    duracion_informe = fields.Integer(string='Duración (copias)', compute='_compute_duracion_informe', store=False)

    # SNAPSHOT
    contometro_actual_snapshot   = fields.Char(string='Contómetro actual (al aprobar)', readonly=True)
    contometro_anterior_snapshot = fields.Char(string='Contómetro anterior (al aprobar)', readonly=True)
    copias_snapshot = fields.Integer(string='Copias desde último cambio (al aprobar)', readonly=True, default=0)
    meses_snapshot  = fields.Integer(string='Meses desde último cambio (al aprobar)', readonly=True, default=0)

    # HISTORIAL TIEMPO REAL
    ultimo_cambio_fecha       = fields.Datetime(string='Último cambio', compute='_compute_ultimo_cambio', store=False)
    ultimo_cambio_contometro  = fields.Char(string='Contómetro en último cambio', compute='_compute_ultimo_cambio', store=False)
    ultimo_tipo_contometro    = fields.Selection([('bn', 'B/N'), ('color', 'Color'), ('total', 'Total')], string='Tipo contómetro', compute='_compute_ultimo_cambio', store=False)
    contometro_actual_linea   = fields.Char(string='Contómetro actual (según tipo)', compute='_compute_ultimo_cambio', store=False)
    meses_desde_ultimo_cambio = fields.Integer(string='Meses desde último cambio', compute='_compute_ultimo_cambio', store=False)

    @api.depends('componente_code', 'nombre_libre', 'subparte_id')
    def _compute_componente_display(self):
        color_map = {'k': 'Black', 'c': 'Cyan', 'm': 'Magenta', 'y': 'Yellow'}
        for record in self:
            if record.nombre_libre:
                record.componente_display = record.nombre_libre
                continue
            code = record.componente_code or ''
            m = re.match(r'^t(\d+)(?:_([kcmy]))?$', code)
            if m:
                tipo = self.env['componente.tipo'].browse(int(m.group(1)))
                nombre = tipo.name if tipo.exists() else f"Componente {m.group(1)}"
                if m.group(2): nombre = f"{nombre} ({color_map.get(m.group(2), m.group(2).upper())})"
                record.componente_display = nombre
                continue
            m2 = re.match(r'^a(\d+)$', code)
            if m2:
                tipo = self.env['accesorio.tipo'].browse(int(m2.group(1)))
                record.componente_display = tipo.name if tipo.exists() else f"Accesorio {m2.group(1)}"
                continue
            record.componente_display = code or '—'

    @api.depends('contador_informe_anterior', 'pedido_id.contometro_k', 'pedido_id.contometro_color', 'color_id')
    def _compute_duracion_informe(self):
        def _to_int(val):
            if not val: return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0
        for record in self:
            anterior = _to_int(record.contador_informe_anterior)
            if not anterior:
                record.duracion_informe = 0
                continue
            if record.color_id: actual = _to_int(record.pedido_id.contometro_color)
            else:
                k = _to_int(record.pedido_id.contometro_k); c = _to_int(record.pedido_id.contometro_color)
                actual = (k + c) if bool(record.pedido_id.contometro_color) else k
            record.duracion_informe = max(0, actual - anterior)

    @api.depends('subparte_id', 'color_id', 'pedido_id.equipo_id', 'pedido_id.contometro_k', 'pedido_id.contometro_color')
    def _compute_ultimo_cambio(self):
        def _to_int(val):
            if not val: return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0
        for record in self:
            equipo_id = record.pedido_id.equipo_id.id if record.pedido_id.equipo_id else False
            if not equipo_id or not record.subparte_id:
                record.ultimo_cambio_fecha = record.ultimo_cambio_contometro = record.ultimo_tipo_contometro = record.contometro_actual_linea = False
                record.meses_desde_ultimo_cambio = 0
                continue
            domain = [('equipo_id', '=', equipo_id), ('subparte_id', '=', record.subparte_id.id), ('pedido_id', '!=', record.pedido_id.id)]
            if record.color_id: domain.append(('color_id', '=', record.color_id.id))
            else: domain.append(('color_id', '=', False))
            ultimo = self.env['ticket.repuesto.historial'].search(domain, order='fecha_cambio desc', limit=1)
            _logger.debug("[_compute_ultimo_cambio] pedido=%s | subparte=%s | color=%s | ultimo_id=%s", record.pedido_id.name, record.subparte_id.name, record.color_id.name if record.color_id else 'B/N', ultimo.id if ultimo else 'ninguno')
            k = _to_int(record.pedido_id.contometro_k); c = _to_int(record.pedido_id.contometro_color)
            if ultimo:
                record.ultimo_cambio_fecha = ultimo.fecha_cambio
                record.ultimo_cambio_contometro = ultimo.contometro_cambio
                record.ultimo_tipo_contometro = ultimo.tipo_contometro
                tipo = ultimo.tipo_contometro
                if tipo == 'color': record.contometro_actual_linea = record.pedido_id.contometro_color or '0'
                elif tipo == 'total': record.contometro_actual_linea = str(k + c) if (k + c) > 0 else '0'
                else: record.contometro_actual_linea = record.pedido_id.contometro_k or '0'
                if ultimo.fecha_cambio:
                    diff = relativedelta(datetime.now(), ultimo.fecha_cambio)
                    record.meses_desde_ultimo_cambio = diff.months + (diff.years * 12)
                else:
                    record.meses_desde_ultimo_cambio = 0
            else:
                es_color = (record.pedido_id.equipo_id.tipo_maquina_id == 'color')
                if record.color_id: record.contometro_actual_linea = record.pedido_id.contometro_color or '0'
                elif es_color: record.contometro_actual_linea = str(k + c) if (k + c) > 0 else '0'
                else: record.contometro_actual_linea = record.pedido_id.contometro_k or '0'
                record.ultimo_cambio_fecha = record.ultimo_cambio_contometro = record.ultimo_tipo_contometro = False
                record.meses_desde_ultimo_cambio = 0

    @api.model
    def create(self, vals):
        _logger.info("[ticket.repuesto.pedido.linea] create() — pedido_id=%s | subparte_id=%s | color_id=%s | cantidad=%s", vals.get('pedido_id'), vals.get('subparte_id'), vals.get('color_id'), vals.get('cantidad'))
        return super().create(vals)
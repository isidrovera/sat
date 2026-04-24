# -*- coding: utf-8 -*-
"""
Sistema de recordatorios para pedidos de repuestos.

Envía recordatorios diarios a las áreas responsables cuando un pedido lleva
más de 24h sin acción en los siguientes estados:

    - esperando_gerencia  → Gerencia debe aprobar / pedir informe / rechazar
    - informe_recibido    → Gerencia debe aprobar / rechazar tras informe
    - informe_solicitado  → Comercial debe enviar informe técnico
    - stock_en_revision   → Comercial debe confirmar stock

Frecuencia : 24h a partir del cambio de estado
Tope       : 5 recordatorios por estado
Cron       : diario 8:00 AM
"""

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

TOPE_RECORDATORIOS = 5

# Configuración por estado: (campo_fecha_referencia, email_destino, metodo_correo_base)
CONFIG_RECORDATORIOS = {
    'esperando_gerencia': {
        'campo_fecha': 'fecha_envio_gerencia',
        'metodo_correo': '_recordatorio_gerencia_evaluacion',
        'area': 'Gerencia',
    },
    'informe_recibido': {
        'campo_fecha': 'fecha_informe_recibido',
        'metodo_correo': '_recordatorio_gerencia_informe_recibido',
        'area': 'Gerencia',
    },
    'informe_solicitado': {
        'campo_fecha': 'fecha_solicitud_informe',
        'metodo_correo': '_recordatorio_comercial_informe',
        'area': 'Comercial',
    },
    'stock_en_revision': {
        'campo_fecha': 'fecha_aprobacion',
        'metodo_correo': '_recordatorio_comercial_stock',
        'area': 'Comercial',
    },
}


class TicketRepuestoPedidoRecordatorio(models.Model):
    _inherit = 'ticket.repuesto.pedido'

    # ============================================================
    # CAMPOS DE CONTROL DE RECORDATORIOS
    # ============================================================

    ultimo_recordatorio_fecha = fields.Datetime(
        string='Último recordatorio enviado',
        readonly=True,
        copy=False,
    )
    recordatorios_enviados = fields.Integer(
        string='Recordatorios enviados',
        default=0,
        readonly=True,
        copy=False,
        help='Número de recordatorios enviados en el estado actual. Se resetea al cambiar de estado.',
    )
    estado_recordatorio_anterior = fields.Char(
        string='Estado al último recordatorio',
        readonly=True,
        copy=False,
        help='Estado en el que se envió el último recordatorio — usado para detectar cambios de estado.',
    )

    # ============================================================
    # RESET AL CAMBIAR DE ESTADO
    # ============================================================

    def write(self, vals):
        """
        Si el estado cambia a uno de los estados con recordatorios activos,
        resetea el contador para empezar desde cero en el nuevo estado.
        """
        if 'estado' in vals:
            for rec in self:
                if vals['estado'] != rec.estado and vals['estado'] in CONFIG_RECORDATORIOS:
                    vals.setdefault('recordatorios_enviados', 0)
                    vals.setdefault('ultimo_recordatorio_fecha', False)
                    vals.setdefault('estado_recordatorio_anterior', False)
        return super().write(vals)

    # ============================================================
    # CRON — ENTRY POINT
    # ============================================================

    @api.model
    def _cron_enviar_recordatorios_pedidos(self):
        """
        Cron diario que recorre pedidos activos en estados con recordatorio
        y envía notificación si corresponde (24h desde última acción,
        máx. 5 recordatorios por estado).
        """
        _logger.info("[cron_recordatorios] ===== Inicio ejecución =====")

        estados_activos = list(CONFIG_RECORDATORIOS.keys())
        pedidos = self.search([
            ('estado', 'in', estados_activos),
            ('recordatorios_enviados', '<', TOPE_RECORDATORIOS),
        ])

        _logger.info(
            "[cron_recordatorios] pedidos candidatos: %s",
            len(pedidos),
        )

        enviados = 0
        for pedido in pedidos:
            try:
                if pedido._evaluar_y_enviar_recordatorio():
                    enviados += 1
            except Exception as e:
                _logger.error(
                    "[cron_recordatorios] ERROR pedido=%s | %s",
                    pedido.name, str(e),
                )

        _logger.info(
            "[cron_recordatorios] ===== Fin | enviados=%s / candidatos=%s =====",
            enviados, len(pedidos),
        )

    def _evaluar_y_enviar_recordatorio(self):
        """
        Evalúa un pedido y envía recordatorio si corresponde.
        Retorna True si envió, False si no.
        """
        self.ensure_one()

        config = CONFIG_RECORDATORIOS.get(self.estado)
        if not config:
            return False

        # Fecha de referencia: cuándo entró en este estado
        fecha_ref = self[config['campo_fecha']]
        if not fecha_ref:
            _logger.warning(
                "[recordatorio] pedido=%s estado=%s sin fecha de referencia (%s)",
                self.name, self.estado, config['campo_fecha'],
            )
            return False

        ahora = fields.Datetime.now()

        # Regla 1 — al menos 24h desde que entró al estado
        horas_en_estado = (ahora - fecha_ref).total_seconds() / 3600
        if horas_en_estado < 24:
            _logger.debug(
                "[recordatorio] pedido=%s | aún no cumple 24h en estado (%s h)",
                self.name, round(horas_en_estado, 1),
            )
            return False

        # Regla 2 — al menos 24h desde último recordatorio (si hubo)
        if self.ultimo_recordatorio_fecha:
            horas_desde_ultimo = (ahora - self.ultimo_recordatorio_fecha).total_seconds() / 3600
            if horas_desde_ultimo < 24:
                _logger.debug(
                    "[recordatorio] pedido=%s | aún no cumple 24h desde último (%s h)",
                    self.name, round(horas_desde_ultimo, 1),
                )
                return False

        # Regla 3 — no exceder tope
        if self.recordatorios_enviados >= TOPE_RECORDATORIOS:
            _logger.info(
                "[recordatorio] pedido=%s | tope alcanzado (%s) — no se envía más",
                self.name, TOPE_RECORDATORIOS,
            )
            return False

        # Enviar recordatorio
        metodo = config['metodo_correo']
        numero = self.recordatorios_enviados + 1
        dias = int(horas_en_estado // 24)

        _logger.info(
            "[recordatorio] ENVIANDO pedido=%s | estado=%s | #%s | días=%s | área=%s",
            self.name, self.estado, numero, dias, config['area'],
        )

        getattr(self, metodo)(numero=numero, dias=dias)

        # Registrar envío
        self.write({
            'ultimo_recordatorio_fecha': ahora,
            'recordatorios_enviados': numero,
            'estado_recordatorio_anterior': self.estado,
        })

        self.message_post(body=_(
            "⏰ <b>Recordatorio #%s enviado a %s</b><br/>"
            "Pedido pendiente desde hace %s día(s) en estado '%s'."
        ) % (numero, config['area'], dias, self.estado))

        return True

    # ============================================================
    # BANNER DE RECORDATORIO
    # ============================================================

    def _banner_recordatorio(self, numero, dias, area):
        """
        Banner ámbar/rojo que se antepone al correo original.
        Color ámbar hasta recordatorio 3, rojo a partir del 4.
        """
        if numero >= 4:
            color_fondo = '#DC2626'
            icono = '🚨'
            urgencia = 'URGENTE'
        else:
            color_fondo = '#D97706'
            icono = '⏰'
            urgencia = 'RECORDATORIO'

        return (
            f"<div style='background:{color_fondo};color:#fff;padding:14px 20px;"
            f"border-radius:6px;margin-bottom:12px;text-align:center;'>"
            f"<div style='font-size:18px;font-weight:bold;margin-bottom:4px;'>"
            f"{icono} {urgencia} #{numero} de {TOPE_RECORDATORIOS}"
            f"</div>"
            f"<div style='font-size:13px;opacity:0.95;'>"
            f"Este pedido lleva <b>{dias} día(s)</b> pendiente de acción por parte de <b>{area}</b>."
            f"</div>"
            f"</div>"
        )

    # ============================================================
    # RECORDATORIOS POR ESTADO — reutilizan lógica de correos originales
    # ============================================================

    def _recordatorio_gerencia_evaluacion(self, numero, dias):
        """Recordatorio para estado 'esperando_gerencia'."""
        self.ensure_one()
        from . import ticket_repuesto_pedido as _m  # noqa: F401
        EMAIL_GERENCIA = 'lincoln@corapsac.com'

        # Banner + header + cuerpo original
        banner = self._banner_recordatorio(numero, dias, 'Gerencia')
        header = self._header_correo(
            '🔧 Pedido de Repuestos pendiente de aprobación',
            'Requiere su evaluación',
        )

        cont_k = self.contometro_k or '—'
        cont_color = self.contometro_color or '—'
        cont_bloque = (
            "<div style='display:table;width:100%;border-collapse:separate;"
            "border-spacing:8px 0;margin-bottom:12px;'>"
            "<div style='display:table-cell;vertical-align:top;width:50%;'>"
            "<div style='background:#EBF3FF;border-left:3px solid #2D5AA0;"
            "border-radius:4px;padding:8px 12px;'>"
            "<div style='font-size:10px;color:#6b7280;'>Contómetro K (B/N)</div>"
            f"<div style='font-size:16px;font-weight:bold;color:#1f2d3d;'>{cont_k}</div>"
            "</div></div>"
        )
        if self.contometro_color:
            cont_bloque += (
                "<div style='display:table-cell;vertical-align:top;width:50%;'>"
                "<div style='background:#FFF3E8;border-left:3px solid #D85A30;"
                "border-radius:4px;padding:8px 12px;'>"
                "<div style='font-size:10px;color:#6b7280;'>Contómetro Color</div>"
                f"<div style='font-size:16px;font-weight:bold;color:#1f2d3d;'>{cont_color}</div>"
                "</div></div>"
            )
        cont_bloque += "</div>"

        cuerpo = (
            banner +
            self._info_pedido_html() + cont_bloque +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>"
            "<p style='font-size:12px;color:#6b7280;margin-bottom:6px;'>"
            "La columna <b>Diferencia</b> muestra las copias desde el último cambio "
            "de ese repuesto en este equipo."
            "</p>" +
            self._lineas_html(con_historial=True) +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('aprobar'),       '✅ Aprobar',           '#059669') +
            self._boton_html(self._url_accion('pedir-informe'), '📋 Solicitar informe', '#D97706') +
            self._boton_html(self._url_accion('rechazar'),      '❌ Rechazar',          '#DC2626') +
            "</p>"
        )

        asunto = f"[SAT][Recordatorio #{numero}] Pedido {self.name} pendiente hace {dias} día(s)"
        self._enviar_correo_simple(
            EMAIL_GERENCIA, asunto,
            self._wrap_correo(header, cuerpo),
        )

    def _recordatorio_gerencia_informe_recibido(self, numero, dias):
        """Recordatorio para estado 'informe_recibido' — Gerencia aún no aprueba tras informe."""
        self.ensure_one()
        EMAIL_GERENCIA = 'lincoln@corapsac.com'

        banner = self._banner_recordatorio(numero, dias, 'Gerencia')
        header = self._header_correo(
            '📎 Informe de Comercial esperando su decisión',
            'Ya cuenta con el informe técnico solicitado',
        )
        url_odoo = (
            f"{self._get_base_url()}/web#id={self.id}"
            f"&model=ticket.repuesto.pedido&view_type=form"
        )

        cuerpo = (
            banner +
            f"<p>Comercial ya completó el informe del pedido <b>{self.name}</b> "
            f"y sigue esperando su decisión.</p>" +
            self._info_pedido_html() +
            (f"<p><b>Nota de Comercial:</b><br/>"
             f"<span style='color:#374151;'>{self.nota_comercial}</span></p>"
             if self.nota_comercial else '') +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html(con_historial=True) +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('aprobar'),  '✅ Aprobar',           '#059669') +
            self._boton_html(self._url_accion('rechazar'), '❌ Rechazar',          '#DC2626') +
            self._boton_html(url_odoo,                     '🔗 Ver en el sistema', '#1B3A6B') +
            "</p>"
        )

        asunto = f"[SAT][Recordatorio #{numero}] Pedido {self.name} con informe esperando hace {dias} día(s)"
        self._enviar_correo_simple(
            EMAIL_GERENCIA, asunto,
            self._wrap_correo(header, cuerpo),
        )

    def _recordatorio_comercial_informe(self, numero, dias):
        """Recordatorio para estado 'informe_solicitado' — Comercial debe enviar informe."""
        self.ensure_one()
        EMAIL_COMERCIAL = 'comercial01@andescopiers.com.pe, comercial@andescopiers.com.pe'

        banner = self._banner_recordatorio(numero, dias, 'Comercial')
        header = self._header_correo(
            '📋 Gerencia sigue esperando el informe técnico',
            color='#D97706',
        )

        cuerpo = (
            banner +
            "<p>Gerencia requiere el informe previo para evaluar este pedido. "
            "Por favor complete los contadores y observaciones:</p>" +
            self._info_pedido_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html() +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('informe'), '📎 Completar informe técnico', '#D97706') +
            "</p>"
        )

        asunto = f"[SAT][Recordatorio #{numero}] Pedido {self.name} — Informe pendiente hace {dias} día(s)"
        self._enviar_correo_simple(
            EMAIL_COMERCIAL, asunto,
            self._wrap_correo(header, cuerpo),
        )

    def _recordatorio_comercial_stock(self, numero, dias):
        """Recordatorio para estado 'stock_en_revision' — Comercial debe confirmar stock."""
        self.ensure_one()
        EMAIL_COMERCIAL = 'comercial01@andescopiers.com.pe, comercial@andescopiers.com.pe'

        banner = self._banner_recordatorio(numero, dias, 'Comercial')
        header = self._header_correo(
            '📦 Verificación de stock pendiente',
            'Pedido aprobado — falta confirmar disponibilidad',
            color='#059669',
        )

        lineas_pendientes = self.linea_ids.filtered(
            lambda l: l.estado_stock not in ('disponible', 'recibido')
        )
        resumen_pendientes = (
            f"<p style='background:#FEF3C7;border-left:3px solid #D97706;"
            f"padding:8px 12px;border-radius:4px;font-size:12px;'>"
            f"<b>{len(lineas_pendientes)} de {len(self.linea_ids)} líneas</b> "
            f"aún sin estado de stock confirmado.</p>"
        ) if lineas_pendientes else ''

        cuerpo = (
            banner +
            "<p>Este pedido fue aprobado por Gerencia y sigue esperando que "
            "verifique la disponibilidad de los repuestos:</p>" +
            self._info_pedido_html() +
            resumen_pendientes +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:12px 0;'/>" +
            self._lineas_html(con_historial=False) +
            "<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0;'/>"
            "<p style='text-align:center;'>" +
            self._boton_html(self._url_accion('stock'), '📦 Gestionar stock del pedido', '#059669') +
            "</p>"
        )

        asunto = f"[SAT][Recordatorio #{numero}] Pedido {self.name} — Stock pendiente hace {dias} día(s)"
        self._enviar_correo_simple(
            EMAIL_COMERCIAL, asunto,
            self._wrap_correo(header, cuerpo),
        )
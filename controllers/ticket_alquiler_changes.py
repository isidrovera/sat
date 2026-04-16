# -*- coding: utf-8 -*-
# controllers/pedido_portal.py
#
# Rutas públicas para acciones por correo sin login.
# Todas las rutas usan token UUID único del pedido.
#
# Gerencia  → /pedido/<token>/aprobar
#             /pedido/<token>/rechazar
#             /pedido/<token>/pedir-informe
# Comercial → /pedido/<token>/stock          (GET  — página gestión stock)
#             /pedido/<token>/stock/guardar   (POST — guarda estados líneas)
#             /pedido/<token>/informe         (GET  — página informe técnico)
#             /pedido/<token>/informe/guardar (POST — guarda datos informe)
# Logística → /pedido/<token>/entregar

from odoo import http, fields, _
from odoo.http import request
import logging
import base64

_logger = logging.getLogger(__name__)

# ============================================================
# HELPERS DE RESPUESTA
# ============================================================

def _render_confirmacion(titulo, mensaje, color='#059669', icono='✅'):
    """Página de confirmación simple para acciones de Gerencia y Logística."""
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <title>{titulo}</title>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: Arial, Helvetica, sans-serif;
                background: #f3f4f6;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: 20px;
            }}
            .card {{
                background: #fff;
                border-radius: 10px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                max-width: 480px;
                width: 100%;
                overflow: hidden;
            }}
            .card-header {{
                background: {color};
                color: #fff;
                padding: 24px 28px;
                text-align: center;
            }}
            .card-header .icono {{
                font-size: 40px;
                display: block;
                margin-bottom: 8px;
            }}
            .card-header h1 {{
                font-size: 20px;
                font-weight: bold;
            }}
            .card-body {{
                padding: 28px;
                text-align: center;
                color: #374151;
                line-height: 1.6;
            }}
            .card-body p {{ margin-bottom: 12px; font-size: 15px; }}
            .footer {{
                border-top: 1px solid #e5e7eb;
                padding: 14px 28px;
                text-align: center;
                font-size: 12px;
                color: #9ca3af;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="card-header">
                <span class="icono">{icono}</span>
                <h1>{titulo}</h1>
            </div>
            <div class="card-body">
                {mensaje}
            </div>
            <div class="footer">Andes Copiers SAC — Sistema de Taller SAT</div>
        </div>
    </body>
    </html>
    """


def _render_error(titulo, mensaje):
    return _render_confirmacion(titulo, mensaje, color='#DC2626', icono='❌')


def _render_info(titulo, mensaje):
    return _render_confirmacion(titulo, mensaje, color='#1B3A6B', icono='ℹ️')


def _get_pedido_by_token(token):
    if not token or len(token) < 10:
        return None, _render_error(
            'Token inválido',
            '<p>El enlace que usaste no es válido o está incompleto.</p>'
            '<p>Verifique que copió el enlace completo del correo.</p>'
        )

    pedido = request.env['ticket.repuesto.pedido'].sudo().search(
        [('token', '=', token)], limit=1
    )

    if not pedido:
        return None, _render_error(
            'Pedido no encontrado',
            '<p>No se encontró ningún pedido asociado a este enlace.</p>'
            '<p>Es posible que el enlace haya expirado o sea incorrecto.</p>'
        )

    return pedido, None


# ============================================================
# CONTROLADOR
# ============================================================

class PedidoPortalController(http.Controller):

    # ============================================================
    # GERENCIA — Aprobar
    # ============================================================

    @http.route(
        '/pedido/<string:token>/aprobar',
        type='http',
        auth='public',
        methods=['GET'],
        website=False,
        csrf=False,
    )
    def pedido_aprobar(self, token, **kwargs):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        _logger.info(
            "[portal/aprobar] token=%s... pedido=%s estado=%s",
            token[:8], pedido.name, pedido.estado
        )

        if pedido.estado not in ('esperando_gerencia', 'informe_recibido'):
            estado_label = dict(
                pedido._fields['estado'].selection
            ).get(pedido.estado, pedido.estado)
            return _render_info(
                'Acción ya procesada',
                f'<p>Este pedido ya fue procesado.</p>'
                f'<p><b>Estado actual:</b> {estado_label}</p>'
                f'<p>No es necesaria ninguna acción adicional.</p>'
            )

        try:
            pedido.action_aprobar_gerencia(desde_token=True)
            _logger.info(
                "[portal/aprobar] pedido=%s aprobado via token",
                pedido.name
            )
            return _render_confirmacion(
                'Pedido aprobado',
                f'<p>El pedido <b>{pedido.name}</b> fue aprobado correctamente.</p>'
                f'<p>Se notificó a Comercial y Logística para continuar el proceso.</p>'
                f'<p><b>Equipo:</b> {pedido.modelo_nombre} — {pedido.serie}</p>',
                color='#059669',
                icono='✅'
            )
        except Exception as e:
            _logger.error(
                "[portal/aprobar] ERROR pedido=%s | %s",
                pedido.name, str(e)
            )
            return _render_error(
                'Error al aprobar',
                f'<p>Ocurrió un error al procesar la aprobación.</p>'
                f'<p>Por favor, ingrese al sistema directamente.</p>'
                f'<p style="font-size:12px;color:#9ca3af;">{str(e)}</p>'
            )

    # ============================================================
    # GERENCIA — Rechazar (GET muestra formulario, POST procesa)
    # ============================================================

    @http.route(
        '/pedido/<string:token>/rechazar',
        type='http',
        auth='public',
        methods=['GET'],
        website=False,
        csrf=False,
    )
    def pedido_rechazar_form(self, token, **kwargs):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado not in ('esperando_gerencia', 'informe_recibido'):
            estado_label = dict(
                pedido._fields['estado'].selection
            ).get(pedido.estado, pedido.estado)
            return _render_info(
                'Acción ya procesada',
                f'<p>Este pedido ya fue procesado.</p>'
                f'<p><b>Estado actual:</b> {estado_label}</p>'
            )

        return f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <title>Rechazar pedido {pedido.name}</title>
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: Arial, Helvetica, sans-serif;
                    background: #f3f4f6;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    padding: 20px;
                }}
                .card {{
                    background: #fff;
                    border-radius: 10px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                    max-width: 500px;
                    width: 100%;
                    overflow: hidden;
                }}
                .card-header {{
                    background: #DC2626;
                    color: #fff;
                    padding: 20px 28px;
                }}
                .card-header h1 {{ font-size: 18px; }}
                .card-header p {{
                    font-size: 13px;
                    opacity: 0.85;
                    margin-top: 4px;
                }}
                .card-body {{ padding: 28px; }}
                .info-box {{
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-left: 3px solid #DC2626;
                    border-radius: 4px;
                    padding: 12px 14px;
                    margin-bottom: 20px;
                    font-size: 13px;
                    color: #374151;
                }}
                .info-box b {{ color: #1f2d3d; }}
                label {{
                    display: block;
                    font-size: 13px;
                    font-weight: bold;
                    color: #374151;
                    margin-bottom: 6px;
                }}
                textarea {{
                    width: 100%;
                    padding: 10px 12px;
                    border: 1px solid #d1d5db;
                    border-radius: 6px;
                    font-size: 14px;
                    font-family: Arial, sans-serif;
                    resize: vertical;
                    min-height: 100px;
                    outline: none;
                    transition: border-color 0.2s;
                }}
                textarea:focus {{ border-color: #DC2626; }}
                .btn-rechazar {{
                    display: block;
                    width: 100%;
                    padding: 12px;
                    background: #DC2626;
                    color: #fff;
                    border: none;
                    border-radius: 6px;
                    font-size: 15px;
                    font-weight: bold;
                    cursor: pointer;
                    margin-top: 16px;
                    transition: background 0.2s;
                }}
                .btn-rechazar:hover {{ background: #b91c1c; }}
                .footer {{
                    border-top: 1px solid #e5e7eb;
                    padding: 12px 28px;
                    text-align: center;
                    font-size: 11px;
                    color: #9ca3af;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="card-header">
                    <h1>❌ Rechazar pedido</h1>
                    <p>Esta acción notificará al técnico con el motivo indicado</p>
                </div>
                <div class="card-body">
                    <div class="info-box">
                        <b>Pedido:</b> {pedido.name}<br/>
                        <b>Equipo:</b> {pedido.modelo_nombre or '—'} — {pedido.serie or '—'}<br/>
                        <b>Cliente:</b> {pedido.cliente_id.name or '—'}<br/>
                        <b>Técnico:</b> {pedido.tecnico_id.name or '—'}
                    </div>
                    <form method="POST" action="/pedido/{token}/rechazar/confirmar">
                        <label for="motivo">Motivo del rechazo *</label>
                        <textarea id="motivo" name="motivo"
                                  placeholder="Describa el motivo del rechazo..."
                                  required></textarea>
                        <button type="submit" class="btn-rechazar">
                            ❌ Confirmar rechazo
                        </button>
                    </form>
                </div>
                <div class="footer">Andes Copiers SAC — Sistema de Taller SAT</div>
            </div>
        </body>
        </html>
        """

    @http.route(
        '/pedido/<string:token>/rechazar/confirmar',
        type='http',
        auth='public',
        methods=['POST'],
        website=False,
        csrf=False,
    )
    def pedido_rechazar_confirmar(self, token, **post):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado not in ('esperando_gerencia', 'informe_recibido'):
            return _render_info(
                'Acción ya procesada',
                '<p>Este pedido ya fue procesado previamente.</p>'
            )

        motivo = post.get('motivo', '').strip()
        if not motivo:
            return _render_error(
                'Motivo requerido',
                '<p>Debe ingresar un motivo para rechazar el pedido.</p>'
                f'<p><a href="/pedido/{token}/rechazar" '
                f'style="color:#DC2626;">← Volver</a></p>'
            )

        try:
            pedido.action_rechazar_gerencia(motivo=motivo, desde_token=True)
            _logger.info(
                "[portal/rechazar] pedido=%s rechazado | motivo=%s",
                pedido.name, motivo[:50]
            )
            return _render_confirmacion(
                'Pedido rechazado',
                f'<p>El pedido <b>{pedido.name}</b> fue rechazado.</p>'
                f'<p><b>Motivo registrado:</b> {motivo}</p>'
                f'<p>El técnico fue notificado por correo.</p>',
                color='#DC2626',
                icono='❌'
            )
        except Exception as e:
            _logger.error(
                "[portal/rechazar] ERROR pedido=%s | %s",
                pedido.name, str(e)
            )
            return _render_error(
                'Error al rechazar',
                f'<p>Ocurrió un error al procesar el rechazo.</p>'
                f'<p style="font-size:12px;color:#9ca3af;">{str(e)}</p>'
            )

    # ============================================================
    # GERENCIA — Pedir informe a Comercial
    # ============================================================

    @http.route(
        '/pedido/<string:token>/pedir-informe',
        type='http',
        auth='public',
        methods=['GET'],
        website=False,
        csrf=False,
    )
    def pedido_pedir_informe(self, token, **kwargs):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado != 'esperando_gerencia':
            estado_label = dict(
                pedido._fields['estado'].selection
            ).get(pedido.estado, pedido.estado)
            return _render_info(
                'Acción no disponible',
                f'<p>El pedido se encuentra en estado: <b>{estado_label}</b></p>'
                f'<p>Solo se puede solicitar informe desde "Esperando Gerencia".</p>'
            )

        try:
            pedido.action_solicitar_informe_comercial(desde_token=True)
            _logger.info(
                "[portal/pedir-informe] pedido=%s informe solicitado a comercial",
                pedido.name
            )
            return _render_confirmacion(
                'Informe solicitado',
                f'<p>Se solicitó un informe técnico a Comercial para el pedido '
                f'<b>{pedido.name}</b>.</p>'
                f'<p>Recibirá una notificación cuando Comercial envíe el informe.</p>',
                color='#D97706',
                icono='📋'
            )
        except Exception as e:
            _logger.error(
                "[portal/pedir-informe] ERROR pedido=%s | %s",
                pedido.name, str(e)
            )
            return _render_error(
                'Error',
                f'<p>Ocurrió un error al solicitar el informe.</p>'
                f'<p style="font-size:12px;color:#9ca3af;">{str(e)}</p>'
            )

    # ============================================================
    # COMERCIAL — Página gestión de stock (GET)
    # ============================================================

    @http.route(
        '/pedido/<string:token>/stock',
        type='http',
        auth='public',
        methods=['GET'],
        website=False,
        csrf=False,
    )
    def pedido_stock(self, token, **kwargs):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado != 'stock_en_revision':
            estado_label = dict(
                pedido._fields['estado'].selection
            ).get(pedido.estado, pedido.estado)
            return _render_info(
                'Pedido no disponible para gestión de stock',
                f'<p>El pedido <b>{pedido.name}</b> se encuentra en estado: '
                f'<b>{estado_label}</b></p>'
                f'<p>La gestión de stock solo está disponible cuando el pedido '
                f'está en "Comercial revisando stock".</p>'
            )

        opciones_stock = [
            ('pendiente',  'Pendiente verificación'),
            ('disponible', 'En stock ✅'),
            ('sin_stock',  'Sin stock — en compra ⏳'),
            ('recibido',   'Recibido de proveedor ✅'),
        ]

        filas_html = ''
        for i, linea in enumerate(pedido.linea_ids):
            color_nombre = linea.color_id.name if linea.color_id else 'B/N'
            color_bg = {
                'Black':   '#374151',
                'Cyan':    '#0891b2',
                'Magenta': '#db2777',
                'Yellow':  '#d97706',
                'B/N':     '#4b5563',
            }.get(color_nombre, '#4b5563')

            opciones_select = ''
            for val, label in opciones_stock:
                selected = 'selected' if linea.estado_stock == val else ''
                opciones_select += (
                    f"<option value='{val}' {selected}>{label}</option>"
                )

            obs_val   = linea.observacion_stock or ''
            fecha_val = str(linea.fecha_disponible) if linea.fecha_disponible else ''

            filas_html += f"""
            <tr class="fila-linea" data-index="{i}">
                <td class="td-num">{i + 1}</td>
                <td class="td-comp">
                    <strong>{linea.componente_display or '—'}</strong>
                </td>
                <td class="td-sub">{linea.subparte_id.name or linea.nombre_libre or '—'}</td>
                <td class="td-color">
                    <span class="badge-color" style="background:{color_bg};">
                        {color_nombre}
                    </span>
                </td>
                <td class="td-cant">{int(linea.cantidad)}</td>
                <td class="td-estado">
                    <select name="estado_stock_{linea.id}"
                            class="select-stock"
                            data-linea="{linea.id}"
                            onchange="onEstadoChange(this)">
                        {opciones_select}
                    </select>
                </td>
                <td class="td-fecha">
                    <input type="date"
                           name="fecha_disponible_{linea.id}"
                           class="input-fecha"
                           value="{fecha_val}"
                           style="display:{'block' if linea.estado_stock == 'sin_stock' else 'none'};"
                    />
                </td>
                <td class="td-obs">
                    <input type="text"
                           name="observacion_stock_{linea.id}"
                           class="input-obs"
                           placeholder="Nota..."
                           value="{obs_val}"
                           maxlength="120"
                    />
                </td>
            </tr>
            """

        total       = len(pedido.linea_ids)
        disponibles = len(pedido.linea_ids.filtered(
            lambda l: l.estado_stock in ('disponible', 'recibido')
        ))
        sin_stock   = len(pedido.linea_ids.filtered(
            lambda l: l.estado_stock == 'sin_stock'
        ))
        pendientes  = total - disponibles - sin_stock

        return f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <title>Stock — {pedido.name}</title>
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: Arial, Helvetica, sans-serif;
                    background: #f3f4f6;
                    padding: 20px;
                    color: #1f2d3d;
                }}
                .container {{ max-width: 1000px; margin: 0 auto; }}
                .header {{
                    background: #1B3A6B;
                    color: #fff;
                    padding: 18px 24px;
                    border-radius: 8px 8px 0 0;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 10px;
                }}
                .header h1 {{ font-size: 17px; }}
                .header .sub {{ font-size: 12px; opacity: 0.8; margin-top: 3px; }}
                .badge-estado {{
                    background: #D97706;
                    color: #fff;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                .info-bar {{
                    display: flex;
                    gap: 10px;
                    background: #fff;
                    border: 1px solid #e5e7eb;
                    border-top: none;
                    padding: 14px 20px;
                    flex-wrap: wrap;
                }}
                .info-card {{
                    flex: 1;
                    min-width: 120px;
                    background: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 6px;
                    padding: 10px 14px;
                    text-align: center;
                }}
                .info-card .num {{
                    font-size: 22px;
                    font-weight: bold;
                    color: #1B3A6B;
                }}
                .info-card .lbl {{ font-size: 11px; color: #6b7280; margin-top: 2px; }}
                .acciones {{
                    background: #fff;
                    border: 1px solid #e5e7eb;
                    border-top: none;
                    padding: 12px 20px;
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    align-items: center;
                }}
                .btn {{
                    padding: 9px 18px;
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                    transition: opacity 0.2s;
                }}
                .btn:hover {{ opacity: 0.85; }}
                .btn-todos    {{ background: #1B3A6B; color: #fff; }}
                .btn-guardar  {{ background: #D97706; color: #fff; }}
                .btn-confirmar {{
                    background: #059669;
                    color: #fff;
                    margin-left: auto;
                }}
                .btn-confirmar:disabled {{
                    background: #9ca3af;
                    cursor: not-allowed;
                    opacity: 1;
                }}
                .tabla-wrap {{
                    background: #fff;
                    border: 1px solid #e5e7eb;
                    border-top: none;
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                }}
                thead tr {{ background: #1B3A6B; color: #fff; }}
                thead th {{
                    padding: 10px 8px;
                    text-align: left;
                    font-size: 12px;
                    white-space: nowrap;
                }}
                tbody tr:nth-child(even) {{ background: #f9fafb; }}
                tbody tr:nth-child(odd)  {{ background: #fff; }}
                tbody td {{ padding: 8px; border-bottom: 1px solid #e5e7eb; }}
                .td-num   {{ text-align: center; color: #9ca3af; width: 40px; }}
                .td-cant  {{ text-align: center; width: 50px; }}
                .td-color {{ text-align: center; width: 80px; }}
                .badge-color {{
                    color: #fff;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                .select-stock {{
                    width: 100%;
                    padding: 6px 8px;
                    border: 1px solid #d1d5db;
                    border-radius: 4px;
                    font-size: 12px;
                    background: #fff;
                    min-width: 180px;
                }}
                .select-stock.ok   {{ border-color: #059669; background: #f0fdf4; }}
                .select-stock.warn {{ border-color: #D97706; background: #fffbeb; }}
                .select-stock.pend {{ border-color: #9ca3af; }}
                .input-fecha, .input-obs {{
                    width: 100%;
                    padding: 5px 8px;
                    border: 1px solid #d1d5db;
                    border-radius: 4px;
                    font-size: 12px;
                }}
                .input-fecha {{ min-width: 130px; }}
                .input-obs   {{ min-width: 160px; }}
                .toast {{
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    background: #1B3A6B;
                    color: #fff;
                    padding: 12px 20px;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                    opacity: 0;
                    transition: opacity 0.3s;
                    z-index: 999;
                }}
                .toast.show {{ opacity: 1; }}
                .footer {{
                    text-align: center;
                    font-size: 11px;
                    color: #9ca3af;
                    padding: 14px;
                    background: #fff;
                    border: 1px solid #e5e7eb;
                    border-top: none;
                    border-radius: 0 0 8px 8px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div>
                        <h1>📦 Gestión de Stock — {pedido.name}</h1>
                        <div class="sub">
                            {pedido.modelo_nombre or '—'} ({pedido.serie or '—'}) |
                            Cliente: {pedido.cliente_id.name or '—'}
                        </div>
                    </div>
                    <span class="badge-estado">Revisando stock</span>
                </div>
                <div class="info-bar">
                    <div class="info-card">
                        <div class="num">{total}</div>
                        <div class="lbl">Total items</div>
                    </div>
                    <div class="info-card">
                        <div class="num" id="num-disponibles">{disponibles}</div>
                        <div class="lbl">Disponibles</div>
                    </div>
                    <div class="info-card">
                        <div class="num" id="num-sinstock">{sin_stock}</div>
                        <div class="lbl">En compra</div>
                    </div>
                    <div class="info-card">
                        <div class="num" id="num-pendientes">{pendientes}</div>
                        <div class="lbl">Sin verificar</div>
                    </div>
                </div>
                <div class="acciones">
                    <button class="btn btn-todos" onclick="marcarTodos()">
                        ✅ Marcar todos disponibles
                    </button>
                    <button class="btn btn-guardar" onclick="guardarStock()">
                        💾 Guardar cambios
                    </button>
                    <button class="btn btn-confirmar"
                            id="btn-confirmar"
                            onclick="confirmarStockCompleto()"
                            {'disabled' if not pedido.todas_disponibles else ''}>
                        🚀 Confirmar stock completo
                    </button>
                </div>
                <form id="form-stock" method="POST"
                      action="/pedido/{token}/stock/guardar">
                    <input type="hidden" name="confirmar" id="input-confirmar" value="0"/>
                    <div class="tabla-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th class="td-num">#</th>
                                    <th>Componente</th>
                                    <th>Subparte / Repuesto</th>
                                    <th class="td-color">Color</th>
                                    <th class="td-cant">Cant.</th>
                                    <th>Estado stock</th>
                                    <th>Fecha estimada</th>
                                    <th>Nota</th>
                                </tr>
                            </thead>
                            <tbody id="tbody-lineas">
                                {filas_html}
                            </tbody>
                        </table>
                    </div>
                </form>
                <div class="footer">Andes Copiers SAC — Sistema de Taller SAT</div>
            </div>
            <div class="toast" id="toast"></div>
            <script>
                const TOTAL = {total};
                function contarEstados() {{
                    let disponibles = 0, sinStock = 0, pendientes = 0;
                    document.querySelectorAll('.select-stock').forEach(sel => {{
                        const v = sel.value;
                        if (v === 'disponible' || v === 'recibido') disponibles++;
                        else if (v === 'sin_stock') sinStock++;
                        else pendientes++;
                        sel.className = 'select-stock';
                        if (v === 'disponible' || v === 'recibido') sel.classList.add('ok');
                        else if (v === 'sin_stock') sel.classList.add('warn');
                        else sel.classList.add('pend');
                    }});
                    document.getElementById('num-disponibles').textContent = disponibles;
                    document.getElementById('num-sinstock').textContent    = sinStock;
                    document.getElementById('num-pendientes').textContent  = pendientes;
                    document.getElementById('btn-confirmar').disabled = (disponibles !== TOTAL);
                }}
                function onEstadoChange(sel) {{
                    const row   = sel.closest('tr');
                    const fecha = row.querySelector('.input-fecha');
                    if (fecha) fecha.style.display = sel.value === 'sin_stock' ? 'block' : 'none';
                    contarEstados();
                }}
                function marcarTodos() {{
                    document.querySelectorAll('.select-stock').forEach(sel => {{
                        sel.value = 'disponible';
                        const row   = sel.closest('tr');
                        const fecha = row.querySelector('.input-fecha');
                        if (fecha) fecha.style.display = 'none';
                    }});
                    contarEstados();
                    mostrarToast('✅ Todos los items marcados como disponibles');
                }}
                function guardarStock() {{
                    document.getElementById('input-confirmar').value = '0';
                    mostrarToast('💾 Guardando...');
                    document.getElementById('form-stock').submit();
                }}
                function confirmarStockCompleto() {{
                    if (!confirm(
                        '¿Confirma que TODOS los repuestos están disponibles?\\n\\n'
                        + 'Esta acción notificará a Logística para preparar la entrega.'
                    )) return;
                    document.getElementById('input-confirmar').value = '1';
                    document.getElementById('form-stock').submit();
                }}
                function mostrarToast(msg) {{
                    const t = document.getElementById('toast');
                    t.textContent = msg;
                    t.classList.add('show');
                    setTimeout(() => t.classList.remove('show'), 2500);
                }}
                document.addEventListener('DOMContentLoaded', contarEstados);
            </script>
        </body>
        </html>
        """

    # ============================================================
    # COMERCIAL — Guardar stock (POST)
    # ============================================================

    @http.route(
        '/pedido/<string:token>/stock/guardar',
        type='http',
        auth='public',
        methods=['POST'],
        website=False,
        csrf=False,
    )
    def pedido_stock_guardar(self, token, **post):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        try:
            confirmar = post.get('confirmar') == '1'

            for linea in pedido.linea_ids:
                estado = post.get(f'estado_stock_{linea.id}')
                fecha  = post.get(f'fecha_disponible_{linea.id}')
                obs    = post.get(f'observacion_stock_{linea.id}')

                vals = {}
                if estado:
                    vals['estado_stock'] = estado
                if fecha:
                    vals['fecha_disponible'] = fecha
                else:
                    vals['fecha_disponible'] = False
                if obs is not None:
                    vals['observacion_stock'] = obs
                if vals:
                    linea.sudo().write(vals)

            _logger.info(
                "[portal/stock/guardar] pedido=%s stock guardado | confirmar=%s",
                pedido.name, confirmar
            )

            if confirmar:
                sin_stock = pedido.linea_ids.filtered(
                    lambda l: l.estado_stock not in ('disponible', 'recibido')
                )
                if sin_stock:
                    return _render_error(
                        'Stock incompleto',
                        f'<p>Aún hay <b>{len(sin_stock)}</b> línea(s) sin stock confirmado.</p>'
                        f'<p>Debe marcar todos los items como disponibles antes de continuar.</p>'
                    )

                # action_stock_completo: cambia estado, crea ticket,
                # notifica a Logística y Soporte
                pedido.sudo().action_stock_completo()

                ticket_inst = pedido.ticket_instalacion_id

                return _render_confirmacion(
                    'Stock confirmado',
                    f'<p>El pedido <b>{pedido.name}</b> tiene stock completo.</p>'
                    f'<p>Ticket de instalación creado: <b>{ticket_inst.name if ticket_inst else "—"}</b></p>'
                    f'<p>Se notificó a Logística y Soporte.</p>',
                    color='#059669',
                    icono='📦'
                )

            return request.redirect(f"/pedido/{token}/stock")

        except Exception as e:
            _logger.error(
                "[portal/stock/guardar] ERROR pedido=%s | %s",
                pedido.name, str(e)
            )
            return _render_error(
                'Error al guardar',
                '<p>Ocurrió un error al guardar los datos.</p>'
                f'<p style="font-size:12px;color:#9ca3af;">{str(e)}</p>'
            )

    # ============================================================
    # COMERCIAL — Página informe técnico (GET)
    # ============================================================

    @http.route(
        '/pedido/<string:token>/informe',
        type='http',
        auth='public',
        methods=['GET'],
        website=False,
        csrf=False,
    )
    def pedido_informe_form(self, token, **kwargs):
        """
        Página de informe técnico para Comercial.
        Por cada línea muestra:
          - Componente / Subparte / Color / Cantidad  (readonly)
          - Contador actual del pedido                (readonly, desde pedido)
          - Contador anterior                         (pre-llenado desde historial o manual)
          - Duración (copias)                         (calculado en JS)
          - Fecha último cambio                       (pre-llenada desde historial o manual)
          - Observación                               (libre)
        Más nota general y adjunto opcional.
        Al guardar notifica a Gerencia con la tabla completa.
        """
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado != 'informe_solicitado':
            estado_label = dict(
                pedido._fields['estado'].selection
            ).get(pedido.estado, pedido.estado)
            return _render_info(
                'Informe no requerido',
                f'<p>El pedido se encuentra en estado: <b>{estado_label}</b></p>'
                f'<p>El informe solo puede enviarse cuando Gerencia lo haya solicitado.</p>'
            )

        import re

        def _to_int(val):
            if not val:
                return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0

        def _fmt_num(val):
            try:
                n = int(re.sub(r'[^\d]', '', str(val)) or 0)
                return f"{n:,}" if n else ''
            except Exception:
                return ''

        # ── Generar filas de la tabla ──────────────────────────────────
        filas_html = ''
        for i, linea in enumerate(pedido.linea_ids):
            color_nombre = linea.color_id.name if linea.color_id else 'B/N'
            color_bg = {
                'Black':   '#374151', 'Cyan':    '#0891b2',
                'Magenta': '#db2777', 'Yellow':  '#d97706', 'B/N': '#4b5563',
            }.get(color_nombre, '#4b5563')

            # Contador actual según tipo de línea (viene del pedido, readonly)
            if linea.color_id:
                cont_actual_raw = pedido.contometro_color or '0'
            else:
                k = _to_int(pedido.contometro_k)
                c = _to_int(pedido.contometro_color)
                es_color = bool(pedido.contometro_color)
                cont_actual_raw = str(k + c) if es_color else (pedido.contometro_k or '0')

            cont_actual_int = _to_int(cont_actual_raw)
            cont_actual_fmt = _fmt_num(cont_actual_raw)

            # Pre-llenar desde historial si existe
            hist_anterior = linea.ultimo_cambio_contometro or ''
            hist_fecha    = (
                linea.ultimo_cambio_fecha.strftime('%Y-%m-%d')
                if linea.ultimo_cambio_fecha else ''
            )
            tiene_historial = bool(hist_anterior)

            # Valor guardado tiene prioridad sobre historial
            val_anterior = linea.contador_informe_anterior or hist_anterior
            val_fecha    = (
                linea.fecha_informe_cambio.strftime('%Y-%m-%d')
                if linea.fecha_informe_cambio
                else hist_fecha
            )
            val_obs = linea.observacion_informe or ''

            # Duración inicial pre-calculada
            dur_inicial = 0
            if val_anterior:
                dur_inicial = max(0, cont_actual_int - _to_int(val_anterior))
            dur_display = f"+{dur_inicial:,}" if dur_inicial else '—'

            badge_fuente = (
                "<span class='badge-auto'>Auto ✓</span>"
                if tiene_historial else
                "<span class='badge-manual'>Manual</span>"
            )
            readonly_attr = 'readonly' if tiene_historial else ''

            filas_html += f"""
            <tr class="fila-linea">
                <td class="td-num">{i + 1}</td>
                <td class="td-comp">
                    <strong>{linea.componente_display or '—'}</strong>
                    <div class="sub-text">
                        {linea.subparte_id.name or linea.nombre_libre or '—'}
                    </div>
                </td>
                <td class="td-color">
                    <span class="badge-color" style="background:{color_bg};">
                        {color_nombre}
                    </span>
                </td>
                <td class="td-cant">{int(linea.cantidad)}</td>
                <td class="td-actual">
                    {cont_actual_fmt or '—'}
                </td>
                <td class="td-anterior">
                    {badge_fuente}
                    <input type="text"
                           name="contador_anterior_{linea.id}"
                           class="input-contador input-anterior"
                           data-linea="{linea.id}"
                           data-actual="{cont_actual_int}"
                           value="{_fmt_num(val_anterior) if val_anterior else ''}"
                           placeholder="Ej: 125,400"
                           {readonly_attr}
                    />
                </td>
                <td class="td-duracion">
                    <span class="duracion-valor" id="dur_{linea.id}">
                        {dur_display}
                    </span>
                </td>
                <td class="td-fecha">
                    <input type="date"
                           name="fecha_cambio_{linea.id}"
                           class="input-fecha"
                           value="{val_fecha}"
                           {readonly_attr}
                    />
                </td>
                <td class="td-obs">
                    <input type="text"
                           name="observacion_{linea.id}"
                           class="input-obs"
                           placeholder="Observación..."
                           value="{val_obs}"
                           maxlength="150"
                    />
                </td>
            </tr>
            """

        total_lineas = len(pedido.linea_ids)

        return f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <title>Informe técnico — {pedido.name}</title>
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: Arial, Helvetica, sans-serif;
                    background: #f3f4f6;
                    padding: 20px;
                    color: #1f2d3d;
                    font-size: 13px;
                }}
                .container {{ max-width: 1100px; margin: 0 auto; }}

                .header {{
                    background: #D97706;
                    color: #fff;
                    padding: 18px 24px;
                    border-radius: 8px 8px 0 0;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 10px;
                }}
                .header h1 {{ font-size: 17px; }}
                .header .sub {{ font-size: 12px; opacity: 0.85; margin-top: 3px; }}

                .info-bar {{
                    background: #fffbeb;
                    border: 1px solid #fde68a;
                    border-top: none;
                    padding: 10px 20px;
                    font-size: 13px;
                    color: #374151;
                    display: flex;
                    gap: 24px;
                    flex-wrap: wrap;
                    align-items: center;
                }}
                .info-bar b {{ color: #1f2d3d; }}

                .tabla-wrap {{
                    background: #fff;
                    border: 1px solid #e5e7eb;
                    border-top: none;
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 12px;
                }}
                thead tr {{ background: #1B3A6B; color: #fff; }}
                thead th {{
                    padding: 9px 8px;
                    text-align: left;
                    white-space: nowrap;
                    font-size: 11px;
                }}
                tbody tr:nth-child(even) {{ background: #f9fafb; }}
                tbody tr:nth-child(odd)  {{ background: #fff; }}
                tbody td {{
                    padding: 7px 8px;
                    border-bottom: 1px solid #f0f0f0;
                    vertical-align: middle;
                }}
                .td-num      {{ text-align:center; color:#9ca3af; width:36px; }}
                .td-cant     {{ text-align:center; width:46px; }}
                .td-color    {{ text-align:center; width:76px; }}
                .td-actual   {{
                    text-align:right;
                    font-family:monospace;
                    font-size:12px;
                    width:100px;
                    color:#1B3A6B;
                    font-weight:bold;
                }}
                .td-anterior {{ width:170px; }}
                .td-duracion {{
                    text-align:right;
                    width:90px;
                    font-weight:bold;
                    color:#059669;
                    font-family:monospace;
                    font-size:13px;
                }}
                .td-fecha {{ width:140px; }}
                .td-obs   {{ min-width:160px; }}

                .badge-color {{
                    color:#fff;
                    padding:2px 8px;
                    border-radius:10px;
                    font-size:10px;
                    font-weight:bold;
                }}
                .badge-auto {{
                    background:#dbeafe;
                    color:#1d4ed8;
                    font-size:9px;
                    padding:1px 5px;
                    border-radius:8px;
                    display:block;
                    margin-bottom:3px;
                    width:fit-content;
                }}
                .badge-manual {{
                    background:#fef3c7;
                    color:#92400e;
                    font-size:9px;
                    padding:1px 5px;
                    border-radius:8px;
                    display:block;
                    margin-bottom:3px;
                    width:fit-content;
                }}
                .sub-text {{
                    font-size:11px;
                    color:#6b7280;
                    margin-top:2px;
                }}
                .input-contador, .input-fecha, .input-obs {{
                    width:100%;
                    padding:5px 7px;
                    border:1px solid #d1d5db;
                    border-radius:4px;
                    font-size:12px;
                    outline:none;
                    transition:border-color 0.15s;
                }}
                .input-contador:focus,
                .input-fecha:focus,
                .input-obs:focus {{ border-color:#D97706; }}
                .input-contador[readonly],
                .input-fecha[readonly] {{
                    background:#f3f4f6;
                    color:#6b7280;
                    cursor:default;
                    border-color:#e5e7eb;
                }}
                .duracion-valor.negativo {{ color:#DC2626; }}

                .leyenda {{
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-top:none;
                    padding:8px 20px;
                    font-size:11px;
                    color:#6b7280;
                    display:flex;
                    gap:20px;
                    flex-wrap:wrap;
                    align-items:center;
                }}

                .nota-wrap {{
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-top:none;
                    padding:12px 20px;
                    display:flex;
                    gap:14px;
                    align-items:flex-start;
                    flex-wrap:wrap;
                }}
                .nota-wrap label {{
                    font-size:12px;
                    font-weight:bold;
                    color:#374151;
                    white-space:nowrap;
                    padding-top:8px;
                    min-width:90px;
                }}
                .nota-wrap textarea {{
                    flex:1;
                    min-width:200px;
                    padding:8px 10px;
                    border:1px solid #d1d5db;
                    border-radius:5px;
                    font-size:13px;
                    font-family:Arial, sans-serif;
                    resize:vertical;
                    min-height:60px;
                    outline:none;
                }}
                .nota-wrap textarea:focus {{ border-color:#D97706; }}

                .adjunto-wrap {{
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-top:none;
                    padding:10px 20px;
                    display:flex;
                    align-items:center;
                    gap:14px;
                    flex-wrap:wrap;
                }}
                .adjunto-wrap label {{
                    font-size:12px;
                    font-weight:bold;
                    color:#374151;
                    white-space:nowrap;
                    min-width:90px;
                }}
                .adjunto-wrap input[type=file] {{
                    font-size:12px;
                    border:1px solid #d1d5db;
                    border-radius:5px;
                    padding:5px 8px;
                }}

                .acciones {{
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-top:none;
                    padding:12px 20px;
                    display:flex;
                    gap:10px;
                    align-items:center;
                    flex-wrap:wrap;
                }}
                .btn {{
                    padding:9px 20px;
                    border:none;
                    border-radius:6px;
                    font-size:13px;
                    font-weight:bold;
                    cursor:pointer;
                    transition:opacity 0.2s;
                }}
                .btn:hover {{ opacity:0.85; }}
                .btn-enviar {{
                    background:#D97706;
                    color:#fff;
                    margin-left:auto;
                    padding:10px 28px;
                    font-size:14px;
                }}
                .btn-limpiar {{
                    background:#f3f4f6;
                    color:#374151;
                    border:1px solid #d1d5db;
                }}

                .toast {{
                    position:fixed;
                    bottom:20px;
                    right:20px;
                    background:#1B3A6B;
                    color:#fff;
                    padding:12px 20px;
                    border-radius:8px;
                    font-size:13px;
                    font-weight:bold;
                    opacity:0;
                    transition:opacity 0.3s;
                    z-index:999;
                }}
                .toast.show {{ opacity:1; }}

                .footer {{
                    text-align:center;
                    font-size:11px;
                    color:#9ca3af;
                    padding:14px;
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-top:none;
                    border-radius:0 0 8px 8px;
                }}
            </style>
        </head>
        <body>
            <div class="container">

                <!-- HEADER -->
                <div class="header">
                    <div>
                        <h1>📋 Informe técnico — {pedido.name}</h1>
                        <div class="sub">
                            {pedido.modelo_nombre or '—'} ({pedido.serie or '—'}) |
                            Cliente: {pedido.cliente_id.name or '—'} |
                            Técnico: {pedido.tecnico_id.name or '—'}
                        </div>
                    </div>
                    <span style="background:#fff;color:#D97706;padding:4px 12px;
                                 border-radius:20px;font-size:12px;font-weight:bold;">
                        Informe solicitado
                    </span>
                </div>

                <!-- INFO CONTÓMETROS -->
                <div class="info-bar">
                    <span><b>Cont. K (B/N):</b> {pedido.contometro_k or '—'}</span>
                    {'<span><b>Cont. Color:</b> ' + (pedido.contometro_color or '—') + '</span>' if pedido.contometro_color else ''}
                    <span><b>Total repuestos:</b> {total_lineas}</span>
                </div>

                <form id="form-informe" method="POST"
                      action="/pedido/{token}/informe/guardar"
                      enctype="multipart/form-data">

                    <!-- TABLA DE LÍNEAS -->
                    <div class="tabla-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th class="td-num">#</th>
                                    <th>Componente / Repuesto</th>
                                    <th class="td-color">Color</th>
                                    <th class="td-cant">Cant.</th>
                                    <th style="text-align:right;">Cont. Actual</th>
                                    <th>Cont. Anterior</th>
                                    <th style="text-align:right;">Duración</th>
                                    <th>Fecha Cambio</th>
                                    <th>Observación</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filas_html}
                            </tbody>
                        </table>
                    </div>

                    <!-- LEYENDA -->
                    <div class="leyenda">
                        <span>
                            <span class="badge-auto">Auto ✓</span>
                            Pre-cargado desde historial del sistema
                        </span>
                        <span>
                            <span class="badge-manual">Manual</span>
                            Sin historial — ingrese manualmente
                        </span>
                        <span style="margin-left:auto;">
                            Duración = Contador actual − Contador anterior
                        </span>
                    </div>

                    <!-- NOTA GENERAL -->
                    <div class="nota-wrap">
                        <label for="nota">Nota general:</label>
                        <textarea id="nota" name="nota"
                            placeholder="Resumen del informe o comentarios adicionales..."
                        ></textarea>
                    </div>

                    <!-- ADJUNTO OPCIONAL -->
                    <div class="adjunto-wrap">
                        <label for="adjunto">Adjunto (opcional):</label>
                        <input type="file" id="adjunto" name="adjunto"
                               accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"/>
                        <span style="font-size:11px;color:#9ca3af;">PDF, Word o imagen</span>
                    </div>

                    <!-- ACCIONES -->
                    <div class="acciones">
                        <button type="button" class="btn btn-limpiar"
                                onclick="limpiarManuales()">
                            🔄 Limpiar campos manuales
                        </button>
                        <button type="submit" class="btn btn-enviar">
                            📤 Enviar informe a Gerencia
                        </button>
                    </div>

                </form>

                <div class="footer">Andes Copiers SAC — Sistema de Taller SAT</div>
            </div>

            <div class="toast" id="toast"></div>

            <script>
                // ── Calcular duración al cambiar contador anterior ──────
                function calcularDuracion(input) {{
                    const linea    = input.dataset.linea;
                    const actual   = parseInt(input.dataset.actual) || 0;
                    const rawVal   = input.value.replace(/[^\d]/g, '');
                    const anterior = parseInt(rawVal) || 0;
                    const durEl    = document.getElementById('dur_' + linea);
                    if (!durEl) return;

                    if (!anterior) {{
                        durEl.textContent = '—';
                        durEl.className   = 'duracion-valor';
                        return;
                    }}

                    const dur = actual - anterior;
                    durEl.textContent = (dur >= 0 ? '+' : '') +
                                        dur.toLocaleString('es-PE');
                    durEl.className = 'duracion-valor' + (dur < 0 ? ' negativo' : '');
                }}

                // ── Formatear número con separador de miles ─────────────
                function formatearContador(input) {{
                    const cursor = input.selectionStart;
                    const raw    = input.value.replace(/[^\d]/g, '');
                    if (!raw) {{ input.value = ''; return; }}
                    input.value = parseInt(raw).toLocaleString('es-PE');
                    try {{ input.setSelectionRange(cursor, cursor); }} catch(e) {{}}
                }}

                // ── Limpiar solo campos manuales (no readonly) ──────────
                function limpiarManuales() {{
                    if (!confirm('¿Limpiar los campos ingresados manualmente?')) return;
                    document.querySelectorAll(
                        '.input-anterior:not([readonly]), .input-fecha:not([readonly])'
                    ).forEach(el => {{
                        el.value = '';
                        if (el.classList.contains('input-anterior')) {{
                            calcularDuracion(el);
                        }}
                    }});
                    mostrarToast('🔄 Campos manuales limpiados');
                }}

                function mostrarToast(msg) {{
                    const t = document.getElementById('toast');
                    t.textContent = msg;
                    t.classList.add('show');
                    setTimeout(() => t.classList.remove('show'), 2500);
                }}

                // ── Inicializar eventos ─────────────────────────────────
                document.addEventListener('DOMContentLoaded', function() {{
                    document.querySelectorAll('.input-anterior:not([readonly])').forEach(inp => {{
                        inp.addEventListener('input', function() {{
                            formatearContador(this);
                            calcularDuracion(this);
                        }});
                    }});
                }});
            </script>
        </body>
        </html>
        """

    # ============================================================
    # COMERCIAL — Guardar informe (POST)
    # ============================================================

    @http.route(
        '/pedido/<string:token>/informe/guardar',
        type='http',
        auth='public',
        methods=['POST'],
        website=False,
        csrf=False,
    )
    def pedido_informe_guardar(self, token, **post):
        """
        Recibe datos del informe de Comercial por línea:
          - contador_anterior_<id>
          - fecha_cambio_<id>
          - observacion_<id>
        Más nota general y adjunto opcional.
        Guarda en campos nuevos de la línea y llama action_informe_recibido
        (que notifica a Gerencia) sin alterar su lógica.
        """
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado != 'informe_solicitado':
            return _render_info(
                'Informe ya recibido',
                '<p>El informe de este pedido ya fue procesado.</p>'
            )

        try:
            import re

            # ── 1. Guardar datos por línea ─────────────────────────────
            for linea in pedido.linea_ids:
                lid = linea.id

                raw_anterior = post.get(f'contador_anterior_{lid}', '').strip()
                fecha_cambio = post.get(f'fecha_cambio_{lid}', '').strip()
                observacion  = post.get(f'observacion_{lid}', '').strip()

                # Quitar separadores de miles antes de guardar
                anterior_limpio = re.sub(r'[^\d]', '', raw_anterior) if raw_anterior else ''

                vals = {}
                if anterior_limpio:
                    vals['contador_informe_anterior'] = anterior_limpio
                if fecha_cambio:
                    vals['fecha_informe_cambio'] = fecha_cambio
                if observacion:
                    vals['observacion_informe'] = observacion

                if vals:
                    linea.sudo().write(vals)

            _logger.info(
                "[portal/informe/guardar] pedido=%s líneas guardadas",
                pedido.name
            )

            # ── 2. Nota general ────────────────────────────────────────
            nota = post.get('nota', '').strip()

            # ── 3. Adjunto opcional ────────────────────────────────────
            adjunto_vals = None
            adjunto = request.httprequest.files.get('adjunto')
            if adjunto and adjunto.filename:
                try:
                    datos_b64 = base64.b64encode(adjunto.read()).decode('utf-8')
                    adjunto_vals = {
                        'nombre': adjunto.filename,
                        'datos':  datos_b64,
                    }
                    _logger.info(
                        "[portal/informe/guardar] pedido=%s adjunto=%s",
                        pedido.name, adjunto.filename
                    )
                except Exception as e:
                    _logger.warning(
                        "[portal/informe/guardar] Error adjunto pedido=%s | %s",
                        pedido.name, str(e)
                    )

            # ── 4. Notificar a Gerencia (lógica existente sin tocar) ───
            pedido.action_informe_recibido(nota=nota, adjunto_vals=adjunto_vals)

            _logger.info(
                "[portal/informe/guardar] pedido=%s informe enviado a gerencia",
                pedido.name
            )

            return _render_confirmacion(
                'Informe enviado',
                f'<p>El informe del pedido <b>{pedido.name}</b> '
                f'fue enviado a Gerencia correctamente.</p>'
                f'<p>Recibirá notificación cuando Gerencia tome una decisión.</p>'
                + (f'<p><b>Nota enviada:</b> {nota}</p>' if nota else ''),
                color='#D97706',
                icono='📎'
            )

        except Exception as e:
            _logger.error(
                "[portal/informe/guardar] ERROR pedido=%s | %s",
                pedido.name, str(e)
            )
            return _render_error(
                'Error al enviar informe',
                f'<p>{str(e)}</p>'
                f'<p><a href="/pedido/{token}/informe" '
                f'style="color:#D97706;">← Volver</a></p>'
            )

    # ============================================================
    # LOGÍSTICA — Confirmar entrega
    # ============================================================

    @http.route(
        '/pedido/<string:token>/entregar',
        type='http',
        auth='public',
        methods=['GET'],
        website=False,
        csrf=False,
    )
    def pedido_entregar(self, token, **kwargs):
        pedido, error = _get_pedido_by_token(token)
        if error:
            return error

        if pedido.estado != 'stock_completo':
            estado_label = dict(
                pedido._fields['estado'].selection
            ).get(pedido.estado, pedido.estado)
            return _render_info(
                'Acción ya procesada',
                f'<p>El pedido se encuentra en estado: <b>{estado_label}</b></p>'
                f'<p>La confirmación de entrega ya fue procesada o '
                f'el pedido no está listo para entrega.</p>'
            )

        try:
            pedido.action_confirmar_entrega(desde_token=True)
            ticket_inst = pedido.ticket_instalacion_id

            info_ticket = ''
            if ticket_inst:
                info_ticket = (
                    f'<p><b>Ticket de instalación creado:</b> {ticket_inst.name}</p>'
                    f'<p>El técnico fue notificado para proceder con la instalación.</p>'
                )

            _logger.info(
                "[portal/entregar] pedido=%s entrega confirmada | ticket=%s",
                pedido.name,
                ticket_inst.name if ticket_inst else 'N/A'
            )

            return _render_confirmacion(
                'Entrega confirmada',
                f'<p>La entrega del pedido <b>{pedido.name}</b> fue confirmada.</p>'
                f'<p><b>Técnico:</b> {pedido.tecnico_id.name or "—"}</p>'
                f'{info_ticket}',
                color='#059669',
                icono='🚚'
            )
        except Exception as e:
            _logger.error(
                "[portal/entregar] ERROR pedido=%s | %s",
                pedido.name, str(e)
            )
            return _render_error(
                'Error al confirmar entrega',
                f'<p>{str(e)}</p>'
            )
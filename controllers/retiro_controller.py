# -*- coding: utf-8 -*-
"""
Controller: Página de motivo de retiro
=======================================
Archivo: controllers/retiro_controller.py

Rutas:
  GET  /sat/retiro/<token>        → muestra página HTML con opciones
  POST /sat/retiro/<token>        → procesa el motivo elegido
"""
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Mapa de motivo → descripción larga para la página de confirmación
MOTIVOS_DISPLAY = {
    'cliente_tarde':     'El cliente aún no llega, lo estoy esperando',
    'sin_autorizacion':  'No me autorizaron el ingreso',
    'ausencia_temporal': 'Salí momentáneamente, regreso a terminar',
    'finalizado':        'Ya finalicé el servicio',
}

# Colores por motivo para el botón seleccionado
MOTIVOS_COLOR = {
    'cliente_tarde':     '#F59E0B',
    'sin_autorizacion':  '#EF4444',
    'ausencia_temporal': '#3B82F6',
    'finalizado':        '#10B981',
}


def _html_base(contenido, titulo="Confirmación de retiro"):
    """Genera el HTML base responsive optimizado para móvil."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0"/>
  <title>{titulo}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #F1F5F9;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }}

    .card {{
      background: #FFFFFF;
      border-radius: 16px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      padding: 28px 24px 32px;
      width: 100%;
      max-width: 420px;
    }}

    .logo {{
      text-align: center;
      margin-bottom: 20px;
    }}
    .logo-text {{
      font-size: 13px;
      color: #94A3B8;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .titulo {{
      font-size: 20px;
      font-weight: 700;
      color: #1E293B;
      text-align: center;
      margin-bottom: 6px;
    }}

    .subtitulo {{
      font-size: 14px;
      color: #64748B;
      text-align: center;
      margin-bottom: 24px;
      line-height: 1.5;
    }}

    .ticket-info {{
      background: #F8FAFC;
      border: 1px solid #E2E8F0;
      border-radius: 10px;
      padding: 14px 16px;
      margin-bottom: 24px;
    }}
    .ticket-info .label {{
      font-size: 11px;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 600;
      margin-bottom: 2px;
    }}
    .ticket-info .valor {{
      font-size: 15px;
      color: #1E293B;
      font-weight: 600;
    }}
    .ticket-info .fila {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
    }}
    .ticket-info .fila > div {{
      flex: 1;
    }}

    .opciones {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 24px;
    }}

    .opcion {{
      display: flex;
      align-items: flex-start;
      gap: 14px;
      padding: 16px;
      border: 2px solid #E2E8F0;
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.15s ease;
      background: #FFFFFF;
      width: 100%;
      text-align: left;
      -webkit-tap-highlight-color: transparent;
    }}
    .opcion:active {{
      transform: scale(0.98);
    }}
    .opcion.seleccionada {{
      border-color: var(--color);
      background: var(--bg);
    }}
    .opcion-icono {{
      font-size: 24px;
      flex-shrink: 0;
      margin-top: 1px;
    }}
    .opcion-texto .opcion-titulo {{
      font-size: 14px;
      font-weight: 600;
      color: #1E293B;
      line-height: 1.3;
      margin-bottom: 2px;
    }}
    .opcion-texto .opcion-desc {{
      font-size: 12px;
      color: #64748B;
      line-height: 1.4;
    }}

    .btn-confirmar {{
      width: 100%;
      padding: 16px;
      border: none;
      border-radius: 12px;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
      background: #CBD5E1;
      color: #FFFFFF;
      letter-spacing: 0.02em;
    }}
    .btn-confirmar.activo {{
      background: #1E293B;
    }}
    .btn-confirmar.activo:active {{
      transform: scale(0.98);
      background: #0F172A;
    }}

    .alerta {{
      background: #FEF3C7;
      border: 1px solid #FCD34D;
      border-radius: 10px;
      padding: 12px 14px;
      font-size: 13px;
      color: #92400E;
      text-align: center;
      margin-bottom: 20px;
      line-height: 1.5;
    }}

    /* Estados finales */
    .estado-icono {{
      font-size: 56px;
      text-align: center;
      margin-bottom: 16px;
    }}
    .estado-titulo {{
      font-size: 22px;
      font-weight: 700;
      color: #1E293B;
      text-align: center;
      margin-bottom: 10px;
    }}
    .estado-mensaje {{
      font-size: 15px;
      color: #64748B;
      text-align: center;
      line-height: 1.6;
    }}
    .estado-detalle {{
      background: #F8FAFC;
      border: 1px solid #E2E8F0;
      border-radius: 10px;
      padding: 14px 16px;
      margin-top: 20px;
      font-size: 14px;
      color: #475569;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <span class="logo-text">Andes Solution Copiers</span>
    </div>
    {contenido}
  </div>
</body>
</html>"""


class RetiroController(http.Controller):

    # ─────────────────────────────────────────────────────────────
    #  GET — mostrar página de opciones
    # ─────────────────────────────────────────────────────────────

    @http.route('/sat/retiro/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def retiro_get(self, token, **kwargs):
        TokenModel = request.env['ticket.retiro.token'].sudo()
        token_rec  = TokenModel.buscar_token_valido(token)

        if not token_rec:
            # Token inválido, expirado o ya usado
            token_any = TokenModel.search([('token', '=', token)], limit=1)
            if token_any and token_any.estado == 'respondido':
                contenido = self._html_ya_respondido(token_any)
            elif token_any and token_any.estado == 'cancelado':
                contenido = self._html_cancelado()
            else:
                contenido = self._html_expirado()
            return request.make_response(
                _html_base(contenido),
                headers=[('Content-Type', 'text/html; charset=utf-8')]
            )

        ticket   = token_rec.ticket_id
        tecnico  = ticket.responsable
        cliente  = ticket.partner_id
        tiempo   = token_rec.tiempo_en_sitio_minutos

        from pytz import timezone as pytz_tz, UTC
        import odoo.fields as flds

        def fmt_hora(dt):
            if not dt:
                return '--'
            try:
                return UTC.localize(dt).astimezone(pytz_tz('America/Lima')).strftime('%H:%M')
            except Exception:
                return '--'

        def fmt_min(mins):
            if not mins:
                return '--'
            h, m = int(mins // 60), int(mins % 60)
            return f"{h}h {m}min" if h else f"{m}min"

        hora_llegada = fmt_hora(ticket.fecha_llegada)
        tiempo_str   = fmt_min(tiempo)

        contenido = f"""
<h1 class="titulo">¿Por qué saliste del sitio?</h1>
<p class="subtitulo">Selecciona el motivo para que coordinación esté informada</p>

<div class="ticket-info">
  <div class="fila">
    <div>
      <div class="label">Técnico</div>
      <div class="valor">{tecnico.name if tecnico else 'N/A'}</div>
    </div>
    <div>
      <div class="label">Cliente</div>
      <div class="valor">{cliente.name if cliente else 'N/A'}</div>
    </div>
  </div>
  <div style="margin-top:10px">
    <div class="label">Ticket</div>
    <div class="valor">{ticket.name}</div>
  </div>
  <div class="fila" style="margin-top:10px">
    <div>
      <div class="label">Llegada</div>
      <div class="valor">{hora_llegada}</div>
    </div>
    <div>
      <div class="label">Tiempo en sitio</div>
      <div class="valor">{tiempo_str}</div>
    </div>
  </div>
</div>

<div class="alerta">
  ⏱ Tienes <strong>15 minutos</strong> para confirmar.<br/>
  Si no respondes, coordinación será notificada.
</div>

<form method="POST" action="/sat/retiro/{token}" id="form-retiro">
  <input type="hidden" name="csrf_token" value="{request.csrf_token()}"/>
  <input type="hidden" name="motivo" id="motivo-input" value=""/>

  <div class="opciones">

    <button type="button" class="opcion"
            style="--color:#F59E0B; --bg:#FFFBEB"
            onclick="elegir(this, 'cliente_tarde')">
      <span class="opcion-icono">⏳</span>
      <div class="opcion-texto">
        <div class="opcion-titulo">Cliente aún no llega</div>
        <div class="opcion-desc">Lo estoy esperando, regreso cuando llegue</div>
      </div>
    </button>

    <button type="button" class="opcion"
            style="--color:#EF4444; --bg:#FEF2F2"
            onclick="elegir(this, 'sin_autorizacion')">
      <span class="opcion-icono">🚫</span>
      <div class="opcion-texto">
        <div class="opcion-titulo">No me autorizaron el ingreso</div>
        <div class="opcion-desc">Seguridad, encargado ausente u otro impedimento</div>
      </div>
    </button>

    <button type="button" class="opcion"
            style="--color:#3B82F6; --bg:#EFF6FF"
            onclick="elegir(this, 'ausencia_temporal')">
      <span class="opcion-icono">🔄</span>
      <div class="opcion-texto">
        <div class="opcion-titulo">Salí momentáneamente</div>
        <div class="opcion-desc">Almuerzo, repuesto, compra — regreso a terminar</div>
      </div>
    </button>

    <button type="button" class="opcion"
            style="--color:#10B981; --bg:#ECFDF5"
            onclick="elegir(this, 'finalizado')">
      <span class="opcion-icono">✅</span>
      <div class="opcion-texto">
        <div class="opcion-titulo">Ya finalicé el servicio</div>
        <div class="opcion-desc">El trabajo está completado</div>
      </div>
    </button>

  </div>

  <button type="submit" class="btn-confirmar" id="btn-confirmar" disabled>
    Confirmar motivo
  </button>
</form>

<script>
  var motivoActual = null;

  function elegir(btn, motivo) {{
    document.querySelectorAll('.opcion').forEach(function(el) {{
      el.classList.remove('seleccionada');
    }});
    btn.classList.add('seleccionada');
    document.getElementById('motivo-input').value = motivo;
    var btnConf = document.getElementById('btn-confirmar');
    btnConf.disabled = false;
    btnConf.classList.add('activo');
    motivoActual = motivo;
  }}

  document.getElementById('form-retiro').addEventListener('submit', function(e) {{
    if (!motivoActual) {{
      e.preventDefault();
      return;
    }}
    var btn = document.getElementById('btn-confirmar');
    btn.disabled = true;
    btn.textContent = 'Enviando...';
  }});
</script>
"""
        return request.make_response(
            _html_base(contenido, titulo=f"Retiro — {ticket.name}"),
            headers=[('Content-Type', 'text/html; charset=utf-8')]
        )

    # ─────────────────────────────────────────────────────────────
    #  POST — procesar motivo elegido
    # ─────────────────────────────────────────────────────────────

    @http.route('/sat/retiro/<string:token>', type='http', auth='public', methods=['POST'], csrf=False)
    def retiro_post(self, token, **post):
        motivo = post.get('motivo', '').strip()

        motivos_validos = {'cliente_tarde', 'sin_autorizacion', 'ausencia_temporal', 'finalizado'}
        if motivo not in motivos_validos:
            contenido = self._html_error("Motivo no válido. Por favor regresa e intenta de nuevo.")
            return request.make_response(
                _html_base(contenido),
                headers=[('Content-Type', 'text/html; charset=utf-8')]
            )

        TokenModel = request.env['ticket.retiro.token'].sudo()
        token_rec  = TokenModel.buscar_token_valido(token)

        if not token_rec:
            contenido = self._html_expirado()
            return request.make_response(
                _html_base(contenido),
                headers=[('Content-Type', 'text/html; charset=utf-8')]
            )

        ticket = token_rec.ticket_id
        ok     = token_rec.marcar_respondido(motivo)

        if not ok:
            contenido = self._html_expirado()
            return request.make_response(
                _html_base(contenido),
                headers=[('Content-Type', 'text/html; charset=utf-8')]
            )

        ubicacion_actual = {
            'latitude':  token_rec.lat_salida or None,
            'longitude': token_rec.lon_salida or None,
        }

        # Procesar según motivo
        try:
            if motivo == 'finalizado':
                ticket._registrar_evento("Técnico confirmó finalización via link de retiro")
                ticket.sudo()._registrar_finalizacion_tracking()

            elif motivo == 'cliente_tarde':
                ticket._registrar_evento("Técnico informa: cliente aún no llega, esperando")
                try:
                    ticket.notificar_motivo_retiro(
                        motivo=motivo,
                        ubicacion_actual=ubicacion_actual,
                        tiempo_en_sitio=token_rec.tiempo_en_sitio_minutos,
                    )
                except Exception as e:
                    _logger.error("[RETIRO] Error notificando cliente_tarde: %s", e)

            elif motivo == 'sin_autorizacion':
                ticket._registrar_evento("Técnico informa: no le autorizaron el ingreso")
                try:
                    ticket.notificar_motivo_retiro(
                        motivo=motivo,
                        ubicacion_actual=ubicacion_actual,
                        tiempo_en_sitio=token_rec.tiempo_en_sitio_minutos,
                    )
                except Exception as e:
                    _logger.error("[RETIRO] Error notificando sin_autorizacion: %s", e)

            elif motivo == 'ausencia_temporal':
                ticket._registrar_evento("Técnico informa: salida temporal, regresa a terminar")
                try:
                    ticket.notificar_motivo_retiro(
                        motivo=motivo,
                        ubicacion_actual=ubicacion_actual,
                        tiempo_en_sitio=token_rec.tiempo_en_sitio_minutos,
                    )
                except Exception as e:
                    _logger.error("[RETIRO] Error notificando ausencia_temporal: %s", e)

        except Exception as e:
            _logger.error("[RETIRO] Error procesando motivo %s para ticket %s: %s",
                          motivo, ticket.name, e)

        contenido = self._html_confirmado(motivo, ticket)
        return request.make_response(
            _html_base(contenido, titulo="Motivo registrado"),
            headers=[('Content-Type', 'text/html; charset=utf-8')]
        )

    # ─────────────────────────────────────────────────────────────
    #  PÁGINAS DE ESTADO
    # ─────────────────────────────────────────────────────────────

    def _html_confirmado(self, motivo, ticket):
        iconos = {
            'cliente_tarde':     '⏳',
            'sin_autorizacion':  '🚫',
            'ausencia_temporal': '🔄',
            'finalizado':        '✅',
        }
        textos = {
            'cliente_tarde':     ('Recibido', 'Coordinación sabe que estás esperando al cliente.'),
            'sin_autorizacion':  ('Recibido', 'Coordinación fue notificada para gestionar el acceso.'),
            'ausencia_temporal': ('Recibido', 'Cuando regreses al sitio, el sistema lo detectará automáticamente.'),
            'finalizado':        ('Servicio cerrado', 'El ticket ha sido finalizado correctamente. ¡Buen trabajo!'),
        }
        icono  = iconos.get(motivo, '✅')
        titulo, mensaje = textos.get(motivo, ('Registrado', 'Motivo guardado correctamente.'))

        return f"""
<div class="estado-icono">{icono}</div>
<h1 class="estado-titulo">{titulo}</h1>
<p class="estado-mensaje">{mensaje}</p>
<div class="estado-detalle">
  <strong>{ticket.name}</strong><br/>
  {ticket.partner_id.name if ticket.partner_id else ''}
</div>
"""

    def _html_expirado(self):
        return """
<div class="estado-icono">⏰</div>
<h1 class="estado-titulo">Link expirado</h1>
<p class="estado-mensaje">
  Este link ya no es válido porque pasaron los 15 minutos.<br/><br/>
  Coordinación ya fue notificada automáticamente.
</p>
"""

    def _html_ya_respondido(self, token_rec):
        from pytz import timezone as pytz_tz, UTC
        def fmt_hora(dt):
            if not dt:
                return '--'
            try:
                return UTC.localize(dt).astimezone(pytz_tz('America/Lima')).strftime('%H:%M')
            except Exception:
                return '--'
        hora = fmt_hora(token_rec.respondido_en)
        return f"""
<div class="estado-icono">✅</div>
<h1 class="estado-titulo">Ya respondiste</h1>
<p class="estado-mensaje">
  Registraste tu motivo a las <strong>{hora}</strong>.<br/><br/>
  <em>{token_rec.motivo_label}</em>
</p>
"""

    def _html_cancelado(self):
        return """
<div class="estado-icono">↩️</div>
<h1 class="estado-titulo">Regresaste al sitio</h1>
<p class="estado-mensaje">
  Detectamos que volviste a la ubicación del servicio.<br/><br/>
  No es necesario confirmar ningún motivo.
</p>
"""

    def _html_error(self, mensaje):
        return f"""
<div class="estado-icono">⚠️</div>
<h1 class="estado-titulo">Error</h1>
<p class="estado-mensaje">{mensaje}</p>
"""
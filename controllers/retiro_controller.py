
# -*- coding: utf-8 -*-
"""
Controlador de confirmación de motivo de retiro
================================================
Archivo: sat/controllers/retiro_controller.py
Compatible con Odoo 19

Rutas existentes:
GET  /sat/retiro/<token>
POST /sat/retiro/<token>

REGLAS:
- Un token vigente permite registrar una respuesta.
- El token no autoriza finalizar administrativamente tickets.
- La respuesta no acredita por sí sola una salida GPS.
- El motivo 'finalizado' es una declaración del técnico.
- Nunca ejecutar action_finalizar() desde este controlador.
- Nunca ejecutar _registrar_finalizacion_tracking().
- Nunca escribir fecha_salida_sitio.
- No inventar fechas ni posiciones GPS.
- No afirmar entrega de WhatsApp sin confirmación.
- Proteger POST contra CSRF.
- Escapar datos dinámicos antes de mostrarlos en HTML.
"""

import logging
from html import escape

from pytz import UTC, timezone as pytz_timezone

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


MOTIVOS_DISPLAY = {
    'cliente_tarde': (
        'El cliente aún no llega, lo estoy esperando'
    ),
    'sin_autorizacion': (
        'No me autorizaron el ingreso'
    ),
    'ausencia_temporal': (
        'Salí momentáneamente, regreso a terminar'
    ),
    'finalizado': (
        'Ya terminé el trabajo técnico'
    ),
}

MOTIVOS_ICONOS = {
    'cliente_tarde': '⏳',
    'sin_autorizacion': '🚫',
    'ausencia_temporal': '🔄',
    'finalizado': '✅',
}

MOTIVOS_DESCRIPCION = {
    'cliente_tarde': (
        'Estoy esperando al cliente o responsable.'
    ),
    'sin_autorizacion': (
        'No permitieron el ingreso o continuar la atención.'
    ),
    'ausencia_temporal': (
        'Salí temporalmente y regresaré al sitio.'
    ),
    'finalizado': (
        'El trabajo técnico terminó. '
        'El cierre del ticket se realiza en Odoo.'
    ),
}


def _esc(valor):
    """Evita insertar HTML de registros o parámetros."""
    if valor is None or valor is False:
        return ''
    return escape(str(valor), quote=True)


def _fmt_hora(dt):
    """
    Presentación local de una fecha existente.

    No genera fechas nuevas ni modifica el registro.
    """
    if not dt:
        return '--'

    try:
        fecha = fields.Datetime.to_datetime(dt)

        if fecha.tzinfo is None:
            fecha = UTC.localize(fecha)

        return fecha.astimezone(
            pytz_timezone('America/Lima')
        ).strftime('%d/%m/%Y %H:%M')

    except Exception:
        _logger.exception(
            '[RETIRO] Error formateando fecha'
        )
        return '--'


def _fmt_minutos(valor):
    """
    Formatea la duración registrada.

    Un valor ausente no se presenta como duración real.
    """
    if valor is None or valor is False:
        return '--'

    try:
        minutos = float(valor)

        if minutos < 0:
            return '--'

        total = int(minutos)
        horas, restantes = divmod(total, 60)

        if horas:
            return f'{horas}h {restantes}min'

        return f'{restantes}min'

    except (TypeError, ValueError):
        return '--'


def _html_base(contenido, titulo='Confirmación de retiro'):
    """
    HTML responsive para el teléfono del técnico.

    El contenido es generado por el controlador.
    Los campos provenientes de Odoo se escapan
    individualmente antes de interpolarlos.
    """
    titulo = _esc(titulo)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>

<style>
:root {{
    --primary: #26364D;
    --background: #F2F5F9;
    --surface: #FFFFFF;
    --border: #E2E8F0;
    --text: #1E293B;
    --muted: #64748B;
    --success: #15803D;
    --warning: #B45309;
    --danger: #B91C1C;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    padding: 18px;
    min-height: 100vh;
    background: var(--background);
    font-family: -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, sans-serif;
    color: var(--text);
    display: flex;
    align-items: center;
    justify-content: center;
}}

.card {{
    width: 100%;
    max-width: 460px;
    padding: 28px 24px;
    border-radius: 18px;
    background: var(--surface);
    box-shadow: 0 8px 36px rgba(18, 30, 50, .09);
}}

.brand {{
    text-align: center;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: .09em;
    color: var(--primary);
    margin-bottom: 22px;
}}

.title {{
    font-size: 23px;
    line-height: 1.25;
    text-align: center;
    margin: 0 0 10px;
}}

.subtitle {{
    text-align: center;
    color: var(--muted);
    font-size: 14px;
    line-height: 1.6;
    margin: 0 0 24px;
}}

.info {{
    border: 1px solid var(--border);
    background: #F8FAFC;
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 20px;
}}

.info-row {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 7px 0;
    border-bottom: 1px solid #E9EDF2;
}}

.info-row:last-child {{
    border-bottom: 0;
}}

.label {{
    color: var(--muted);
    font-size: 12px;
}}

.value {{
    font-size: 13px;
    font-weight: 600;
    text-align: right;
    overflow-wrap: anywhere;
}}

.alert {{
    border-radius: 10px;
    padding: 13px;
    font-size: 13px;
    line-height: 1.55;
    margin-bottom: 20px;
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    color: #92400E;
}}

.options {{
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 22px;
}}

.option {{
    display: flex;
    align-items: flex-start;
    gap: 13px;
    padding: 15px;
    border: 2px solid var(--border);
    border-radius: 12px;
    background: white;
    cursor: pointer;
    width: 100%;
    text-align: left;
    font-family: inherit;
}}

.option.selected {{
    border-color: #2563EB;
    background: #EFF6FF;
}}

.option-icon {{
    font-size: 24px;
    flex-shrink: 0;
}}

.option-title {{
    font-size: 14px;
    font-weight: 700;
    line-height: 1.4;
}}

.option-desc {{
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
    margin-top: 3px;
}}

.button {{
    width: 100%;
    border: 0;
    border-radius: 12px;
    padding: 16px;
    background: var(--primary);
    color: white;
    font-weight: 700;
    font-size: 15px;
    cursor: pointer;
}}

.button:disabled {{
    background: #CBD5E1;
    cursor: not-allowed;
}}

.state-icon {{
    font-size: 54px;
    text-align: center;
    margin-bottom: 16px;
}}

.state-title {{
    font-size: 22px;
    font-weight: 750;
    text-align: center;
    margin: 0 0 12px;
}}

.state-text {{
    text-align: center;
    font-size: 14px;
    color: var(--muted);
    line-height: 1.65;
}}

.state-detail {{
    background: #F8FAFC;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 15px;
    text-align: center;
    margin-top: 22px;
    font-size: 13px;
    line-height: 1.6;
    overflow-wrap: anywhere;
}}

.footer {{
    margin-top: 24px;
    text-align: center;
    color: #94A3B8;
    font-size: 11px;
    line-height: 1.6;
}}

@media(max-width: 480px) {{
    body {{
        padding: 12px;
        align-items: flex-start;
    }}

    .card {{
        padding: 24px 18px;
    }}

    .title {{
        font-size: 21px;
    }}
}}
</style>
</head>

<body>
<main class="card">
    <div class="brand">COPIER COMPANY S.A.C.</div>
    {contenido}
    <div class="footer">
        Sistema de Atención Técnica SAT<br>
        Confirmación de motivo de retiro
    </div>
</main>
</body>
</html>"""


class RetiroController(http.Controller):

    # ==========================================================
    # RESPUESTA HTML
    # ==========================================================

    def _respuesta(self, contenido, titulo, status=200):
        """
        Evita almacenar páginas que contienen
        información vinculada a un token privado.
        """
        response = request.make_response(
            _html_base(contenido, titulo),
            headers=[
                ('Content-Type', 'text/html; charset=utf-8'),
                ('Cache-Control', 'no-store, max-age=0'),
                ('Pragma', 'no-cache'),
                ('X-Content-Type-Options', 'nosniff'),
                ('Referrer-Policy', 'no-referrer'),
                ('X-Frame-Options', 'DENY'),
            ],
        )
        response.status_code = status
        return response

    # ==========================================================
    # CONSULTA DEL TOKEN
    # ==========================================================

    @staticmethod
    def _buscar_token(token, vigente=True):
        """
        Solo acepta cadenas con formato razonable.

        El modelo comprueba estado y vencimiento.
        """
        if not isinstance(token, str):
            return request.env['ticket.retiro.token']

        if not token or len(token) > 256:
            return request.env['ticket.retiro.token']

        TokenModel = request.env[
            'ticket.retiro.token'
        ].sudo()

        if vigente:
            return TokenModel.buscar_token_valido(token)

        return TokenModel.search([
            ('token', '=', token),
        ], limit=1)

    # ==========================================================
    # GET - FORMULARIO
    # ==========================================================

    @http.route(
        '/sat/retiro/<string:token>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    def retiro_get(self, token, **kwargs):

        token_rec = self._buscar_token(
            token, vigente=True
        )

        if not token_rec:
            token_any = self._buscar_token(
                token, vigente=False
            )

            if token_any and token_any.estado == 'respondido':
                contenido = self._html_ya_respondido(
                    token_any
                )

            elif token_any and token_any.estado == 'cancelado':
                contenido = self._html_cancelado()

            else:
                contenido = self._html_expirado()

            return self._respuesta(
                contenido,
                'Confirmación de retiro',
            )

        ticket = token_rec.ticket_id

        if not ticket.exists():
            return self._respuesta(
                self._html_expirado(),
                'Enlace no disponible',
            )

        tecnico = ticket.responsable
        cliente = ticket.partner_id

        tecnico_nombre = _esc(
            tecnico.name if tecnico else 'No asignado'
        )

        cliente_nombre = _esc(
            cliente.name if cliente else 'No registrado'
        )

        ticket_nombre = _esc(ticket.name)

        llegada = _fmt_hora(
            ticket.fecha_llegada
        )

        duracion = _fmt_minutos(
            token_rec.tiempo_en_sitio_minutos
        )

        vencimiento = _fmt_hora(
            token_rec.expira_en
        )

        csrf_token = _esc(
            request.csrf_token()
        )

        # Solo se utiliza el token recibido en URL,
        # escapado antes de colocarlo en HTML.
        accion = _esc(
            '/sat/retiro/%s' % token
        )

        opciones_html = []

        for codigo, titulo in MOTIVOS_DISPLAY.items():

            icono = MOTIVOS_ICONOS[codigo]
            descripcion = MOTIVOS_DESCRIPCION[codigo]

            opciones_html.append(f"""
<button type="button"
        class="option"
        data-motivo="{_esc(codigo)}">
    <span class="option-icon">{icono}</span>
    <span>
        <span class="option-title">
            {_esc(titulo)}
        </span>
        <span class="option-desc">
            {_esc(descripcion)}
        </span>
    </span>
</button>
""")

        opciones = ''.join(opciones_html)

        contenido = f"""
<h1 class="title">Confirmación de retiro</h1>

<p class="subtitle">
    Se detectó una posible salida de la ubicación.
    Indica qué sucedió para informar a coordinación.
</p>

<div class="info">

    <div class="info-row">
        <span class="label">Técnico</span>
        <span class="value">{tecnico_nombre}</span>
    </div>

    <div class="info-row">
        <span class="label">Cliente</span>
        <span class="value">{cliente_nombre}</span>
    </div>

    <div class="info-row">
        <span class="label">Ticket</span>
        <span class="value">{ticket_nombre}</span>
    </div>

    <div class="info-row">
        <span class="label">Llegada registrada</span>
        <span class="value">{_esc(llegada)}</span>
    </div>

    <div class="info-row">
        <span class="label">Tiempo registrado</span>
        <span class="value">{_esc(duracion)}</span>
    </div>

    <div class="info-row">
        <span class="label">Enlace válido hasta</span>
        <span class="value">{_esc(vencimiento)}</span>
    </div>

</div>

<div class="alert">
    Esta confirmación no finaliza automáticamente
    el ticket ni sustituye los registros GPS.
    El trabajo técnico se cierra mediante
    el procedimiento normal de Odoo.
</div>

<form method="POST"
      action="{accion}"
      id="form-retiro">

    <input type="hidden"
           name="csrf_token"
           value="{csrf_token}">

    <input type="hidden"
           name="motivo"
           id="motivo-input"
           value="">

    <div class="options">
        {opciones}
    </div>

    <button type="submit"
            class="button"
            id="btn-confirmar"
            disabled>
        Confirmar motivo
    </button>

</form>

<script>
(function() {{
    const opciones = document.querySelectorAll(
        '.option'
    );

    const input = document.getElementById(
        'motivo-input'
    );

    const boton = document.getElementById(
        'btn-confirmar'
    );

    const formulario = document.getElementById(
        'form-retiro'
    );

    opciones.forEach(function(opcion) {{
        opcion.addEventListener('click', function() {{

            opciones.forEach(function(elemento) {{
                elemento.classList.remove('selected');
            }});

            opcion.classList.add('selected');

            input.value = opcion.dataset.motivo;

            boton.disabled = false;
        }});
    }});

    formulario.addEventListener(
        'submit',
        function(evento) {{

            if (!input.value) {{
                evento.preventDefault();
                return;
            }}

            boton.disabled = true;
            boton.textContent = 'Registrando...';
        }}
    );
}})();
</script>
"""

        return self._respuesta(
            contenido,
            'Confirmación de retiro - %s' % ticket.name,
        )

    # ==========================================================
    # POST - REGISTRAR MOTIVO
    # ==========================================================

    @http.route(
        '/sat/retiro/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=True,
        sitemap=False,
    )
    def retiro_post(self, token, **post):

        motivo = str(
            post.get('motivo') or ''
        ).strip()

        if motivo not in MOTIVOS_DISPLAY:
            return self._respuesta(
                self._html_error(
                    'Seleccione un motivo válido.'
                ),
                'Motivo no válido',
                status=400,
            )

        token_rec = self._buscar_token(
            token, vigente=True
        )

        if not token_rec:
            token_any = self._buscar_token(
                token, vigente=False
            )

            if token_any and token_any.estado == 'respondido':
                return self._respuesta(
                    self._html_ya_respondido(token_any),
                    'Respuesta registrada',
                )

            if token_any and token_any.estado == 'cancelado':
                return self._respuesta(
                    self._html_cancelado(),
                    'Confirmación cancelada',
                )

            return self._respuesta(
                self._html_expirado(),
                'Enlace no disponible',
            )

        ticket = token_rec.ticket_id

        if not ticket.exists():
            return self._respuesta(
                self._html_expirado(),
                'Enlace no disponible',
            )

        # ------------------------------------------------------
        # REGISTRAR RESPUESTA EN MODELO
        # ------------------------------------------------------

        try:
            registrado = token_rec.marcar_respondido(
                motivo
            )

        except Exception:
            _logger.exception(
                '[RETIRO] Error al registrar '
                'respuesta token_id=%s',
                token_rec.id,
            )

            return self._respuesta(
                self._html_error(
                    'No se pudo registrar la respuesta. '
                    'Comunícate con coordinación.'
                ),
                'Error de confirmación',
                status=500,
            )

        if not registrado:
            return self._respuesta(
                self._html_expirado(),
                'Enlace no disponible',
            )

        # ------------------------------------------------------
        # AUDITORÍA EN EL TICKET
        # ------------------------------------------------------

        descripcion = MOTIVOS_DISPLAY[motivo]

        try:
            ticket.sudo()._registrar_evento(
                'Confirmación de motivo de retiro: %s. '
                'Token ID: %s. '
                'Declaración del técnico; no equivale '
                'a finalización administrativa ni '
                'certificación GPS de salida.'
                % (descripcion, token_rec.id)
            )

        except Exception:
            _logger.exception(
                '[RETIRO] Error de anotación '
                'en historial ticket_id=%s',
                ticket.id,
            )

        # ------------------------------------------------------
        # NOTIFICAR A COORDINACIÓN
        # ------------------------------------------------------

        ubicacion_actual = None

        # Se conservan las coordenadas registradas
        # cuando se creó el token, si existen.
        # No se presentan como ubicación actual.
        if (
            token_rec.lat_salida != 0
            or token_rec.lon_salida != 0
        ):
            ubicacion_actual = {
                'latitude': token_rec.lat_salida,
                'longitude': token_rec.lon_salida,
            }

        aviso_aceptado = False

        try:
            aviso_aceptado = bool(
                ticket.sudo().notificar_motivo_retiro(
                    motivo=motivo,
                    ubicacion_actual=ubicacion_actual,
                    tiempo_en_sitio=(
                        token_rec.tiempo_en_sitio_minutos
                    ),
                )
            )

        except Exception:
            _logger.exception(
                '[RETIRO] Error notificando motivo '
                'ticket_id=%s token_id=%s',
                ticket.id,
                token_rec.id,
            )

        if not aviso_aceptado:
            _logger.warning(
                '[RETIRO] Motivo registrado pero '
                'notificación no confirmada '
                'ticket_id=%s token_id=%s',
                ticket.id,
                token_rec.id,
            )

            try:
                ticket.sudo()._registrar_evento(
                    'El motivo fue registrado, '
                    'pero el proveedor WhatsApp '
                    'no confirmó aceptar la notificación.'
                )
            except Exception:
                _logger.exception(
                    '[RETIRO] Error registrando '
                    'incidencia de notificación'
                )

        # ------------------------------------------------------
        # NO FINALIZAR NI REGISTRAR SALIDA
        # ------------------------------------------------------

        # No llamar action_finalizar().
        # No llamar _registrar_finalizacion_tracking().
        # No escribir estado='finalizado'.
        # No escribir fecha_salida_sitio.
        # No desbloquear la siguiente visita.
        #
        # La respuesta es una declaración del técnico.
        # La salida física se confirma por el flujo
        # independiente de visitas y GPS.

        _logger.info(
            '[RETIRO] Motivo registrado '
            'ticket_id=%s token_id=%s motivo=%s '
            'aviso_aceptado=%s',
            ticket.id,
            token_rec.id,
            motivo,
            aviso_aceptado,
        )

        return self._respuesta(
            self._html_confirmado(
                motivo,
                ticket,
                aviso_aceptado,
            ),
            'Motivo registrado',
        )

    # ==========================================================
    # PÁGINAS DE RESULTADO
    # ==========================================================

    def _html_confirmado(
        self,
        motivo,
        ticket,
        aviso_aceptado=False,
    ):

        icono = MOTIVOS_ICONOS.get(
            motivo, '✅'
        )

        mensajes = {
            'cliente_tarde': (
                'Se registró que estás esperando '
                'al cliente.'
            ),
            'sin_autorizacion': (
                'Se registró la falta de autorización '
                'para ingresar o continuar.'
            ),
            'ausencia_temporal': (
                'Se registró tu salida temporal. '
                'La visita sigue pendiente '
                'del control de regreso o salida.'
            ),
            'finalizado': (
                'Se registró que declaras haber '
                'terminado el trabajo técnico. '
                'El ticket debe finalizarse '
                'mediante el procedimiento '
                'administrativo de Odoo.'
            ),
        }

        mensaje = mensajes.get(
            motivo,
            'Tu motivo fue registrado.'
        )

        if aviso_aceptado:
            aviso = (
                'La plataforma de mensajería '
                'aceptó la solicitud de aviso. '
                'Esto no confirma su entrega ni lectura.'
            )
        else:
            aviso = (
                'La respuesta quedó registrada, '
                'pero no se confirmó el envío '
                'del aviso a coordinación.'
            )

        return f"""
<div class="state-icon">{icono}</div>

<h1 class="state-title">
    Motivo registrado
</h1>

<p class="state-text">
    {_esc(mensaje)}
</p>

<div class="state-detail">
    <strong>{_esc(ticket.name)}</strong><br>
    {_esc(
        ticket.partner_id.name
        if ticket.partner_id else ''
    )}
    <br><br>
    {_esc(aviso)}
</div>
"""

    def _html_expirado(self):

        return """
<div class="state-icon">⏰</div>

<h1 class="state-title">
    Enlace no disponible
</h1>

<p class="state-text">
    El enlace expiró, ya fue utilizado
    o dejó de estar vigente.
    <br><br>
    Comunícate con coordinación
    si necesitas registrar tu motivo.
</p>
"""

    def _html_ya_respondido(self, token_rec):

        hora = _fmt_hora(
            token_rec.respondido_en
        )

        motivo = (
            token_rec.motivo_label
            or MOTIVOS_DISPLAY.get(
                token_rec.motivo, ''
            )
        )

        return f"""
<div class="state-icon">✅</div>

<h1 class="state-title">
    Respuesta registrada anteriormente
</h1>

<p class="state-text">
    El motivo fue registrado el
    <strong>{_esc(hora)}</strong>.
</p>

<div class="state-detail">
    {_esc(motivo)}
</div>
"""

    def _html_cancelado(self):

        return """
<div class="state-icon">↩️</div>

<h1 class="state-title">
    Confirmación cancelada
</h1>

<p class="state-text">
    Esta solicitud de confirmación
    fue cancelada.
    <br><br>
    No es necesario responderla.
    Si necesitas informar un retiro,
    comunícate con coordinación.
</p>
"""

    def _html_error(self, mensaje):

        return f"""
<div class="state-icon">⚠️</div>

<h1 class="state-title">
    No se pudo procesar
</h1>

<p class="state-text">
    {_esc(mensaje)}
</p>
"""

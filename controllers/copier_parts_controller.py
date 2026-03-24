import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CopierPartsController(http.Controller):

    # =========================================================================
    # HELPERS INTERNOS
    # =========================================================================

    def _render_error(self, titulo, mensaje):
        """Página genérica de error."""
        return request.render('sat.portal_copier_parts_error', {
            'titulo':  titulo,
            'mensaje': mensaje,
        })

    def _render_ok(self, titulo, mensaje, detalle=None):
        """Página genérica de éxito."""
        return request.render('sat.portal_copier_parts_ok', {
            'titulo':  titulo,
            'mensaje': mensaje,
            'detalle': detalle,
        })

    def _get_solicitud_por_token_gerencia(self, token):
        """Busca solicitud vigente por token de gerencia."""
        return request.env['copier.parts.request'].sudo().search(
            [('token_gerencia', '=', token)], limit=1
        )

    def _get_solicitud_por_token_logistica(self, token):
        """Busca solicitud vigente por token de logística."""
        return request.env['copier.parts.request'].sudo().search(
            [('token_logistica', '=', token)], limit=1
        )

    # =========================================================================
    # GERENCIA — APROBAR
    # GET  → muestra resumen de solicitud + botón confirmar
    # POST → aprueba, invalida token, notifica a logística
    # =========================================================================

    @http.route(
        '/parts/gerencia/<string:token>/aprobar',
        type='http',
        auth='public',
        website=True,
        methods=['GET', 'POST'],
        csrf=False,
    )
    def gerencia_aprobar(self, token, **kwargs):
        solicitud = self._get_solicitud_por_token_gerencia(token)

        # Token ya usado o inválido
        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido. '
                'La solicitud puede haber sido aprobada o rechazada anteriormente.'
            )

        # Validar estado — solo draft puede aprobarse
        if solicitud.state != 'draft':
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Solicitud ya procesada',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong> '
                f'y no puede ser procesada nuevamente.'
            )

        # ── POST: confirmar aprobación ────────────────────────────────────────
        if request.httprequest.method == 'POST':
            try:
                solicitud._aprobar()
                _logger.info(
                    "CopierPartsRequest %s aprobada via token gerencia.", solicitud.name
                )
            except Exception as e:
                _logger.exception(
                    "Error aprobando CopierPartsRequest %s: %s", solicitud.name, e
                )
                return self._render_error(
                    'Error al procesar',
                    f'Ocurrió un error al aprobar la solicitud: {str(e)}'
                )

            return self._render_ok(
                '✅ Solicitud Aprobada',
                f'La solicitud <strong>{solicitud.name}</strong> fue aprobada correctamente.',
                detalle='Logística fue notificada para proceder con la entrega.'
            )

        # ── GET: mostrar resumen para confirmar ───────────────────────────────
        return request.render('sat.portal_copier_parts_gerencia_aprobar', {
            'solicitud': solicitud,
            'error':     None,
        })

    # =========================================================================
    # GERENCIA — RECHAZAR
    # GET → rechaza directamente con un clic, invalida token
    # =========================================================================

    @http.route(
        '/parts/gerencia/<string:token>/rechazar',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
        csrf=False,
    )
    def gerencia_rechazar(self, token, **kwargs):
        solicitud = self._get_solicitud_por_token_gerencia(token)

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido.'
            )

        if solicitud.state != 'draft':
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Solicitud ya procesada',
                f'Esta solicitud ya se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong>.'
            )

        try:
            solicitud._rechazar()
            _logger.info(
                "CopierPartsRequest %s rechazada via token gerencia.", solicitud.name
            )
        except Exception as e:
            _logger.exception(
                "Error rechazando CopierPartsRequest %s: %s", solicitud.name, e
            )
            return self._render_error(
                'Error al procesar',
                f'Ocurrió un error al rechazar la solicitud: {str(e)}'
            )

        return self._render_ok(
            '❌ Solicitud Rechazada',
            f'La solicitud <strong>{solicitud.name}</strong> fue rechazada.',
            detalle='El técnico solicitante será notificado.'
        )

    # =========================================================================
    # LOGÍSTICA — CONFIRMAR ENTREGA
    # GET  → muestra resumen de partes a entregar + botón confirmar
    # POST → confirma entrega, invalida token, notifica al técnico
    # =========================================================================

    @http.route(
        '/parts/logistica/<string:token>/entregar',
        type='http',
        auth='public',
        website=True,
        methods=['GET', 'POST'],
        csrf=False,
    )
    def logistica_entregar(self, token, **kwargs):
        solicitud = self._get_solicitud_por_token_logistica(token)

        # Token ya usado o inválido
        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido. '
                'La entrega puede haber sido confirmada anteriormente.'
            )

        # Solo se puede entregar si está aprobada
        if solicitud.state != 'approved':
            if solicitud.state == 'delivered':
                return self._render_error(
                    'Entrega ya confirmada',
                    f'La solicitud <strong>{solicitud.name}</strong> '
                    f'ya fue marcada como entregada.'
                )
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Acción no disponible',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong>. '
                f'Solo se puede confirmar entrega cuando está Aprobada.'
            )

        # ── POST: confirmar entrega ───────────────────────────────────────────
        if request.httprequest.method == 'POST':
            try:
                solicitud._confirmar_entrega()
                _logger.info(
                    "CopierPartsRequest %s entregada via token logistica.", solicitud.name
                )
            except Exception as e:
                _logger.exception(
                    "Error confirmando entrega CopierPartsRequest %s: %s", solicitud.name, e
                )
                return self._render_error(
                    'Error al procesar',
                    f'Ocurrió un error al confirmar la entrega: {str(e)}'
                )

            return self._render_ok(
                '✅ Entrega Confirmada',
                f'La entrega de la solicitud <strong>{solicitud.name}</strong> '
                f'fue confirmada correctamente.',
                detalle='El técnico solicitante fue notificado para pasar a recoger las partes.'
            )

        # ── GET: mostrar resumen para confirmar ───────────────────────────────
        return request.render('sat.portal_copier_parts_logistica_entregar', {
            'solicitud': solicitud,
            'error':     None,
        })
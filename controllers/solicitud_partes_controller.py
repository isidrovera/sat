import base64
import logging
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class SolicitudPartesController(http.Controller):

    # =========================================================================
    # HELPERS INTERNOS
    # =========================================================================

    def _render_error(self, titulo, mensaje):
        """Página genérica de error/estado."""
        return request.render('sat.portal_solicitud_partes_error', {
            'titulo':  titulo,
            'mensaje': mensaje,
        })

    def _render_ok(self, titulo, mensaje, detalle=None):
        """Página genérica de éxito."""
        return request.render('sat.portal_solicitud_partes_ok', {
            'titulo':  titulo,
            'mensaje': mensaje,
            'detalle': detalle,
        })

    # =========================================================================
    # GERENCIA — APROBAR  (GET directo, sin formulario)
    # =========================================================================

    @http.route(
        '/partes/gerencia/<string:token>/aprobar',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
        csrf=False,
    )
    def gerencia_aprobar(self, token, **kwargs):
        """
        GET → aprueba la solicitud directamente con un solo clic.

        El técnico de retiro y el responsable de reposición ya fueron definidos
        al crear la solicitud por el técnico solicitante.
        Gerencia solo aprueba o rechaza — no elige nada.
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('token_gerencia', '=', token)], limit=1)

        # Token inválido o ya usado
        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido. '
                'La solicitud puede haber sido aprobada o rechazada anteriormente.'
            )

        # Verificar estado correcto
        if solicitud.state != 'submitted':
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Solicitud ya procesada',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong> '
                f'y no puede ser procesada nuevamente.'
            )

        # Validar que tenga técnico y responsable definidos
        if not solicitud.tecnico_asignado_id:
            return self._render_error(
                'Datos incompletos',
                f'La solicitud <strong>{solicitud.name}</strong> no tiene técnico de retiro '
                f'asignado. Un administrador debe corregirlo desde Odoo antes de aprobar.'
            )

        if not solicitud.responsable_reposicion_id:
            return self._render_error(
                'Datos incompletos',
                f'La solicitud <strong>{solicitud.name}</strong> no tiene responsable de '
                f'reposición asignado. Un administrador debe corregirlo desde Odoo antes de aprobar.'
            )

        # Aprobar directamente
        try:
            solicitud._aprobar()
            _logger.info("Solicitud %s aprobada via token (1 clic).", solicitud.name)
        except Exception as e:
            _logger.exception("Error aprobando solicitud %s: %s", solicitud.name, e)
            return self._render_error(
                'Error al procesar',
                f'Ocurrió un error al aprobar la solicitud: {str(e)}'
            )

        return self._render_ok(
            '✅ Solicitud Aprobada',
            f'La solicitud <strong>{solicitud.name}</strong> fue aprobada correctamente.',
            detalle=(
                f'Técnico de retiro: <strong>{solicitud.tecnico_asignado_id.name}</strong><br/>'
                f'Responsable de reposición: <strong>{solicitud.responsable_reposicion_id.name}</strong><br/>'
                f'Ambos han sido notificados.'
            )
        )

    # =========================================================================
    # GERENCIA — RECHAZAR  (GET directo, un solo clic)
    # =========================================================================

    @http.route(
        '/partes/gerencia/<string:token>/rechazar',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
        csrf=False,
    )
    def gerencia_rechazar(self, token, **kwargs):
        """
        GET → rechaza la solicitud directamente con un solo clic.
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('token_gerencia', '=', token)], limit=1)

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido.'
            )

        if solicitud.state != 'submitted':
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Solicitud ya procesada',
                f'Esta solicitud ya se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong>.'
            )

        try:
            solicitud._rechazar()
            _logger.info("Solicitud %s rechazada via token (1 clic).", solicitud.name)
        except Exception as e:
            _logger.exception("Error rechazando solicitud %s: %s", solicitud.name, e)
            return self._render_error(
                'Error al procesar',
                f'Ocurrió un error al rechazar la solicitud: {str(e)}'
            )

        return self._render_ok(
            '❌ Solicitud Rechazada',
            f'La solicitud <strong>{solicitud.name}</strong> fue rechazada.',
            detalle='El solicitante será notificado.'
        )

    # =========================================================================
    # TÉCNICO — RETIRO
    # =========================================================================

    @http.route(
        '/partes/retirar/<string:token>',
        type='http',
        auth='public',
        website=True,
        methods=['GET', 'POST'],
        csrf=False,
    )
    def tecnico_retirar(self, token, **kwargs):
        """
        GET  → muestra info de la máquina + lista de partes con checkboxes.
        POST → confirma retiro de las partes marcadas.
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace no es válido o la solicitud no existe.'
            )

        # Solo se puede retirar si está aprobada
        if solicitud.state not in ('approved',):
            if solicitud.todas_retiradas or solicitud.state in ('completed', 'replaced'):
                return self._render_error(
                    'Retiro ya completado',
                    f'Todas las partes de la solicitud '
                    f'<strong>{solicitud.name}</strong> ya fueron retiradas.'
                )
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Acción no disponible',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong>. '
                f'Solo se puede retirar cuando está Aprobada.'
            )

        # Partes pendientes de retiro
        partes_pendientes = solicitud.parte_ids.filtered(
            lambda l: l.estado == 'pendiente'
        )

        if not partes_pendientes:
            return self._render_error(
                'Sin partes pendientes',
                f'Todas las partes de la solicitud '
                f'<strong>{solicitud.name}</strong> ya fueron retiradas.'
            )

        # ── POST: procesar retiro ─────────────────────────────────────────────
        if request.httprequest.method == 'POST':
            ids_marcados = request.httprequest.form.getlist('parte_ids')

            if not ids_marcados:
                return request.render('sat.portal_tecnico_retirar', {
                    'solicitud':         solicitud,
                    'partes_pendientes': partes_pendientes,
                    'error': 'Debe marcar al menos una parte para confirmar el retiro.',
                })

            try:
                ids_marcados = [int(i) for i in ids_marcados]
            except (ValueError, TypeError):
                return self._render_error('Error', 'Datos de formulario inválidos.')

            try:
                for linea in solicitud.parte_ids.filtered(
                    lambda l: l.id in ids_marcados and l.estado == 'pendiente'
                ):
                    linea._confirmar_retiro()

                # Verificar si todas están retiradas → completar solicitud
                solicitud._compute_estado_partes()
                if solicitud.todas_retiradas:
                    solicitud._completar_retiro()

                _logger.info(
                    "Retiro confirmado para solicitud %s — %s partes.",
                    solicitud.name, len(ids_marcados)
                )

            except Exception as e:
                _logger.exception(
                    "Error confirmando retiro solicitud %s: %s", solicitud.name, e
                )
                return self._render_error(
                    'Error al procesar',
                    f'Ocurrió un error al confirmar el retiro: {str(e)}'
                )

            # Partes que quedaron pendientes (no marcadas en este envío)
            restantes = solicitud.parte_ids.filtered(lambda l: l.estado == 'pendiente')

            if restantes:
                return self._render_ok(
                    '✅ Retiro Parcial Confirmado',
                    f'Se confirmó el retiro de <strong>{len(ids_marcados)}</strong> parte(s) '
                    f'de la solicitud <strong>{solicitud.name}</strong>.',
                    detalle=(
                        f'Quedan <strong>{len(restantes)}</strong> parte(s) pendientes de retiro. '
                        f'Puedes usar el mismo enlace para confirmarlas cuando las retires.'
                    )
                )

            return self._render_ok(
                '✅ Retiro Completo',
                f'Todas las partes de la solicitud '
                f'<strong>{solicitud.name}</strong> fueron retiradas correctamente.',
                detalle=(
                    f'El responsable de reposición '
                    f'<strong>{solicitud.responsable_reposicion_id.name}</strong> '
                    f'fue notificado para proceder con la reposición.'
                )
            )

        # ── GET: mostrar formulario ───────────────────────────────────────────
        return request.render('sat.portal_tecnico_retirar', {
            'solicitud':         solicitud,
            'partes_pendientes': partes_pendientes,
            'error':             None,
        })

    # =========================================================================
    # RESPONSABLE — REPOSICIÓN
    # =========================================================================

    @http.route(
        '/partes/reponer/<string:token>',
        type='http',
        auth='public',
        website=True,
        methods=['GET', 'POST'],
        csrf=False,
    )
    def responsable_reponer(self, token, **kwargs):
        """
        GET  → muestra partes retiradas con formulario de reposición + foto.
        POST → procesa reposición de cada parte con foto y condición.
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace no es válido o la solicitud no existe.'
            )

        # Solo se puede reponer si el retiro ya ocurrió
        if solicitud.state not in ('completed', 'approved'):
            if solicitud.state == 'replaced':
                return self._render_error(
                    'Reposición ya completada',
                    f'Todas las partes de la solicitud '
                    f'<strong>{solicitud.name}</strong> ya fueron repuestas.'
                )
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Acción no disponible',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong>. '
                f'Las partes deben ser retiradas primero.'
            )

        partes_retiradas = solicitud.parte_ids.filtered(
            lambda l: l.estado == 'retirado'
        )

        if not partes_retiradas:
            return self._render_error(
                'Sin partes para reponer',
                f'No hay partes pendientes de reposición en la solicitud '
                f'<strong>{solicitud.name}</strong>.'
            )

        # ── POST: procesar reposición ─────────────────────────────────────────
        if request.httprequest.method == 'POST':
            form  = request.httprequest.form
            files = request.httprequest.files
            errores = []

            for linea in partes_retiradas:
                condicion    = form.get(f'condicion_{linea.id}')
                observaciones = form.get(f'observaciones_{linea.id}', '')
                foto_file    = files.get(f'foto_{linea.id}')

                # Validaciones por línea
                if not condicion:
                    errores.append(f'Parte "{linea.parte}": debe seleccionar condición.')
                    continue

                if not foto_file or not foto_file.filename:
                    errores.append(f'Parte "{linea.parte}": debe adjuntar foto.')
                    continue

                # Validar tipo de archivo
                allowed_types = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
                if foto_file.content_type not in allowed_types:
                    errores.append(
                        f'Parte "{linea.parte}": solo se aceptan imágenes (JPG, PNG, GIF, WEBP).'
                    )
                    continue

                # Validar tamaño (máx 5MB)
                foto_data = foto_file.read()
                if len(foto_data) > 5 * 1024 * 1024:
                    errores.append(
                        f'Parte "{linea.parte}": la imagen no debe superar 5MB.'
                    )
                    continue

                foto_b64 = base64.b64encode(foto_data).decode('utf-8')

                try:
                    linea._confirmar_reposicion(
                        condicion=condicion,
                        foto=foto_b64,
                        foto_filename=foto_file.filename,
                        observaciones=observaciones,
                    )
                except Exception as e:
                    _logger.exception(
                        "Error reponiendo línea %s solicitud %s: %s",
                        linea.id, solicitud.name, e
                    )
                    errores.append(f'Parte "{linea.parte}": {str(e)}')

            if errores:
                # Recargar partes retiradas (algunas pueden haberse procesado ya)
                partes_retiradas_act = solicitud.parte_ids.filtered(
                    lambda l: l.estado == 'retirado'
                )
                return request.render('sat.portal_responsable_reponer', {
                    'solicitud':       solicitud,
                    'partes_retiradas': partes_retiradas_act,
                    'errores':         errores,
                })

            # Verificar si todas están repuestas → completar reposición
            solicitud._compute_estado_partes()
            if solicitud.todas_repuestas:
                solicitud._completar_reposicion()

            _logger.info(
                "Reposición completada para solicitud %s.", solicitud.name
            )

            return self._render_ok(
                '✅ Reposición Completada',
                f'Todas las partes de la solicitud '
                f'<strong>{solicitud.name}</strong> fueron repuestas correctamente.',
                detalle='El registro ha sido actualizado en el sistema.'
            )

        # ── GET: mostrar formulario ───────────────────────────────────────────
        return request.render('sat.portal_responsable_reponer', {
            'solicitud':       solicitud,
            'partes_retiradas': partes_retiradas,
            'errores':         [],
        })
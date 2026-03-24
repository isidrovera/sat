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
            'titulo': titulo,
            'mensaje': mensaje,
        })

    def _render_ok(self, titulo, mensaje, detalle=None):
        """Página genérica de éxito."""
        return request.render('sat.portal_solicitud_partes_ok', {
            'titulo': titulo,
            'mensaje': mensaje,
            'detalle': detalle,
        })

    def _get_tecnicos(self):
        """Retorna lista de técnicos activos (grupo Técnico SAT o todos los usuarios internos)."""
        try:
            grupo = request.env.ref('sat.group_sat_tecnico', raise_if_not_found=False)
            if grupo:
                return grupo.users.filtered(lambda u: u.active).sudo()
        except Exception:
            pass
        # Fallback: todos los usuarios internos activos
        return request.env['res.users'].sudo().search([
            ('active', '=', True),
            ('share', '=', False),
        ])

    # =========================================================================
    # GERENCIA — APROBAR
    # =========================================================================

    @http.route(
        '/partes/gerencia/<string:token>/aprobar',
        type='http',
        auth='public',
        website=True,
        methods=['GET', 'POST'],
        csrf=False,
    )
    def gerencia_aprobar(self, token, **kwargs):
        """
        GET  → muestra resumen de la solicitud + selector de técnico
        POST → valida, aprueba, notifica
        """
        Solicitud = request.env['solicitud.partes'].sudo()

        # Buscar por token de gerencia vigente
        solicitud = Solicitud.search([('token_gerencia', '=', token)], limit=1)

        # Token ya usado o inválido
        if not solicitud:
            # ¿Existe pero ya fue procesada?
            procesada = Solicitud.search([
                ('token_gerencia', '=', False),
                ('access_token', '!=', False),
            ], limit=0)  # No podemos identificarla sin token — mostrar mensaje genérico
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido. '
                'La solicitud puede haber sido aprobada o rechazada anteriormente.'
            )

        # Verificar que esté en estado correcto
        if solicitud.state != 'submitted':
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Solicitud ya procesada',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong> '
                f'y no puede ser procesada nuevamente.'
            )

        tecnicos = self._get_tecnicos()

        # ── POST: procesar aprobación ─────────────────────────────────────────
        if request.httprequest.method == 'POST':
            tecnico_id = kwargs.get('tecnico_id')

            if not tecnico_id:
                return request.render('sat.portal_gerencia_aprobar', {
                    'solicitud': solicitud,
                    'tecnicos': tecnicos,
                    'error': 'Debe seleccionar un técnico para continuar.',
                })

            try:
                tecnico_id = int(tecnico_id)
            except (ValueError, TypeError):
                return request.render('sat.portal_gerencia_aprobar', {
                    'solicitud': solicitud,
                    'tecnicos': tecnicos,
                    'error': 'Técnico seleccionado no válido.',
                })

            tecnico = request.env['res.users'].sudo().browse(tecnico_id)
            if not tecnico.exists():
                return request.render('sat.portal_gerencia_aprobar', {
                    'solicitud': solicitud,
                    'tecnicos': tecnicos,
                    'error': 'El técnico seleccionado no existe.',
                })

            try:
                solicitud._aprobar(tecnico_id)
                _logger.info(
                    "Solicitud %s aprobada via token. Técnico: %s",
                    solicitud.name, tecnico.name
                )
            except Exception as e:
                _logger.exception("Error aprobando solicitud %s: %s", solicitud.name, e)
                return self._render_error(
                    'Error al procesar',
                    f'Ocurrió un error al aprobar la solicitud: {str(e)}'
                )

            return self._render_ok(
                '✅ Solicitud Aprobada',
                f'La solicitud <strong>{solicitud.name}</strong> fue aprobada correctamente.',
                detalle=f'Técnico asignado para retiro: <strong>{tecnico.name}</strong>'
            )

        # ── GET: mostrar formulario ───────────────────────────────────────────
        return request.render('sat.portal_gerencia_aprobar', {
            'solicitud': solicitud,
            'tecnicos': tecnicos,
            'error': None,
        })

    # =========================================================================
    # GERENCIA — RECHAZAR
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
        GET → rechaza la solicitud directamente (un solo clic).
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
            _logger.info("Solicitud %s rechazada via token.", solicitud.name)
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
        GET  → muestra info de la máquina + lista de partes con checkboxes
        POST → confirma retiro de todas las partes marcadas
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace no es válido o la solicitud no existe.'
            )

        # Validar estado — solo se puede retirar si está aprobada
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
            # Los checkboxes envían parte_ids[] con los IDs marcados
            ids_marcados = request.httprequest.form.getlist('parte_ids')

            if not ids_marcados:
                return request.render('sat.portal_tecnico_retirar', {
                    'solicitud': solicitud,
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
                _logger.exception("Error confirmando retiro solicitud %s: %s", solicitud.name, e)
                return self._render_error(
                    'Error al procesar',
                    f'Ocurrió un error al confirmar el retiro: {str(e)}'
                )

            # Partes que quedaron pendientes (no marcadas)
            restantes = solicitud.parte_ids.filtered(lambda l: l.estado == 'pendiente')

            if restantes:
                return self._render_ok(
                    '✅ Retiro Parcial Confirmado',
                    f'Se confirmó el retiro de {len(ids_marcados)} parte(s) '
                    f'de la solicitud <strong>{solicitud.name}</strong>.',
                    detalle=f'Quedan <strong>{len(restantes)}</strong> parte(s) pendientes de retiro.'
                )

            return self._render_ok(
                '✅ Retiro Completo',
                f'Todas las partes de la solicitud '
                f'<strong>{solicitud.name}</strong> fueron retiradas correctamente.',
                detalle='El responsable de reposición fue notificado.'
            )

        # ── GET: mostrar formulario ───────────────────────────────────────────
        return request.render('sat.portal_tecnico_retirar', {
            'solicitud': solicitud,
            'partes_pendientes': partes_pendientes,
            'error': None,
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
        GET  → muestra partes retiradas con formulario de reposición + foto
        POST → procesa reposición de cada parte con foto
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace no es válido o la solicitud no existe.'
            )

        # Solo se puede reponer si está en completed (retiro hecho)
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
            form = request.httprequest.form
            files = request.httprequest.files
            errores = []

            for linea in partes_retiradas:
                condicion = form.get(f'condicion_{linea.id}')
                observaciones = form.get(f'observaciones_{linea.id}', '')
                foto_file = files.get(f'foto_{linea.id}')

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
                # Recargar partes retiradas (algunas pueden haberse procesado)
                partes_retiradas_act = solicitud.parte_ids.filtered(
                    lambda l: l.estado == 'retirado'
                )
                return request.render('sat.portal_responsable_reponer', {
                    'solicitud': solicitud,
                    'partes_retiradas': partes_retiradas_act,
                    'errores': errores,
                })

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
            'solicitud': solicitud,
            'partes_retiradas': partes_retiradas,
            'errores': [],
        })
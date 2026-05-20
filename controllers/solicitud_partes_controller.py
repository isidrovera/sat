# -*- coding: utf-8 -*-

import base64
import logging

from odoo import http
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

    def _buscar_solicitud_reposicion_por_token(self, token):
        """
        Busca una solicitud/línea de reposición por token.

        Soporta:

        1) Flujo actual:
           solicitud.partes.access_token

        2) Flujo antiguo:
           solicitud.partes.linea.access_token_linea

        Retorna:
            solicitud, partes_retiradas, tipo_token

        tipo_token:
            - 'solicitud'
            - 'linea'
            - False
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        Linea = request.env['solicitud.partes.linea'].sudo()

        _logger.warning(
            "[PARTES][REPOSICION][BUSCAR_TOKEN] Inicio token=%s",
            token,
        )

        if not token:
            _logger.warning(
                "[PARTES][REPOSICION][BUSCAR_TOKEN] Token vacío"
            )
            return False, Linea.browse(), False

        # ---------------------------------------------------------------------
        # 1) Buscar primero por token principal de solicitud — flujo actual
        # ---------------------------------------------------------------------
        solicitud = Solicitud.search([
            ('access_token', '=', token),
        ], limit=1)

        if solicitud:
            partes_retiradas = solicitud.parte_ids.filtered(
                lambda l: l.estado == 'retirado'
            )

            _logger.warning(
                "[PARTES][REPOSICION][BUSCAR_TOKEN] Encontrado en solicitud.partes "
                "solicitud_id=%s name=%s state=%s partes_retiradas=%s",
                solicitud.id,
                solicitud.name,
                solicitud.state,
                len(partes_retiradas),
            )

            return solicitud, partes_retiradas, 'solicitud'

        # ---------------------------------------------------------------------
        # 2) Compatibilidad: buscar por token antiguo de línea
        # ---------------------------------------------------------------------
        linea = Linea.search([
            ('access_token_linea', '=', token),
        ], limit=1)

        if linea:
            solicitud = linea.solicitud_id

            if linea.estado == 'retirado':
                partes_retiradas = linea
            else:
                partes_retiradas = Linea.browse()

            _logger.warning(
                "[PARTES][REPOSICION][BUSCAR_TOKEN] Encontrado en solicitud.partes.linea "
                "linea_id=%s solicitud_id=%s solicitud=%s linea_estado=%s partes_retiradas=%s",
                linea.id,
                solicitud.id if solicitud else False,
                solicitud.name if solicitud else False,
                linea.estado,
                len(partes_retiradas),
            )

            return solicitud, partes_retiradas, 'linea'

        _logger.warning(
            "[PARTES][REPOSICION][BUSCAR_TOKEN] Token no encontrado token=%s",
            token,
        )

        return False, Linea.browse(), False

    def _procesar_reposicion_lineas(self, solicitud, partes_retiradas, form, files):
        """
        Procesa la reposición de una o varias líneas.

        Soporta formularios nuevos:
            condicion_<linea.id>
            observaciones_<linea.id>
            foto_<linea.id>

        Y formulario antiguo:
            condicion
            observaciones
            foto
        """
        errores = []

        for linea in partes_retiradas:
            condicion = (
                form.get(f'condicion_{linea.id}')
                or form.get('condicion')
            )
            observaciones = (
                form.get(f'observaciones_{linea.id}')
                or form.get('observaciones')
                or ''
            )
            foto_file = (
                files.get(f'foto_{linea.id}')
                or files.get('foto')
            )

            _logger.warning(
                "[PARTES][REPOSICION][PROCESAR_LINEA] "
                "solicitud=%s linea_id=%s parte=%s estado=%s condicion=%s foto=%s content_type=%s",
                solicitud.name if solicitud else False,
                linea.id,
                linea.parte,
                linea.estado,
                condicion,
                bool(foto_file and foto_file.filename),
                foto_file.content_type if foto_file else False,
            )

            if linea.estado != 'retirado':
                errores.append(
                    f'Parte "{linea.parte}": no está en estado Retirado.'
                )
                continue

            if not condicion:
                errores.append(
                    f'Parte "{linea.parte}": debe seleccionar condición.'
                )
                continue

            if condicion not in ('bueno', 'defectuoso'):
                errores.append(
                    f'Parte "{linea.parte}": condición inválida.'
                )
                continue

            if not foto_file or not foto_file.filename:
                errores.append(
                    f'Parte "{linea.parte}": debe adjuntar foto.'
                )
                continue

            allowed_types = {
                'image/jpeg',
                'image/png',
                'image/gif',
                'image/webp',
            }

            if foto_file.content_type not in allowed_types:
                errores.append(
                    f'Parte "{linea.parte}": solo se aceptan imágenes JPG, PNG, GIF o WEBP.'
                )
                continue

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

                _logger.warning(
                    "[PARTES][REPOSICION][PROCESAR_LINEA][OK] "
                    "linea_id=%s parte=%s solicitud=%s",
                    linea.id,
                    linea.parte,
                    solicitud.name if solicitud else False,
                )

            except Exception as e:
                _logger.exception(
                    "[PARTES][REPOSICION][PROCESAR_LINEA][ERROR] "
                    "linea_id=%s solicitud=%s error=%s",
                    linea.id,
                    solicitud.name if solicitud else False,
                    e,
                )
                errores.append(
                    f'Parte "{linea.parte}": {str(e)}'
                )

        return errores

    # =========================================================================
    # GERENCIA — APROBAR
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
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('token_gerencia', '=', token)], limit=1)

        _logger.warning(
            "[PARTES][GERENCIA_APROBAR] token=%s solicitud_id=%s state=%s",
            token,
            solicitud.id if solicitud else False,
            solicitud.state if solicitud else False,
        )

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace ya fue utilizado o no es válido. '
                'La solicitud puede haber sido aprobada o rechazada anteriormente.'
            )

        if solicitud.state != 'submitted':
            estados = dict(solicitud._fields['state'].selection)
            return self._render_error(
                'Solicitud ya procesada',
                f'Esta solicitud se encuentra en estado '
                f'<strong>{estados.get(solicitud.state, solicitud.state)}</strong> '
                f'y no puede ser procesada nuevamente.'
            )

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

        try:
            solicitud._aprobar()
            _logger.info(
                "[PARTES][GERENCIA_APROBAR] Solicitud %s aprobada vía token.",
                solicitud.name,
            )
        except Exception as e:
            _logger.exception(
                "[PARTES][GERENCIA_APROBAR][ERROR] solicitud=%s error=%s",
                solicitud.name,
                e,
            )
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
        GET → rechaza la solicitud directamente con un solo clic.
        """
        Solicitud = request.env['solicitud.partes'].sudo()
        solicitud = Solicitud.search([('token_gerencia', '=', token)], limit=1)

        _logger.warning(
            "[PARTES][GERENCIA_RECHAZAR] token=%s solicitud_id=%s state=%s",
            token,
            solicitud.id if solicitud else False,
            solicitud.state if solicitud else False,
        )

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
            _logger.info(
                "[PARTES][GERENCIA_RECHAZAR] Solicitud %s rechazada vía token.",
                solicitud.name,
            )
        except Exception as e:
            _logger.exception(
                "[PARTES][GERENCIA_RECHAZAR][ERROR] solicitud=%s error=%s",
                solicitud.name,
                e,
            )
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

        _logger.warning(
            "[PARTES][RETIRO][ENTRADA] token=%s solicitud_id=%s state=%s",
            token,
            solicitud.id if solicitud else False,
            solicitud.state if solicitud else False,
        )

        if not solicitud:
            return self._render_error(
                'Enlace no válido',
                'Este enlace no es válido o la solicitud no existe.'
            )

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

            _logger.warning(
                "[PARTES][RETIRO][POST] solicitud=%s ids_marcados=%s",
                solicitud.name,
                ids_marcados,
            )

            if not ids_marcados:
                return request.render('sat.portal_tecnico_retirar', {
                    'solicitud': solicitud,
                    'partes_pendientes': partes_pendientes,
                    'error': 'Debe marcar al menos una parte para confirmar el retiro.',
                })

            try:
                ids_marcados = [int(i) for i in ids_marcados]
            except (ValueError, TypeError):
                return self._render_error(
                    'Error',
                    'Datos de formulario inválidos.'
                )

            try:
                lineas_a_retirar = solicitud.parte_ids.filtered(
                    lambda l: l.id in ids_marcados and l.estado == 'pendiente'
                )

                for linea in lineas_a_retirar:
                    _logger.warning(
                        "[PARTES][RETIRO][LINEA] Confirmando retiro linea_id=%s parte=%s estado=%s",
                        linea.id,
                        linea.parte,
                        linea.estado,
                    )
                    linea._confirmar_retiro()

                solicitud._compute_estado_partes()

                if solicitud.todas_retiradas:
                    solicitud._completar_retiro()

                _logger.info(
                    "[PARTES][RETIRO][OK] Retiro confirmado para solicitud %s — %s partes.",
                    solicitud.name,
                    len(lineas_a_retirar),
                )

            except Exception as e:
                _logger.exception(
                    "[PARTES][RETIRO][ERROR] solicitud=%s error=%s",
                    solicitud.name,
                    e,
                )
                return self._render_error(
                    'Error al procesar',
                    f'Ocurrió un error al confirmar el retiro: {str(e)}'
                )

            restantes = solicitud.parte_ids.filtered(
                lambda l: l.estado == 'pendiente'
            )

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
            'solicitud': solicitud,
            'partes_pendientes': partes_pendientes,
            'error': None,
        })

    # =========================================================================
    # RESPONSABLE — REPOSICIÓN UNIFICADA
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
        GET:
            Muestra partes retiradas pendientes de reposición.

        POST:
            Procesa la reposición con condición, foto y observaciones.

        Este controlador unifica:
            - Token actual de solicitud:
              solicitud.partes.access_token

            - Token antiguo de línea:
              solicitud.partes.linea.access_token_linea
        """
        try:
            solicitud, partes_retiradas, tipo_token = (
                self._buscar_solicitud_reposicion_por_token(token)
            )

            if not solicitud:
                return self._render_error(
                    'Enlace no válido',
                    'No se pudo procesar la solicitud. '
                    'El enlace puede ser inválido o haber expirado.'
                )

            _logger.warning(
                "[PARTES][REPOSICION][ENTRADA] "
                "tipo_token=%s solicitud_id=%s solicitud=%s state=%s partes_retiradas=%s",
                tipo_token,
                solicitud.id,
                solicitud.name,
                solicitud.state,
                len(partes_retiradas),
            )

            # -----------------------------------------------------------------
            # Validar estado de la solicitud
            # -----------------------------------------------------------------
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

            # -----------------------------------------------------------------
            # Validar que haya partes retiradas
            # -----------------------------------------------------------------
            if not partes_retiradas:
                return self._render_error(
                    'Sin partes para reponer',
                    f'No hay partes pendientes de reposición en la solicitud '
                    f'<strong>{solicitud.name}</strong>.'
                )

            # -----------------------------------------------------------------
            # POST: procesar reposición
            # -----------------------------------------------------------------
            if request.httprequest.method == 'POST':
                form = request.httprequest.form
                files = request.httprequest.files

                _logger.warning(
                    "[PARTES][REPOSICION][POST] solicitud=%s tipo_token=%s partes=%s form_keys=%s file_keys=%s",
                    solicitud.name,
                    tipo_token,
                    partes_retiradas.ids,
                    list(form.keys()),
                    list(files.keys()),
                )

                errores = self._procesar_reposicion_lineas(
                    solicitud=solicitud,
                    partes_retiradas=partes_retiradas,
                    form=form,
                    files=files,
                )

                if errores:
                    if tipo_token == 'linea':
                        partes_retiradas_act = partes_retiradas.filtered(
                            lambda l: l.estado == 'retirado'
                        )
                    else:
                        partes_retiradas_act = solicitud.parte_ids.filtered(
                            lambda l: l.estado == 'retirado'
                        )

                    _logger.warning(
                        "[PARTES][REPOSICION][POST][ERRORES] "
                        "solicitud=%s errores=%s partes_restantes=%s",
                        solicitud.name,
                        errores,
                        partes_retiradas_act.ids,
                    )

                    return request.render('sat.portal_responsable_reponer', {
                        'solicitud': solicitud,
                        'partes_retiradas': partes_retiradas_act,
                        'errores': errores,
                        'token': token,
                        'tipo_token': tipo_token,
                    })

                solicitud._compute_estado_partes()

                if solicitud.todas_repuestas:
                    solicitud._completar_reposicion()

                _logger.warning(
                    "[PARTES][REPOSICION][POST][FIN] solicitud=%s state=%s todas_repuestas=%s",
                    solicitud.name,
                    solicitud.state,
                    solicitud.todas_repuestas,
                )

                return self._render_ok(
                    '✅ Reposición Completada',
                    f'La reposición de la solicitud '
                    f'<strong>{solicitud.name}</strong> fue registrada correctamente.',
                    detalle='El registro ha sido actualizado en el sistema.'
                )

            # -----------------------------------------------------------------
            # GET: mostrar formulario
            # -----------------------------------------------------------------
            _logger.warning(
                "[PARTES][REPOSICION][GET] Render formulario solicitud=%s tipo_token=%s partes=%s",
                solicitud.name,
                tipo_token,
                partes_retiradas.ids,
            )

            return request.render('sat.portal_responsable_reponer', {
                'solicitud': solicitud,
                'partes_retiradas': partes_retiradas,
                'errores': [],
                'token': token,
                'tipo_token': tipo_token,
            })

        except Exception as e:
            _logger.exception(
                "[PARTES][REPOSICION][ERROR_GENERAL] token=%s error=%s",
                token,
                e,
            )
            return self._render_error(
                'Error al procesar',
                f'Ocurrió un error al cargar la reposición: {str(e)}'
            )

    # =========================================================================
    # RESPONSABLE — REPOSICIÓN SUBMIT ANTIGUO / COMPATIBILIDAD
    # =========================================================================

    @http.route(
        '/partes/reponer/submit',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
        csrf=False,
    )
    def reponer_parte_submit_compat(self, **post):
        """
        Compatibilidad con formularios antiguos que enviaban a:

            /partes/reponer/submit

        Espera:
            token
            condicion
            foto
            observaciones

        También soporta campos nuevos:
            condicion_<linea.id>
            foto_<linea.id>
            observaciones_<linea.id>
        """
        token = post.get('token') or request.httprequest.form.get('token')

        try:
            _logger.warning(
                "[PARTES][REPOSICION][SUBMIT_COMPAT] Inicio token=%s form_keys=%s file_keys=%s",
                token,
                list(request.httprequest.form.keys()),
                list(request.httprequest.files.keys()),
            )

            solicitud, partes_retiradas, tipo_token = (
                self._buscar_solicitud_reposicion_por_token(token)
            )

            if not solicitud:
                return self._render_error(
                    'Enlace no válido',
                    'No se pudo procesar la solicitud. '
                    'El enlace puede ser inválido o haber expirado.'
                )

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

            if not partes_retiradas:
                return self._render_error(
                    'Sin partes para reponer',
                    f'No hay partes pendientes de reposición en la solicitud '
                    f'<strong>{solicitud.name}</strong>.'
                )

            errores = self._procesar_reposicion_lineas(
                solicitud=solicitud,
                partes_retiradas=partes_retiradas,
                form=request.httprequest.form,
                files=request.httprequest.files,
            )

            if errores:
                if tipo_token == 'linea':
                    partes_retiradas_act = partes_retiradas.filtered(
                        lambda l: l.estado == 'retirado'
                    )
                else:
                    partes_retiradas_act = solicitud.parte_ids.filtered(
                        lambda l: l.estado == 'retirado'
                    )

                return request.render('sat.portal_responsable_reponer', {
                    'solicitud': solicitud,
                    'partes_retiradas': partes_retiradas_act,
                    'errores': errores,
                    'token': token,
                    'tipo_token': tipo_token,
                })

            solicitud._compute_estado_partes()

            if solicitud.todas_repuestas:
                solicitud._completar_reposicion()

            _logger.warning(
                "[PARTES][REPOSICION][SUBMIT_COMPAT][FIN] solicitud=%s state=%s todas_repuestas=%s",
                solicitud.name,
                solicitud.state,
                solicitud.todas_repuestas,
            )

            return self._render_ok(
                '✅ Reposición Completada',
                f'La reposición de la solicitud '
                f'<strong>{solicitud.name}</strong> fue registrada correctamente.',
                detalle='El registro ha sido actualizado en el sistema.'
            )

        except Exception as e:
            _logger.exception(
                "[PARTES][REPOSICION][SUBMIT_COMPAT][ERROR_GENERAL] token=%s error=%s",
                token,
                e,
            )
            return self._render_error(
                'Error al procesar',
                f'Ocurrió un error al procesar la reposición: {str(e)}'
            )
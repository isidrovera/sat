# -*- coding: utf-8 -*-

import base64
import logging

from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, MissingError

_logger = logging.getLogger(__name__)


class ReparacionesAvanceController(http.Controller):

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _get_reparacion_by_token(self, token):
        """
        Busca una reparación por token de avance.
        Se usa sudo porque el enlace puede abrirse fuera del backend.
        """
        if not token:
            return request.env['reparaciones.reparaciones'].sudo().browse()

        return request.env['reparaciones.reparaciones'].sudo().search([
            ('avance_token', '=', token)
        ], limit=1)

    def _get_avance_options(self):
        """
        Opciones activas agrupadas por categoría.
        """
        options = request.env['reparacion.avance.opcion'].sudo().search([
            ('active', '=', True)
        ], order='sequence, category, name')

        grouped = {}

        category_labels = dict(
            request.env['reparacion.avance.opcion']._fields['category'].selection
        )

        for option in options:
            key = option.category or 'otro'
            if key not in grouped:
                grouped[key] = {
                    'label': category_labels.get(key, key),
                    'options': [],
                }
            grouped[key]['options'].append(option)

        return grouped

    def _is_truthy(self, value):
        """
        Convierte valores del formulario a booleano.
        """
        return value in ('1', 'true', 'True', 'on', 'yes', 'si', 'sí')

    def _prepare_file_values_from_files(self, files):
        """
        Prepara archivos subidos para que el modelo los guarde
        en reparacion.avance.linea.
        """
        file_values = []

        if not files:
            return file_values

        for file_storage in files:
            if not file_storage:
                continue

            filename = file_storage.filename or 'foto_avance.jpg'
            content = file_storage.read()

            if not content:
                continue

            file_values.append({
                'name': filename,
                'datas': base64.b64encode(content),
                'mimetype': file_storage.content_type or 'image/jpeg',
            })

        return file_values

    def _extract_option_data_from_post(self, post):
        """
        Convierte los datos del formulario en option_data para create_avance_rapido.

        Formato esperado:
        - opcion_ids: ids seleccionados
        - color_<opcion_id>: black/cyan/magenta/yellow/varios
        - parte_<opcion_id>: texto
        - detalle_<opcion_id>: texto
        """
        option_ids = request.httprequest.form.getlist('opcion_ids')
        option_data = []

        for raw_id in option_ids:
            try:
                opcion_id = int(raw_id)
            except Exception:
                continue

            color = post.get(f'color_{opcion_id}') or False
            parte = post.get(f'parte_{opcion_id}') or False
            detalle = post.get(f'detalle_{opcion_id}') or False

            option_data.append({
                'opcion_id': opcion_id,
                'color': color,
                'parte': parte,
                'detalle': detalle,
            })

        return option_data

    def _render_avance_page(self, reparacion, token, error=False, success=False, avance=False):
        """
        Renderiza la página de avance.
        """
        grouped_options = self._get_avance_options()

        values = {
            'reparacion': reparacion,
            'token': token,
            'grouped_options': grouped_options,
            'error': error,
            'success': success,
            'avance': avance,
        }

        return request.render('sat.reparaciones_avance_page', values)

    # -------------------------------------------------------------------------
    # ROUTES
    # -------------------------------------------------------------------------

    @http.route(
        ['/reparacion/avance/<string:token>'],
        type='http',
        auth='public',
        website=True,
        csrf=True,
        methods=['GET'],
    )
    def reparacion_avance_page(self, token, **kwargs):
        """
        Página pública por token para registrar avance.
        """
        reparacion = self._get_reparacion_by_token(token)

        if not reparacion:
            return request.render('sat.reparaciones_avance_error_page', {
                'title': _('Enlace inválido'),
                'message': _('El enlace de avance no existe o ya no está disponible.'),
            })

        if reparacion.estado_id != 'en_revision':
            return request.render('sat.reparaciones_avance_error_page', {
                'title': _('Reparación no está en revisión'),
                'message': _(
                    'Esta reparación ya no se encuentra en revisión. '
                    'No es necesario registrar un nuevo avance.'
                ),
                'reparacion': reparacion,
            })

        return self._render_avance_page(reparacion, token)

    @http.route(
        ['/reparacion/avance/<string:token>/guardar'],
        type='http',
        auth='public',
        website=True,
        csrf=True,
        methods=['POST'],
    )
    def reparacion_avance_guardar(self, token, **post):
        """
        Guarda el avance rápido desde la página pública.
        """
        reparacion = self._get_reparacion_by_token(token)

        if not reparacion:
            return request.render('sat.reparaciones_avance_error_page', {
                'title': _('Enlace inválido'),
                'message': _('El enlace de avance no existe o ya no está disponible.'),
            })

        if reparacion.estado_id != 'en_revision':
            return request.render('sat.reparaciones_avance_error_page', {
                'title': _('Reparación no está en revisión'),
                'message': _(
                    'Esta reparación ya no se encuentra en revisión. '
                    'No se guardó el avance.'
                ),
                'reparacion': reparacion,
            })

        option_data = self._extract_option_data_from_post(post)
        detalle = post.get('detalle') or False
        notificar_asesora = self._is_truthy(post.get('notificar_asesora'))

        if not option_data and not detalle:
            return self._render_avance_page(
                reparacion,
                token,
                error=_('Seleccione al menos una opción de avance o escriba un detalle.'),
            )

        files = request.httprequest.files.getlist('fotos')
        file_values = []

        try:
            file_values = self._prepare_file_values_from_files(files)
        except Exception as e:
            _logger.exception(
                "[AVANCE REPARACIÓN] Error subiendo fotos para reparación ID %s: %s",
                reparacion.id,
                e,
            )
            return self._render_avance_page(
                reparacion,
                token,
                error=_('No se pudieron subir las fotos. Intente nuevamente.'),
            )

        try:
            avance = reparacion.create_avance_rapido(
                option_data=option_data,
                detalle=detalle,
                file_values=file_values,
                notificar_asesora=notificar_asesora,
            )
        except Exception as e:
            _logger.exception(
                "[AVANCE REPARACIÓN] Error creando avance para reparación ID %s: %s",
                reparacion.id,
                e,
            )
            return self._render_avance_page(
                reparacion,
                token,
                error=_('No se pudo guardar el avance. Revise los datos e intente nuevamente.'),
            )

        message = _('Avance guardado correctamente.')

        if notificar_asesora:
            if avance.asesora_notificada:
                message = _('Avance guardado y notificado a la asesora correctamente.')
            else:
                message = _(
                    'Avance guardado, pero no se pudo notificar a la asesora. '
                    'Revise el historial de la reparación.'
                )

        return self._render_avance_page(
            reparacion,
            token,
            success=message,
            avance=avance,
        )
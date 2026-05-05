# -*- coding: utf-8 -*-

import base64
import logging
import mimetypes

from odoo import http, fields, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class EvidenciaController(http.Controller):

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _buscar_ticket_por_token(self, token):
        """Busca el ticket por token. Devuelve None si no existe."""
        if not token:
            _logger.warning("[EVIDENCIA] Token vacío recibido")
            return None

        ticket = request.env['ticket.alquiler'].sudo().search([
            ('evidencia_token', '=', token)
        ], limit=1)

        if not ticket:
            _logger.warning("[EVIDENCIA] Token inválido/no encontrado: %s", token)
            return None

        _logger.info(
            "[EVIDENCIA] Ticket encontrado por token | ticket_id=%s | name=%s | estado=%s",
            ticket.id,
            ticket.name,
            ticket.estado,
        )

        return ticket

    def _float_safe(self, value, default=0.0):
        """Convierte a float sin romper si viene vacío o inválido."""
        try:
            if value in (None, '', False):
                return default
            return float(value)
        except Exception:
            return default

    # -------------------------------------------------------------------------
    # Página pública
    # -------------------------------------------------------------------------

    @http.route(
        '/evidencia/<string:token>',
        type='http',
        auth='public',
        website=False,
        csrf=False
    )
    def evidencia_page(self, token, **kw):
        """Página pública para subir fotos de evidencia."""

        _logger.info("[EVIDENCIA PAGE] Solicitud recibida | token=%s", token)

        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            _logger.warning("[EVIDENCIA PAGE] Render token inválido | token=%s", token)
            return request.render('sat.evidencia_token_invalido', {})

        if ticket.estado == 'finalizado':
            _logger.info(
                "[EVIDENCIA PAGE] Ticket finalizado, no permite subir fotos | ticket_id=%s | name=%s",
                ticket.id,
                ticket.name,
            )
            return request.render('sat.evidencia_ticket_cerrado', {
                'ticket': ticket,
            })

        fotos_antes = ticket.evidencia_foto_ids.filtered(lambda f: f.momento == 'antes')
        fotos_despues = ticket.evidencia_foto_ids.filtered(lambda f: f.momento == 'despues')

        _logger.info(
            "[EVIDENCIA PAGE] Render página evidencia | ticket_id=%s | antes=%s | despues=%s",
            ticket.id,
            len(fotos_antes),
            len(fotos_despues),
        )

        return request.render('sat.evidencia_page_template', {
            'ticket': ticket,
            'token': token,
            'fotos_antes': fotos_antes,
            'fotos_despues': fotos_despues,
        })

    # -------------------------------------------------------------------------
    # Imagen pública segura por token
    # -------------------------------------------------------------------------

    @http.route(
        '/evidencia/<string:token>/foto/<int:foto_id>',
        type='http',
        auth='public',
        website=False,
        csrf=False
    )
    def evidencia_foto_publica(self, token, foto_id, **kw):
        """
        Sirve una imagen públicamente, pero validando que:
        - El token exista.
        - La foto pertenezca al ticket del token.
        """

        _logger.info(
            "[EVIDENCIA FOTO] Solicitud imagen | token=%s | foto_id=%s",
            token,
            foto_id,
        )

        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            _logger.warning(
                "[EVIDENCIA FOTO] Token inválido para imagen | token=%s | foto_id=%s",
                token,
                foto_id,
            )
            return request.not_found()

        foto = request.env['ticket.evidencia.foto'].sudo().search([
            ('id', '=', foto_id),
            ('ticket_id', '=', ticket.id),
        ], limit=1)

        if not foto:
            _logger.warning(
                "[EVIDENCIA FOTO] Foto no encontrada o no pertenece al ticket | ticket_id=%s | foto_id=%s",
                ticket.id,
                foto_id,
            )
            return request.not_found()

        if not foto.imagen_original:
            _logger.warning(
                "[EVIDENCIA FOTO] Foto sin imagen_original | ticket_id=%s | foto_id=%s",
                ticket.id,
                foto.id,
            )
            return request.not_found()

        try:
            image_data = base64.b64decode(foto.imagen_original)
        except Exception:
            _logger.exception(
                "[EVIDENCIA FOTO] Error decodificando imagen | ticket_id=%s | foto_id=%s",
                ticket.id,
                foto.id,
            )
            return request.not_found()

        filename = foto.imagen_original_filename or 'evidencia.jpg'
        mimetype = mimetypes.guess_type(filename)[0] or 'image/jpeg'

        _logger.info(
            "[EVIDENCIA FOTO] Imagen servida correctamente | ticket_id=%s | foto_id=%s | filename=%s | mimetype=%s",
            ticket.id,
            foto.id,
            filename,
            mimetype,
        )

        return request.make_response(
            image_data,
            headers=[
                ('Content-Type', mimetype),
                ('Content-Disposition', 'inline; filename="%s"' % filename),
                ('Cache-Control', 'private, max-age=3600'),
            ]
        )

    # -------------------------------------------------------------------------
    # Upload JSON
    # -------------------------------------------------------------------------

    @http.route(
        '/evidencia/<string:token>/upload',
        type='json',
        auth='public',
        csrf=False,
        methods=['POST']
    )
    def evidencia_upload(self, token, **kw):
        """Recibe la foto en base64 desde el cliente."""

        _logger.info("[EVIDENCIA UPLOAD] Solicitud recibida | token=%s", token)
        _logger.info("[EVIDENCIA UPLOAD] KW recibidos keys=%s", list(kw.keys()))

        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            _logger.warning("[EVIDENCIA UPLOAD] Token inválido | token=%s", token)
            return {
                'success': False,
                'error': 'Token inválido',
            }

        if ticket.estado == 'finalizado':
            _logger.warning(
                "[EVIDENCIA UPLOAD] Ticket finalizado, upload rechazado | ticket_id=%s | name=%s",
                ticket.id,
                ticket.name,
            )
            return {
                'success': False,
                'error': 'El ticket ya fue finalizado, no se aceptan más fotos.',
            }

        momento = kw.get('momento')
        imagen_base64 = kw.get('imagen_base64')
        latitud = kw.get('latitud')
        longitud = kw.get('longitud')
        precision = kw.get('precision', 0)
        filename = kw.get('filename') or 'evidencia.jpg'

        _logger.info(
            "[EVIDENCIA UPLOAD] Datos recibidos | ticket_id=%s | momento=%s | filename=%s | lat=%s | lng=%s | precision=%s",
            ticket.id,
            momento,
            filename,
            latitud,
            longitud,
            precision,
        )

        # ---------------------------------------------------------------------
        # Validaciones
        # ---------------------------------------------------------------------

        if momento not in ('antes', 'despues'):
            _logger.warning(
                "[EVIDENCIA UPLOAD] Momento inválido | ticket_id=%s | momento=%s",
                ticket.id,
                momento,
            )
            return {
                'success': False,
                'error': 'Momento inválido. Debe ser antes o después.',
            }

        if not imagen_base64:
            _logger.warning(
                "[EVIDENCIA UPLOAD] No se recibió imagen | ticket_id=%s",
                ticket.id,
            )
            return {
                'success': False,
                'error': 'No se recibió imagen.',
            }

        if ',' in imagen_base64:
            _logger.info("[EVIDENCIA UPLOAD] Imagen viene como dataURL, separando cabecera")
            imagen_base64 = imagen_base64.split(',', 1)[1]

        try:
            decoded = base64.b64decode(imagen_base64, validate=True)
        except Exception as e:
            _logger.error(
                "[EVIDENCIA UPLOAD] Base64 inválido | ticket_id=%s | error=%s",
                ticket.id,
                e,
            )
            return {
                'success': False,
                'error': 'Formato de imagen inválido.',
            }

        size_bytes = len(decoded)
        size_kb = round(size_bytes / 1024, 2)
        size_mb = round(size_bytes / 1024 / 1024, 2)

        _logger.info(
            "[EVIDENCIA UPLOAD] Imagen decodificada | ticket_id=%s | size_kb=%s | size_mb=%s",
            ticket.id,
            size_kb,
            size_mb,
        )

        max_size_mb = 10
        if size_bytes > max_size_mb * 1024 * 1024:
            _logger.warning(
                "[EVIDENCIA UPLOAD] Imagen demasiado grande | ticket_id=%s | size_mb=%s | max_mb=%s",
                ticket.id,
                size_mb,
                max_size_mb,
            )
            return {
                'success': False,
                'error': 'La imagen es demasiado grande. Máximo permitido: %s MB.' % max_size_mb,
            }

        lat_float = self._float_safe(latitud)
        lng_float = self._float_safe(longitud)
        precision_float = self._float_safe(precision)

        sin_gps = not (lat_float and lng_float)

        _logger.info(
            "[EVIDENCIA UPLOAD] GPS procesado | ticket_id=%s | lat=%s | lng=%s | precision=%s | sin_gps=%s",
            ticket.id,
            lat_float,
            lng_float,
            precision_float,
            sin_gps,
        )

        # ---------------------------------------------------------------------
        # Crear foto
        # ---------------------------------------------------------------------

        try:
            foto_vals = {
                'ticket_id': ticket.id,
                'momento': momento,
                'imagen_original': imagen_base64,
                'imagen_original_filename': filename,
                'latitud': lat_float,
                'longitud': lng_float,
                'precision_gps': precision_float,
                'timestamp_captura': fields.Datetime.now(),
                'user_agent': request.httprequest.headers.get('User-Agent', ''),
                'ip_origen': request.httprequest.remote_addr,
            }

            _logger.info(
                "[EVIDENCIA UPLOAD] Creando ticket.evidencia.foto | ticket_id=%s | vals_keys=%s",
                ticket.id,
                list(foto_vals.keys()),
            )

            foto = request.env['ticket.evidencia.foto'].sudo().create(foto_vals)

            _logger.info(
                "[EVIDENCIA UPLOAD] Foto creada correctamente | foto_id=%s | ticket_id=%s | momento=%s",
                foto.id,
                ticket.id,
                momento,
            )

            msg = "📸 Nueva foto de evidencia (%s) subida desde el link público.<br/>" % momento

            if sin_gps:
                msg += "⚠️ Sin coordenadas GPS.<br/>"
            else:
                msg += "📍 Coordenadas: %s, %s<br/>" % (lat_float, lng_float)
                msg += "🎯 Precisión GPS: %s m<br/>" % round(precision_float, 2)

            msg += "🖼️ Foto ID: %s" % foto.id

            _logger.info(
                "[EVIDENCIA UPLOAD] Publicando mensaje en chatter | ticket_id=%s | foto_id=%s",
                ticket.id,
                foto.id,
            )

            ticket.sudo().message_post(
                body=msg,
                message_type='notification',
            )

            _logger.info(
                "[EVIDENCIA UPLOAD] Upload finalizado OK | ticket_id=%s | foto_id=%s",
                ticket.id,
                foto.id,
            )

            return {
                'success': True,
                'foto_id': foto.id,
                'mensaje': 'Foto subida correctamente.',
            }

        except Exception as e:
            _logger.exception(
                "[EVIDENCIA UPLOAD] Error guardando foto | ticket_id=%s | error=%s",
                ticket.id,
                e,
            )
            return {
                'success': False,
                'error': 'Error guardando la foto: %s' % str(e),
            }
# -*- coding: utf-8 -*-
import base64
import logging
from odoo import http, fields, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class EvidenciaController(http.Controller):

    def _buscar_ticket_por_token(self, token):
        """Busca el ticket por token. Devuelve None si no existe."""
        if not token:
            return None
        ticket = request.env['ticket.alquiler'].sudo().search([
            ('evidencia_token', '=', token)
        ], limit=1)
        return ticket if ticket else None

    @http.route('/evidencia/<string:token>', type='http', auth='public',
                website=False, csrf=False)
    def evidencia_page(self, token, **kw):
        """Página pública para subir fotos de evidencia."""
        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            return request.render('sat.evidencia_token_invalido', {})

        if ticket.estado == 'finalizado':
            return request.render('sat.evidencia_ticket_cerrado', {
                'ticket': ticket,
            })

        # Cargar fotos ya subidas para mostrar en galería
        fotos_antes = ticket.evidencia_foto_ids.filtered(lambda f: f.momento == 'antes')
        fotos_despues = ticket.evidencia_foto_ids.filtered(lambda f: f.momento == 'despues')

        return request.render('sat.evidencia_page_template', {
            'ticket': ticket,
            'token': token,
            'fotos_antes': fotos_antes,
            'fotos_despues': fotos_despues,
        })

    @http.route('/evidencia/<string:token>/upload', type='json', auth='public',
            csrf=False, methods=['POST'])
    def evidencia_upload(self, token, **kw):
        """Recibe la foto en base64 desde el cliente."""
        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            return {'success': False, 'error': 'Token inválido'}

        if ticket.estado == 'finalizado':
            return {'success': False, 'error': 'El ticket ya fue finalizado, no se aceptan más fotos.'}

        momento = kw.get('momento')
        imagen_base64 = kw.get('imagen_base64')
        latitud = kw.get('latitud')
        longitud = kw.get('longitud')
        precision = kw.get('precision', 0)
        filename = kw.get('filename', 'evidencia.jpg')

        # Validaciones
        if momento not in ('antes', 'despues'):
            return {'success': False, 'error': 'Momento inválido (debe ser antes o después).'}
        if not imagen_base64:
            return {'success': False, 'error': 'No se recibió imagen.'}
        # GPS ya no es obligatorio - se acepta sin coordenadas pero se loguea

        if ',' in imagen_base64:
            imagen_base64 = imagen_base64.split(',', 1)[1]

        try:
            base64.b64decode(imagen_base64)
        except Exception as e:
            _logger.error("[evidencia_upload] base64 inválido: %s", e)
            return {'success': False, 'error': 'Formato de imagen inválido.'}

        try:
            sin_gps = not (latitud and longitud)
            foto = request.env['ticket.evidencia.foto'].sudo().create({
                'ticket_id': ticket.id,
                'momento': momento,
                'imagen_original': imagen_base64,
                'imagen_original_filename': filename,
                'latitud': float(latitud) if latitud else 0,
                'longitud': float(longitud) if longitud else 0,
                'precision_gps': float(precision) if precision else 0,
                'timestamp_captura': fields.Datetime.now(),
                'user_agent': request.httprequest.headers.get('User-Agent', ''),
                'ip_origen': request.httprequest.remote_addr,
            })

            _logger.info(
                "[evidencia_upload] Foto creada id=%s ticket=%s momento=%s lat=%s lng=%s sin_gps=%s",
                foto.id, ticket.name, momento, latitud, longitud, sin_gps
            )

            msg = "📸 Nueva foto de evidencia (%s) subida desde el link público.<br/>" % momento
            if sin_gps:
                msg += "⚠️ Sin coordenadas GPS"
            else:
                msg += "Coordenadas: %s, %s" % (latitud, longitud)

            ticket.message_post(body=msg, message_type='notification')

            return {
                'success': True,
                'foto_id': foto.id,
                'mensaje': 'Foto subida correctamente.',
            }
        except Exception as e:
            _logger.exception("[evidencia_upload] Error guardando foto: %s", e)
            return {'success': False, 'error': f'Error guardando la foto: {str(e)}'}
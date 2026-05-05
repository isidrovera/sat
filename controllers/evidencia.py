# -*- coding: utf-8 -*-

import base64
import logging
import mimetypes
import requests

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class EvidenciaController(http.Controller):

    # -------------------------------------------------------------------------
    # Helpers generales
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
            "[EVIDENCIA] Ticket encontrado | ticket_id=%s | name=%s | estado=%s",
            ticket.id,
            ticket.name,
            ticket.estado,
        )

        return ticket

    def _float_safe(self, value, default=0.0):
        """Convierte valor a float sin romper."""
        try:
            if value in (None, '', False):
                return default
            return float(value)
        except Exception:
            return default

    def _get_ticket_company(self, ticket):
        """Obtiene la empresa asociada al ticket o la empresa actual."""
        try:
            if hasattr(ticket, 'company_id') and ticket.company_id:
                return ticket.company_id.sudo()
        except Exception:
            pass

        return request.env.company.sudo()

    def _get_logo_base64(self, company):
        """Obtiene logo base64 de la empresa."""
        logo_b64 = False

        try:
            if hasattr(company, 'logo') and company.logo:
                logo_b64 = company.logo
        except Exception:
            logo_b64 = False

        if not logo_b64:
            try:
                if hasattr(company, 'logo_web') and company.logo_web:
                    logo_b64 = company.logo_web
            except Exception:
                logo_b64 = False

        return logo_b64

    # -------------------------------------------------------------------------
    # Helpers Traccar / dirección
    # -------------------------------------------------------------------------

    def _get_traccar_config(self):
        """Lee configuración de Traccar desde parámetros del sistema."""
        ICP = request.env['ir.config_parameter'].sudo()

        cfg = {
            'url': ICP.get_param('traccar.url', 'https://gps.andessolutioncopiers.com'),
            'email': ICP.get_param('traccar.email'),
            'password': ICP.get_param('traccar.password'),
            'timeout': int(ICP.get_param('traccar.timeout', '10') or 10),
        }

        if cfg['url']:
            cfg['url'] = cfg['url'].rstrip('/')

        return cfg

    def _get_traccar_session(self):
        """
        Inicia sesión en Traccar usando los mismos parámetros que ya usa tu módulo.
        """
        cfg = self._get_traccar_config()

        if not cfg.get('email') or not cfg.get('password'):
            _logger.warning(
                "[EVIDENCIA TRACCAR] traccar.email/traccar.password no configurados"
            )
            return None, cfg

        try:
            session = requests.Session()

            resp = session.post(
                "%s/api/session" % cfg['url'],
                data={
                    'email': cfg['email'],
                    'password': cfg['password'],
                },
                timeout=cfg['timeout'],
            )

            _logger.info(
                "[EVIDENCIA TRACCAR] Login HTTP=%s | url=%s",
                resp.status_code,
                cfg['url'],
            )

            if resp.status_code != 200:
                _logger.warning(
                    "[EVIDENCIA TRACCAR] Login falló | status=%s | body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                return None, cfg

            return session, cfg

        except Exception as e:
            _logger.exception("[EVIDENCIA TRACCAR] Error login Traccar: %s", e)
            return None, cfg

    def _normalizar_direccion(self, address):
        """
        Recorta/limpia dirección para que se vea bien en la foto.
        """
        if not address:
            return False

        address = str(address).replace('\n', ' ').strip()

        partes = [
            p.strip()
            for p in address.split(',')
            if p and p.strip()
        ]

        limpias = []

        for p in partes:
            # Evitar códigos postales muy largos o partes poco útiles
            if p.isdigit() and len(p) >= 5:
                continue

            if p not in limpias:
                limpias.append(p)

        if limpias:
            return ', '.join(limpias[:6])

        return address[:180]

    def _direccion_desde_traccar_positions(self, lat, lng):
        """
        Primer intento:
        Usar /api/positions de Traccar y buscar una posición cercana con address.

        Esto aprovecha que Traccar ya guarda/muestra address en posiciones.
        Sirve especialmente porque tus técnicos ya están reportando desde celular.
        """
        session, cfg = self._get_traccar_session()

        if not session:
            return False

        try:
            resp = session.get(
                "%s/api/positions" % cfg['url'],
                timeout=cfg['timeout'],
            )

            _logger.info(
                "[EVIDENCIA GEOCODE] Traccar /api/positions HTTP=%s",
                resp.status_code,
            )

            if resp.status_code != 200:
                _logger.warning(
                    "[EVIDENCIA GEOCODE] Traccar positions falló | status=%s | body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False

            positions = resp.json() or []

            mejor = None
            mejor_distancia = None

            for pos in positions:
                pos_lat = pos.get('latitude')
                pos_lng = pos.get('longitude')
                address = pos.get('address')

                if not pos_lat or not pos_lng or not address:
                    continue

                distancia = self._haversine_metros(lat, lng, pos_lat, pos_lng)

                if mejor is None or distancia < mejor_distancia:
                    mejor = pos
                    mejor_distancia = distancia

            if mejor and mejor_distancia is not None:
                _logger.info(
                    "[EVIDENCIA GEOCODE] Mejor dirección Traccar | deviceId=%s | distancia=%.1fm | address=%s",
                    mejor.get('deviceId'),
                    mejor_distancia,
                    mejor.get('address'),
                )

                # Si la posición está razonablemente cerca, usamos esa dirección.
                # Puedes cambiar 250 por 500 si quieres ser más flexible.
                if mejor_distancia <= 250:
                    return self._normalizar_direccion(mejor.get('address'))

                _logger.warning(
                    "[EVIDENCIA GEOCODE] Dirección Traccar encontrada pero lejos | distancia=%.1fm",
                    mejor_distancia,
                )

            return False

        except Exception as e:
            _logger.exception(
                "[EVIDENCIA GEOCODE] Error consultando Traccar positions: %s",
                e,
            )
            return False

    def _direccion_desde_nominatim_directo(self, lat, lng):
        """
        Respaldo:
        Usa Nominatim directo si Traccar no devuelve dirección.
        No usa Google.
        """
        try:
            _logger.info(
                "[EVIDENCIA GEOCODE] Intentando Nominatim directo | lat=%s | lng=%s",
                lat,
                lng,
            )

            url = 'https://nominatim.openstreetmap.org/reverse'
            params = {
                'format': 'jsonv2',
                'lat': lat,
                'lon': lng,
                'zoom': 18,
                'addressdetails': 1,
                'accept-language': 'es',
            }
            headers = {
                'User-Agent': 'AndesSolutionCopiers-Odoo-SAT/1.0',
            }

            resp = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=8,
            )

            _logger.info(
                "[EVIDENCIA GEOCODE] Nominatim HTTP=%s",
                resp.status_code,
            )

            if resp.status_code != 200:
                _logger.warning(
                    "[EVIDENCIA GEOCODE] Nominatim falló | status=%s | body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False

            data = resp.json() or {}
            display_name = data.get('display_name')

            if display_name:
                direccion = self._normalizar_direccion(display_name)
                _logger.info(
                    "[EVIDENCIA GEOCODE] Dirección Nominatim OK | address=%s",
                    direccion,
                )
                return direccion

            return False

        except Exception as e:
            _logger.exception("[EVIDENCIA GEOCODE] Error Nominatim: %s", e)
            return False

    @staticmethod
    def _haversine_metros(lat1, lon1, lat2, lon2):
        """
        Calcula distancia entre dos puntos GPS.
        Copiado en simple para no depender del modelo ticket_tracking.py.
        """
        import math

        R = 6371000
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        d_phi = math.radians(float(lat2) - float(lat1))
        d_lambda = math.radians(float(lon2) - float(lon1))

        a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        )

        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

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
            _logger.warning("[EVIDENCIA PAGE] Token inválido | token=%s", token)
            return request.render('sat.evidencia_token_invalido', {})

        if ticket.estado == 'finalizado':
            _logger.info(
                "[EVIDENCIA PAGE] Ticket finalizado | ticket_id=%s | name=%s",
                ticket.id,
                ticket.name,
            )
            return request.render('sat.evidencia_ticket_cerrado', {
                'ticket': ticket,
            })

        fotos_antes = ticket.evidencia_foto_ids.filtered(lambda f: f.momento == 'antes')
        fotos_despues = ticket.evidencia_foto_ids.filtered(lambda f: f.momento == 'despues')

        _logger.info(
            "[EVIDENCIA PAGE] Render OK | ticket_id=%s | antes=%s | despues=%s",
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
                "[EVIDENCIA FOTO] Token inválido | token=%s | foto_id=%s",
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
                "[EVIDENCIA FOTO] Foto no encontrada/no pertenece al ticket | ticket_id=%s | foto_id=%s",
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
            "[EVIDENCIA FOTO] Imagen servida OK | ticket_id=%s | foto_id=%s | mimetype=%s",
            ticket.id,
            foto.id,
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
    # Logo público seguro por token
    # -------------------------------------------------------------------------

    @http.route(
        '/evidencia/<string:token>/logo',
        type='http',
        auth='public',
        website=False,
        csrf=False
    )
    def evidencia_company_logo(self, token, **kw):
        """
        Devuelve logo de la empresa para dibujarlo sobre la foto.
        """
        _logger.info("[EVIDENCIA LOGO] Solicitud logo | token=%s", token)

        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            _logger.warning("[EVIDENCIA LOGO] Token inválido | token=%s", token)
            return request.not_found()

        company = self._get_ticket_company(ticket)
        logo_b64 = self._get_logo_base64(company)

        if not logo_b64:
            _logger.warning(
                "[EVIDENCIA LOGO] Empresa sin logo | company_id=%s | company=%s",
                company.id,
                company.name,
            )
            return request.not_found()

        try:
            logo_data = base64.b64decode(logo_b64)
        except Exception:
            _logger.exception(
                "[EVIDENCIA LOGO] Error decodificando logo | company_id=%s",
                company.id,
            )
            return request.not_found()

        _logger.info(
            "[EVIDENCIA LOGO] Logo servido OK | company_id=%s | company=%s | size_kb=%s",
            company.id,
            company.name,
            round(len(logo_data) / 1024, 2),
        )

        return request.make_response(
            logo_data,
            headers=[
                ('Content-Type', 'image/png'),
                ('Content-Disposition', 'inline; filename="company_logo.png"'),
                ('Cache-Control', 'private, max-age=3600'),
            ]
        )

    # -------------------------------------------------------------------------
    # Geocode público por token usando Traccar
    # -------------------------------------------------------------------------

    @http.route(
        '/evidencia/<string:token>/geocode',
        type='json',
        auth='public',
        csrf=False,
        methods=['POST']
    )
    def evidencia_reverse_geocode(self, token, **kw):
        """
        Convierte lat/lng a dirección.
        Prioridad:
        1) Traccar /api/positions buscando posición cercana con address.
        2) Nominatim directo como respaldo.
        3) Coordenadas si no hay dirección.
        """
        _logger.info(
            "[EVIDENCIA GEOCODE] Solicitud recibida | token=%s | kw=%s",
            token,
            kw,
        )

        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            _logger.warning("[EVIDENCIA GEOCODE] Token inválido | token=%s", token)
            return {
                'success': False,
                'provider': False,
                'address': False,
                'error': 'Token inválido',
            }

        lat = self._float_safe(kw.get('lat'))
        lng = self._float_safe(kw.get('lng'))

        if not lat or not lng:
            _logger.warning(
                "[EVIDENCIA GEOCODE] Coordenadas inválidas | ticket_id=%s | lat=%s | lng=%s",
                ticket.id,
                lat,
                lng,
            )
            return {
                'success': False,
                'provider': False,
                'address': False,
                'error': 'Coordenadas inválidas',
            }

        _logger.info(
            "[EVIDENCIA GEOCODE] Procesando | ticket_id=%s | lat=%s | lng=%s",
            ticket.id,
            lat,
            lng,
        )

        direccion = self._direccion_desde_traccar_positions(lat, lng)

        if direccion:
            _logger.info(
                "[EVIDENCIA GEOCODE] Dirección final desde Traccar | ticket_id=%s | address=%s",
                ticket.id,
                direccion,
            )
            return {
                'success': True,
                'provider': 'traccar_positions',
                'address': direccion,
            }

        direccion = self._direccion_desde_nominatim_directo(lat, lng)

        if direccion:
            _logger.info(
                "[EVIDENCIA GEOCODE] Dirección final desde Nominatim | ticket_id=%s | address=%s",
                ticket.id,
                direccion,
            )
            return {
                'success': True,
                'provider': 'nominatim',
                'address': direccion,
            }

        fallback = "Lat: %.6f, Lng: %.6f" % (lat, lng)

        _logger.warning(
            "[EVIDENCIA GEOCODE] Sin dirección, usando coordenadas | ticket_id=%s | fallback=%s",
            ticket.id,
            fallback,
        )

        return {
            'success': True,
            'provider': 'fallback_coords',
            'address': fallback,
        }

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
        """Recibe la foto marcada en base64 desde el cliente."""
        _logger.info("[EVIDENCIA UPLOAD] Solicitud recibida | token=%s", token)
        _logger.info("[EVIDENCIA UPLOAD] KW keys=%s", list(kw.keys()))

        ticket = self._buscar_ticket_por_token(token)

        if not ticket:
            _logger.warning("[EVIDENCIA UPLOAD] Token inválido | token=%s", token)
            return {
                'success': False,
                'error': 'Token inválido',
            }

        if ticket.estado == 'finalizado':
            _logger.warning(
                "[EVIDENCIA UPLOAD] Ticket finalizado, upload rechazado | ticket_id=%s",
                ticket.id,
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
        direccion = kw.get('direccion') or False

        _logger.info(
            "[EVIDENCIA UPLOAD] Datos | ticket_id=%s | momento=%s | filename=%s | lat=%s | lng=%s | precision=%s | direccion=%s",
            ticket.id,
            momento,
            filename,
            latitud,
            longitud,
            precision,
            direccion,
        )

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
            _logger.info("[EVIDENCIA UPLOAD] Imagen dataURL detectada, separando cabecera")
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
                "[EVIDENCIA UPLOAD] Imagen muy grande | ticket_id=%s | size_mb=%s | max_mb=%s",
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

        try:
            vals = {
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
                list(vals.keys()),
            )

            foto = request.env['ticket.evidencia.foto'].sudo().create(vals)

            _logger.info(
                "[EVIDENCIA UPLOAD] Foto creada OK | foto_id=%s | ticket_id=%s | momento=%s",
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

            if direccion:
                msg += "🗺️ Dirección: %s<br/>" % direccion

            msg += "🖼️ Foto ID: %s" % foto.id

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
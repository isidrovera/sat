# -*- coding: utf-8 -*-
"""Mapa GPS privado de Odoo y enlace público de corta duración.

Nunca entrega las credenciales ni la URL interna de Traccar al navegador.
"""
import logging
import math
from datetime import timedelta

import requests
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class SatGpsTrackingController(http.Controller):

    def _visita_interna(self, visita_id):
        user = request.env.user
        visita = request.env['sat.visita.tecnica'].sudo().browse(visita_id).exists()
        if not visita:
            return None
        gerente = user.has_group('sat.sat_jefes_group_user') or user.has_group('base.group_system')
        participa = user.has_group('sat.sat_tecnica_group_user') and user in visita.participante_ids.mapped('tecnico_id')
        return visita if gerente or participa else None

    def _render_mapa(self, visita, data_url, publico=False, ticket_id=None):
        tiles_url = request.env['ir.config_parameter'].sudo().get_param(
            'sat.gps.tiles_url', 'https://tile.openstreetmap.org/{z}/{x}/{y}.png')
        return request.render('sat.sat_gps_live_map', {
            'visita': visita,
            'data_url': data_url,
            'tiles_url': tiles_url,
            'gps_publico': publico,
            'ticket_id': ticket_id,
        }, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                    'X-Robots-Tag': 'noindex, nofollow'})

    @http.route('/seguimiento/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def seguimiento_cliente(self, token, **kw):
        visita = request.env['sat.visita.tecnica']._gps_buscar_token_valido(token)
        if not visita:
            return request.not_found()
        return self._render_mapa(visita, '/seguimiento/%s/datos' % token, publico=True)

    @http.route('/sat/gps/visita/<int:visita_id>', type='http', auth='user', website=True)
    def mapa_interno(self, visita_id, ticket_id=None, **kw):
        visita = self._visita_interna(visita_id)
        if not visita:
            return request.not_found()
        if ticket_id:
            try:
                ticket = visita.ticket_ids.filtered(lambda t: t.id == int(ticket_id))[:1]
            except (ValueError, TypeError):
                ticket = False
            if not ticket:
                return request.not_found()
        datos_url = '/sat/gps/visita/%s/datos' % visita.id
        if ticket_id:
            datos_url += '?ticket_id=%s' % int(ticket_id)
        return self._render_mapa(visita, datos_url,
                                 ticket_id=int(ticket_id) if ticket_id else None)

    @http.route('/seguimiento/<string:token>/datos', type='http', auth='public', methods=['GET'], csrf=False)
    def datos_cliente(self, token, **kw):
        visita = request.env['sat.visita.tecnica']._gps_buscar_token_valido(token)
        if not visita:
            return request.make_json_response({'error': 'enlace_invalido'}, status=404,
                                              headers={'Cache-Control': 'no-store'})
        return request.make_json_response(self._datos_visita(visita, publico=True),
                                          headers={'Cache-Control': 'no-store'})

    @http.route('/sat/gps/visita/<int:visita_id>/datos', type='http', auth='user', methods=['GET'], csrf=False)
    def datos_internos(self, visita_id, ticket_id=None, **kw):
        visita = self._visita_interna(visita_id)
        if not visita:
            return request.make_json_response({'error': 'sin_acceso'}, status=404)
        filtro = None
        if ticket_id:
            try:
                ticket = visita.ticket_ids.filtered(lambda t: t.id == int(ticket_id))[:1]
            except (ValueError, TypeError):
                ticket = False
            if not ticket:
                return request.make_json_response({'error': 'ticket_invalido'}, status=404)
            filtro = ticket.gps_participante_ids.ids
        return request.make_json_response(self._datos_visita(visita, filtro_ids=filtro),
                                          headers={'Cache-Control': 'no-store'})

    @staticmethod
    def _coordenada(lon, lat):
        try:
            lon, lat = float(lon), float(lat)
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(lon) and math.isfinite(lat)
                and -180 <= lon <= 180 and -90 <= lat <= 90 and (lon or lat)):
            return None
        return [lon, lat]

    def _datos_visita(self, visita, publico=False, filtro_ids=None):
        api = request.env['traccar.api.service'].sudo()
        ahora = fields.Datetime.now()
        try:
            posiciones = api.get_all_positions()
        except Exception:
            _logger.exception('[SAT-MAPA] Error consultando posiciones')
            posiciones = {}
        miembros = visita.participante_ids
        if filtro_ids is not None:
            miembros = miembros.filtered(lambda p: p.id in filtro_ids)
        lista = []
        for p in miembros:
            # Nunca publicar ubicaciones de recorridos cerrados o no iniciados.
            if publico and p.estado not in ('en_ruta', 'en_sitio'):
                continue
            item = {'id': p.id, 'nombre': p.tecnico_id.name,
                    'estado': p.estado, 'ultima_posicion': None,
                    'actualizado': None, 'recorrido': [], 'paradas': []}
            pos = posiciones.get(p.traccar_device_id) if p.traccar_device_id else None
            if (pos and p.estado in ('en_ruta', 'en_sitio')
                    and request.env['ticket.alquiler']._gps_posicion_valida(pos, max_edad_min=5)):
                ultima = self._coordenada(pos.get('longitude'), pos.get('latitude'))
                if ultima:
                    item['ultima_posicion'] = ultima
                    item['actualizado'] = pos.get('fixTime')
            if p.fecha_en_ruta and p.traccar_device_id:
                fin = p.fecha_llegada or ahora
                # El portal jamás permite consultar horas anteriores a este servicio.
                if fin >= p.fecha_en_ruta:
                    self._agregar_reporte(api, p.traccar_device_id, p.fecha_en_ruta,
                                          fin, item, publico)
            lista.append(item)
        return {'visita': visita.name, 'destino': self._coordenada(visita.longitud, visita.latitud),
                'tecnicos': lista, 'actualizado': fields.Datetime.to_string(ahora)}

    def _agregar_reporte(self, api, device_id, inicio, fin, item, publico):
        """Reportes Traccar: la evidencia original NO se reemplaza por map matching."""
        try:
            sesion, cfg = api._get_session()
            parametros = {'deviceId': device_id,
                          'from': inicio.strftime('%Y-%m-%dT%H:%M:%SZ'),
                          'to': fin.strftime('%Y-%m-%dT%H:%M:%SZ')}
            resp = sesion.get('%s/api/reports/route' % cfg['url'], params=parametros,
                              timeout=cfg['timeout'], headers={'Accept': 'application/json'})
            resp.raise_for_status()
            puntos = resp.json()
            if not isinstance(puntos, list):
                return
            # Limitar el volumen de salida; conservar orden temporal.
            if len(puntos) > 3000:
                salto = math.ceil(len(puntos) / 3000)
                puntos = puntos[::salto]
            item['recorrido'] = [c for pos in puntos
                                 if (c := self._coordenada(pos.get('longitude'), pos.get('latitude')))]
            if not publico:
                stops = sesion.get('%s/api/reports/stops' % cfg['url'], params=parametros,
                                   timeout=cfg['timeout'], headers={'Accept': 'application/json'})
                if stops.ok and isinstance(stops.json(), list):
                    item['paradas'] = [
                        {'ubicacion': c, 'duracion_ms': s.get('duration', 0),
                         'inicio': s.get('startTime')}
                        for s in stops.json()
                        if (c := self._coordenada(s.get('longitude'), s.get('latitude')))
                    ][:200]
        except (requests.RequestException, ValueError, TypeError):
            _logger.warning('[SAT-MAPA] No se pudo obtener historial device=%s', device_id)

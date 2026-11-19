
# -*- coding: utf-8 -*-
"""Mapa GPS privado de Odoo y enlace público de corta duración.

Las credenciales y la URL interna de Traccar nunca se entregan
al navegador del cliente.
"""

import logging
import math

import requests

from odoo import http, fields
from odoo.http import request


_logger = logging.getLogger(__name__)


class SatGpsTrackingController(http.Controller):

    def _visita_interna(self, visita_id):
        user = request.env.user

        visita = request.env[
            'sat.visita.tecnica'
        ].sudo().browse(visita_id).exists()

        if not visita:
            return None

        gerente = (
            user.has_group('sat.sat_jefes_group_user')
            or user.has_group('base.group_system')
        )

        participa = (
            user.has_group('sat.sat_tecnica_group_user')
            and user in visita.participante_ids.mapped('tecnico_id')
        )

        return visita if gerente or participa else None

    def _render_mapa(
        self,
        visita,
        data_url,
        publico=False,
        ticket_id=None,
    ):
        tiles_url = request.env[
            'ir.config_parameter'
        ].sudo().get_param(
            'sat.gps.tiles_url',
            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        )

        return request.render(
            'sat.sat_gps_live_map',
            {
                'visita': visita,
                'data_url': data_url,
                'tiles_url': tiles_url,
                'gps_publico': publico,
                'ticket_id': ticket_id,
            },
            headers={
                'Cache-Control': 'no-store',
                'Referrer-Policy': 'no-referrer',
                'X-Robots-Tag': 'noindex, nofollow',
            },
        )

    # ---------------------------------------------------------
    # SEGUIMIENTO PÚBLICO DEL CLIENTE
    # ---------------------------------------------------------

    @http.route(
        '/seguimiento/<string:token>',
        type='http',
        auth='public',
        website=True,
        sitemap=False,
    )
    def seguimiento_cliente(self, token, **kw):
        visita = request.env[
            'sat.visita.tecnica'
        ]._gps_buscar_token_valido(token)

        if not visita:
            return request.not_found()

        return self._render_mapa(
            visita,
            '/seguimiento/%s/datos' % token,
            publico=True,
        )

    # ---------------------------------------------------------
    # MAPA INTERNO
    # ---------------------------------------------------------

    @http.route(
        '/sat/gps/visita/<int:visita_id>',
        type='http',
        auth='user',
        website=True,
    )
    def mapa_interno(self, visita_id, ticket_id=None, **kw):
        visita = self._visita_interna(visita_id)

        if not visita:
            return request.not_found()

        ticket_id_validado = None

        if ticket_id:
            try:
                ticket_id_validado = int(ticket_id)

                ticket = visita.ticket_ids.filtered(
                    lambda t: t.id == ticket_id_validado
                )[:1]

            except (ValueError, TypeError):
                ticket = False

            if not ticket:
                return request.not_found()

        datos_url = (
            '/sat/gps/visita/%s/datos' % visita.id
        )

        if ticket_id_validado:
            datos_url += (
                '?ticket_id=%s' % ticket_id_validado
            )

        return self._render_mapa(
            visita,
            datos_url,
            ticket_id=ticket_id_validado,
        )

    # ---------------------------------------------------------
    # API PÚBLICA
    # ---------------------------------------------------------

    @http.route(
        '/seguimiento/<string:token>/datos',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def datos_cliente(self, token, **kw):
        visita = request.env[
            'sat.visita.tecnica'
        ]._gps_buscar_token_valido(token)

        if not visita:
            return request.make_json_response(
                {'error': 'enlace_invalido'},
                status=404,
                headers={'Cache-Control': 'no-store'},
            )

        return request.make_json_response(
            self._datos_visita(
                visita,
                publico=True,
            ),
            headers={'Cache-Control': 'no-store'},
        )

    # ---------------------------------------------------------
    # API INTERNA
    # ---------------------------------------------------------

    @http.route(
        '/sat/gps/visita/<int:visita_id>/datos',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def datos_internos(
        self,
        visita_id,
        ticket_id=None,
        **kw,
    ):
        visita = self._visita_interna(visita_id)

        if not visita:
            return request.make_json_response(
                {'error': 'sin_acceso'},
                status=404,
            )

        filtro = None

        if ticket_id:
            try:
                ticket = visita.ticket_ids.filtered(
                    lambda t: t.id == int(ticket_id)
                )[:1]

            except (ValueError, TypeError):
                ticket = False

            if not ticket:
                return request.make_json_response(
                    {'error': 'ticket_invalido'},
                    status=404,
                )

            filtro = ticket.gps_participante_ids.ids

        return request.make_json_response(
            self._datos_visita(
                visita,
                filtro_ids=filtro,
            ),
            headers={'Cache-Control': 'no-store'},
        )

    # ---------------------------------------------------------
    # VALIDACIÓN DE COORDENADAS
    # ---------------------------------------------------------

    @staticmethod
    def _coordenada(lon, lat):
        try:
            lon = float(lon)
            lat = float(lat)

        except (TypeError, ValueError):
            return None

        if not (
            math.isfinite(lon)
            and math.isfinite(lat)
            and -180 <= lon <= 180
            and -90 <= lat <= 90
            and (lon or lat)
        ):
            return None

        return [lon, lat]

    # ---------------------------------------------------------
    # DATOS GPS DE LA VISITA
    # ---------------------------------------------------------

    def _datos_visita(
        self,
        visita,
        publico=False,
        filtro_ids=None,
    ):
        api = request.env[
            'traccar.api.service'
        ].sudo()

        ahora = fields.Datetime.now()

        try:
            posiciones = api.get_all_positions()

        except Exception:
            _logger.exception(
                '[SAT-MAPA] Error consultando posiciones'
            )
            posiciones = {}

        miembros = visita.participante_ids

        if filtro_ids is not None:
            miembros = miembros.filtered(
                lambda p: p.id in filtro_ids
            )

        lista = []

        for participante in miembros:

            # No publicar técnicos cuyos recorridos
            # no comenzaron o ya están cerrados.
            if (
                publico
                and participante.estado not in (
                    'en_ruta',
                    'en_sitio',
                )
            ):
                continue

            item = {
                'id': participante.id,
                'nombre': participante.tecnico_id.name,
                'estado': participante.estado,
                'ultima_posicion': None,
                'actualizado': None,
                'gps_en_vivo': False,
                'recorrido': [],
                'paradas': [],
            }

            device_id = participante.traccar_device_id

            # ---------------------------------------------
            # POSICIÓN RECIENTE
            # ---------------------------------------------

            pos = (
                posiciones.get(device_id)
                if device_id
                else None
            )

            if (
                pos
                and participante.estado in (
                    'en_ruta',
                    'en_sitio',
                )
                and request.env[
                    'ticket.alquiler'
                ]._gps_posicion_valida(
                    pos,
                    max_edad_min=5,
                )
            ):
                ultima = self._coordenada(
                    pos.get('longitude'),
                    pos.get('latitude'),
                )

                if ultima:
                    item['ultima_posicion'] = ultima
                    item['actualizado'] = pos.get(
                        'fixTime'
                    )
                    item['gps_en_vivo'] = True

            # ---------------------------------------------
            # HISTORIAL REAL DEL RECORRIDO
            # ---------------------------------------------

            if (
                participante.fecha_en_ruta
                and device_id
            ):
                # El recorrido de traslado termina
                # en la llegada física registrada.
                fin = (
                    participante.fecha_llegada
                    or ahora
                )

                if fin >= participante.fecha_en_ruta:
                    self._agregar_reporte(
                        api,
                        device_id,
                        participante.fecha_en_ruta,
                        fin,
                        item,
                        publico,
                    )

            # ---------------------------------------------
            # CONSERVAR ÚLTIMA UBICACIÓN CONOCIDA
            # ---------------------------------------------

            # Si Traccar dejó de enviar posiciones
            # recientes, utilizamos la última coordenada
            # REAL del historial de esta visita.
            #
            # No se presenta como ubicación en vivo.

            if (
                item['ultima_posicion'] is None
                and item['recorrido']
            ):
                item['ultima_posicion'] = (
                    item['recorrido'][-1]
                )

                item['actualizado'] = item.get(
                    'ultima_fecha_recorrido'
                )

                item['gps_en_vivo'] = False

            # Campo auxiliar: no enviarlo al navegador.
            item.pop(
                'ultima_fecha_recorrido',
                None,
            )

            lista.append(item)

        return {
            'visita': visita.name,
            'cliente': (
                visita.partner_id.name
                or 'Cliente'
            ),
            'destino': self._coordenada(
                visita.longitud,
                visita.latitud,
            ),
            'tecnicos': lista,
            'actualizado': fields.Datetime.to_string(
                ahora
            ),
        }

    # ---------------------------------------------------------
    # CONSULTAR HISTORIAL EN TRACCAR
    # ---------------------------------------------------------

    def _agregar_reporte(
        self,
        api,
        device_id,
        inicio,
        fin,
        item,
        publico,
    ):
        """
        Conserva las coordenadas originales de Traccar.

        No inventa puntos y no modifica el recorrido
        mediante map matching.
        """

        try:
            sesion, cfg = api._get_session()

            parametros = {
                'deviceId': device_id,
                'from': inicio.strftime(
                    '%Y-%m-%dT%H:%M:%SZ'
                ),
                'to': fin.strftime(
                    '%Y-%m-%dT%H:%M:%SZ'
                ),
            }

            resp = sesion.get(
                '%s/api/reports/route' % cfg['url'],
                params=parametros,
                timeout=cfg['timeout'],
                headers={
                    'Accept': 'application/json',
                },
            )

            resp.raise_for_status()

            puntos = resp.json()

            if not isinstance(puntos, list):
                return

            # ---------------------------------------------
            # LIMITAR VOLUMEN SIN PERDER EL ÚLTIMO PUNTO
            # ---------------------------------------------

            if len(puntos) > 3000:
                salto = math.ceil(
                    len(puntos) / 3000
                )

                muestra = puntos[::salto]

                # El último punto debe conservarse
                # aunque no coincida con el salto.
                if muestra[-1] is not puntos[-1]:
                    muestra.append(puntos[-1])

                puntos = muestra

            # ---------------------------------------------
            # COORDENADAS VÁLIDAS
            # ---------------------------------------------

            recorrido = []
            ultima_fecha = None

            for pos in puntos:
                if not isinstance(pos, dict):
                    continue

                coordenada = self._coordenada(
                    pos.get('longitude'),
                    pos.get('latitude'),
                )

                if not coordenada:
                    continue

                recorrido.append(coordenada)

                ultima_fecha = (
                    pos.get('fixTime')
                    or pos.get('deviceTime')
                )

            item['recorrido'] = recorrido

            item['ultima_fecha_recorrido'] = (
                ultima_fecha
            )

            # ---------------------------------------------
            # PARADAS: SOLO PERSONAL INTERNO
            # ---------------------------------------------

            if not publico:
                stops = sesion.get(
                    '%s/api/reports/stops' % cfg['url'],
                    params=parametros,
                    timeout=cfg['timeout'],
                    headers={
                        'Accept': 'application/json',
                    },
                )

                if stops.ok:
                    paradas = stops.json()

                    if isinstance(paradas, list):
                        resultado = []

                        for parada in paradas:
                            if not isinstance(
                                parada,
                                dict,
                            ):
                                continue

                            ubicacion = self._coordenada(
                                parada.get('longitude'),
                                parada.get('latitude'),
                            )

                            if not ubicacion:
                                continue

                            resultado.append({
                                'ubicacion': ubicacion,
                                'duracion_ms': parada.get(
                                    'duration',
                                    0,
                                ),
                                'inicio': parada.get(
                                    'startTime'
                                ),
                            })

                        item['paradas'] = resultado[:200]

        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ):
            _logger.warning(
                '[SAT-MAPA] No se pudo obtener '
                'historial device=%s',
                device_id,
            )

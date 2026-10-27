
# -*- coding: utf-8 -*-
"""
Controlador API: Traccar -> Odoo 19
=================================
Archivo: sat/controllers/traccar_api.py

Responsabilidades:
- Autenticar las solicitudes de Traccar.
- Validar el contenido recibido.
- Conservar la fecha original de los eventos.
- Identificar dispositivo, posición y geocerca.
- Enviar eventos al modelo ticket.alquiler.
- Devolver el resultado real del procesamiento.

Este controlador NO:
- Finaliza tickets.
- Inventa fechas GPS.
- Registra salidas físicas directamente.
- Inicia rutas por movimiento genérico.
- Omite las validaciones del modelo SAT.
"""

import json
import logging
import hmac

from datetime import datetime

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class TraccarController(http.Controller):

    EVENTOS_PERMITIDOS = frozenset({
        'geofenceEnter',
        'geofenceExit',
        'deviceMoving',
    })

    MAX_BODY_BYTES = 128 * 1024

    # ==========================================================
    # AUTENTICACIÓN
    # ==========================================================

    def _validar_authorization(self):
        """
        Valida Bearer Token contra traccar.api_key.

        No registra el token recibido ni el configurado.
        """
        auth_header = (
            request.httprequest.headers.get(
                'Authorization', ''
            ) or ''
        ).strip()

        partes = auth_header.split()

        if len(partes) != 2:
            _logger.warning(
                "[TRACCAR-AUTH] Authorization ausente "
                "o formato incorrecto"
            )
            return False

        esquema, token_recibido = partes

        if esquema.lower() != 'bearer':
            _logger.warning(
                "[TRACCAR-AUTH] Esquema no permitido"
            )
            return False

        token_configurado = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('traccar.api_key', default='')
        )

        token_configurado = (
            token_configurado or ''
        ).strip()

        if not token_configurado:
            _logger.error(
                "[TRACCAR-AUTH] Falta configurar "
                "traccar.api_key"
            )
            return False

        if not hmac.compare_digest(
            token_recibido.encode('utf-8'),
            token_configurado.encode('utf-8'),
        ):
            _logger.warning(
                "[TRACCAR-AUTH] Credencial no válida"
            )
            return False

        return True

    # ==========================================================
    # RESPUESTAS JSON
    # ==========================================================

    @staticmethod
    def _json_response(data, status=200):
        respuesta = Response(
            json.dumps(
                data,
                ensure_ascii=False,
                default=str,
            ),
            status=status,
            content_type='application/json; charset=utf-8',
        )

        respuesta.headers['Cache-Control'] = 'no-store'
        respuesta.headers['X-Content-Type-Options'] = 'nosniff'

        return respuesta

    # ==========================================================
    # VALIDACIONES GENERALES
    # ==========================================================

    @staticmethod
    def _entero_positivo(valor):
        """
        Devuelve un identificador positivo o None.
        No convierte booleanos en identificadores.
        """
        if isinstance(valor, bool):
            return None

        try:
            numero = int(valor)
        except (TypeError, ValueError, OverflowError):
            return None

        return numero if numero > 0 else None

    @staticmethod
    def _coordenada(valor, minimo, maximo):
        if isinstance(valor, bool):
            return None

        try:
            numero = float(valor)
        except (TypeError, ValueError, OverflowError):
            return None

        import math

        if not math.isfinite(numero):
            return None

        if not minimo <= numero <= maximo:
            return None

        return numero

    @staticmethod
    def _validar_fecha_evento(valor):
        """
        Requiere un instante con zona horaria explícita.

        No reemplaza event.time con:
        - Fecha de recepción de Odoo.
        - Hora actual.
        - position.fixTime.
        - position.serverTime.
        """
        if not isinstance(valor, str) or not valor.strip():
            return False

        try:
            fecha = datetime.fromisoformat(
                valor.strip().replace('Z', '+00:00')
            )
        except (ValueError, TypeError):
            return False

        if fecha.tzinfo is None:
            return False

        return True

    # ==========================================================
    # EXTRACCIÓN DE DATOS
    # ==========================================================

    def _extraer_datos(self, body):
        """
        Conserva las referencias originales de Traccar
        sin inventar campos ausentes.
        """
        event = body.get('event') or {}
        device = body.get('device') or {}
        position = body.get('position') or {}
        geofence = body.get('geofence') or {}

        for nombre, bloque in (
            ('event', event),
            ('device', device),
            ('position', position),
            ('geofence', geofence),
        ):
            if not isinstance(bloque, dict):
                raise ValueError(
                    "El bloque '%s' debe ser un objeto JSON"
                    % nombre
                )

        tipo = event.get('type')

        device_id = self._entero_positivo(
            device.get('id') or event.get('deviceId')
        )

        geofence_id = self._entero_positivo(
            geofence.get('id') or event.get('geofenceId')
        )

        event_id = self._entero_positivo(
            event.get('id')
        )

        position_id = self._entero_positivo(
            position.get('id') or event.get('positionId')
        )

        # La fecha real de un evento se obtiene
        # exclusivamente del objeto event.
        event_time = event.get('eventTime')

        if not event_time:
            event_time = event.get('time')

        latitude = self._coordenada(
            position.get('latitude'), -90, 90
        )

        longitude = self._coordenada(
            position.get('longitude'), -180, 180
        )

        atributos = position.get('attributes') or {}

        if not isinstance(atributos, dict):
            atributos = {}

        datos = {
            'eventId': event_id,
            'eventTime': event_time,
            'positionId': position_id,
            'geofenceId': geofence_id,
            'latitude': latitude,
            'longitude': longitude,
            'speed': position.get('speed'),
            'address': position.get('address'),
            'accuracy': position.get(
                'accuracy',
                atributos.get('accuracy'),
            ),
            'valid': position.get('valid'),
            'fixTime': position.get('fixTime'),
            'deviceTime': position.get('deviceTime'),
            'serverTime': position.get('serverTime'),
        }

        return {
            'tipo': tipo,
            'device_id': device_id,
            'device_name': device.get('name'),
            'datos': datos,
        }

    # ==========================================================
    # WEBHOOK PRINCIPAL
    # ==========================================================

    @http.route(
        '/api/traccar/evento',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def recibir_evento_traccar(self, **kwargs):
        """
        Punto de entrada de eventos Traccar.

        Mantiene la ruta existente.

        auth='public' permite utilizar request.env
        con la base de datos seleccionada.

        La autorización funcional sigue dependiendo
        del Bearer Token validado a continuación.
        """

        # ------------------------------------------------------
        # 1. AUTENTICAR ANTES DE PROCESAR
        # ------------------------------------------------------

        if not self._validar_authorization():
            return self._json_response({
                'success': False,
                'error': 'No autorizado',
            }, status=401)

        # ------------------------------------------------------
        # 2. COMPROBAR TAMAÑO
        # ------------------------------------------------------

        raw_body = request.httprequest.get_data(
            cache=True
        )

        if len(raw_body) > self.MAX_BODY_BYTES:
            return self._json_response({
                'success': False,
                'error': 'Contenido demasiado grande',
            }, status=413)

        if not raw_body:
            return self._json_response({
                'success': False,
                'error': 'Cuerpo vacío',
            }, status=400)

        # ------------------------------------------------------
        # 3. DECODIFICAR JSON
        # ------------------------------------------------------

        try:
            body = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError):
            _logger.warning(
                "[TRACCAR] JSON inválido"
            )
            return self._json_response({
                'success': False,
                'error': 'JSON inválido',
            }, status=400)

        if not isinstance(body, dict):
            return self._json_response({
                'success': False,
                'error': 'Se requiere un objeto JSON',
            }, status=400)

        # ------------------------------------------------------
        # 4. EXTRAER DATOS
        # ------------------------------------------------------

        try:
            paquete = self._extraer_datos(body)
        except ValueError as exc:
            return self._json_response({
                'success': False,
                'error': str(exc),
            }, status=400)

        evento_tipo = paquete['tipo']
        device_id = paquete['device_id']
        datos = paquete['datos']

        # ------------------------------------------------------
        # 5. EVENTOS ADMITIDOS
        # ------------------------------------------------------

        if evento_tipo not in self.EVENTOS_PERMITIDOS:
            _logger.info(
                "[TRACCAR] Evento ignorado: %s",
                evento_tipo,
            )

            return self._json_response({
                'success': True,
                'ignored': True,
                'event': evento_tipo,
                'tickets': [],
            })

        # ------------------------------------------------------
        # 6. IDENTIFICACIÓN DE DISPOSITIVO
        # ------------------------------------------------------

        if not device_id:
            _logger.warning(
                "[TRACCAR] Evento %s sin deviceId",
                evento_tipo,
            )

            return self._json_response({
                'success': False,
                'error': 'Dispositivo no identificado',
            }, status=422)

        # ------------------------------------------------------
        # 7. VALIDACIONES DE GEOCERCA
        # ------------------------------------------------------

        if evento_tipo in (
            'geofenceEnter',
            'geofenceExit',
        ):
            if not datos['geofenceId']:
                _logger.warning(
                    "[TRACCAR] %s sin geofenceId "
                    "device=%s",
                    evento_tipo,
                    device_id,
                )

                return self._json_response({
                    'success': False,
                    'error': 'Geocerca no identificada',
                }, status=422)

            if not self._validar_fecha_evento(
                datos['eventTime']
            ):
                _logger.warning(
                    "[TRACCAR] %s sin fecha original "
                    "válida, device=%s",
                    evento_tipo,
                    device_id,
                )

                return self._json_response({
                    'success': False,
                    'error': (
                        'Fecha original del evento '
                        'ausente o inválida'
                    ),
                }, status=422)

        # ------------------------------------------------------
        # 8. REGISTRO TÉCNICO DEL EVENTO
        # ------------------------------------------------------

        _logger.info(
            "[TRACCAR] Recibido tipo=%s "
            "device=%s eventId=%s "
            "positionId=%s geofenceId=%s "
            "eventTime=%s",
            evento_tipo,
            device_id,
            datos['eventId'],
            datos['positionId'],
            datos['geofenceId'],
            datos['eventTime'],
        )

        # ------------------------------------------------------
        # 9. ENVIAR AL MODELO SAT EXISTENTE
        # ------------------------------------------------------

        try:
            resultado = (
                request.env['ticket.alquiler']
                .sudo()
                .api_actualizar_estado_gps(
                    device_id,
                    evento_tipo,
                    datos,
                )
            )

        except Exception:
            _logger.exception(
                "[TRACCAR] Error procesando evento "
                "tipo=%s device=%s eventId=%s",
                evento_tipo,
                device_id,
                datos['eventId'],
            )

            return self._json_response({
                'success': False,
                'error': 'Error interno procesando GPS',
            }, status=500)

        # ------------------------------------------------------
        # 10. VALIDAR RESULTADO DEL MODELO
        # ------------------------------------------------------

        if not isinstance(resultado, dict):
            _logger.error(
                "[TRACCAR] Respuesta inesperada "
                "tipo=%s device=%s",
                evento_tipo,
                device_id,
            )

            return self._json_response({
                'success': False,
                'error': 'Respuesta no válida del modelo',
            }, status=500)

        if resultado.get('success') is not True:
            _logger.warning(
                "[TRACCAR] Modelo rechazó evento "
                "tipo=%s device=%s eventId=%s",
                evento_tipo,
                device_id,
                datos['eventId'],
            )

            return self._json_response({
                'success': False,
                'error': resultado.get(
                    'error',
                    'Evento no procesado',
                ),
                'tickets': [],
            }, status=422)

        # ------------------------------------------------------
        # 11. RESPUESTA CORRECTA
        # ------------------------------------------------------

        tickets = resultado.get(
            'tickets_actualizados', []
        )

        if not isinstance(tickets, list):
            tickets = []

        _logger.info(
            "[TRACCAR] Evento procesado "
            "tipo=%s device=%s eventId=%s "
            "tickets=%s",
            evento_tipo,
            device_id,
            datos['eventId'],
            len(tickets),
        )

        return self._json_response({
            'success': True,
            'event': evento_tipo,
            'deviceId': device_id,
            'eventId': datos['eventId'],
            'positionId': datos['positionId'],
            'geofenceId': datos['geofenceId'],
            'tickets': tickets,
        })

# -*- coding: utf-8 -*-
"""
Fase 1 — Controlador API para integración Traccar/Bot → Odoo
=============================================================
Endpoints REST para que el bot (o cualquier sistema externo)
pueda actualizar el estado de los tickets basado en eventos GPS.

Archivo: controllers/traccar_api.py
Módulo: sat (o donde tengas ticket.alquiler)

Seguridad: API Key compartida (configurada en Odoo como parámetro del sistema)
           Parámetro: traccar.api_key
"""
import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class TraccarWebhookController(http.Controller):
    """
    Controlador que recibe eventos desde el bot de WhatsApp.
    El flujo es: Traccar → event.forward → Bot → (procesa) → este endpoint → Odoo
    """

    def _validar_api_key(self):
        """
        Valida el API key enviado en el header x-api-key.
        La key se configura en Odoo: Ajustes > Técnico > Parámetros del sistema
        Clave: traccar.api_key
        """
        api_key_recibida = request.httprequest.headers.get('x-api-key', '')
        api_key_config = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('traccar.api_key', default='')
        )

        if not api_key_config:
            _logger.error("[TRACCAR-API] traccar.api_key no configurada en parámetros del sistema")
            return False

        return api_key_recibida == api_key_config

    def _json_response(self, data, status=200):
        """Helper para respuestas JSON."""
        return Response(
            json.dumps(data, ensure_ascii=False, default=str),
            status=status,
            content_type='application/json',
        )

    # ═══════════════════════════════════════════════════════════════
    #  POST /api/traccar/evento
    #  Recibe un evento GPS procesado por el bot
    # ═══════════════════════════════════════════════════════════════

    @http.route(
        '/api/traccar/evento',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def recibir_evento_gps(self, **kwargs):
        """
        Recibe evento GPS del bot y actualiza tickets correspondientes.

        Body esperado (JSON):
        {
            "device_id": 123,              // ID del dispositivo en Traccar
            "event_type": "geofenceEnter",  // Tipo de evento Traccar
            "data": {                       // Datos adicionales
                "latitude": -12.046,
                "longitude": -77.042,
                "speed": 0,
                "address": "Av. Javier Prado ...",
                "geofenceId": 456,
                "deviceName": "Celular-Juan"
            }
        }

        Respuesta:
        {
            "success": true,
            "tecnico": "Juan Pérez",
            "evento": "geofenceEnter",
            "tickets_actualizados": [
                {"id": 1, "name": "TK-0001", "estado": "en_sitio"}
            ]
        }
        """
        if not self._validar_api_key():
            return {'success': False, 'error': 'API key inválida'}

        try:
            params = request.jsonrequest
            device_id = params.get('device_id')
            event_type = params.get('event_type')
            data = params.get('data', {})

            if not device_id or not event_type:
                return {
                    'success': False,
                    'error': 'device_id y event_type son requeridos',
                }

            _logger.info(
                "[TRACCAR-API] Evento: device=%s tipo=%s",
                device_id, event_type,
            )

            resultado = (
                request.env['ticket.alquiler']
                .sudo()
                .api_actualizar_estado_gps(device_id, event_type, data)
            )

            return resultado

        except Exception as e:
            _logger.exception("[TRACCAR-API] Error procesando evento")
            return {'success': False, 'error': str(e)}

    # ═══════════════════════════════════════════════════════════════
    #  POST /api/traccar/estado-manual
    #  Permite al técnico cambiar estado manualmente (desde app/WA)
    # ═══════════════════════════════════════════════════════════════

    @http.route(
        '/api/traccar/estado-manual',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def cambio_estado_manual(self, **kwargs):
        """
        Permite cambio de estado manual desde el bot de WhatsApp.
        Ejemplo: técnico escribe "llegué" o presiona un botón.

        Body esperado:
        {
            "ticket_name": "TK-0001",    // O "ticket_id": 123
            "nuevo_estado": "en_sitio",   // en_ruta, en_sitio, en_revision
            "telefono_tecnico": "51987654321"  // Para identificar al técnico
        }
        """
        if not self._validar_api_key():
            return {'success': False, 'error': 'API key inválida'}

        try:
            params = request.jsonrequest
            ticket_name = params.get('ticket_name')
            ticket_id = params.get('ticket_id')
            nuevo_estado = params.get('nuevo_estado')
            telefono = params.get('telefono_tecnico')

            # Buscar ticket
            domain = []
            if ticket_id:
                domain = [('id', '=', ticket_id)]
            elif ticket_name:
                domain = [('name', '=', ticket_name)]
            else:
                return {'success': False, 'error': 'Debe indicar ticket_name o ticket_id'}

            ticket = request.env['ticket.alquiler'].sudo().search(domain, limit=1)
            if not ticket:
                return {'success': False, 'error': 'Ticket no encontrado'}

            # Ejecutar acción según estado solicitado
            acciones = {
                'en_ruta': ticket.action_en_ruta,
                'en_sitio': ticket.action_en_sitio,
                'en_revision': ticket.action_en_revision,
            }

            accion = acciones.get(nuevo_estado)
            if not accion:
                return {
                    'success': False,
                    'error': f'Estado no válido: {nuevo_estado}. Opciones: en_ruta, en_sitio, en_revision',
                }

            accion()

            return {
                'success': True,
                'ticket': ticket.name,
                'estado': ticket.estado,
                'message': f'Ticket {ticket.name} actualizado a {ticket.estado}',
            }

        except Exception as e:
            _logger.exception("[TRACCAR-API] Error en cambio manual")
            return {'success': False, 'error': str(e)}

    # ═══════════════════════════════════════════════════════════════
    #  GET /api/traccar/tickets-tecnico
    #  Consulta tickets activos de un técnico (para el bot)
    # ═══════════════════════════════════════════════════════════════

    @http.route(
        '/api/traccar/tickets-tecnico',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def tickets_tecnico(self, **kwargs):
        """
        Retorna los tickets activos de un técnico.
        Útil para que el bot muestre al técnico su agenda del día.

        Body esperado:
        {
            "device_id": 123,          // ID dispositivo Traccar
            // O alternativamente:
            "telefono": "51987654321"   // Teléfono del técnico
        }
        """
        if not self._validar_api_key():
            return {'success': False, 'error': 'API key inválida'}

        try:
            params = request.jsonrequest
            device_id = params.get('device_id')
            telefono = params.get('telefono')

            tecnico = None

            if device_id:
                vinculo = (
                    request.env['tecnico.dispositivo.gps']
                    .sudo()
                    .search([
                        ('traccar_device_id', '=', device_id),
                        ('activo', '=', True),
                    ], limit=1)
                )
                if vinculo:
                    tecnico = vinculo.user_id

            if not tecnico and telefono:
                # Buscar por teléfono del técnico
                partner = request.env['res.partner'].sudo().search([
                    '|',
                    ('mobile', 'like', telefono[-9:]),
                    ('phone', 'like', telefono[-9:]),
                ], limit=1)
                if partner:
                    user = request.env['res.users'].sudo().search([
                        ('partner_id', '=', partner.id),
                    ], limit=1)
                    tecnico = user

            if not tecnico:
                return {'success': False, 'error': 'Técnico no encontrado'}

            # Buscar tickets activos del día
            from datetime import datetime, timedelta
            hoy_inicio = datetime.now().replace(hour=0, minute=0, second=0)
            hoy_fin = hoy_inicio + timedelta(days=1)

            tickets = (
                request.env['ticket.alquiler']
                .sudo()
                .search([
                    ('responsable', '=', tecnico.id),
                    ('estado', 'in', [
                        'proceso', 'en_ruta', 'en_sitio', 'en_revision',
                    ]),
                    ('agenda', '>=', hoy_inicio),
                    ('agenda', '<', hoy_fin),
                ], order='agenda asc')
            )

            tickets_data = []
            for t in tickets:
                tickets_data.append({
                    'id': t.id,
                    'name': t.name,
                    'estado': t.estado,
                    'cliente': t.partner_id.name or 'N/A',
                    'direccion': t.direccion_id_r or 'N/A',
                    'hora_agenda': t.agenda.strftime('%H:%M') if t.agenda else 'N/A',
                    'equipo': t.modelo_id_r or 'N/A',
                    'serie': t.serie_id_r or 'N/A',
                    'tipo_servicio': t.tipo_servicio_id or 'N/A',
                    'latitud': t.equipo_latitud,
                    'longitud': t.equipo_longitud,
                    'google_maps_url': t.google_maps_url or '',
                    'google_maps_nav_url': t.google_maps_nav_url or '',
                })

            return {
                'success': True,
                'tecnico': tecnico.name,
                'total_tickets': len(tickets),
                'tickets': tickets_data,
            }

        except Exception as e:
            _logger.exception("[TRACCAR-API] Error consultando tickets")
            return {'success': False, 'error': str(e)}

    # ═══════════════════════════════════════════════════════════════
    #  GET /api/traccar/resumen-ticket
    #  Obtiene resumen de tracking de un ticket
    # ═══════════════════════════════════════════════════════════════

    @http.route(
        '/api/traccar/resumen-ticket',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def resumen_ticket(self, **kwargs):
        """
        Retorna el resumen de tracking formateado para WhatsApp.

        Body: {"ticket_name": "TK-0001"} o {"ticket_id": 123}
        """
        if not self._validar_api_key():
            return {'success': False, 'error': 'API key inválida'}

        try:
            params = request.jsonrequest
            ticket_name = params.get('ticket_name')
            ticket_id = params.get('ticket_id')

            domain = []
            if ticket_id:
                domain = [('id', '=', ticket_id)]
            elif ticket_name:
                domain = [('name', '=', ticket_name)]
            else:
                return {'success': False, 'error': 'Debe indicar ticket_name o ticket_id'}

            ticket = request.env['ticket.alquiler'].sudo().search(domain, limit=1)
            if not ticket:
                return {'success': False, 'error': 'Ticket no encontrado'}

            return {
                'success': True,
                'resumen': ticket.get_tracking_summary(),
                'datos': {
                    'id': ticket.id,
                    'name': ticket.name,
                    'estado': ticket.estado,
                    'tecnico': ticket.responsable.name or 'N/A',
                    'cliente': ticket.partner_id.name or 'N/A',
                    'tiempo_traslado': ticket.tiempo_traslado_minutos,
                    'tiempo_en_sitio': ticket.tiempo_en_sitio_minutos,
                    'tiempo_total': ticket.tiempo_total_atencion_minutos,
                    'es_puntual': ticket.es_puntual,
                    'puntualidad_minutos': ticket.diferencia_puntualidad_minutos,
                },
            }

        except Exception as e:
            _logger.exception("[TRACCAR-API] Error obteniendo resumen")
            return {'success': False, 'error': str(e)}
# controllers/main.py

from odoo import http, fields
from odoo.http import request
import logging
import json

_logger = logging.getLogger(__name__)

class ContadorAPI(http.Controller):

    @http.route('/api/actualizar_contador', type='http', auth='public', methods=['POST'], csrf=False)
    def actualizar_contador(self, **kwargs):
        """
        Endpoint público protegido por token para actualizar contadores de una máquina en alquiler.
        """
        
        # Leer el JSON del cuerpo de la petición
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception as e:
            _logger.error(f"❌ Error al parsear JSON: {e}")
            return request.make_response(
                json.dumps({"error": "JSON inválido"}),
                headers={'Content-Type': 'application/json'},
                status=400
            )

        token = data.get('token')
        serie = data.get('serie')

        if not token:
            _logger.warning("❌ Token no proporcionado")
            return request.make_response(
                json.dumps({"error": "Token requerido"}),
                headers={'Content-Type': 'application/json'},
                status=401
            )

        # Validar token dinámico desde parámetros del sistema
        try:
            token_valido = request.env['ir.config_parameter'].sudo().get_param('api.contador.token')
            if not token_valido:
                _logger.error("❌ Token no configurado en parámetros del sistema")
                return request.make_response(
                    json.dumps({"error": "Configuración de token no encontrada"}),
                    headers={'Content-Type': 'application/json'},
                    status=500
                )
                
            if token != token_valido:
                _logger.warning("❌ Token inválido recibido")
                return request.make_response(
                    json.dumps({"error": "Token inválido"}),
                    headers={'Content-Type': 'application/json'},
                    status=401
                )
        except Exception as e:
            _logger.error(f"❌ Error al validar token: {e}")
            return request.make_response(
                json.dumps({"error": "Error en validación de token"}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

        if not serie:
            return request.make_response(
                json.dumps({"error": "Falta el número de serie"}),
                headers={'Content-Type': 'application/json'},
                status=400
            )

        # Buscar el equipo en alquiler por número de serie
        try:
            equipo = request.env['alquiler'].sudo().search([('serie', '=', serie)], limit=1)
        except Exception as e:
            _logger.error(f"❌ Error al buscar equipo: {e}")
            return request.make_response(
                json.dumps({"error": "Error al buscar equipo"}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

        if not equipo:
            _logger.warning(f"❌ No se encontró equipo con serie: {serie}")
            return request.make_response(
                json.dumps({"error": f"No se encontró ningún equipo con la serie '{serie}'"}),
                headers={'Content-Type': 'application/json'},
                status=404
            )

        # Obtener los contadores
        contador_bn = data.get('contador_bn')
        contador_color = data.get('contador_color')
        contador_scan = data.get('contador_scan')

        valores = {}
        
        # Validar y convertir contadores
        try:
            if contador_bn is not None:
                valores['contador_bn'] = int(contador_bn)
            if contador_color is not None:
                valores['contador_color'] = int(contador_color)
            if contador_scan is not None:
                valores['contador_scan'] = int(contador_scan)
        except (ValueError, TypeError) as e:
            _logger.error(f"❌ Error al convertir contadores: {e}")
            return request.make_response(
                json.dumps({"error": "Los valores de contador deben ser números enteros"}),
                headers={'Content-Type': 'application/json'},
                status=400
            )

        if not valores:
            return request.make_response(
                json.dumps({"error": "No se proporcionaron valores de contador válidos"}),
                headers={'Content-Type': 'application/json'},
                status=400
            )

        # Agregar fecha de actualización
        valores['fecha_ultima_actualizacion'] = fields.Datetime.now()

        # Actualizar el equipo
        try:
            equipo.sudo().write(valores)
            _logger.info(f"✅ Contadores actualizados para equipo con serie {serie}: {valores}")
        except Exception as e:
            _logger.error(f"❌ Error al actualizar equipo: {e}")
            return request.make_response(
                json.dumps({"error": "Error interno al actualizar los contadores"}),
                headers={'Content-Type': 'application/json'},
                status=500
            )

        # Preparar respuesta exitosa
        fecha_actualizacion = valores.pop('fecha_ultima_actualizacion')
        
        return request.make_response(
            json.dumps({
                "status": "success",
                "message": "Contadores actualizados correctamente",
                "serie": serie,
                "valores_actualizados": valores,
                "fecha_actualizacion": fecha_actualizacion.isoformat()
            }),
            headers={'Content-Type': 'application/json'},
            status=200
        )

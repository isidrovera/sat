# controllers/main.py

from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class ContadorAPI(http.Controller):

    @http.route('/api/actualizar_contador', type='json', auth='public', methods=['POST'], csrf=False)
    def actualizar_contador(self, **kwargs):
        """
        Endpoint público protegido por token para actualizar contadores de una máquina en alquiler.
        """
        TOKEN_ESPERADO = "mi-token-seguro"

        token = kwargs.get('token')
        serie = kwargs.get('serie')

        if token != TOKEN_ESPERADO:
            _logger.warning("❌ Token inválido recibido")
            return {"error": "Token inválido"}

        if not serie:
            return {"error": "Falta el número de serie"}

        # Buscar el equipo en alquiler por número de serie
        equipo = request.env['alquiler'].sudo().search([('serie', '=', serie)], limit=1)

        if not equipo:
            _logger.warning(f"❌ No se encontró equipo con serie: {serie}")
            return {"error": f"No se encontró ningún equipo con la serie '{serie}'"}

        # Obtener los contadores (pueden ser nulos, se ignoran si no se envían)
        contador_bn = kwargs.get('contador_bn')
        contador_color = kwargs.get('contador_color')
        contador_scan = kwargs.get('contador_scan')

        valores = {}
        if contador_bn is not None:
            valores['contador_bn'] = int(contador_bn)
        if contador_color is not None:
            valores['contador_color'] = int(contador_color)
        if contador_scan is not None:
            valores['contador_scan'] = int(contador_scan)

        if not valores:
            return {"error": "No se proporcionaron valores de contador válidos"}

        valores['fecha_ultima_actualizacion'] = fields.Datetime.now()

        equipo.sudo().write(valores)

        _logger.info(f"✅ Contadores actualizados para equipo con serie {serie}: {valores}")

        return {
            "status": "ok",
            "serie": serie,
            "valores_actualizados": valores
        }

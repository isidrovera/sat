from odoo import http
from odoo.http import request
import json

class ControladorGraficos(http.Controller):
    @http.route('/configurar_grafico', type='json', auth='user', methods=['POST'])
    def configurar_grafico(self, modelo, fecha_inicio=None, fecha_fin=None, campos=None):
        # Guardar configuración en la sesión para simplificar
        request.session['config_grafico'] = {
            'modelo': modelo,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'campos': campos
        }
        return {"estado": "Configuración guardada"}

    @http.route('/obtener_datos_grafico', type='json', auth='user')
    def obtener_datos_grafico(self):
        config = request.session.get('config_grafico')
        if not config:
            return {"error": "No se encontró configuración"}

        modelo = request.env[config['modelo']]
        dominio = []
        if config['fecha_inicio']:
            dominio.append(('create_date', '>=', config['fecha_inicio']))
        if config['fecha_fin']:
            dominio.append(('create_date', '<=', config['fecha_fin']))
        
        registros = modelo.search(dominio)
        etiquetas = [reg.display_name for reg in registros]
        datos = [getattr(reg, config['campos'][0], 0) for reg in registros]  # Asumiendo un solo campo

        return {
            'labels': etiquetas,
            'datasets': [{
                'label': config['modelo'],
                'data': datos
            }]
        }

from odoo import http
from odoo.http import request
import werkzeug

class InspeccionController(http.Controller):

    @http.route(['/inspeccion/<string:token>'], type='http', auth='public', website=True)
    def formulario_inspeccion(self, token):
        alquiler = request.env['alquiler'].sudo().search([('token', '=', token)], limit=1)
        if not alquiler:
            return request.not_found()

        values = {
            'alquiler': alquiler,
            'page_name': 'Formulario de Inspección',
            'tipos_control': [
                ('usuario', 'Por Usuario'),
                ('departamento', 'Por Departamento'),
                ('proyecto', 'Por Proyecto')
            ],
            'frecuencias_reporte': [
                ('diario', 'Diario'),
                ('semanal', 'Semanal'),
                ('mensual', 'Mensual')
            ]
        }
        return request.render('sat.formulario_inspeccion_template', values)

    @http.route(['/inspeccion/submit'], type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def submit_inspeccion(self, **post):
        alquiler = request.env['alquiler'].sudo().search([('token', '=', post.get('token'))], limit=1)
        if not alquiler:
            return request.not_found()
        
        vals = {
            'alquiler_id': alquiler.id,
            'punto_corriente': post.get('punto_corriente'),
            'voltaje': float(post.get('voltaje', 0)),
            'punto_red': post.get('punto_red'),
            'wifi': post.get('wifi'),
            'area_sistemas': post.get('area_sistemas') == 'on',  # Checkbox enviado como "on"
            'contacto_sistemas': post.get('contacto_sistemas'),
            
            # Control de Impresión
            'control_impresion': post.get('control_impresion') == 'on',
            'tipo_control': post.get('tipo_control'),
            'cantidad_usuarios': int(post.get('cantidad_usuarios', 0)),
            'requiere_reportes': post.get('requiere_reportes') == 'on',
            'frecuencia_reportes': post.get('frecuencia_reportes'),
            
            # Entorno de PCs
            'cantidad_windows': int(post.get('cantidad_windows', 0)),
            'cantidad_mac': int(post.get('cantidad_mac', 0)),
            'cantidad_linux': int(post.get('cantidad_linux', 0)),
            
            # Configuración de Escaneo
            'usar_smb': post.get('usar_smb') == 'on',
            'usar_ftp': post.get('usar_ftp') == 'on',
            'usar_email': post.get('usar_email') == 'on',
            'tipo_servidor_email': post.get('tipo_servidor_email'),
            'servidor_email_propio': post.get('servidor_email_propio'),
            
            # Espacio Físico y Acceso
            'piso': int(post.get('piso', 0)),
            'ascensor': post.get('ascensor') == 'on',
            'espacio': float(post.get('espacio', 0)),
            'ancho_pasillo': float(post.get('ancho_pasillo', 0)),
            'tiene_estacionamiento': post.get('tiene_estacionamiento') == 'on',
            'observaciones_estacionamiento': post.get('observaciones_estacionamiento'),
            
            'observaciones': post.get('observaciones')
        }

                
        # Si ya existe una inspección anterior, actualizamos
        inspeccion_existente = request.env['inspeccion.resultado'].sudo().search([
            ('alquiler_id', '=', alquiler.id)
        ], limit=1)
        
        if inspeccion_existente:
            inspeccion_existente.write(vals)
        else:
            request.env['inspeccion.resultado'].sudo().create(vals)
        
        return werkzeug.utils.redirect('/inspeccion/gracias')

    @http.route(['/inspeccion/gracias'], type='http', auth='public', website=True)
    def gracias_inspeccion(self):
        return request.render('sat.gracias_inspeccion_template')





class CopierPartsController(http.Controller):
    
    @http.route('/parts/approve/<string:token>', type='http', auth='public')
    def approve_request(self, token):
        parts_request = request.env['copier.parts.request'].sudo().search([('access_token', '=', token)], limit=1)
        if parts_request and parts_request.state == 'draft':
            parts_request.action_approve()
            return request.render('sat.approval_success_template', {})
        return request.render('sat.invalid_request_template', {})

    @http.route('/parts/deliver/<string:token>', type='http', auth='public')
    def deliver_parts(self, token):
        parts_request = request.env['copier.parts.request'].sudo().search([('access_token', '=', token)], limit=1)
        if parts_request and parts_request.state == 'approved':
            parts_request.action_deliver()
            return request.render('sat.delivery_success_template', {})
        return request.render('sat.invalid_request_template', {})
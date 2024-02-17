from odoo import http
from odoo.http import request
import json
import logging
from datetime import date


class AlquilerQRController(http.Controller):
    @http.route('/api/escanear_qr', auth='public', type='http', methods=['GET'], website=True)
    def escanear_qr(self, id_registro=None):
        if not id_registro:
            return request.redirect('/pagina_error')
        
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        if not registro:
            return request.redirect('/pagina_error')

        # Aquí se podrían agregar más datos según sea necesario
        datos_registro = {
            'id': registro.id,
            'modelo_maquina': registro.name.name,
            'serie': registro.serie,
            'cliente': registro.cliente_id.name,
        }
        
        # Redirigir a la página con opciones, pasando los datos_registro como contexto
        return request.render('sat.pagina_con_opciones', {'datos_registro': datos_registro})
    


class PublicTicketController(http.Controller):
    # Ruta GET para mostrar el formulario
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['GET'], website=True)
    def display_reportar_incidencia(self, **kw):
        # Suponiendo que obtienes el ID del registro a través de la URL
        id_registro = kw.get('id_registro')
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        values = {
            'partner_id': registro.cliente_id.id if registro.cliente_id else '',
            'direccion': registro.direccion if registro.direccion else '',
            'contacto_id': registro.contacto_id if registro.contacto_id else '',
            'celular': registro.celular if registro.celular else '',
            'correo': registro.correo_ if registro.correo_ else '',
            'product_id': registro.id,
            # Otros campos que necesitas pasar al formulario
        }
        return request.render('sat.reportar_incidencia_form', values)
    @http.route('/pagina_confirmacion', type='http', auth="public", website=True)
    def pagina_confirmacion(self, **kw):
        return request.render('sat.pagina_confirmacion')

    # Ruta POST para procesar el formulario
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['POST'], website=True)
    def submit_reportar_incidencia(self, **post):
        try:
            ticket_vals = {
                'partner_id': int(post.get('partner_id')),
                'direccion_id_r': post.get('direccion'),
                'contacto_id_r': post.get('contacto_id'),
                'celular_id_r': post.get('celular'),
                'corre_id_r': post.get('correo'),
                'product_alquiler': int(post.get('product_id')),
                'description': post.get('description'),
                'reporter_name': post.get('reporter_name'),
                'reporter_phone': post.get('reporter_phone'),
                'problem_photo': post.get('problem_photo'),
            }
            # Crear el ticket
            request.env['ticket.alquiler'].sudo().create(ticket_vals)
            return request.redirect('/pagina_confirmacion')
        except Exception as e:
            # Log the error and redirect to an error page
            _logger.exception("Failed to create ticket: %s", e)
            return request.render('sat.error_page', {'error': str(e)})



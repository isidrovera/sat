# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Campos computados para mostrar mapas
    url_mapa_entrada = fields.Char(
        string="URL Mapa Entrada", 
        compute='_compute_url_mapa_entrada',
        help="URL de Google Maps para ubicación de entrada"
    )
    url_mapa_salida = fields.Char(
        string="URL Mapa Salida", 
        compute='_compute_url_mapa_salida',
        help="URL de Google Maps para ubicación de salida"
    )
    
    # URLs de mapas estáticos para embebido
    mapa_estatico_entrada = fields.Char(
        string="Mapa Estático Entrada",
        compute='_compute_mapa_estatico_entrada',
        help="URL de imagen de mapa estático para ubicación de entrada"
    )
    mapa_estatico_salida = fields.Char(
        string="Mapa Estático Salida", 
        compute='_compute_mapa_estatico_salida',
        help="URL de imagen de mapa estático para ubicación de salida"
    )
    
    # Campos de resumen de ubicación
    resumen_ubicacion_entrada = fields.Char(
        string="Ubicación de Entrada",
        compute='_compute_resumenes_ubicacion',
        help="Resumen de ubicación de entrada"
    )
    resumen_ubicacion_salida = fields.Char(
        string="Ubicación de Salida",
        compute='_compute_resumenes_ubicacion', 
        help="Resumen de ubicación de salida"
    )
    
    tiene_ubicacion_entrada = fields.Boolean(
        string="Tiene Ubicación de Entrada",
        compute='_compute_tiene_datos_ubicacion',
        store=True,
        help="Si la entrada tiene datos de ubicación"
    )
    tiene_ubicacion_salida = fields.Boolean(
        string="Tiene Ubicación de Salida", 
        compute='_compute_tiene_datos_ubicacion',
        store=True,
        help="Si la salida tiene datos de ubicación"
    )

    # Campo HTML para mostrar el mapa embebido de entrada
    mapa_entrada_html = fields.Html(
        string="Mapa de Entrada",
        compute='_compute_mapas_html',
        help="Mapa embebido de la ubicación de entrada"
    )
    
    # Campo HTML para mostrar el mapa embebido de salida
    mapa_salida_html = fields.Html(
        string="Mapa de Salida",
        compute='_compute_mapas_html',
        help="Mapa embebido de la ubicación de salida"
    )

    @api.depends('in_latitude', 'in_longitude')
    def _compute_url_mapa_entrada(self):
        for record in self:
            if record.in_latitude and record.in_longitude:
                record.url_mapa_entrada = f"https://maps.google.com?q={record.in_latitude},{record.in_longitude}"
            else:
                record.url_mapa_entrada = False

    @api.depends('out_latitude', 'out_longitude')
    def _compute_url_mapa_salida(self):
        for record in self:
            if record.out_latitude and record.out_longitude:
                record.url_mapa_salida = f"https://maps.google.com?q={record.out_latitude},{record.out_longitude}"
            else:
                record.url_mapa_salida = False

    @api.depends('in_latitude', 'in_longitude')
    def _compute_mapa_estatico_entrada(self):
        for record in self:
            if record.in_latitude and record.in_longitude:
                # URL de Google Static Maps API sin API key para funcionar básicamente
                record.mapa_estatico_entrada = (
                    f"https://maps.googleapis.com/maps/api/staticmap?"
                    f"center={record.in_latitude},{record.in_longitude}&"
                    f"zoom=15&size=400x300&"
                    f"markers=color:green%7Clabel:E%7C{record.in_latitude},{record.in_longitude}&"
                    f"maptype=roadmap"
                )
            else:
                record.mapa_estatico_entrada = False

    @api.depends('out_latitude', 'out_longitude')
    def _compute_mapa_estatico_salida(self):
        for record in self:
            if record.out_latitude and record.out_longitude:
                # URL de Google Static Maps API sin API key para funcionar básicamente
                record.mapa_estatico_salida = (
                    f"https://maps.googleapis.com/maps/api/staticmap?"
                    f"center={record.out_latitude},{record.out_longitude}&"
                    f"zoom=15&size=400x300&"
                    f"markers=color:red%7Clabel:S%7C{record.out_latitude},{record.out_longitude}&"
                    f"maptype=roadmap"
                )
            else:
                record.mapa_estatico_salida = False

    @api.depends('in_city', 'in_country_name', 'out_city', 'out_country_name', 'in_latitude', 'in_longitude', 'out_latitude', 'out_longitude')
    def _compute_resumenes_ubicacion(self):
        for record in self:
            # Resumen de ubicación de entrada
            partes_entrada = []
            if record.in_city:
                partes_entrada.append(record.in_city)
            if record.in_country_name:
                partes_entrada.append(record.in_country_name)
            if record.in_latitude and record.in_longitude:
                partes_entrada.append(f"({record.in_latitude:.6f}, {record.in_longitude:.6f})")
            record.resumen_ubicacion_entrada = ', '.join(partes_entrada) if partes_entrada else "Sin ubicación registrada"
            
            # Resumen de ubicación de salida
            partes_salida = []
            if record.out_city:
                partes_salida.append(record.out_city)
            if record.out_country_name:
                partes_salida.append(record.out_country_name)
            if record.out_latitude and record.out_longitude:
                partes_salida.append(f"({record.out_latitude:.6f}, {record.out_longitude:.6f})")
            record.resumen_ubicacion_salida = ', '.join(partes_salida) if partes_salida else "Sin ubicación registrada"

    @api.depends('in_latitude', 'in_longitude', 'out_latitude', 'out_longitude')
    def _compute_tiene_datos_ubicacion(self):
        for record in self:
            record.tiene_ubicacion_entrada = bool(record.in_latitude and record.in_longitude)
            record.tiene_ubicacion_salida = bool(record.out_latitude and record.out_longitude)

    @api.depends('in_latitude', 'in_longitude', 'out_latitude', 'out_longitude', 'mapa_estatico_entrada', 'mapa_estatico_salida')
    def _compute_mapas_html(self):
        for record in self:
            # Mapa HTML para entrada
            if record.tiene_ubicacion_entrada and record.mapa_estatico_entrada:
                record.mapa_entrada_html = f'''
                <div style="text-align: center; padding: 10px; border: 1px solid #ddd; border-radius: 8px; background: #f9f9f9;">
                    <h4 style="color: #28a745; margin-bottom: 10px;">
                        <i class="fa fa-sign-in"></i> Ubicación de Entrada
                    </h4>
                    <p><strong>Coordenadas:</strong> {record.in_latitude:.6f}, {record.in_longitude:.6f}</p>
                    <p><strong>Ciudad:</strong> {record.in_city or 'No disponible'}</p>
                    <p><strong>País:</strong> {record.in_country_name or 'No disponible'}</p>
                    <p><strong>IP:</strong> {record.in_ip_address or 'No disponible'}</p>
                    <p><strong>Navegador:</strong> {record.in_browser or 'No disponible'}</p>
                    <div style="margin: 15px 0;">
                        <img src="{record.mapa_estatico_entrada}" alt="Mapa de Entrada" 
                             style="max-width: 100%; border: 2px solid #28a745; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"/>
                    </div>
                    <a href="{record.url_mapa_entrada}" target="_blank" 
                       style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                        <i class="fa fa-external-link"></i> Ver en Google Maps
                    </a>
                </div>
                '''
            else:
                record.mapa_entrada_html = '''
                <div style="text-align: center; padding: 30px; color: #666; border: 1px dashed #ccc; border-radius: 8px; background: #f8f9fa;">
                    <i class="fa fa-map-marker" style="font-size: 48px; color: #dee2e6; margin-bottom: 15px;"></i>
                    <h5 style="color: #6c757d;">Sin datos de ubicación</h5>
                    <p>No se registró ubicación para la entrada</p>
                </div>
                '''

            # Mapa HTML para salida
            if record.tiene_ubicacion_salida and record.mapa_estatico_salida:
                record.mapa_salida_html = f'''
                <div style="text-align: center; padding: 10px; border: 1px solid #ddd; border-radius: 8px; background: #f9f9f9;">
                    <h4 style="color: #dc3545; margin-bottom: 10px;">
                        <i class="fa fa-sign-out"></i> Ubicación de Salida
                    </h4>
                    <p><strong>Coordenadas:</strong> {record.out_latitude:.6f}, {record.out_longitude:.6f}</p>
                    <p><strong>Ciudad:</strong> {record.out_city or 'No disponible'}</p>
                    <p><strong>País:</strong> {record.out_country_name or 'No disponible'}</p>
                    <p><strong>IP:</strong> {record.out_ip_address or 'No disponible'}</p>
                    <p><strong>Navegador:</strong> {record.out_browser or 'No disponible'}</p>
                    <div style="margin: 15px 0;">
                        <img src="{record.mapa_estatico_salida}" alt="Mapa de Salida" 
                             style="max-width: 100%; border: 2px solid #dc3545; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"/>
                    </div>
                    <a href="{record.url_mapa_salida}" target="_blank" 
                       style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                        <i class="fa fa-external-link"></i> Ver en Google Maps
                    </a>
                </div>
                '''
            else:
                record.mapa_salida_html = '''
                <div style="text-align: center; padding: 30px; color: #666; border: 1px dashed #ccc; border-radius: 8px; background: #f8f9fa;">
                    <i class="fa fa-map-marker" style="font-size: 48px; color: #dee2e6; margin-bottom: 15px;"></i>
                    <h5 style="color: #6c757d;">Sin datos de ubicación</h5>
                    <p>No se registró ubicación para la salida</p>
                </div>
                '''

    def action_abrir_mapa_entrada(self):
        """Abrir ubicación de entrada en Google Maps"""
        self.ensure_one()
        if not self.url_mapa_entrada:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No hay datos de ubicación para la entrada',
                    'type': 'warning',
                }
            }
        return {
            'type': 'ir.actions.act_url',
            'url': self.url_mapa_entrada,
            'target': 'new'
        }

    def action_abrir_mapa_salida(self):
        """Abrir ubicación de salida en Google Maps"""
        self.ensure_one()
        if not self.url_mapa_salida:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No hay datos de ubicación para la salida',
                    'type': 'warning',
                }
            }
        return {
            'type': 'ir.actions.act_url',
            'url': self.url_mapa_salida,
            'target': 'new'
        }
# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Campos GPS sin complicaciones
    gps_latitude = fields.Float(
        string='GPS Latitude',
        digits=(10, 7),
        help='GPS latitude when attendance was recorded'
    )
    
    gps_longitude = fields.Float(
        string='GPS Longitude', 
        digits=(10, 7),
        help='GPS longitude when attendance was recorded'
    )
    
    gps_accuracy = fields.Float(
        string='GPS Accuracy (meters)',
        help='GPS accuracy in meters when location was captured'
    )
    
    location_source = fields.Selection([
        ('geoip', 'IP Geolocation'),
        ('gps', 'GPS'),
        ('manual', 'Manual'),
    ], string='Location Source', default='geoip')
    
    gps_timestamp = fields.Datetime(
        string='GPS Timestamp',
        help='When the GPS location was captured'
    )

    @api.model
    def create(self, vals):
        """
        Override create para capturar datos GPS desde el contexto
        """
        # Obtener datos GPS del contexto si están disponibles
        gps_data = self.env.context.get('gps_data', {})
        
        if gps_data:
            if gps_data.get('latitude'):
                vals['gps_latitude'] = gps_data['latitude']
            if gps_data.get('longitude'):
                vals['gps_longitude'] = gps_data['longitude']
            if gps_data.get('accuracy'):
                vals['gps_accuracy'] = gps_data['accuracy']
            if gps_data.get('source'):
                vals['location_source'] = gps_data['source']
            if gps_data.get('timestamp'):
                vals['gps_timestamp'] = gps_data['timestamp']
        
        return super().create(vals)
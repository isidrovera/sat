# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Campos adicionales para GPS
    gps_accuracy = fields.Float(
        string='GPS Accuracy (meters)',
        help='GPS accuracy in meters when location was captured'
    )
    
    location_source = fields.Selection([
        ('gps', 'GPS'),
        ('geoip', 'IP Geolocation'),
        ('manual', 'Manual'),
    ], string='Location Source', default='geoip',
    help='How the location was determined')
    
    gps_timestamp = fields.Datetime(
        string='GPS Timestamp',
        help='When the GPS location was captured'
    )

    def _attendance_action_change(self):
        """
        OVERRIDE: Mantener compatibilidad con el método original
        """
        # Obtener datos de geolocalización desde el contexto si están disponibles
        geo_data = self.env.context.get('geo_data', {})
        
        # Llamar al método original
        result = super()._attendance_action_change()
        
        # Si tenemos datos GPS adicionales, actualizar el registro
        if geo_data and result and hasattr(result, 'id'):
            attendance_vals = {}
            
            # Guardar información adicional de GPS
            if geo_data.get('location_source') == 'gps':
                attendance_vals.update({
                    'location_source': 'gps',
                    'gps_timestamp': fields.Datetime.now(),
                })
                
                # Si tenemos accuracy del GPS
                if geo_data.get('accuracy'):
                    attendance_vals['gps_accuracy'] = geo_data['accuracy']
                    
            elif geo_data.get('location_source') == 'geoip':
                attendance_vals['location_source'] = 'geoip'
            
            # Actualizar el registro si hay cambios
            if attendance_vals:
                try:
                    result.write(attendance_vals)
                    _logger.info(f"Updated attendance {result.id} with GPS data: {attendance_vals}")
                except Exception as e:
                    _logger.warning(f"Could not update attendance GPS data: {e}")
        
        return result
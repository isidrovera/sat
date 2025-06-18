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

    def init(self):
        """
        Forzar la creación de las columnas GPS si no existen
        """
        super().init()
        # Verificar y crear columnas GPS para hr_attendance
        gps_columns = [
            ('gps_accuracy', 'NUMERIC'),
            ('location_source', 'VARCHAR'),
            ('gps_timestamp', 'TIMESTAMP')
        ]
        
        for column_name, column_type in gps_columns:
            self._cr.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'hr_attendance' 
                AND column_name = %s
            """, (column_name,))
            if not self._cr.fetchone():
                self._cr.execute(f"""
                    ALTER TABLE hr_attendance 
                    ADD COLUMN {column_name} {column_type}
                """)
        
        # Actualizar registros existentes con location_source por defecto
        self._cr.execute("""
            UPDATE hr_attendance 
            SET location_source = 'geoip' 
            WHERE location_source IS NULL
        """)

    def _attendance_action_change(self, geo_data=None):
        """
        OVERRIDE: Mejorar el procesamiento de datos de ubicación GPS
        """
        result = super()._attendance_action_change(geo_data)
        
        # Si tenemos datos GPS adicionales, actualizar el registro
        if geo_data and hasattr(self, 'id') and self.id:
            attendance_vals = {}
            
            # Guardar información adicional de GPS
            if geo_data.get('location_source') == 'gps':
                attendance_vals.update({
                    'location_source': 'gps',
                    'gps_timestamp': fields.Datetime.now(),
                })
                
                # Si tenemos accuracy del GPS (se puede pasar desde JavaScript)
                if geo_data.get('accuracy'):
                    attendance_vals['gps_accuracy'] = geo_data['accuracy']
                    
            elif geo_data.get('location_source') == 'geoip':
                attendance_vals['location_source'] = 'geoip'
            
            # Actualizar el registro si hay cambios
            if attendance_vals:
                try:
                    self.write(attendance_vals)
                    _logger.info(f"Updated attendance {self.id} with GPS data: {attendance_vals}")
                except Exception as e:
                    _logger.warning(f"Could not update attendance GPS data: {e}")
        
        return result

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def attendance_manual(self, next_action, entered_pin=None, latitude=False, longitude=False):
        """
        OVERRIDE: Agregar soporte GPS para check-in/out manual desde backend
        """
        # Preparar datos de geolocalización
        geo_data = {
            'mode': 'manual',
            'ip_address': self.env.context.get('ip_address', ''),
            'browser': self.env.context.get('user_agent', ''),
        }
        
        # Si tenemos coordenadas GPS, usarlas
        if latitude and longitude:
            geo_data.update({
                'latitude': latitude,
                'longitude': longitude,
                'location_source': 'gps',
                'city': 'GPS Location',
                'country_name': 'Unknown',
            })
        else:
            # Fallback a detección por IP
            try:
                from odoo.http import request
                if request and hasattr(request, 'geoip'):
                    geo_data.update({
                        'city': request.geoip.city.name or 'Unknown',
                        'country_name': request.geoip.country.name or 'Unknown',
                        'latitude': request.geoip.location.latitude or False,
                        'longitude': request.geoip.location.longitude or False,
                        'location_source': 'geoip',
                    })
            except:
                geo_data.update({
                    'city': 'Unknown',
                    'country_name': 'Unknown',
                    'latitude': False,
                    'longitude': False,
                    'location_source': 'manual',
                })
        
        # Llamar al método de cambio de asistencia con datos de ubicación
        return self._attendance_action_change(geo_data)
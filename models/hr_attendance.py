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

    def _auto_init(self):
        """
        Hook llamado automáticamente por Odoo para inicializar el modelo
        """
        # Llamar al método padre primero
        result = super()._auto_init()
        
        # Asegurar que las columnas GPS existen
        self._create_gps_columns()
        
        return result

    def _create_gps_columns(self):
        """
        Crear columnas GPS si no existen
        """
        gps_columns = {
            'gps_accuracy': 'NUMERIC',
            'location_source': 'VARCHAR DEFAULT \'geoip\'',
            'gps_timestamp': 'TIMESTAMP'
        }
        
        for column_name, column_type in gps_columns.items():
            # Verificar si la columna existe
            self._cr.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'hr_attendance' 
                AND column_name = %s
            """, (column_name,))
            
            if not self._cr.fetchone():
                try:
                    self._cr.execute(f"""
                        ALTER TABLE hr_attendance 
                        ADD COLUMN {column_name} {column_type}
                    """)
                    self._cr.commit()
                except Exception as e:
                    # Si hay error, hacer rollback y continuar
                    self._cr.rollback()

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
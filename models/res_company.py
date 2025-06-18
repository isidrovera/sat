# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Configuraciones GPS para asistencias
    attendance_gps_required = fields.Boolean(
        string='Require GPS Location',
        default=False,
        help='Require GPS location for all attendance records. If disabled, IP-based location will be used as fallback.'
    )
    
    attendance_gps_timeout = fields.Integer(
        string='GPS Timeout (ms)',
        default=10000,
        help='Maximum time to wait for GPS location in milliseconds (default: 10 seconds)'
    )
    
    attendance_gps_accuracy = fields.Float(
        string='GPS Accuracy Threshold (meters)',
        default=100.0,
        help='Maximum acceptable GPS accuracy in meters. Locations with lower accuracy will be rejected.'
    )
    
    attendance_gps_enable_geofencing = fields.Boolean(
        string='Enable Geofencing',
        default=False,
        help='Enable location-based attendance validation (geofencing)'
    )
    
    attendance_gps_office_locations = fields.Text(
        string='Office Locations (GPS)',
        help='JSON format with office locations for geofencing: [{"name": "Main Office", "lat": 40.7128, "lng": -74.0060, "radius": 200}]'
    )
    
    attendance_gps_allow_home_office = fields.Boolean(
        string='Allow Home Office',
        default=True,
        help='Allow attendance from any location (disable geofencing restrictions)'
    )

    def init(self):
        """
        Forzar la creación de las columnas GPS si no existen
        """
        super().init()
        # Verificar y crear columnas si no existen
        self._cr.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'res_company' 
            AND column_name = 'attendance_gps_required'
        """)
        if not self._cr.fetchone():
            self._cr.execute("""
                ALTER TABLE res_company 
                ADD COLUMN attendance_gps_required BOOLEAN DEFAULT FALSE
            """)
        
        # Verificar otras columnas GPS
        gps_columns = [
            ('attendance_gps_timeout', 'INTEGER DEFAULT 10000'),
            ('attendance_gps_accuracy', 'NUMERIC DEFAULT 100.0'),
            ('attendance_gps_enable_geofencing', 'BOOLEAN DEFAULT FALSE'),
            ('attendance_gps_office_locations', 'TEXT'),
            ('attendance_gps_allow_home_office', 'BOOLEAN DEFAULT TRUE')
        ]
        
        for column_name, column_type in gps_columns:
            self._cr.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'res_company' 
                AND column_name = %s
            """, (column_name,))
            if not self._cr.fetchone():
                self._cr.execute(f"""
                    ALTER TABLE res_company 
                    ADD COLUMN {column_name} {column_type}
                """)

    @api.model
    def _get_gps_settings(self):
        """
        Retorna configuraciones GPS para JavaScript
        """
        company = self.env.company
        return {
            'gps_required': company.attendance_gps_required,
            'gps_timeout': company.attendance_gps_timeout,
            'gps_accuracy': company.attendance_gps_accuracy,
            'geofencing_enabled': company.attendance_gps_enable_geofencing,
            'allow_home_office': company.attendance_gps_allow_home_office,
        }
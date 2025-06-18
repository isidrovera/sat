# -*- coding: utf-8 -*-
from odoo import models, fields, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Configuraciones GPS específicas por empleado
    require_gps_attendance = fields.Boolean(
        string='Require GPS for Attendance',
        default=True,
        help='Require GPS location when this employee checks in/out'
    )
    
    gps_accuracy_threshold = fields.Float(
        string='GPS Accuracy Threshold (meters)',
        default=100.0,
        help='Maximum acceptable GPS accuracy in meters'
    )

    @api.model
    def get_gps_settings(self):
        """
        Retorna configuraciones GPS para el empleado actual
        """
        employee = self.env.user.employee_id
        if not employee:
            return {
                'gps_required': False,
                'gps_timeout': 10000,
                'gps_accuracy': 100.0,
            }
        
        return {
            'gps_required': employee.require_gps_attendance,
            'gps_timeout': 10000,  # 10 segundos
            'gps_accuracy': employee.gps_accuracy_threshold,
        }
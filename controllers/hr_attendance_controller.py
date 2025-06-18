# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.addons.hr_attendance.controllers.hr_attendance import HrAttendance as BaseHrAttendance
import logging

_logger = logging.getLogger(__name__)

class HrAttendance(BaseHrAttendance):
    """
    Hereda el controlador base para agregar funcionalidad GPS mejorada
    """

    @staticmethod
    def _get_geoip_response(mode, latitude=False, longitude=False):
        """
        OVERRIDE: Prioriza GPS real sobre GeoIP
        """
        # Usar coordenadas GPS reales si están disponibles
        if latitude and longitude:
            gps_data = {
                'latitude': latitude,
                'longitude': longitude,
                'ip_address': request.geoip.ip,
                'browser': request.httprequest.user_agent.browser,
                'mode': mode,
                'location_source': 'gps'  # Identificar fuente de ubicación
            }
            
            # Intentar obtener ciudad/país por GeoIP como fallback
            try:
                gps_data.update({
                    'city': request.geoip.city.name or _('GPS Location'),
                    'country_name': request.geoip.country.name or request.geoip.continent.name or _('Unknown'),
                })
            except:
                gps_data.update({
                    'city': _('GPS Location'),
                    'country_name': _('Unknown'),
                })
            
            _logger.info(f"GPS coordinates captured: lat={latitude}, lon={longitude}, mode={mode}")
            return gps_data
        else:
            # Fallback a implementación original
            _logger.info(f"Using GeoIP fallback for location, mode={mode}")
            return {
                'city': request.geoip.city.name or _('Unknown'),
                'country_name': request.geoip.country.name or request.geoip.continent.name or _('Unknown'),
                'latitude': request.geoip.location.latitude or False,
                'longitude': request.geoip.location.longitude or False,
                'ip_address': request.geoip.ip,
                'browser': request.httprequest.user_agent.browser,
                'mode': mode,
                'location_source': 'geoip'
            }

    @http.route('/hr_attendance/attendance_barcode_scanned', type="json", auth="public")
    def scan_barcode(self, token, barcode, latitude=False, longitude=False):
        """
        OVERRIDE: Agrega soporte para coordenadas GPS en escaneo de códigos
        """
        company = self._get_company(token)
        if company:
            employee = request.env['hr.employee'].sudo().search([
                ('barcode', '=', barcode), 
                ('company_id', '=', company.id)
            ], limit=1)
            
            if employee:
                # Crear respuesta de geolocalización con GPS real
                geo_response = self._get_geoip_response('kiosk', latitude=latitude, longitude=longitude)
                
                # Procesar check-in/check-out
                employee._attendance_action_change(geo_response)
                
                return self._get_employee_info_response(employee)
        return {}

    @http.route('/hr_attendance/systray_check_in_out', type="json", auth="user")
    def systray_attendance(self, latitude=False, longitude=False):
        """
        OVERRIDE: Mejora logging para systray con GPS
        """
        employee = request.env.user.employee_id
        
        if not employee:
            return {'error': _('No employee found for current user')}
        
        # Crear respuesta de geolocalización con GPS real
        geo_ip_response = self._get_geoip_response(
            mode='systray',
            latitude=latitude,
            longitude=longitude
        )
        
        # Procesar check-in/check-out
        employee._attendance_action_change(geo_ip_response)
        
        return self._get_employee_info_response(employee)
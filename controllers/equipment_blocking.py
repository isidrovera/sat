# controllers/equipment_blocking.py

from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class EquipmentBlockingController(http.Controller):

    @http.route('/equipment/blocking/dashboard', type='http', auth='user', website=True)
    def blocking_dashboard(self, **kwargs):
        """Dashboard principal para gestión de bloqueos"""
        try:
            # Obtener datos del dashboard
            equipment_model = request.env['alquiler']
            dashboard_data = equipment_model.get_dashboard_data()
            
            # Obtener lista de usuarios para asignación
            users = request.env['res.users'].search([
                ('active', '=', True),
                ('share', '=', False)
            ])
            
            return request.render('sat.equipment_blocking_dashboard_template', {
                'dashboard_data': dashboard_data,
                'users': users
            })
            
        except Exception as e:
            _logger.error(f"Error en dashboard de bloqueos: {str(e)}")
            return request.render('sat.error_template', {
                'error_message': 'Error al cargar el dashboard'
            })

    @http.route('/equipment/blocking/search', type='json', auth='user', methods=['POST'])
    def search_equipments(self, search_term='', only_pending=False):
        """Busca equipos por serie, cliente, modelo, etc."""
        try:
            equipment_model = request.env['alquiler']
            
            if only_pending:
                # Solo equipos que requieren atención
                domain = [('estado_bloqueo', 'in', ['suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'])]
            else:
                # Búsqueda normal
                if search_term:
                    domain = ['|', '|', '|',
                              ('serie', 'ilike', search_term),
                              ('cliente_id.name', 'ilike', search_term),
                              ('name.name', 'ilike', search_term),
                              ('marca', 'ilike', search_term)]
                else:
                    # Cargar todos los equipos (limitado)
                    domain = []
            
            equipos_records = equipment_model.search(domain, limit=100, order='estado_bloqueo desc, serie')
            equipos = []
            
            for equipo in equipos_records:
                equipos.append({
                    'id': equipo.id,
                    'serie': equipo.serie or '',
                    'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                    'modelo': equipo.name.name if equipo.name else '',
                    'marca': equipo.marca or '',
                    'estado_bloqueo': equipo.estado_bloqueo,
                    'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                    'direccion': equipo.direccion or '',
                    'acceso_remoto': equipo.acceso_remoto_disponible,
                    'ip_equipo': equipo.ip_equipo or '',
                    'motivo_bloqueo': equipo.motivo_bloqueo or '',
                    'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                    'puede_suspender': equipo.estado_bloqueo == 'activo',
                    'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'] and equipo.acceso_remoto_disponible,
                    'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'] and equipo.acceso_remoto_disponible
                })
            
            return {
                'status': 'success',
                'equipos': equipos
            }
            
        except Exception as e:
            _logger.error(f"Error en búsqueda de equipos: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/equipment/blocking/suspend', type='json', auth='user', methods=['POST'])
    def suspend_service(self, equipment_id, motivo=''):
        """Suspende el servicio de un equipo"""
        try:
            equipment = request.env['alquiler'].browse(int(equipment_id))
            
            if not equipment.exists():
                return {
                    'status': 'error',
                    'message': 'Equipo no encontrado'
                }
            
            # Suspender servicio
            equipment.action_suspender_servicio(
                motivo=motivo or 'Suspendido desde dashboard',
                usuario_id=request.env.user.id
            )
            
            return {
                'status': 'success',
                'message': f'Servicio suspendido para equipo {equipment.serie}'
            }
            
        except Exception as e:
            _logger.error(f"Error al suspender servicio: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/equipment/blocking/block', type='json', auth='user', methods=['POST'])
    def block_equipment(self, equipment_id, motivo=''):
        """Bloquea un equipo remotamente"""
        try:
            equipment = request.env['alquiler'].browse(int(equipment_id))
            
            if not equipment.exists():
                return {
                    'status': 'error',
                    'message': 'Equipo no encontrado'
                }
            
            # Bloquear equipo
            resultado = equipment.action_bloquear_equipo(
                motivo=motivo or 'Bloqueado desde dashboard',
                usuario_id=request.env.user.id
            )
            
            return {
                'status': 'success' if resultado['success'] else 'warning',
                'message': resultado['message']
            }
            
        except Exception as e:
            _logger.error(f"Error al bloquear equipo: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/equipment/blocking/unblock', type='json', auth='user', methods=['POST'])
    def unblock_equipment(self, equipment_id, motivo=''):
        """Desbloquea un equipo"""
        try:
            equipment = request.env['alquiler'].browse(int(equipment_id))
            
            if not equipment.exists():
                return {
                    'status': 'error',
                    'message': 'Equipo no encontrado'
                }
            
            # Desbloquear equipo
            resultado = equipment.action_desbloquear_equipo(
                motivo=motivo or 'Desbloqueado desde dashboard',
                usuario_id=request.env.user.id
            )
            
            return {
                'status': 'success' if resultado['success'] else 'warning',
                'message': resultado['message']
            }
            
        except Exception as e:
            _logger.error(f"Error al desbloquear equipo: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/equipment/blocking/dashboard_data', type='json', auth='user', methods=['POST'])
    def get_dashboard_data(self):
        """Obtiene datos actualizados del dashboard"""
        try:
            equipment_model = request.env['alquiler']
            dashboard_data = equipment_model.get_dashboard_data()
            
            return {
                'status': 'success',
                'data': dashboard_data
            }
            
        except Exception as e:
            _logger.error(f"Error al obtener datos del dashboard: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
# controllers/equipment_blocking.py

from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class EquipmentBlockingController(http.Controller):

    @http.route('/equipment/blocking/dashboard', type='http', auth='public', website=True)
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
    def search_equipments(self, search_term=''):
        """Busca equipos por serie, cliente, modelo, etc."""
        try:
            equipment_model = request.env['alquiler']
            equipos = equipment_model.buscar_equipos_web(search_term)
            
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
                motivo=motivo,
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
                motivo=motivo,
                usuario_id=request.env.user.id
            )
            
            return {
                'status': 'success' if resultado['success'] else 'error',
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
                motivo=motivo,
                usuario_id=request.env.user.id
            )
            
            return {
                'status': 'success' if resultado['success'] else 'error',
                'message': resultado['message']
            }
            
        except Exception as e:
            _logger.error(f"Error al desbloquear equipo: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/equipment/blocking/update_config', type='json', auth='user', methods=['POST'])
    def update_equipment_config(self, equipment_id, **kwargs):
        """Actualiza configuración de un equipo"""
        try:
            equipment = request.env['alquiler'].browse(int(equipment_id))
            
            if not equipment.exists():
                return {
                    'status': 'error',
                    'message': 'Equipo no encontrado'
                }
            
            # Actualizar configuración
            values = {}
            
            if 'acceso_remoto_disponible' in kwargs:
                values['acceso_remoto_disponible'] = kwargs['acceso_remoto_disponible']
                
            if 'ip_equipo' in kwargs:
                values['ip_equipo'] = kwargs['ip_equipo']
                
            if 'asesor_ventas_id' in kwargs:
                values['asesor_ventas_id'] = int(kwargs['asesor_ventas_id']) if kwargs['asesor_ventas_id'] else False
                
            if 'soporte_tecnico_id' in kwargs:
                values['soporte_tecnico_id'] = int(kwargs['soporte_tecnico_id']) if kwargs['soporte_tecnico_id'] else False
                
            if 'observaciones_bloqueo' in kwargs:
                values['observaciones_bloqueo'] = kwargs['observaciones_bloqueo']
            
            if values:
                equipment.write(values)
            
            return {
                'status': 'success',
                'message': 'Configuración actualizada correctamente'
            }
            
        except Exception as e:
            _logger.error(f"Error al actualizar configuración: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/equipment/blocking/get_equipment_details', type='json', auth='user', methods=['POST'])
    def get_equipment_details(self, equipment_id):
        """Obtiene detalles completos de un equipo"""
        try:
            equipment = request.env['alquiler'].browse(int(equipment_id))
            
            if not equipment.exists():
                return {
                    'status': 'error',
                    'message': 'Equipo no encontrado'
                }
            
            # Obtener historial de tickets
            tickets = request.env['ticket.alquiler'].search([
                ('product_alquiler', '=', equipment.id)
            ], order='create_date desc', limit=5)
            
            tickets_data = []
            for ticket in tickets:
                tickets_data.append({
                    'name': ticket.name,
                    'fecha': ticket.create_date.strftime('%d/%m/%Y'),
                    'estado': ticket.estado,
                    'tipo_servicio': ticket.tipo_servicio_id
                })
            
            return {
                'status': 'success',
                'equipment': {
                    'id': equipment.id,
                    'serie': equipment.serie,
                    'cliente': equipment.cliente_id.name if equipment.cliente_id else '',
                    'modelo': equipment.name.name if equipment.name else '',
                    'marca': equipment.marca,
                    'direccion': equipment.direccion,
                    'contacto': equipment.contacto_id,
                    'celular': equipment.celular,
                    'correo': equipment.correo_,
                    'estado_bloqueo': equipment.estado_bloqueo,
                    'motivo_bloqueo': equipment.motivo_bloqueo,
                    'fecha_bloqueo': equipment.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipment.fecha_bloqueo else '',
                    'fecha_desbloqueo': equipment.fecha_desbloqueo.strftime('%d/%m/%Y %H:%M') if equipment.fecha_desbloqueo else '',
                    'acceso_remoto_disponible': equipment.acceso_remoto_disponible,
                    'ip_equipo': equipment.ip_equipo,
                    'asesor_ventas_id': equipment.asesor_ventas_id.id if equipment.asesor_ventas_id else False,
                    'asesor_ventas_name': equipment.asesor_ventas_id.name if equipment.asesor_ventas_id else '',
                    'soporte_tecnico_id': equipment.soporte_tecnico_id.id if equipment.soporte_tecnico_id else False,
                    'soporte_tecnico_name': equipment.soporte_tecnico_id.name if equipment.soporte_tecnico_id else '',
                    'observaciones_bloqueo': equipment.observaciones_bloqueo,
                    'tickets_recientes': tickets_data
                }
            }
            
        except Exception as e:
            _logger.error(f"Error al obtener detalles del equipo: {str(e)}")
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
# controllers/dashboard_controller.py

from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class EquipmentBlockingDashboardController(http.Controller):
    """Controlador para el dashboard de bloqueo de equipos - Backend de Odoo"""

    @http.route('/web/dataset/call_kw/alquiler/get_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_dashboard_data(self, **kwargs):
        """Obtiene datos del dashboard para equipos alquilados"""
        try:
            # Verificar permisos del usuario
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            alquiler_model = request.env['alquiler']
            
            # Contar equipos por estado de bloqueo (solo alquilados)
            domain_base = [('estado_alquiler_id', '=', 'alquilada')]
            
            equipos_activos = alquiler_model.search_count(
                domain_base + [('estado_bloqueo', '=', 'activo')]
            )
            equipos_suspendidos = alquiler_model.search_count(
                domain_base + [('estado_bloqueo', '=', 'suspendido')]
            )
            equipos_bloqueados = alquiler_model.search_count(
                domain_base + [('estado_bloqueo', '=', 'bloqueado')]
            )
            equipos_no_accesibles = alquiler_model.search_count(
                domain_base + [('estado_bloqueo', '=', 'no_accesible')]
            )
            pendientes_bloqueo = alquiler_model.search_count(
                domain_base + [('estado_bloqueo', '=', 'pendiente_bloqueo')]
            )
            pendientes_desbloqueo = alquiler_model.search_count(
                domain_base + [('estado_bloqueo', '=', 'pendiente_desbloqueo')]
            )
            
            return {
                'equipos_activos': equipos_activos,
                'equipos_suspendidos': equipos_suspendidos,
                'equipos_bloqueados': equipos_bloqueados,
                'equipos_no_accesibles': equipos_no_accesibles,
                'pendientes_bloqueo': pendientes_bloqueo,
                'pendientes_desbloqueo': pendientes_desbloqueo,
                'total_alquilados': sum([
                    equipos_activos, equipos_suspendidos, equipos_bloqueados,
                    equipos_no_accesibles, pendientes_bloqueo, pendientes_desbloqueo
                ])
            }
            
        except Exception as e:
            _logger.error(f"Error obteniendo datos del dashboard: {str(e)}")
            return {'error': str(e)}

    @http.route('/web/dataset/call_kw/alquiler/search_equipments', type='json', auth='user', methods=['POST'])
    def search_equipments(self, search_term='', estado_filtro='', **kwargs):
        """Busca equipos alquilados"""
        try:
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            alquiler_model = request.env['alquiler']
            
            # Domain base para equipos alquilados
            domain = [('estado_alquiler_id', '=', 'alquilada')]
            
            # Agregar filtro de búsqueda si existe
            if search_term:
                search_domain = [
                    '|', '|', '|',
                    ('serie', 'ilike', search_term),
                    ('cliente_id.name', 'ilike', search_term),
                    ('name.name', 'ilike', search_term),
                    ('marca', 'ilike', search_term)
                ]
                domain.extend(search_domain)
            
            # Agregar filtro por estado si existe
            if estado_filtro:
                domain.append(('estado_bloqueo', '=', estado_filtro))
            
            # Buscar equipos
            equipments = alquiler_model.search(domain, order='cliente_id, serie')
            
            # Procesar datos para el frontend
            equipments_data = []
            for equipment in equipments:
                equipments_data.append(self._format_equipment_data(equipment))
            
            return equipments_data
            
        except Exception as e:
            _logger.error(f"Error buscando equipos: {str(e)}")
            return {'error': str(e)}

    @http.route('/web/dataset/call_kw/alquiler/action_suspender_servicio', type='json', auth='user', methods=['POST'])
    def action_suspender_servicio(self, equipment_id, motivo='', **kwargs):
        """Suspende el servicio de un equipo"""
        try:
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            equipment = request.env['alquiler'].browse(equipment_id)
            
            if not equipment.exists():
                return {'error': 'Equipo no encontrado'}
            
            if equipment.estado_alquiler_id != 'alquilada':
                return {'error': 'Solo se pueden suspender equipos alquilados'}
            
            if equipment.estado_bloqueo != 'activo':
                return {'error': 'Solo se pueden suspender equipos activos'}
            
            # Ejecutar suspensión
            equipment.write({
                'estado_bloqueo': 'suspendido',
                'motivo_bloqueo': motivo,
                'fecha_bloqueo': fields.Datetime.now(),
                'usuario_bloqueo': request.env.user.id,
                'notificado_bloqueo': False
            })
            
            # Log de actividad
            equipment.message_post(
                body=f"Servicio suspendido por {request.env.user.name}. Motivo: {motivo}",
                message_type='notification'
            )
            
            return {
                'success': True,
                'message': f'Servicio suspendido para equipo {equipment.serie}',
                'nuevo_estado': 'suspendido'
            }
            
        except Exception as e:
            _logger.error(f"Error suspendiendo servicio: {str(e)}")
            return {'error': str(e)}

    @http.route('/web/dataset/call_kw/alquiler/action_bloquear_equipo', type='json', auth='user', methods=['POST'])
    def action_bloquear_equipo(self, equipment_id, motivo='', **kwargs):
        """Bloquea un equipo remotamente"""
        try:
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            equipment = request.env['alquiler'].browse(equipment_id)
            
            if not equipment.exists():
                return {'error': 'Equipo no encontrado'}
            
            if equipment.estado_alquiler_id != 'alquilada':
                return {'error': 'Solo se pueden bloquear equipos alquilados'}
            
            if equipment.estado_bloqueo not in ['activo', 'suspendido']:
                return {'error': 'El equipo no puede ser bloqueado en su estado actual'}
            
            # Verificar acceso remoto
            if not equipment.acceso_remoto_disponible:
                return {'error': 'El equipo no tiene acceso remoto configurado'}
            
            # Ejecutar bloqueo
            equipment.write({
                'estado_bloqueo': 'bloqueado',
                'motivo_bloqueo': motivo,
                'fecha_bloqueo': fields.Datetime.now(),
                'usuario_bloqueo': request.env.user.id,
                'notificado_bloqueo': False
            })
            
            # Log de actividad
            equipment.message_post(
                body=f"Equipo bloqueado remotamente por {request.env.user.name}. Motivo: {motivo}",
                message_type='notification'
            )
            
            return {
                'success': True,
                'message': f'Equipo {equipment.serie} bloqueado remotamente',
                'nuevo_estado': 'bloqueado'
            }
            
        except Exception as e:
            _logger.error(f"Error bloqueando equipo: {str(e)}")
            return {'error': str(e)}

    @http.route('/web/dataset/call_kw/alquiler/action_desbloquear_equipo', type='json', auth='user', methods=['POST'])
    def action_desbloquear_equipo(self, equipment_id, motivo='', **kwargs):
        """Desbloquea un equipo"""
        try:
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            equipment = request.env['alquiler'].browse(equipment_id)
            
            if not equipment.exists():
                return {'error': 'Equipo no encontrado'}
            
            if equipment.estado_alquiler_id != 'alquilada':
                return {'error': 'Solo se pueden desbloquear equipos alquilados'}
            
            if equipment.estado_bloqueo not in ['bloqueado', 'suspendido']:
                return {'error': 'El equipo no puede ser desbloqueado en su estado actual'}
            
            # Ejecutar desbloqueo
            equipment.write({
                'estado_bloqueo': 'activo',
                'motivo_bloqueo': False,
                'fecha_desbloqueo': fields.Datetime.now(),
                'usuario_bloqueo': request.env.user.id,
                'notificado_desbloqueo': False
            })
            
            # Log de actividad
            observacion = f" - Observaciones: {motivo}" if motivo else ""
            equipment.message_post(
                body=f"Equipo desbloqueado por {request.env.user.name}{observacion}",
                message_type='notification'
            )
            
            return {
                'success': True,
                'message': f'Equipo {equipment.serie} desbloqueado correctamente',
                'nuevo_estado': 'activo'
            }
            
        except Exception as e:
            _logger.error(f"Error desbloqueando equipo: {str(e)}")
            return {'error': str(e)}

    @http.route('/web/dataset/call_kw/alquiler/get_equipment_details', type='json', auth='user', methods=['POST'])
    def get_equipment_details(self, equipment_id, **kwargs):
        """Obtiene detalles de un equipo"""
        try:
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            equipment = request.env['alquiler'].browse(equipment_id)
            
            if not equipment.exists():
                return {'error': 'Equipo no encontrado'}
            
            return self._format_equipment_data(equipment, include_details=True)
            
        except Exception as e:
            _logger.error(f"Error obteniendo detalles del equipo: {str(e)}")
            return {'error': str(e)}

    def _format_equipment_data(self, equipment, include_details=False):
        """Formatea los datos de un equipo para el frontend"""
        try:
            from odoo import fields
            
            # Mapeo de estados
            estado_labels = {
                'activo': 'Activo',
                'suspendido': 'Suspendido',
                'bloqueado': 'Bloqueado',
                'no_accesible': 'No Accesible',
                'pendiente_bloqueo': 'Pend. Bloqueo',
                'pendiente_desbloqueo': 'Pend. Desbloqueo'
            }
            
            data = {
                'id': equipment.id,
                'serie': equipment.serie or '',
                'cliente': equipment.cliente_id.name if equipment.cliente_id else '',
                'cliente_id': equipment.cliente_id.id if equipment.cliente_id else False,
                'modelo': equipment.name.name if equipment.name else '',
                'marca': equipment.marca or '',
                'direccion': equipment.direccion or '',
                'ip_equipo': equipment.ip_equipo or '',
                'estado_bloqueo': equipment.estado_bloqueo or 'activo',
                'estado_label': estado_labels.get(equipment.estado_bloqueo, equipment.estado_bloqueo),
                'acceso_remoto': equipment.acceso_remoto_disponible or False,
                'motivo_bloqueo': equipment.motivo_bloqueo or '',
                'fecha_bloqueo': equipment.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipment.fecha_bloqueo else '',
                'puede_suspender': equipment.estado_bloqueo == 'activo',
                'puede_bloquear': equipment.estado_bloqueo in ['activo', 'suspendido'] and equipment.acceso_remoto_disponible,
                'puede_desbloquear': equipment.estado_bloqueo in ['bloqueado', 'suspendido']
            }
            
            if include_details:
                # Obtener tickets recientes
                tickets = request.env['ticket.alquiler'].search([
                    ('product_alquiler', '=', equipment.id)
                ], order='create_date desc', limit=5)
                
                tickets_data = []
                for ticket in tickets:
                    tickets_data.append({
                        'name': ticket.name,
                        'fecha': ticket.create_date.strftime('%d/%m/%Y'),
                        'estado': ticket.estado,
                        'tipo_servicio': ticket.tipo_servicio_id.name if ticket.tipo_servicio_id else ''
                    })
                
                data.update({
                    'contacto': equipment.contacto_id or '',
                    'celular': equipment.celular or '',
                    'correo': equipment.correo_ or '',
                    'fecha_desbloqueo': equipment.fecha_desbloqueo.strftime('%d/%m/%Y %H:%M') if equipment.fecha_desbloqueo else '',
                    'asesor_ventas_id': equipment.asesor_ventas_id.id if equipment.asesor_ventas_id else False,
                    'asesor_ventas_name': equipment.asesor_ventas_id.name if equipment.asesor_ventas_id else '',
                    'soporte_tecnico_id': equipment.soporte_tecnico_id.id if equipment.soporte_tecnico_id else False,
                    'soporte_tecnico_name': equipment.soporte_tecnico_id.name if equipment.soporte_tecnico_id else '',
                    'observaciones_bloqueo': equipment.observaciones_bloqueo or '',
                    'tickets_recientes': tickets_data
                })
            
            return data
            
        except Exception as e:
            _logger.error(f"Error formateando datos del equipo: {str(e)}")
            return {
                'id': equipment.id,
                'serie': equipment.serie or '',
                'error': 'Error al procesar datos del equipo'
            }

    @http.route('/web/dataset/call_kw/alquiler/update_equipment_config', type='json', auth='user', methods=['POST'])
    def update_equipment_config(self, equipment_id, **config_data):
        """Actualiza configuración de un equipo"""
        try:
            if not request.env.user.has_group('base.group_user'):
                return {'error': 'Permisos insuficientes'}
            
            equipment = request.env['alquiler'].browse(equipment_id)
            
            if not equipment.exists():
                return {'error': 'Equipo no encontrado'}
            
            if equipment.estado_alquiler_id != 'alquilada':
                return {'error': 'Solo se pueden configurar equipos alquilados'}
            
            # Filtrar campos permitidos
            allowed_fields = [
                'ip_equipo', 'acceso_remoto_disponible', 'observaciones_bloqueo',
                'asesor_ventas_id', 'soporte_tecnico_id'
            ]
            
            update_values = {}
            for field in allowed_fields:
                if field in config_data:
                    update_values[field] = config_data[field]
            
            if update_values:
                equipment.write(update_values)
                
                # Log de actividad
                equipment.message_post(
                    body=f"Configuración actualizada por {request.env.user.name}",
                    message_type='notification'
                )
            
            return {
                'success': True,
                'message': 'Configuración actualizada correctamente'
            }
            
        except Exception as e:
            _logger.error(f"Error actualizando configuración: {str(e)}")
            return {'error': str(e)}
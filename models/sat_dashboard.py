from odoo import models, fields, api
from datetime import date, timedelta
import logging

# Configuración de logger
_logger = logging.getLogger(__name__)

class SatDashboard(models.Model):
    _name = 'sat.dashboard'
    _description = 'Dashboard de análisis'

    @api.model
    def get_dashboard_data(self):
        # Total de máquinas en `sat.sat`
        total_maquinas = self.env['sat.sat'].search_count([('estado_ventas_id', '!=', 'entregada')])
        _logger.info("Total de máquinas: %s", total_maquinas)

        # Máquinas por disponibilidad
        maquinas_disponibles = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'disponible')])
        maquinas_separadas = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'separada')])
        maquinas_no_disponibles = self.env['sat.sat'].search_count([('disponibilidad_id', '=', 'no_disponible')])
        
        _logger.info("Máquinas - Disponibles: %s, Separadas: %s, No Disponibles: %s", maquinas_disponibles, maquinas_separadas, maquinas_no_disponibles)

        # Máquinas por estado
        maquinas_sin_revisar = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'sin_revisar')])
        maquinas_con_problemas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'con_problemas')])
        maquinas_de_partes = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'de_partes')])        
        maquinas_en_revision = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'en_revision')])
        maquinas_finalizadas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'finalizado')])
        maquinas_para_revision = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'para_revision')])
        maquinas_problemas = self.env['sat.sat'].search_count([('estado_ventas_id', '=', 'con_problemas')])
        _logger.info("Máquinas por estado - Sin Revisar: %s, En Revisión: %s, Finalizadas: %s, Con Problemas: %s", maquinas_sin_revisar, maquinas_en_revision, maquinas_finalizadas, maquinas_problemas)
        

        # Total de máquinas en `alquiler`
        total_maquinas_alquiler = self.env['alquiler'].search_count(['|',('estado_alquiler_id', '!=', 'externo'),('estado_alquiler_id', '!=', 'vendida')])
        alquiler_sin_revisar = self.env['alquiler'].search_count([('estado_alquiler_id', '=', 'sin_revisar')])
        alquiler_alquilada = self.env['alquiler'].search_count([('estado_alquiler_id', '=', 'alquilada')])
        alquiler_revisada = self.env['alquiler'].search_count([('estado_alquiler_id', '=', 'revisada')])
        alquiler_lista = self.env['alquiler'].search_count([('estado_alquiler_id', '=', 'lista')])
        alquiler_con_problemas = self.env['alquiler'].search_count([('estado_alquiler_id', '=', 'con_problemas')])
        _logger.info("Total de máquinas alquiler: %s", total_maquinas_alquiler, alquiler_sin_revisar)

        # Alquiler por Cliente
        alquiler_por_cliente = self.env['alquiler'].read_group(
                ['|',
                 ('estado_alquiler_id', '!=', 'externo'),
                 ('estado_alquiler_id', '!=', 'vendida'),
                 ('cliente_id', '!=', False)], 
                ['cliente_id'], 
                ['cliente_id']
            )
            
        # Procesamiento de datos por cliente
        clientes_totales_alquiler = {}
        for grupo in alquiler_por_cliente:
                if grupo.get('cliente_id') and grupo['cliente_id']:
                    nombre_cliente = grupo['cliente_id'][1]  # Nombre del cliente
                    cantidad = grupo['cliente_id_count']  # Número de alquileres
                    clientes_totales_alquiler[nombre_cliente] = cantidad

        _logger.info("Datos por cliente procesados: %s", clientes_totales_alquiler)

        # Máquinas por asesora
        asesora_data = self.env['sat.sat'].read_group([('asesora_id', '!=', False)], ['asesora_id'], ['asesora_id'])
        asesora_totales = {a['asesora_id'][1]: a['asesora_id_count'] for a in asesora_data}
        _logger.info("Máquinas por asesora: %s", asesora_totales)

        # Total de reparaciones en `reparaciones.reparaciones`
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])
        reparaciones_en_revision = self.env['reparaciones.reparaciones'].search_count([('estado_id', '=', 'en_revision')])
        reparaciones_finalizado = self.env['reparaciones.reparaciones'].search_count([('estado_id', '=', 'finalizado')])
        _logger.info("Total de reparaciones: %s, Reparaciones en revisión: %s", total_reparaciones, reparaciones_en_revision)

        # Reparaciones diarias, mensuales, y anuales
        today = fields.Date.today()
        reparaciones_hoy = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', today)])
        start_month = today.replace(day=1)
        reparaciones_mes = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', start_month)])
        start_year = today.replace(month=1, day=1)
        reparaciones_ano = self.env['reparaciones.reparaciones'].search_count([('create_date', '>=', start_year)])
        _logger.info("Reparaciones - Hoy: %s, Mes: %s, Año: %s", reparaciones_hoy, reparaciones_mes, reparaciones_ano)

        # Reparaciones por técnico
        reparaciones_por_tecnico = self.env['reparaciones.reparaciones'].read_group(
            [('responsable_id', '!=', False)], 
            ['responsable_id'], 
            ['responsable_id']
        )
        tecnicos_totales = {r['responsable_id'][1]: r['responsable_id_count'] for r in reparaciones_por_tecnico}
        _logger.info("Reparaciones por técnico: %s", tecnicos_totales)

        # Total de tickets en `ticket.alquiler`
        total_tickets = self.env['ticket.alquiler'].search_count([])
        tickets_nuevos = self.env['ticket.alquiler'].search_count([('estado', '=', 'nuevo')])
        tickets_proceso = self.env['ticket.alquiler'].search_count([('estado', '=', 'proceso')])
        tickets_finalizado = self.env['ticket.alquiler'].search_count([('estado', '=', 'finalizado')])
        
        _logger.info("Total de tickets: %s", total_tickets)

        # Tickets por mes, año y día usando 'agenda'
        tickets_dia = self.env['ticket.alquiler'].search_count([('agenda', '>=', today)])
        tickets_mes = self.env['ticket.alquiler'].search_count([('agenda', '>=', start_month)])
        tickets_ano = self.env['ticket.alquiler'].search_count([('agenda', '>=', start_year)])
        _logger.info("Tickets - Día: %s, Mes: %s, Año: %s", tickets_dia, tickets_mes, tickets_ano)

        # Tickets por Técnico/Responsable
        tickets_por_tecnico = self.env['ticket.alquiler'].read_group(
            [('responsable', '!=', False)], 
            ['responsable'], 
            ['responsable']
        )
        tecnicos_totales_tickets = {t['responsable'][1]: t['responsable_count'] for t in tickets_por_tecnico}
        _logger.info("Tickets por técnico: %s", tecnicos_totales_tickets)

        # Tickets por Cliente
        tickets_por_cliente = self.env['ticket.alquiler'].read_group(
            [('partner_id', '!=', False)], 
            ['partner_id'], 
            ['partner_id']
        )
        clientes_totales_tickets = {c['partner_id'][1]: c['partner_id_count'] for c in tickets_por_cliente}
        _logger.info("Tickets por cliente: %s", clientes_totales_tickets)

        # Tickets por Máquina
        tickets_por_maquina = self.env['ticket.alquiler'].read_group(
            [('product_alquiler', '!=', False)], 
            ['product_alquiler'], 
            ['product_alquiler']
        )
        maquinas_totales_tickets = {m['product_alquiler'][1]: m['product_alquiler_count'] for m in tickets_por_maquina}
        _logger.info("Tickets por máquina: %s", maquinas_totales_tickets)

        # Tickets por mes en el año actual
        tickets_por_mes = {}
        for mes in range(1, 13):
            inicio_mes = date(today.year, mes, 1)
            if mes == 12:
                fin_mes = date(today.year + 1, 1, 1)
            else:
                fin_mes = date(today.year, mes + 1, 1)
            tickets_count_mes = self.env['ticket.alquiler'].search_count([
                ('agenda', '>=', inicio_mes),
                ('agenda', '<', fin_mes)
            ])
            tickets_por_mes[mes] = tickets_count_mes
        _logger.info("Tickets por mes: %s", tickets_por_mes)

        # Tickets por año en los últimos 5 años
        tickets_por_año = {}
        for i in range(5):
            año = today.year - i
            inicio_año = date(año, 1, 1)
            fin_año = date(año + 1, 1, 1)
            tickets_count_año = self.env['ticket.alquiler'].search_count([
                ('agenda', '>=', inicio_año),
                ('agenda', '<', fin_año)
            ])
            tickets_por_año[año] = tickets_count_año
        _logger.info("Tickets por año: %s", tickets_por_año)

        try:
            # Obtener todos los tickets con sus fechas y técnicos
            tickets_por_fecha = {}
            tickets = self.env['ticket.alquiler'].search([('agenda', '!=', False), ('responsable', '!=', False)])
            
            for ticket in tickets:
                if ticket.agenda:
                    fecha_str = fields.Date.to_string(ticket.agenda)  # Convertir a formato YYYY-MM-DD
                    if fecha_str not in tickets_por_fecha:
                        tickets_por_fecha[fecha_str] = []
                    
                    if ticket.responsable:
                        tickets_por_fecha[fecha_str].append({
                            'tecnico': ticket.responsable.id,
                            'tecnico_nombre': ticket.responsable.name,
                        })
            
            _logger.info("Tickets por fecha procesados: %s", tickets_por_fecha)
            
        except Exception as e:
            _logger.error("Error al procesar tickets por fecha: %s", str(e))
            tickets_por_fecha = {}

        # Reparaciones por fecha
        try:
            reparaciones_por_fecha = {}
            reparaciones = self.env['reparaciones.reparaciones'].search([('create_date', '!=', False), ('responsable_id', '!=', False)])
            
            for reparacion in reparaciones:
                if reparacion.create_date:
                    fecha_str = fields.Date.to_string(reparacion.create_date)  # Convertir a formato YYYY-MM-DD
                    if fecha_str not in reparaciones_por_fecha:
                        reparaciones_por_fecha[fecha_str] = []
                    
                    if reparacion.responsable_id:
                        reparaciones_por_fecha[fecha_str].append({
                            'tecnico': reparacion.responsable_id.id,
                            'tecnico_nombre': reparacion.responsable_id.name,
                        })
            
            _logger.info("Reparaciones por fecha procesadas: %s", reparaciones_por_fecha)
            
        except Exception as e:
            _logger.error("Error al procesar reparaciones por fecha: %s", str(e))
            reparaciones_por_fecha = {}

        # DATOS DEL SISTEMA DE BLOQUEO
        equipos_activos = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', 'activo'),
        ])

        equipos_suspendidos = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', 'suspendido'),
        ])

        equipos_bloqueados = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', 'bloqueado'),
        ])

        equipos_no_accesibles = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', 'no_accesible'),
        ])

        equipos_pendiente_bloqueo = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', 'pendiente_bloqueo'),
        ])

        equipos_pendiente_desbloqueo = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', 'pendiente_desbloqueo'),
        ])

        # Equipos que requieren atención inmediata
        equipos_atencion = self.env['alquiler'].search([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', 'in', ['pendiente_bloqueo', 'pendiente_desbloqueo', 'no_accesible']),
        ], limit=10, order='fecha_bloqueo desc')

        equipos_atencion_data = []
        for equipo in equipos_atencion:
            equipos_atencion_data.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'motivo': equipo.motivo_bloqueo or '',
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'direccion': equipo.direccion or '',
                'contacto': equipo.contacto_id or '',
                'celular': equipo.celular or '',
            })

        # Estados de bloqueo por porcentaje (para gráficos)
        total_alquilados = self.env['alquiler'].search_count([
            ('estado_alquiler_id', '=', 'alquilada'),
        ])

        bloqueo_stats = {
            'activos': equipos_activos,
            'suspendidos': equipos_suspendidos,
            'bloqueados': equipos_bloqueados,
            'no_accesibles': equipos_no_accesibles,
            'pendiente_bloqueo': equipos_pendiente_bloqueo,
            'pendiente_desbloqueo': equipos_pendiente_desbloqueo,
            'total': total_alquilados,
        }

        _logger.info("Datos de bloqueo calculados: %s", bloqueo_stats)

        # Crear el diccionario de retorno
        data = {
            'total_maquinas': total_maquinas,
            'maquinas_disponibles': maquinas_disponibles,
            'maquinas_separadas': maquinas_separadas,
            'maquinas_no_disponibles': maquinas_no_disponibles,
            'maquinas_sin_revisar': maquinas_sin_revisar,
            'maquinas_para_revision': maquinas_para_revision,
            'maquinas_en_revision': maquinas_en_revision,
            'maquinas_finalizadas': maquinas_finalizadas,
            'maquinas_con_problemas': maquinas_con_problemas,
            'maquinas_de_partes': maquinas_de_partes,
            'asesora_totales': asesora_totales,
            'total_reparaciones': total_reparaciones,
            'reparaciones_en_revision': reparaciones_en_revision,
            'reparaciones_finalizado': reparaciones_finalizado,
            'reparaciones_hoy': reparaciones_hoy,
            'reparaciones_mes': reparaciones_mes,
            'reparaciones_ano': reparaciones_ano,
            'reparaciones_por_fecha': reparaciones_por_fecha,
            'tecnicos_totales': tecnicos_totales,
            'total_tickets': total_tickets,
            'tickets_nuevos': tickets_nuevos,
            'tickets_proceso': tickets_proceso,
            'tickets_finalizado': tickets_finalizado,
            'tickets_dia': tickets_dia,
            'tickets_mes': tickets_mes,
            'tickets_ano': tickets_ano,
            'tickets_por_fecha': tickets_por_fecha,
            'tecnicos_totales_tickets': tecnicos_totales_tickets,
            'clientes_totales_tickets': clientes_totales_tickets,
            'maquinas_totales_tickets': maquinas_totales_tickets,
            'tickets_por_mes': tickets_por_mes,
            'tickets_por_año': tickets_por_año,
            'total_maquinas_alquiler': total_maquinas_alquiler,
            'clientes_totales_alquiler': clientes_totales_alquiler,
            'alquiler_por_cliente': alquiler_por_cliente,
            'alquiler_sin_revisar': alquiler_sin_revisar, 
            'alquiler_alquilada': alquiler_alquilada,
            'alquiler_revisada': alquiler_revisada,
            'alquiler_lista': alquiler_lista,
            'alquiler_con_problemas': alquiler_con_problemas,
            # NUEVOS DATOS DE BLOQUEO
            'equipos_activos': equipos_activos,
            'equipos_suspendidos': equipos_suspendidos,
            'equipos_bloqueados': equipos_bloqueados,
            'equipos_no_accesibles': equipos_no_accesibles,
            'equipos_pendiente_bloqueo': equipos_pendiente_bloqueo,
            'equipos_pendiente_desbloqueo': equipos_pendiente_desbloqueo,
            'total_equipos_alquilados_activos': total_alquilados,
            'equipos_atencion': equipos_atencion_data,
            'bloqueo_stats': bloqueo_stats,
        }

        # Imprimir el diccionario completo para verificar que contiene todos los datos
        _logger.info("Datos del dashboard: %s", data)

        return data

    @api.model
    def get_bloqueo_data(self):
        """
        Método específico para obtener datos del sistema de bloqueo
        Útil para actualizaciones independientes del dashboard principal
        """
        try:
            # Obtener datos del modelo alquiler usando los métodos ya existentes
            dashboard_data = self.env['alquiler'].get_dashboard_data_alquilados()
            
            # Equipos que requieren atención
            equipos_criticos = self.env['alquiler'].search([
                ('estado_alquiler_id', '=', 'alquilada'),
                ('estado_bloqueo', 'in', ['pendiente_bloqueo', 'pendiente_desbloqueo', 'no_accesible'])
            ], limit=20, order='fecha_bloqueo desc')
            
            equipos_criticos_data = []
            for equipo in equipos_criticos:
                equipos_criticos_data.append({
                    'id': equipo.id,
                    'serie': equipo.serie,
                    'cliente': equipo.cliente_id.name if equipo.cliente_id else 'Sin cliente',
                    'modelo': equipo.name.name if equipo.name else 'Sin modelo',
                    'estado_bloqueo': equipo.estado_bloqueo,
                    'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                    'motivo': equipo.motivo_bloqueo or 'Sin motivo especificado',
                    'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                    'direccion': equipo.direccion or 'Sin dirección',
                    'contacto': equipo.contacto_id or 'Sin contacto',
                    'celular': equipo.celular or 'Sin teléfono',
                    'ip_equipo': equipo.ip_equipo or 'No configurada',
                    'acceso_remoto': equipo.acceso_remoto_disponible,
                    'puede_suspender': equipo.estado_bloqueo == 'activo',
                    'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                    'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido']
                })

            # Resumen ejecutivo
            total_equipos = dashboard_data.get('total_alquilados', 0)
            equipos_problemas = dashboard_data.get('equipos_suspendidos', 0) + \
                              dashboard_data.get('equipos_bloqueados', 0) + \
                              dashboard_data.get('equipos_no_accesibles', 0) + \
                              dashboard_data.get('pendientes_bloqueo', 0) + \
                              dashboard_data.get('pendientes_desbloqueo', 0)

            porcentaje_problemas = (equipos_problemas / total_equipos * 100) if total_equipos > 0 else 0

            result = {
                'success': True,
                'dashboard_data': dashboard_data,
                'equipos_criticos': equipos_criticos_data,
                'resumen': {
                    'total_equipos': total_equipos,
                    'equipos_con_problemas': equipos_problemas,
                    'porcentaje_problemas': round(porcentaje_problemas, 1),
                    'equipos_operativos': dashboard_data.get('equipos_activos', 0)
                },
                'timestamp': fields.Datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            }

            _logger.info("Datos de bloqueo obtenidos exitosamente: %s equipos críticos", len(equipos_criticos_data))
            return result

        except Exception as e:
            _logger.error("Error al obtener datos de bloqueo: %s", str(e))
            return {
                'success': False,
                'error': str(e),
                'dashboard_data': {},
                'equipos_criticos': [],
                'timestamp': fields.Datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            }

    @api.model
    def accion_bloqueo_rapida(self, equipo_id, accion, motivo=None):
        """
        Método para ejecutar acciones de bloqueo rápidas desde el dashboard
        
        Args:
            equipo_id (int): ID del equipo
            accion (str): 'suspender', 'bloquear', 'desbloquear'
            motivo (str): Motivo de la acción
        
        Returns:
            dict: Resultado de la operación
        """
        try:
            equipo = self.env['alquiler'].browse(equipo_id)
            if not equipo.exists():
                return {'success': False, 'error': 'Equipo no encontrado'}

            usuario_id = self.env.user.id
            
            if accion == 'suspender':
                result = equipo.action_suspender_servicio(motivo, usuario_id)
            elif accion == 'bloquear':
                result = equipo.action_bloquear_equipo(motivo, usuario_id)
            elif accion == 'desbloquear':
                result = equipo.action_desbloquear_equipo(motivo, usuario_id)
            else:
                return {'success': False, 'error': 'Acción no válida'}

            if result:
                _logger.info(f"Acción {accion} ejecutada en equipo {equipo.serie} por usuario {self.env.user.name}")
                return {
                    'success': True, 
                    'message': f'Acción {accion} ejecutada exitosamente',
                    'nuevo_estado': equipo.estado_bloqueo
                }
            else:
                return {'success': False, 'error': 'Error al ejecutar la acción'}

        except Exception as e:
            _logger.error(f"Error en accion_bloqueo_rapida: {str(e)}")
            return {'success': False, 'error': str(e)}
from odoo import api, fields, models, _
from datetime import datetime, timedelta
import calendar
import logging
import json
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
import pandas as pd
import math

_logger = logging.getLogger(__name__)

class EquipmentTechnicianPerformanceReport(models.Model):
    _name = 'equipment.technician.performance.report'
    _description = 'Informe de Evaluación de Rendimiento de Técnicos'
    _rec_name = 'name'
    _order = 'date_from desc, id desc'
    
    name = fields.Char(string='Nombre', required=True, copy=False, readonly=True, default=lambda self: _('Nuevo'))
    date_from = fields.Date(string='Fecha Desde', required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string='Fecha Hasta', required=True, default=lambda self: self._default_date_to())
    user_id = fields.Many2one('res.users', string='Generado por', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Generado'),
        ('sent', 'Enviado')
    ], string='Estado', default='draft', tracking=True)
    
    # Parámetros de configuración
    critical_days = fields.Integer(string='Días Críticos Entre Visitas', default=2,
                                   help='Número de días entre visitas que se considera problemático')
    
    technician_ids = fields.Many2many('res.users', string='Filtrar por Técnicos', 
                                      domain=[('share', '=', False)])
    
    # Datos del análisis
    total_technicians = fields.Integer(string='Total Técnicos Analizados', readonly=True)
    total_rental_machines = fields.Integer(string='Total Máquinas en Alquiler', readonly=True)
    problematic_visits_count = fields.Integer(string='Visitas Problemáticas', readonly=True)
    
    # Datos de rendimiento de técnicos
    technician_performance = fields.Text(string='Rendimiento de Técnicos', readonly=True)
    
    # Datos de equipos problemáticos
    problematic_equipment = fields.Text(string='Equipos con Servicio Deficiente', readonly=True)
    
    # Campos para guardar datos de gráficos
    chart_data = fields.Text(string='Datos de Gráficos', readonly=True)
    
    @api.model
    def _default_date_from(self):
        """Establece la fecha de inicio al primer día del mes actual"""
        today = fields.Date.today()
        return today.replace(day=1)
    
    @api.model
    def _default_date_to(self):
        """Establece la fecha de fin al último día del mes actual"""
        today = fields.Date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.replace(day=last_day)
    
    @api.model
    def create(self, vals):
        """Sobreescribe create para asignar nombre secuencial"""
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('equipment.technician.performance.report') or _('Nuevo')
        return super(EquipmentTechnicianPerformanceReport, self).create(vals)
    
    def action_generate_report(self):
        """Genera el informe de evaluación de rendimiento de técnicos"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo puede generarse un informe que esté en estado Borrador.'))
        
        # Analiza los datos de servicios en los equipos de alquiler
        self._analyze_technician_performance()
        
        # Genera los datos para los gráficos
        self._generate_chart_data()
        
        # Marca el reporte como generado
        self.write({
            'state': 'generated'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.technician.performance.report',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }
    
    def action_send_report(self):
        """Envía el informe por correo electrónico a los destinatarios configurados"""
        self.ensure_one()
        if self.state != 'generated':
            raise UserError(_('Solo puede enviarse un informe que esté en estado Generado.'))
        
        # La lógica de envío de correo se implementará por XML
        self.write({
            'state': 'sent'
        })
        
        return True
    
    def _analyze_technician_performance(self):
        """Analiza el rendimiento de los técnicos basado en visitas repetidas a equipos en alquiler"""
        self.ensure_one()
        
        # Obtener máquinas que están específicamente en estado 'alquilada'
        rental_machines = self.env['product.product'].search([
            ('estado_alquiler_id', '=', 'alquilada')
        ])
        total_rental_machines = len(rental_machines)
        
        if not rental_machines:
            # No hay máquinas en alquiler para analizar
            self.write({
                'total_technicians': 0,
                'total_rental_machines': 0,
                'problematic_visits_count': 0,
                'technician_performance': '[]',
                'problematic_equipment': '[]',
                'chart_data': '{}'
            })
            return
        
        # Dominio base para tickets de equipos en alquiler
        domain = [
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', 'in', rental_machines.ids)
        ]
        
        # Agregar filtro de técnicos si está configurado
        if self.technician_ids:
            domain.append(('responsable', 'in', self.technician_ids.ids))
        
        # Obtener todos los tickets que cumplen con el dominio
        tickets = self.env['ticket.alquiler'].search(domain, order='agenda asc')
        
        # Tipos de servicio a monitorear para evaluar si necesitan seguimiento
        service_types_to_monitor = ['instalacion', 'mantenimiento_preventivo', 'mantenimiento_correctivo', 
                                   'cambio_repuestos', 'revision']
        
        # Diccionario para clasificar problemas por tipo de servicio
        service_reason_map = {
            'instalacion': {
                'reason': 'Problemas con la instalación inicial',
                'suggestion': 'Verificar procedimiento de instalación y capacitación del técnico'
            },
            'mantenimiento_preventivo': {
                'reason': 'Mantenimiento preventivo incompleto o mal ejecutado',
                'suggestion': 'Revisar lista de verificación de mantenimiento preventivo'
            },
            'mantenimiento_correctivo': {
                'reason': 'Reparación incorrecta o incompleta',
                'suggestion': 'Revisar procedimientos de diagnóstico y reparación'
            },
            'cambio_repuestos': {
                'reason': 'Repuestos mal instalados o defectuosos',
                'suggestion': 'Verificar calidad de repuestos y procedimiento de instalación'
            },
            'revision': {
                'reason': 'Revisión superficial, no se detectaron problemas existentes',
                'suggestion': 'Implementar lista de verificación más exhaustiva'
            },
            'default': {
                'reason': 'Servicio técnico incompleto o mal ejecutado',
                'suggestion': 'Revisar procedimientos y capacitación del técnico'
            }
        }
        
        # Organizar tickets por equipo para análisis cronológico
        equipment_tickets = {}
        
        for ticket in tickets:
            # Clave única para identificar equipo (ID y número de serie)
            equipment_key = (ticket.product_alquiler.id, ticket.serie_id_r or '')
            
            if equipment_key not in equipment_tickets:
                equipment_tickets[equipment_key] = []
            
            # Guardar datos relevantes del ticket
            equipment_tickets[equipment_key].append({
                'id': ticket.id,
                'date': ticket.agenda,
                'description': ticket.description or '',
                'technician_id': ticket.responsable.id if ticket.responsable else False,
                'technician_name': ticket.responsable.name if ticket.responsable else 'Sin asignar',
                'partner_id': ticket.partner_id.id if ticket.partner_id else False,
                'partner_name': ticket.partner_id.name if ticket.partner_id else 'Sin cliente',
                'model': ticket.product_alquiler.name.name if ticket.product_alquiler.name else 'Sin modelo',
                'serie': ticket.serie_id_r or '',
                'type': ticket.tipo_servicio_id or 'revision'  # Valor por defecto si es None
            })
        
        # Contadores y datos para análisis
        problematic_visits_count = 0
        problematic_sequences = []
        technician_performance = {}
        problematic_equipment_list = []
        
        # Analizar secuencias de visitas por equipo
        for eq_key, tickets_list in equipment_tickets.items():
            if len(tickets_list) <= 1:
                continue  # Ignorar equipos con una sola visita
            
            # Ordenar tickets por fecha
            sorted_tickets = sorted(tickets_list, key=lambda x: x['date'] or fields.Datetime.now())
            
            # Analizar secuencias de visitas
            for i in range(1, len(sorted_tickets)):
                current = sorted_tickets[i]
                previous = sorted_tickets[i-1]
                
                # Asegurar que ambas fechas existen
                if not current['date'] or not previous['date']:
                    continue
                
                # Calcular días entre visitas
                days_diff = (current['date'] - previous['date']).days
                
                # Verificar si es una visita problemática después de ciertos tipos de servicio
                if previous['type'] in service_types_to_monitor and days_diff <= self.critical_days:
                    problematic_visits_count += 1
                    
                    # Obtener razón y sugerencia según el tipo de servicio previo
                    service_type = previous['type']
                    reason_data = service_reason_map.get(service_type, service_reason_map['default'])
                    
                    # Registro detallado de la secuencia problemática
                    problematic_sequence = {
                        'equipment_id': eq_key[0],
                        'serie': eq_key[1],
                        'model': previous['model'],
                        'client': previous['partner_name'],
                        'first_service': {
                            'id': previous['id'],
                            'date': previous['date'].strftime('%Y-%m-%d %H:%M:%S'),
                            'type': previous['type'],
                            'technician_id': previous['technician_id'],
                            'technician_name': previous['technician_name'],
                            'description': previous['description']
                        },
                        'second_service': {
                            'id': current['id'],
                            'date': current['date'].strftime('%Y-%m-%d %H:%M:%S'),
                            'type': current['type'],
                            'technician_id': current['technician_id'],
                            'technician_name': current['technician_name'],
                            'description': current['description']
                        },
                        'days_between': days_diff,
                        'reason': reason_data['reason'],
                        'suggestion': reason_data['suggestion']
                    }
                    
                    problematic_sequences.append(problematic_sequence)
                    
                    # Actualizar estadísticas del técnico que hizo el primer servicio
                    if previous['technician_id']:
                        tech_id = previous['technician_id']
                        if tech_id not in technician_performance:
                            technician_performance[tech_id] = {
                                'id': tech_id,
                                'name': previous['technician_name'],
                                'total_services': 0,
                                'problematic_services': 0,
                                'equipment_count': set(),
                                'client_count': set(),
                                'service_types': {},
                                'problematic_by_type': {}
                            }
                        
                        # Incrementar contador de servicios problemáticos
                        technician_performance[tech_id]['problematic_services'] += 1
                        technician_performance[tech_id]['equipment_count'].add(eq_key)
                        technician_performance[tech_id]['client_count'].add(previous['partner_id'])
                        
                        # Registrar por tipo de servicio
                        if service_type not in technician_performance[tech_id]['problematic_by_type']:
                            technician_performance[tech_id]['problematic_by_type'][service_type] = 0
                        technician_performance[tech_id]['problematic_by_type'][service_type] += 1
                    
                    # Incluir en equipo problemático si no está ya
                    equipment_already_listed = False
                    for equip in problematic_equipment_list:
                        if equip['id'] == eq_key[0] and equip['serie'] == eq_key[1]:
                            equipment_already_listed = True
                            equip['problematic_sequences'] += 1
                            break
                    
                    if not equipment_already_listed:
                        product = self.env['product.product'].browse(eq_key[0])
                        problematic_equipment_list.append({
                            'id': eq_key[0],
                            'serie': eq_key[1],
                            'model': product.name.name if product.name else 'Sin modelo',
                            'partner': sorted_tickets[0]['partner_name'],
                            'problematic_sequences': 1,
                            'services_count': len(sorted_tickets)
                        })
        
        # Contar total de servicios por técnico para estadísticas completas
        all_techs = {}
        for ticket in tickets:
            tech_id = ticket.responsable.id
            if not tech_id:
                continue
                
            if tech_id not in all_techs:
                all_techs[tech_id] = {
                    'name': ticket.responsable.name,
                    'total_services': 0,
                    'service_types': {}
                }
            
            all_techs[tech_id]['total_services'] += 1
            
            # Contar por tipo de servicio
            service_type = ticket.tipo_servicio_id or 'revision'
            if service_type not in all_techs[tech_id]['service_types']:
                all_techs[tech_id]['service_types'][service_type] = 0
            all_techs[tech_id]['service_types'][service_type] += 1
        
        # Completar estadísticas de técnicos
        processed_technicians = []
        for tech_id, tech_data in technician_performance.items():
            # Agregar total de servicios desde estadísticas generales
            if tech_id in all_techs:
                tech_data['total_services'] = all_techs[tech_id]['total_services']
                tech_data['service_types'] = all_techs[tech_id]['service_types']
            
            # Calcular tasas y convertir conjuntos a contadores
            failure_rate = (tech_data['problematic_services'] / tech_data['total_services'] * 100) if tech_data['total_services'] > 0 else 0
            
            processed_tech = {
                'id': tech_id,
                'name': tech_data['name'],
                'total_services': tech_data['total_services'],
                'problematic_services': tech_data['problematic_services'],
                'failure_rate': round(failure_rate, 2),
                'equipment_count': len(tech_data['equipment_count']),
                'client_count': len(tech_data['client_count']),
                'service_types': tech_data['service_types'],
                'problematic_by_type': tech_data['problematic_by_type'],
                'performance_rating': self._get_performance_rating(failure_rate)
            }
            
            processed_technicians.append(processed_tech)
        
        # Ordenar técnicos por tasa de problemas (descendente)
        processed_technicians = sorted(processed_technicians, key=lambda x: x['failure_rate'], reverse=True)
        
        # Ordenar equipos por número de secuencias problemáticas (descendente)
        problematic_equipment_list = sorted(problematic_equipment_list, 
                                          key=lambda x: x['problematic_sequences'], reverse=True)
        
        # Guardar resultados en el registro
        self.write({
            'total_technicians': len(processed_technicians),
            'total_rental_machines': total_rental_machines,
            'problematic_visits_count': problematic_visits_count,
            'technician_performance': json.dumps(processed_technicians),
            'problematic_equipment': json.dumps(problematic_equipment_list),
            'chart_data': json.dumps({
                'problematic_sequences': problematic_sequences,
                'technician_performance': processed_technicians,
                'problematic_equipment': problematic_equipment_list
            })
        })
    
    def _get_performance_rating(self, failure_rate):
        """Determina la calificación de rendimiento basada en la tasa de problemas"""
        if failure_rate < 5:
            return 'excellent'
        elif failure_rate < 10:
            return 'good'
        elif failure_rate < 20:
            return 'average'
        elif failure_rate < 30:
            return 'below_average'
        else:
            return 'poor'
    
    def _generate_chart_data(self):
        """Genera datos para gráficos y visualizaciones"""
        self.ensure_one()
        
        # Si ya hay datos de gráficos, los usamos
        if not self.chart_data:
            return
            
        chart_data = json.loads(self.chart_data)
        
        # 1. Gráfico de problemas por tipo de servicio previo
        service_type_counts = {}
        for sequence in chart_data.get('problematic_sequences', []):
            service_type = sequence['first_service']['type']
            if service_type not in service_type_counts:
                service_type_counts[service_type] = 0
            service_type_counts[service_type] += 1
        
        # Mapeo de tipos de servicio a nombres más amigables
        service_type_labels = {
            'instalacion': 'Instalación',
            'mantenimiento_preventivo': 'Mant. Preventivo',
            'mantenimiento_correctivo': 'Mant. Correctivo',
            'cambio_repuestos': 'Cambio Repuestos',
            'revision': 'Revisión',
            'retiro': 'Retiro',
            'remoto': 'Asistencia Remota',
            'dejar_toner': 'Entrega Toner'
        }
        
        # Convertir claves a nombres amigables
        service_type_counts_friendly = {
            service_type_labels.get(k, k): v for k, v in service_type_counts.items()
        }
        
        service_chart_data = {
            'labels': list(service_type_counts_friendly.keys()),
            'data': list(service_type_counts_friendly.values()),
        }
        
        # 2. Gráfico de rendimiento de técnicos
        technicians_data = sorted(
            chart_data.get('technician_performance', []), 
            key=lambda x: x['failure_rate'], 
            reverse=True
        )[:10]  # Top 10 técnicos con más problemas
        
        technician_chart_data = {
            'labels': [t['name'] for t in technicians_data],
            'failure_rates': [t['failure_rate'] for t in technicians_data],
            'service_counts': [t['total_services'] for t in technicians_data],
            'problematic_counts': [t['problematic_services'] for t in technicians_data]
        }
        
        # 3. Gráfico de días entre servicios problemáticos
        days_distribution = {}
        for sequence in chart_data.get('problematic_sequences', []):
            days = sequence['days_between']
            if days not in days_distribution:
                days_distribution[days] = 0
            days_distribution[days] += 1
        
        # Ordenar por número de días
        days_sorted = sorted(days_distribution.items())
        
        days_chart_data = {
            'labels': [str(day) for day, _ in days_sorted],
            'data': [count for _, count in days_sorted],
        }
        
        # 4. Gráfico de desempeño por técnico y tipo de servicio
        tech_performance_by_service = {}
        for tech in chart_data.get('technician_performance', []):
            if tech['problematic_services'] == 0:
                continue
                
            tech_name = tech['name']
            tech_performance_by_service[tech_name] = {}
            
            for service_type, count in tech.get('problematic_by_type', {}).items():
                service_name = service_type_labels.get(service_type, service_type)
                tech_performance_by_service[tech_name][service_name] = count
        
        # Preparar datos para gráfico
        performance_labels = []
        performance_datasets = []
        
        # Obtener todos los tipos de servicio únicos
        all_service_types = set()
        for tech_data in tech_performance_by_service.values():
            all_service_types.update(tech_data.keys())
        
        for service_type in all_service_types:
            dataset = {
                'label': service_type,
                'data': []
            }
            
            for tech_name in tech_performance_by_service.keys():
                if performance_labels.count(tech_name) == 0:
                    performance_labels.append(tech_name)
                
                dataset['data'].append(tech_performance_by_service[tech_name].get(service_type, 0))
            
            performance_datasets.append(dataset)
        
        performance_chart_data = {
            'labels': performance_labels,
            'datasets': performance_datasets
        }
        
        # Actualizar los datos de gráficos con esta información adicional
        updated_chart_data = chart_data.copy()
        updated_chart_data.update({
            'service_type_chart': service_chart_data,
            'technician_chart': technician_chart_data,
            'days_chart': days_chart_data,
            'performance_chart': performance_chart_data
        })
        
        self.chart_data = json.dumps(updated_chart_data)
from odoo import api, fields, models, _, SUPERUSER_ID
from datetime import datetime, timedelta
import calendar
import logging
import json
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
import base64
from io import BytesIO
import pandas as pd
import math
import io
try:
    import matplotlib
    matplotlib.use('Agg')  # Backend que no requiere interfaz gráfica
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_ENABLED = True
except ImportError:
    MATPLOTLIB_ENABLED = False
_logger = logging.getLogger(__name__)

class EquipmentVisitReport(models.Model):
    _name = 'equipment.visit.report'
    _description = 'Informe de Visitas Técnicas por Equipo'
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
    chart_images = fields.Text("Imágenes de gráficos en base64", help="Almacena las imágenes de los gráficos en formato JSON con base64")
    # Datos del análisis
    total_visits = fields.Integer(string='Total de Visitas', readonly=True)
    recurring_equipment_count = fields.Integer(string='Equipos Recurrentes', readonly=True)
    first_visit_resolution_rate = fields.Float(string='Tasa de Resolución en Primera Visita (%)', readonly=True)
    average_response_time = fields.Float(string='Tiempo Promedio de Respuesta (días)', readonly=True)
    
    # Archivos generados
    report_data = fields.Binary(string='Datos del Reporte', attachment=True)
    report_filename = fields.Char(string='Nombre del Archivo')
    
    # Destinatarios
    recipient_ids = fields.Many2many('res.users', string='Destinatarios', domain=[('share', '=', False)])
    email_to = fields.Char(string='Destinatarios Adicionales', help='Separados por coma')
    
    # Campos para estadísticas
    critical_equipment_count = fields.Integer(string='Equipos Críticos', readonly=True, help='Equipos con 3 o más visitas')
    top_client_id = fields.Many2one('res.partner', string='Cliente con Más Visitas', readonly=True)
    top_client_visit_count = fields.Integer(string='Visitas del Cliente Principal', readonly=True)
    
    # Campos para guardar datos de gráficos
    chart_data = fields.Text(string='Datos de Gráficos', readonly=True)
    
    # Configuración del reporte
    visit_threshold = fields.Integer(string='Umbral de Visitas Críticas', default=3, 
                                    help='Número de visitas a partir del cual un equipo se considera crítico')
    same_issue_days = fields.Integer(string='Días para Considerar Mismo Problema', default=7,
                                    help='Si hay otra visita dentro de este período por el mismo problema, se considera recurrente')
    
    # NUEVOS CAMPOS PARA ANÁLISIS DE TÉCNICOS
    technician_evaluation = fields.Text(string='Evaluación de Técnicos', readonly=True)
    problematic_technicians = fields.Many2many('res.users', 'report_problematic_techs_rel', 
                                              string='Técnicos con Problemas', readonly=True)
    
    # Análisis por tipo de servicio
    service_type_stats = fields.Text(string='Estadísticas por Tipo de Servicio', readonly=True)
    
    # Análisis de secuencias problemáticas
    problematic_sequences = fields.Text(string='Secuencias de Servicio Problemáticas', readonly=True)
    
    # Indicadores de rendimiento por tipo de servicio
    post_installation_visit_rate = fields.Float(string='Tasa de Visitas Post-Instalación (%)', readonly=True,
                                               help='Porcentaje de instalaciones que requirieron visitas adicionales en periodo corto')
    post_maintenance_visit_rate = fields.Float(string='Tasa de Visitas Post-Mantenimiento (%)', readonly=True,
                                              help='Porcentaje de mantenimientos que requirieron visitas adicionales en periodo corto')
    post_repair_visit_rate = fields.Float(string='Tasa de Visitas Post-Reparación (%)', readonly=True,
                                         help='Porcentaje de reparaciones que requirieron visitas adicionales en periodo corto')
        
    post_review_visit_rate = fields.Float(string='Tasa de Visitas Post-Revisión (%)', readonly=True,
                                          help='Porcentaje de revisiones que requirieron visitas adicionales en periodo corto')

    
    def generate_chart_images(self):
        """Genera las imágenes de los gráficos para el PDF."""
        if not MATPLOTLIB_ENABLED:
            _logger.warning("Matplotlib no está instalado. No se pueden generar imágenes de gráficos.")
            return False
        
        chart_images = {}
        
        # Obtener datos de los gráficos
        chart_data = json.loads(self.chart_data or '{}')
        
        # 1. Gráfico de equipos
        if 'equipment_chart' in chart_data:
            equipment_data = chart_data['equipment_chart']
            labels = equipment_data.get('labels', [])
            data = equipment_data.get('data', [])
            threshold = equipment_data.get('critical_threshold', 3)
            
            if labels and data:
                plt.figure(figsize=(8, 5))
                colors = ['#e74c3c' if d >= threshold else '#3498db' for d in data]
                plt.bar(labels, data, color=colors)
                plt.xticks(rotation=45, ha='right')
                plt.ylabel('Número de Visitas')
                plt.title('Equipos con Más Visitas')
                plt.tight_layout()
                
                # Convertir a PNG
                img_data = io.BytesIO()
                plt.savefig(img_data, format='png', dpi=100)
                img_data.seek(0)
                chart_images['equipment_chart'] = base64.b64encode(img_data.getvalue()).decode('utf-8')
                plt.close()
        
        # 2. Gráfico de clientes
        if 'client_chart' in chart_data:
            client_data = chart_data['client_chart']
            labels = client_data.get('labels', [])
            data = client_data.get('data', [])
            
            if labels and data:
                plt.figure(figsize=(8, 5))
                colors = plt.cm.Paired(np.linspace(0, 1, len(data)))
                plt.pie(data, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
                plt.axis('equal')
                plt.title('Distribución por Cliente')
                plt.tight_layout()
                
                # Convertir a PNG
                img_data = io.BytesIO()
                plt.savefig(img_data, format='png', dpi=100)
                img_data.seek(0)
                chart_images['client_chart'] = base64.b64encode(img_data.getvalue()).decode('utf-8')
                plt.close()
        
        # 3. Gráfico de tendencia
        if 'trend_chart' in chart_data:
            trend_data = chart_data['trend_chart']
            labels = trend_data.get('labels', [])
            data = trend_data.get('data', [])
            
            if labels and data:
                plt.figure(figsize=(8, 5))
                plt.plot(labels, data, marker='o', color='#1abc9c', linewidth=2)
                plt.fill_between(labels, data, alpha=0.2, color='#1abc9c')
                plt.xticks(rotation=45, ha='right')
                plt.ylabel('Días')
                plt.title('Tendencia de Tiempos de Respuesta')
                plt.tight_layout()
                
                # Convertir a PNG
                img_data = io.BytesIO()
                plt.savefig(img_data, format='png', dpi=100)
                img_data.seek(0)
                chart_images['trend_chart'] = base64.b64encode(img_data.getvalue()).decode('utf-8')
                plt.close()
        
        # 4. Gráfico de problemas
        if 'problems_chart' in chart_data:
            problems_data = chart_data['problems_chart']
            labels = problems_data.get('labels', [])
            data = problems_data.get('data', [])
            
            if labels and data:
                plt.figure(figsize=(8, 5))
                
                # Crear gráfico de radar
                angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
                data = data + [data[0]]  # Cerrar el gráfico
                angles = angles + [angles[0]]  # Cerrar el gráfico
                labels = labels + [labels[0]]  # Cerrar el gráfico
                
                fig, ax = plt.subplots(figsize=(8, 5), subplot_kw=dict(polar=True))
                ax.plot(angles, data, color='#f39c12', linewidth=2)
                ax.fill(angles, data, color='#f39c12', alpha=0.2)
                ax.set_thetagrids(np.degrees(angles[:-1]), labels[:-1])
                plt.title('Categorías de Problemas')
                plt.tight_layout()
                
                # Convertir a PNG
                img_data = io.BytesIO()
                plt.savefig(img_data, format='png', dpi=100)
                img_data.seek(0)
                chart_images['problems_chart'] = base64.b64encode(img_data.getvalue()).decode('utf-8')
                plt.close()
        
        # Guardar las imágenes en el registro
        self.write({'chart_images': json.dumps(chart_images)})
        
        return True
    def set_webkit_params(cr, registry):
        env = api.Environment(cr, SUPERUSER_ID, {})
        IrConfigParameter = env['ir.config_parameter']
        IrConfigParameter.set_param('webkit.path', '/usr/local/bin/wkhtmltopdf')
        IrConfigParameter.set_param('webkit.javascriptdelay', '3000')
        IrConfigParameter.set_param('webkit.enablejavascript', 'True')
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
            vals['name'] = self.env['ir.sequence'].next_by_code('equipment.visit.report') or _('Nuevo')
        return super(EquipmentVisitReport, self).create(vals)

    def _get_report_base_filename(self):
        self.ensure_one()
        return f"Informe de Visitas - {self.name}"


    def _generate_chart_data(self):
        """Genera datos para gráficos de análisis"""
        self.ensure_one()
        
        # Obtener todas las visitas técnicas en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', '!=', False)
        ])
        
        # DATOS PARA GRÁFICO 1: Visitas por día/semana
        date_format = '%Y-%m-%d'
        daily_visits = {}
        
        current_date = self.date_from
        while current_date <= self.date_to:
            daily_visits[current_date.strftime(date_format)] = 0
            current_date += relativedelta(days=1)
        
        for ticket in tickets:
            if ticket.agenda:
                visit_date = ticket.agenda.date().strftime(date_format)
                if visit_date in daily_visits:
                    daily_visits[visit_date] += 1
        
        # DATOS PARA GRÁFICO 2: Visitas por tipo de servicio
        service_types = {}
        
        for ticket in tickets:
            service_type = ticket.tipo_servicio_id if hasattr(ticket, 'tipo_servicio_id') else 'sin_especificar'
            
            if service_type not in service_types:
                service_types[service_type] = 0
            
            service_types[service_type] += 1
        
        # DATOS PARA GRÁFICO 3: Visitas por técnico
        technician_visits = {}
        
        for ticket in tickets:
            if ticket.responsable:
                tech_id = ticket.responsable.id
                tech_name = ticket.responsable.name
                
                if tech_id not in technician_visits:
                    technician_visits[tech_id] = {
                        'name': tech_name,
                        'count': 0
                    }
                
                technician_visits[tech_id]['count'] += 1
        
        # DATOS PARA GRÁFICO 4: Visitas por equipo
        equipment_visits = {}
        
        for ticket in tickets:
            eq_id = ticket.product_alquiler.id
            eq_name = ticket.product_alquiler.name.name if hasattr(ticket.product_alquiler, 'name') and hasattr(ticket.product_alquiler.name, 'name') else 'Sin modelo'
            eq_serie = ticket.serie_id_r or 'Sin serie'
            
            eq_key = f"{eq_id}_{eq_serie}"
            eq_label = f"{eq_name} ({eq_serie})"
            
            if eq_key not in equipment_visits:
                equipment_visits[eq_key] = {
                    'label': eq_label,
                    'count': 0,
                    'partner': ticket.partner_id.name if ticket.partner_id else 'Sin cliente',
                    'model': eq_name,
                    'serie': eq_serie,
                    'is_critical': False,
                    'visits': [],
                    'technicians': set(),
                    'problems': []
                }
            
            equipment_visits[eq_key]['count'] += 1
            
            if ticket.responsable:
                equipment_visits[eq_key]['technicians'].add(ticket.responsable.name)
            
            if ticket.description:
                equipment_visits[eq_key]['problems'].append(ticket.description)
            
            equipment_visits[eq_key]['visits'].append({
                'id': ticket.id,
                'date': ticket.agenda,
                'tech_name': ticket.responsable.name if ticket.responsable else 'Sin técnico',
                'tech_id': ticket.responsable.id if ticket.responsable else False
            })
        
        # DATOS PARA GRÁFICO 5: Visitas por cliente
        client_visits = {}
        
        for ticket in tickets:
            if ticket.partner_id:
                client_id = ticket.partner_id.id
                client_name = ticket.partner_id.name
                
                if client_id not in client_visits:
                    client_visits[client_id] = {
                        'name': client_name,
                        'count': 0
                    }
                
                client_visits[client_id]['count'] += 1
        
        # Identificar equipos críticos y procesar datos para gráficos
        equipment_chart = {
            'labels': [],
            'data': [],
            'critical_threshold': self.visit_threshold
        }
        
        client_chart = {
            'labels': [],
            'data': []
        }
        
        special_analysis = []
        table_data = []
        
        # Procesar datos para gráficos y análisis
        for eq_key, eq_data in equipment_visits.items():
            # Determinar si es crítico
            if eq_data['count'] >= self.visit_threshold:
                eq_data['is_critical'] = True
            
            # Datos para gráfico de equipos (solo los 10 con más visitas)
            equipment_chart['labels'].append(eq_data['label'])
            equipment_chart['data'].append(eq_data['count'])
            
            # Determinar si hay visitas cercanas
            has_close_visits = False
            
            if len(eq_data['visits']) > 1:
                sorted_visits = sorted(eq_data['visits'], key=lambda x: x.get('date') or fields.Datetime.now())
                
                for i in range(1, len(sorted_visits)):
                    current_visit = sorted_visits[i]
                    prev_visit = sorted_visits[i-1]
                    
                    if current_visit.get('date') and prev_visit.get('date'):
                        days_diff = (current_visit.get('date') - prev_visit.get('date')).days
                        
                        if days_diff <= self.same_issue_days:
                            has_close_visits = True
                            break
            
            # Determinar problema común
            common_problem = "No especificado"
            if eq_data['problems']:
                # Usar la última descripción como problema común (simplificación)
                common_problem = eq_data['problems'][-1][:50] + "..." if len(eq_data['problems'][-1]) > 50 else eq_data['problems'][-1]
            
            # Datos para tabla
            table_data.append({
                'model': eq_data['model'],
                'serie': eq_data['serie'],
                'partner': eq_data['partner'],
                'visit_count': eq_data['count'],
                'is_critical': eq_data['is_critical'],
                'has_close_visits': has_close_visits,
                'problem': common_problem,
                'technicians': list(eq_data['technicians'])
            })
            
            # Datos para análisis especial
            if eq_data['is_critical'] or has_close_visits:
                special_analysis.append({
                    'model': eq_data['model'],
                    'serie': eq_data['serie'],
                    'partner': eq_data['partner'],
                    'visit_count': eq_data['count'],
                    'common_problem': common_problem,
                    'has_close_visits': has_close_visits,
                    'technicians': list(eq_data['technicians'])
                })
        
        # Ordenar y limitar datos para gráficos
        equipment_chart_data = sorted(zip(equipment_chart['labels'], equipment_chart['data']), 
                                    key=lambda x: x[1], reverse=True)[:10]
        
        equipment_chart['labels'] = [item[0] for item in equipment_chart_data]
        equipment_chart['data'] = [item[1] for item in equipment_chart_data]
        
        # Ordenar y limitar datos para gráfico de clientes
        client_chart_data = sorted([(data['name'], data['count']) for client_id, data in client_visits.items()], 
                                key=lambda x: x[1], reverse=True)[:5]
        
        client_chart['labels'] = [item[0] for item in client_chart_data]
        client_chart['data'] = [item[1] for item in client_chart_data]
        
        
        # Ordenar tabla por cantidad de visitas
        table_data = sorted(table_data, key=lambda x: x['visit_count'], reverse=True)

        # Gráfico de tendencia de tiempos de respuesta (simulado con visitas diarias)
        trend_chart = {
            'labels': list(daily_visits.keys()),
            'data': list(daily_visits.values())
        }

        # Gráfico de problemas más frecuentes
        problem_counts = {}
        for ticket in tickets:
            if ticket.description:
                problem = ticket.description.strip().lower()
                problem_counts[problem] = problem_counts.get(problem, 0) + 1

        sorted_problems = sorted(problem_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        problems_chart = {
            'labels': [p[0].capitalize() for p in sorted_problems],
            'data': [p[1] for p in sorted_problems]
        }

        # ✅ Ahora sí, armar el JSON con todos los gráficos
        chart_data = {
            'equipment_chart': equipment_chart,
            'client_chart': client_chart,
            'table': table_data,
            'special_analysis': special_analysis,
            'trend_chart': trend_chart,
            'problems_chart': problems_chart
        }

        

        
        # Guardar como JSON
        self.write({
            'chart_data': json.dumps(chart_data)
        })
    def action_generate_report(self):
        """Genera el informe de visitas técnicas"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo puede generarse un informe que esté en estado Borrador.'))
        
        # 🔧 Genera las imágenes base64 para el PDF
        self.generate_chart_images()

        # Calcula las estadísticas generales
        self._compute_general_statistics()
        
        # Genera los datos para los gráficos
        self._generate_chart_data()
        
        # NUEVO: Analiza el rendimiento de los técnicos
        self._analyze_technician_performance()
        
        # NUEVO: Analiza secuencias de servicios problemáticas
        self._analyze_service_sequences()
        
        # NUEVO: Genera informe detallado de técnicos
        self._generate_technician_report()
        
        # Marca el reporte como generado
        self.write({
            'state': 'generated'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.visit.report',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }
    def _compute_general_statistics(self):
        """Calcula estadísticas generales de visitas técnicas"""
        self.ensure_one()
        
        # Obtener todas las visitas técnicas en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', '!=', False)
        ])
        
        # Contadores básicos
        total_visits = len(tickets)
        equipment_visits = {}  # Por equipo
        client_visits = {}     # Por cliente
        
        # Tiempos de respuesta
        response_times = []
        first_visit_counts = 0
        resolution_first_visit = 0
        
        # Registrar información de campos para depuración
        if tickets and len(tickets) > 0:
            _logger.info("Campos disponibles en ticket.alquiler: %s", list(tickets[0]._fields.keys()))
        
        # Procesar cada ticket
        for ticket in tickets:
            # Contar por equipo
            eq_key = (ticket.product_alquiler.id, ticket.serie_id_r or '')
            
            if eq_key not in equipment_visits:
                equipment_visits[eq_key] = []
            
            # Verificar estado de resolución
            # Intentar con varios nombres posibles para el campo estado
            is_resolved = False
            
            # Primero verificar si el ticket tiene campos relacionados con finalización
            if hasattr(ticket, 'finalizado'):
                is_resolved = bool(ticket.finalizado)
            elif hasattr(ticket, 'estado') and ticket.estado in ['finalizado', 'terminado', 'done']:
                is_resolved = True
            elif hasattr(ticket, 'state') and ticket.state in ['finalizado', 'terminado', 'done']:
                is_resolved = True
            elif hasattr(ticket, 'stage_id') and ticket.stage_id.name in ['Finalizado', 'Terminado', 'Resuelto']:
                is_resolved = True
            
            equipment_visits[eq_key].append({
                'id': ticket.id,
                'date': ticket.agenda,
                'description': ticket.description,
                'partner_id': ticket.partner_id.id if ticket.partner_id else False,
                'resolved': is_resolved,
                'creation_date': ticket.create_date
            })
            
            # Contar por cliente
            if ticket.partner_id:
                client_id = ticket.partner_id.id
                if client_id not in client_visits:
                    client_visits[client_id] = 0
                client_visits[client_id] += 1
            
            # Calcular tiempo de respuesta (desde creación hasta agenda)
            if ticket.create_date and ticket.agenda:
                response_time = (ticket.agenda - ticket.create_date).total_seconds() / 86400  # Días
                response_times.append(response_time)
        
        # Análisis de equipos recurrentes y críticos
        recurring_equipment_count = 0
        critical_equipment_count = 0
        
        for eq_key, visits in equipment_visits.items():
            # Solo si hay más de una visita al mismo equipo
            if len(visits) > 1:
                # Ordenar visitas por fecha
                sorted_visits = sorted(visits, key=lambda x: x['date'] or fields.Datetime.now())
                
                # Verificar si hay visitas recurrentes (mismo problema)
                recurring = False
                
                for i in range(1, len(sorted_visits)):
                    current = sorted_visits[i]
                    prev = sorted_visits[i-1]
                    
                    # Verificar que ambas fechas existen
                    if current['date'] and prev['date']:
                        days_diff = (current['date'] - prev['date']).days
                        
                        # Si es una visita en plazo corto (mismo problema)
                        if days_diff <= self.same_issue_days:
                            recurring = True
                            break
                
                if recurring:
                    recurring_equipment_count += 1
                
                # Es crítico si supera el umbral de visitas
                if len(visits) >= self.visit_threshold:
                    critical_equipment_count += 1
            
            # Primera visita
            if len(visits) == 1:
                first_visit_counts += 1
                # Si está resuelta en primera visita
                if visits[0]['resolved']:
                    resolution_first_visit += 1
        
        # Encontrar cliente con más visitas
        top_client_id = False
        top_client_visit_count = 0
        
        for client_id, count in client_visits.items():
            if count > top_client_visit_count:
                top_client_id = client_id
                top_client_visit_count = count
        
        # Calcular tasa de resolución en primera visita
        first_visit_resolution_rate = (resolution_first_visit / first_visit_counts * 100) if first_visit_counts > 0 else 0
        
        # Calcular tiempo promedio de respuesta
        average_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Guardar resultados
        self.write({
            'total_visits': total_visits,
            'recurring_equipment_count': recurring_equipment_count,
            'critical_equipment_count': critical_equipment_count,
            'first_visit_resolution_rate': first_visit_resolution_rate,
            'average_response_time': average_response_time,
            'top_client_id': top_client_id,
            'top_client_visit_count': top_client_visit_count
        })
    def action_send_report(self):
        """Envía el informe por correo electrónico a los destinatarios configurados"""
        self.ensure_one()
        if self.state != 'generated':
            raise UserError(_('Solo puede enviarse un informe que esté en estado Generado.'))
        
        if not self.recipient_ids and not self.email_to:
            raise UserError(_('Debe especificar al menos un destinatario para enviar el informe.'))
        
        # Preparar plantilla de correo
        template_id = self.env.ref('sat.email_template_equipment_visit_report', raise_if_not_found=False)
        
        if not template_id:
            # Si no encuentra la plantilla específica, usar una genérica
            template_values = {
                'subject': f'Informe de Visitas Técnicas: {self.name}',
                'body_html': f'''
                    <p>Estimado/a,</p>
                    <p>Adjunto encontrará el informe de visitas técnicas correspondiente al período 
                    {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}.</p>
                    <p>Resumen:</p>
                    <ul>
                        <li>Total de visitas: {self.total_visits}</li>
                        <li>Equipos recurrentes: {self.recurring_equipment_count}</li>
                        <li>Equipos críticos: {self.critical_equipment_count}</li>
                        <li>Tasa de resolución en primera visita: {self.first_visit_resolution_rate:.1f}%</li>
                    </ul>
                    <p>Saludos cordiales,<br/>{self.user_id.name}</p>
                ''',
                'email_from': self.user_id.email_formatted or self.env.company.email_formatted,
                'email_to': self.email_to or '',
                'partner_to': ','.join(str(user.partner_id.id) for user in self.recipient_ids if user.partner_id),
                'attachment_ids': [(4, self.report_data)] if self.report_data else [],
            }
            
            # Enviar correo
            mail = self.env['mail.mail'].create(template_values)
            mail.send()
        else:
            # Usar la plantilla existente
            for user in self.recipient_ids:
                if user.partner_id and user.partner_id.email:
                    template_id.send_mail(self.id, force_send=True, email_values={'partner_ids': [(4, user.partner_id.id)]})
            
            # Si hay destinatarios adicionales por email
            if self.email_to:
                template_id.send_mail(self.id, force_send=True, email_values={'email_to': self.email_to})
        
        # Marcar como enviado
        self.write({
            'state': 'sent'
        })
        
        return True
    def _analyze_technician_performance(self):
        """Analiza el desempeño de cada técnico en base a las visitas realizadas"""
        self.ensure_one()
        
        # Obtener todas las visitas técnicas en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', '!=', False),
            ('responsable', '!=', False)  # Solo tickets con técnico asignado
        ])
        
        # Estructura para almacenar datos de cada técnico
        technician_data = {}
        
        # Procesar cada ticket agrupado por técnico
        for ticket in tickets:
            tech_id = ticket.responsable.id
            
            if tech_id not in technician_data:
                technician_data[tech_id] = {
                    'name': ticket.responsable.name,
                    'total_visits': 0,
                    'equipment_visits': {},  # Visitas agrupadas por equipo
                    'post_installation_visits': 0,  # Visitas tras instalación
                    'post_maintenance_visits': 0,   # Visitas tras mantenimiento
                    'post_repair_visits': 0,        # Visitas tras reparación
                    'post_review_visits': 0,        # NUEVO: Visitas tras revisión
                    'total_installations': 0,
                    'total_maintenances': 0,
                    'total_repairs': 0,
                    'total_reviews': 0,             # NUEVO: Total de revisiones
                    'repeat_visits': 0,             # Visitas repetidas en plazo corto
                    'services_by_type': {},         # Conteo por tipo de servicio
                    'problematic_sequences': [],    # Secuencias problemáticas
                }
            
            # Incrementar contador de visitas totales
            technician_data[tech_id]['total_visits'] += 1
            
            # Contar por tipo de servicio
            service_type = ticket.tipo_servicio_id if hasattr(ticket, 'tipo_servicio_id') else 'sin_especificar'
            if service_type not in technician_data[tech_id]['services_by_type']:
                technician_data[tech_id]['services_by_type'][service_type] = 0
            technician_data[tech_id]['services_by_type'][service_type] += 1
            
            # Contar instalaciones, mantenimientos, revisiones y reparaciones
            if service_type == 'instalacion':
                technician_data[tech_id]['total_installations'] += 1
            elif service_type in ['mantenimiento_preventivo', 'mantenimiento_correctivo']:
                technician_data[tech_id]['total_maintenances'] += 1
            elif service_type in ['cambio_repuestos']:
                technician_data[tech_id]['total_repairs'] += 1
            elif service_type in ['revision']:
                technician_data[tech_id]['total_reviews'] += 1
            
            # Agrupar visitas por equipo - CORRECCIÓN: usar string como clave en lugar de tupla
            # Convertir la tupla a string para usarla como clave
            eq_id = ticket.product_alquiler.id
            eq_serie = ticket.serie_id_r or ''
            eq_key = f"{eq_id}_{eq_serie}"  # Usar una cadena como clave en lugar de una tupla
            
            if eq_key not in technician_data[tech_id]['equipment_visits']:
                technician_data[tech_id]['equipment_visits'][eq_key] = []
            
            technician_data[tech_id]['equipment_visits'][eq_key].append({
                'id': ticket.id,
                'date': ticket.agenda,
                'description': ticket.description,
                'tipo_servicio': service_type,
                'estado_maquina': ticket.product_alquiler.estado_alquiler_id if hasattr(ticket.product_alquiler, 'estado_alquiler_id') else 'sin_estado'
            })
        
        # Analizar visitas por equipo para cada técnico
        problematic_technicians = []
        
        for tech_id, tech_data in technician_data.items():
            # Analizar cada equipo visitado por este técnico
            for eq_key, visits in tech_data['equipment_visits'].items():
                # Solo si hay más de una visita al mismo equipo
                if len(visits) > 1:
                    # Ordenar visitas por fecha
                    sorted_visits = sorted(visits, key=lambda x: x['date'] or fields.Datetime.now())
                    
                    # Analizar secuencia de visitas
                    for i in range(1, len(sorted_visits)):
                        current = sorted_visits[i]
                        prev = sorted_visits[i-1]
                        
                        # Verificar que ambas fechas existen
                        if current['date'] and prev['date']:
                            days_diff = (current['date'] - prev['date']).days
                            
                            # Si es una visita en plazo corto
                            if days_diff <= self.same_issue_days:
                                tech_data['repeat_visits'] += 1
                                
                                # Analizar si la visita previa fue una instalación, mantenimiento, revisión o reparación
                                prev_service = prev['tipo_servicio']
                                
                                # Guardar secuencia problemática para análisis
                                problematic_seq = {
                                    'equipo': eq_key,
                                    'primera_visita': {
                                        'fecha': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                        'tipo': prev_service,
                                        'descripcion': prev['description']
                                    },
                                    'segunda_visita': {
                                        'fecha': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                        'tipo': current['tipo_servicio'],
                                        'descripcion': current['description'],
                                        'dias_diferencia': days_diff
                                    }
                                }
                                tech_data['problematic_sequences'].append(problematic_seq)
                                
                                # Clasificar según el tipo de servicio previo
                                if prev_service == 'instalacion':
                                    tech_data['post_installation_visits'] += 1
                                elif prev_service in ['mantenimiento_preventivo', 'mantenimiento_correctivo']:
                                    tech_data['post_maintenance_visits'] += 1
                                elif prev_service in ['cambio_repuestos']:
                                    tech_data['post_repair_visits'] += 1
                                elif prev_service in ['revision']:
                                    tech_data['post_review_visits'] += 1
        
        # Calcular tasas de visitas post-servicio
        total_post_installation_rate = 0
        total_post_maintenance_rate = 0
        total_post_repair_rate = 0
        total_post_review_rate = 0  # NUEVO: para revisiones
        total_techs = 0
        
        for tech_id, tech_data in technician_data.items():
            # Calcular tasas individuales
            tech_data['post_installation_rate'] = (tech_data['post_installation_visits'] / tech_data['total_installations'] * 100) if tech_data['total_installations'] > 0 else 0
            tech_data['post_maintenance_rate'] = (tech_data['post_maintenance_visits'] / tech_data['total_maintenances'] * 100) if tech_data['total_maintenances'] > 0 else 0
            tech_data['post_repair_rate'] = (tech_data['post_repair_visits'] / tech_data['total_repairs'] * 100) if tech_data['total_repairs'] > 0 else 0
            tech_data['post_review_rate'] = (tech_data['post_review_visits'] / tech_data['total_reviews'] * 100) if tech_data['total_reviews'] > 0 else 0  # NUEVO
            
            # Calcular tasa de repetición general
            repeat_rate = (tech_data['repeat_visits'] / tech_data['total_visits'] * 100) if tech_data['total_visits'] > 0 else 0
            tech_data['repeat_rate'] = repeat_rate
            
            # Identificar técnicos problemáticos
            is_problematic = False
            
            # Criterios para identificar técnicos problemáticos:
            # 1. Alta tasa de repetición general (>30%) con al menos 5 visitas
            if repeat_rate > 30 and tech_data['total_visits'] >= 5:
                is_problematic = True
            
            # 2. Alto número absoluto de visitas repetidas (>=3)
            if tech_data['repeat_visits'] >= 3:
                is_problematic = True
            
            # 3. Alta tasa de repetición post-revisión (>25%)
            if tech_data['post_review_rate'] > 25 and tech_data['total_reviews'] >= 3:
                is_problematic = True
                
            # 4. Alta tasa de repetición post-instalación (>20%)
            if tech_data['post_installation_rate'] > 20 and tech_data['total_installations'] >= 3:
                is_problematic = True
            
            if is_problematic:
                problematic_technicians.append(tech_id)
            
            # Acumular para promedios generales
            if tech_data['total_visits'] >= 5:  # Solo considerar técnicos con actividad significativa
                total_post_installation_rate += tech_data['post_installation_rate']
                total_post_maintenance_rate += tech_data['post_maintenance_rate']
                total_post_repair_rate += tech_data['post_repair_rate']
                total_post_review_rate += tech_data['post_review_rate']
                total_techs += 1
        
        # Calcular promedios generales
        avg_post_installation_rate = total_post_installation_rate / total_techs if total_techs > 0 else 0
        avg_post_maintenance_rate = total_post_maintenance_rate / total_techs if total_techs > 0 else 0
        avg_post_repair_rate = total_post_repair_rate / total_techs if total_techs > 0 else 0
        avg_post_review_rate = total_post_review_rate / total_techs if total_techs > 0 else 0
        
        # CORRECCIÓN: Convertir tech_data a formato serializable JSON
        # No podemos usar directamente technician_data porque contiene objetos que no son serializables
        serializable_tech_data = {}
        for tech_id, data in technician_data.items():
            # Convertir tech_id a string para usarlo como clave
            serializable_tech_data[str(tech_id)] = {
                'name': data['name'],
                'total_visits': data['total_visits'],
                'repeat_visits': data['repeat_visits'],
                'repeat_rate': data['repeat_rate'],
                'post_installation_visits': data['post_installation_visits'],
                'post_maintenance_visits': data['post_maintenance_visits'],
                'post_repair_visits': data['post_repair_visits'],
                'post_review_visits': data['post_review_visits'],
                'total_installations': data['total_installations'],
                'total_maintenances': data['total_maintenances'],
                'total_repairs': data['total_repairs'],
                'total_reviews': data['total_reviews'],
                'post_installation_rate': data['post_installation_rate'],
                'post_maintenance_rate': data['post_maintenance_rate'],
                'post_repair_rate': data['post_repair_rate'],
                'post_review_rate': data['post_review_rate'],
                'problematic_sequences': data['problematic_sequences']
            }
        
        # Guardar resultados
        self.write({
            'technician_evaluation': json.dumps(serializable_tech_data),
            'problematic_technicians': [(6, 0, problematic_technicians)],
            'post_installation_visit_rate': avg_post_installation_rate,
            'post_maintenance_visit_rate': avg_post_maintenance_rate,
            'post_repair_visit_rate': avg_post_repair_rate,
            'post_review_visit_rate': avg_post_review_rate,  # NUEVO
        })

    def _analyze_service_sequences(self):
        """Analiza secuencias de servicios para identificar patrones problemáticos"""
        self.ensure_one()
        
        # Obtener todas las visitas técnicas en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', '!=', False)
        ])
        
        # Agrupar tickets por equipo
        equipment_sequences = {}
        
        for ticket in tickets:
            eq_key = (ticket.product_alquiler.id, ticket.serie_id_r or '')
            
            if eq_key not in equipment_sequences:
                equipment_sequences[eq_key] = {
                    'model': ticket.product_alquiler.name.name if ticket.product_alquiler.name else 'Sin modelo',
                    'serie': ticket.serie_id_r or 'Sin serie',
                    'partner': ticket.partner_id.name if ticket.partner_id else 'Sin cliente',
                    'visits': []
                }
            
            equipment_sequences[eq_key]['visits'].append({
                'id': ticket.id,
                'date': ticket.agenda,
                'description': ticket.description,
                'technician_id': ticket.responsable.id if ticket.responsable else False,
                'technician_name': ticket.responsable.name if ticket.responsable else 'Sin técnico',
                'tipo_servicio': ticket.tipo_servicio_id if hasattr(ticket, 'tipo_servicio_id') else 'sin_especificar',
                'estado_maquina': ticket.product_alquiler.estado_alquiler_id if hasattr(ticket.product_alquiler, 'estado_alquiler_id') else 'sin_estado'
            })
        
        # Analizar secuencias de servicios
        problematic_sequences = []
        service_type_patterns = {}
        
        # Patrones a identificar:
        patterns = {
            'instalacion_problematica': {'first': 'instalacion', 'next_days': self.same_issue_days},
            'mantenimiento_fallido': {'first': ['mantenimiento_preventivo', 'mantenimiento_correctivo'], 'next_days': self.same_issue_days},
            'reparacion_fallida': {'first': 'cambio_repuestos', 'next_days': self.same_issue_days},
            'revision_fallida': {'first': 'revision', 'next_days': self.same_issue_days},
            'revision_retiro': {'first': 'revision', 'next': 'retiro', 'next_days': 30},
            'repeticiones_multiple': {'count': 3, 'period_days': 30},  # 3 o más visitas en 30 días
        }
        
        for eq_key, eq_data in equipment_sequences.items():
            # Solo analizar equipos con múltiples visitas
            if len(eq_data['visits']) > 1:
                # Ordenar visitas por fecha
                sorted_visits = sorted(eq_data['visits'], key=lambda x: x['date'] or fields.Datetime.now())
                
                # Detectar patrones específicos
                for i in range(1, len(sorted_visits)):
                    current = sorted_visits[i]
                    prev = sorted_visits[i-1]
                    
                    # Verificar si ambas fechas existen
                    if current['date'] and prev['date']:
                        days_diff = (current['date'] - prev['date']).days
                        
                        # Construir secuencia para análisis de patrones
                        sequence_key = f"{prev['tipo_servicio']}_to_{current['tipo_servicio']}"
                        
                        if sequence_key not in service_type_patterns:
                            service_type_patterns[sequence_key] = {
                                'count': 0,
                                'avg_days': 0,
                                'total_days': 0,
                                'examples': []
                            }
                        
                        service_type_patterns[sequence_key]['count'] += 1
                        service_type_patterns[sequence_key]['total_days'] += days_diff
                        
                        # Guardar ejemplo si es notable (menos de X días)
                        if days_diff <= self.same_issue_days:
                            if len(service_type_patterns[sequence_key]['examples']) < 5:  # Limitar a 5 ejemplos
                                service_type_patterns[sequence_key]['examples'].append({
                                    'model': eq_data['model'],
                                    'serie': eq_data['serie'],
                                    'partner': eq_data['partner'],
                                    'first_date': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                    'second_date': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                    'days_diff': days_diff,
                                    'technician': current['technician_name'],
                                    'description': current['description']
                                })
                        
                        # Detectar patrones problemáticos
                        # 1. Instalación seguida de otra visita en pocos días
                        if prev['tipo_servicio'] == 'instalacion' and days_diff <= patterns['instalacion_problematica']['next_days']:
                            problematic_sequences.append({
                                'type': 'instalacion_problematica',
                                'model': eq_data['model'],
                                'serie': eq_data['serie'],
                                'partner': eq_data['partner'],
                                'first_visit': {
                                    'date': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                    'technician': prev['technician_name'],
                                    'description': prev['description']
                                },
                                'second_visit': {
                                    'date': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                    'technician': current['technician_name'],
                                    'tipo_servicio': current['tipo_servicio'],
                                    'description': current['description']
                                },
                                'days_diff': days_diff,
                                'same_technician': prev['technician_id'] == current['technician_id']
                            })
                        
                        # 2. Mantenimiento seguido de otra visita en pocos días
                        if prev['tipo_servicio'] in ['mantenimiento_preventivo', 'mantenimiento_correctivo'] and days_diff <= patterns['mantenimiento_fallido']['next_days']:
                            problematic_sequences.append({
                                'type': 'mantenimiento_fallido',
                                'model': eq_data['model'],
                                'serie': eq_data['serie'],
                                'partner': eq_data['partner'],
                                'first_visit': {
                                    'date': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                    'technician': prev['technician_name'],
                                    'description': prev['description']
                                },
                                'second_visit': {
                                    'date': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                    'technician': current['technician_name'],
                                    'tipo_servicio': current['tipo_servicio'],
                                    'description': current['description']
                                },
                                'days_diff': days_diff,
                                'same_technician': prev['technician_id'] == current['technician_id']
                            })
                        
                        # 3. Cambio de repuestos seguido de otra visita en pocos días
                        if prev['tipo_servicio'] == 'cambio_repuestos' and days_diff <= patterns['reparacion_fallida']['next_days']:
                            problematic_sequences.append({
                                'type': 'reparacion_fallida',
                                'model': eq_data['model'],
                                'serie': eq_data['serie'],
                                'partner': eq_data['partner'],
                                'first_visit': {
                                    'date': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                    'technician': prev['technician_name'],
                                    'description': prev['description']
                                },
                                'second_visit': {
                                    'date': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                    'technician': current['technician_name'],
                                    'tipo_servicio': current['tipo_servicio'],
                                    'description': current['description']
                                },
                                'days_diff': days_diff,
                                'same_technician': prev['technician_id'] == current['technician_id']
                            })
                        
                        # 4. Revisión seguida de otra visita en pocos días
                        if prev['tipo_servicio'] == 'revision' and days_diff <= patterns['revision_fallida']['next_days']:
                            problematic_sequences.append({
                                'type': 'revision_fallida',
                                'model': eq_data['model'],
                                'serie': eq_data['serie'],
                                'partner': eq_data['partner'],
                                'first_visit': {
                                    'date': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                    'technician': prev['technician_name'],
                                    'description': prev['description']
                                },
                                'second_visit': {
                                    'date': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                    'technician': current['technician_name'],
                                    'tipo_servicio': current['tipo_servicio'],
                                    'description': current['description']
                                },
                                'days_diff': days_diff,
                                'same_technician': prev['technician_id'] == current['technician_id']
                            })
                        
                        # 5. Revisión seguida de retiro (equipo mal diagnosticado)
                        if prev['tipo_servicio'] == 'revision' and current['tipo_servicio'] == 'retiro' and days_diff <= patterns['revision_retiro']['next_days']:
                            problematic_sequences.append({
                                'type': 'revision_retiro',
                                'model': eq_data['model'],
                                'serie': eq_data['serie'],
                                'partner': eq_data['partner'],
                                'first_visit': {
                                    'date': prev['date'].strftime('%d/%m/%Y') if prev['date'] else 'Sin fecha',
                                    'technician': prev['technician_name'],
                                    'description': prev['description']
                                },
                                'second_visit': {
                                    'date': current['date'].strftime('%d/%m/%Y') if current['date'] else 'Sin fecha',
                                    'technician': current['technician_name'],
                                    'tipo_servicio': current['tipo_servicio'],
                                    'description': current['description']
                                },
                                'days_diff': days_diff,
                                'same_technician': prev['technician_id'] == current['technician_id']
                            })
                
                # 6. Detectar múltiples visitas en un período corto (ej. 3 o más visitas en 30 días)
                if len(sorted_visits) >= patterns['repeticiones_multiple']['count']:
                    # Buscar secuencias de X visitas en Y días
                    for i in range(len(sorted_visits) - patterns['repeticiones_multiple']['count'] + 1):
                        start_visit = sorted_visits[i]
                        end_visit = sorted_visits[i + patterns['repeticiones_multiple']['count'] - 1]
                        
                        # Verificar que ambas fechas existen
                        if start_visit['date'] and end_visit['date']:
                            total_period = (end_visit['date'] - start_visit['date']).days
                            
                            if total_period <= patterns['repeticiones_multiple']['period_days']:
                                # Identificar todos los técnicos involucrados
                                involved_technicians = set()
                                for j in range(i, i + patterns['repeticiones_multiple']['count']):
                                    if sorted_visits[j]['technician_id']:
                                        involved_technicians.add(sorted_visits[j]['technician_name'])
                                
                                problematic_sequences.append({
                                    'type': 'repeticiones_multiple',
                                    'model': eq_data['model'],
                                    'serie': eq_data['serie'],
                                    'partner': eq_data['partner'],
                                    'start_date': start_visit['date'].strftime('%d/%m/%Y') if start_visit['date'] else 'Sin fecha',
                                    'end_date': end_visit['date'].strftime('%d/%m/%Y') if end_visit['date'] else 'Sin fecha',
                                    'total_days': total_period,
                                    'visit_count': patterns['repeticiones_multiple']['count'],
                                    'technicians': list(involved_technicians)
                                })
        
        # Calcular promedios para patrones
        for key, data in service_type_patterns.items():
            if data['count'] > 0:
                data['avg_days'] = data['total_days'] / data['count']
        
        # Ordenar secuencias problemáticas por tipo y fecha
        problematic_sequences = sorted(problematic_sequences, key=lambda x: (x['type'], x.get('days_diff', 0)))
        
        # Guardar resultados
        self.write({
            'problematic_sequences': json.dumps({
                'sequences': problematic_sequences,
                'patterns': service_type_patterns
            })
        })

    def _generate_technician_report(self):
        """Genera un informe detallado del desempeño de los técnicos"""
        self.ensure_one()
        
        if not self.technician_evaluation:
            return
        
        tech_data = json.loads(self.technician_evaluation)
        
        # Preparar datos para informe
        report_data = []
        
        for tech_id, data in tech_data.items():
            # Calcular indicadores de performance
            tech_report = {
                'Técnico': data['name'],
                'Visitas Totales': data['total_visits'],
                'Visitas Repetidas': data['repeat_visits'],
                'Tasa de Repetición (%)': f"{data['repeat_rate']:.1f}%",
                'Post-Instalación (%)': f"{data['post_installation_rate']:.1f}%",
                'Post-Mantenimiento (%)': f"{data['post_maintenance_rate']:.1f}%",
                'Post-Reparación (%)': f"{data['post_repair_rate']:.1f}%",
                'Post-Revisión (%)': f"{data['post_review_rate']:.1f}%",
                'Estado': 'ATENCIÓN REQUERIDA' if int(tech_id) in self.problematic_technicians.ids else 'OK'
            }
            
            report_data.append(tech_report)
        
        # Ordenar por tasa de repetición (descendente)
        report_data = sorted(report_data, key=lambda x: float(x['Tasa de Repetición (%)'].replace('%', '')), reverse=True)
        
        # Generar archivo Excel
        df = pd.DataFrame(report_data)
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Evaluación Técnicos', index=False)
            
            # Formato para el archivo
            workbook = writer.book
            worksheet = writer.sheets['Evaluación Técnicos']
            
            # Formato para técnicos problemáticos
            red_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
            
            # Aplicar formato condicional
            worksheet.conditional_format(1, len(df.columns) - 1, len(report_data), len(df.columns) - 1, {
                'type': 'text',
                'criteria': 'containing',
                'value': 'ATENCIÓN',
                'format': red_format
            })
            
            # Generar también hoja con secuencias problemáticas
            if self.problematic_sequences:
                seq_data = json.loads(self.problematic_sequences)['sequences']
                
                if seq_data:
                    # Preparar datos para la hoja de secuencias
                    seq_report = []
                    
                    for seq in seq_data:
                        if seq['type'] in ['instalacion_problematica', 'mantenimiento_fallido', 'reparacion_fallida', 'revision_fallida']:
                            seq_report.append({
                                'Tipo': self._get_sequence_type_name(seq['type']),
                                'Equipo': f"{seq['model']} ({seq['serie']})",
                                'Cliente': seq['partner'],
                                'Primera Visita': f"{seq['first_visit']['date']} - {seq['first_visit']['technician']}",
                                'Segunda Visita': f"{seq['second_visit']['date']} - {seq['second_visit']['technician']}",
                                'Días Entre Visitas': seq['days_diff'],
                                'Mismo Técnico': 'Sí' if seq.get('same_technician', False) else 'No',
                                'Descripción': seq['second_visit']['description']
                            })
                    
                    # Ordenar por tipo y días entre visitas
                    seq_report = sorted(seq_report, key=lambda x: (x['Tipo'], x['Días Entre Visitas']))
                    
                    # Crear DataFrame y agregar a Excel
                    seq_df = pd.DataFrame(seq_report)
                    seq_df.to_excel(writer, sheet_name='Secuencias Problemáticas', index=False)
                    
                    # Formato para la hoja de secuencias
                    seq_worksheet = writer.sheets['Secuencias Problemáticas']
                    
                    # Formato para visitas muy cercanas (menos de 3 días)
                    critical_format = workbook.add_format({'bg_color': '#FF9999'})
                    warning_format = workbook.add_format({'bg_color': '#FFEB9C'})
                    
                    # Aplicar formato condicional
                    seq_worksheet.conditional_format(1, 5, len(seq_report), 5, {
                        'type': 'cell',
                        'criteria': '<',
                        'value': 3,
                        'format': critical_format
                    })
                    
                    seq_worksheet.conditional_format(1, 5, len(seq_report), 5, {
                        'type': 'cell',
                        'criteria': 'between',
                        'minimum': 3,
                        'maximum': self.same_issue_days,
                        'format': warning_format
                    })
            
            # Agregar hoja de resumen
            summary_data = [
                ['Período del Informe:', f"{self.date_from.strftime('%d/%m/%Y')} al {self.date_to.strftime('%d/%m/%Y')}"],
                ['Total de Visitas:', self.total_visits],
                ['Tasa de Resolución en Primera Visita:', f"{self.first_visit_resolution_rate:.1f}%"],
                ['Tiempo Promedio de Respuesta:', f"{self.average_response_time:.1f} días"],
                ['Equipos Recurrentes:', self.recurring_equipment_count],
                ['Equipos Críticos:', self.critical_equipment_count],
                ['Técnicos Problemáticos:', len(self.problematic_technicians)],
                ['Tasa Promedio Post-Instalación:', f"{self.post_installation_visit_rate:.1f}%"],
                ['Tasa Promedio Post-Mantenimiento:', f"{self.post_maintenance_visit_rate:.1f}%"],
                ['Tasa Promedio Post-Reparación:', f"{self.post_repair_visit_rate:.1f}%"],
                ['Tasa Promedio Post-Revisión:', f"{self.post_review_visit_rate:.1f}%"]
            ]
            
            # Crear DataFrame para resumen
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Resumen', index=False, header=False)
            
            # Formato para resumen
            summary_worksheet = writer.sheets['Resumen']
            bold_format = workbook.add_format({'bold': True})
    def _get_sequence_type_name(self, sequence_type):
        """Devuelve el nombre legible del tipo de secuencia problemática"""
        names = {
            'instalacion_problematica': 'Instalación Fallida',
            'mantenimiento_fallido': 'Mantenimiento Incompleto',
            'reparacion_fallida': 'Reparación Inefectiva',
            'revision_fallida': 'Revisión Inefectiva',
            'revision_retiro': 'Revisión Seguida de Retiro',
            'repeticiones_multiple': 'Múltiples Visitas en Corto Plazo'
        }
        return names.get(sequence_type, sequence_type)

    def action_view_problematic_technicians(self):
        """Acción para ver los técnicos considerados problemáticos"""
        self.ensure_one()
        
        if not self.problematic_technicians:
            raise UserError(_('No hay técnicos problemáticos identificados.'))
        
        return {
            'name': _('Técnicos con Problemas'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.users',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.problematic_technicians.ids)],
        }

    def action_export_technician_analysis(self):
        """Exporta un informe detallado del análisis de técnicos"""
        self.ensure_one()
        
        if not self.technician_evaluation:
            raise UserError(_('No hay datos de evaluación de técnicos disponibles.'))
        
        # Generar informe detallado
        self._generate_technician_report()
        
        # Retornar acción para descargar el archivo
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/report_data/{self.report_filename}?download=true',
            'target': 'self',
        }

    def action_reset_to_draft(self):
        """Restablece el informe a estado borrador para regenerarlo"""
        self.ensure_one()
        
        if self.state == 'sent':
            raise UserError(_('No se puede restablecer un informe que ya ha sido enviado.'))
        
        self.write({
            'state': 'draft',
            'total_visits': 0,
            'recurring_equipment_count': 0,
            'critical_equipment_count': 0,
            'first_visit_resolution_rate': 0,
            'average_response_time': 0,
            'top_client_id': False,
            'top_client_visit_count': 0,
            'chart_data': False,
            'technician_evaluation': False,
            'problematic_technicians': [(5, 0, 0)],  # Limpiar relación
            'service_type_stats': False,
            'problematic_sequences': False,
            'post_installation_visit_rate': 0,
            'post_maintenance_visit_rate': 0,
            'post_repair_visit_rate': 0,
            'post_review_visit_rate': 0,
            'report_data': False,
            'report_filename': False,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.visit.report',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def _cron_generate_monthly_report(self):
        """Cron job para generar automáticamente el reporte mensual"""
        today = fields.Date.today()
        
        # Verificar si es el primer día del mes para generar el reporte del mes anterior
        if today.day == 1:
            # Calcular fechas del mes anterior
            last_month = today - relativedelta(months=1)
            date_from = last_month.replace(day=1)
            last_day = calendar.monthrange(last_month.year, last_month.month)[1]
            date_to = last_month.replace(day=last_day)
            
            # Crear el reporte
            report = self.create({
                'date_from': date_from,
                'date_to': date_to,
                'name': f'Reporte Visitas {date_from.strftime("%B %Y")}',
            })
            
            # Generar el reporte
            try:
                report.action_generate_report()
                
                # Buscar configuración de destinatarios predeterminados
                IrDefault = self.env['ir.default']
                default_recipients = IrDefault.get('equipment.visit.report', 'recipient_ids')
                default_emails = IrDefault.get('equipment.visit.report', 'email_to')
                
                if default_recipients or default_emails:
                    report.write({
                        'recipient_ids': default_recipients,
                        'email_to': default_emails
                    })
                    report.action_send_report()
                
                _logger.info(f"Reporte mensual de visitas generado automáticamente: {report.name}")
            except Exception as e:
                _logger.error(f"Error al generar el reporte mensual automático: {str(e)}")

    # Clase para configuraciones
    class EquipmentVisitReportSettings(models.TransientModel):
        _name = 'equipment.visit.report.settings'
        _description = 'Configuración de Informes de Visitas Técnicas'
        
        def _default_recipient_ids(self):
            return self.env['ir.default'].get('equipment.visit.report', 'recipient_ids')
        
        def _default_email_to(self):
            return self.env['ir.default'].get('equipment.visit.report', 'email_to')
        
        def _default_threshold(self):
            return self.env['ir.default'].get('equipment.visit.report', 'visit_threshold') or 3
        
        def _default_days(self):
            return self.env['ir.default'].get('equipment.visit.report', 'same_issue_days') or 7
        
        recipient_ids = fields.Many2many('res.users', string='Destinatarios Predeterminados', default=_default_recipient_ids)
        email_to = fields.Char(string='Emails Adicionales', default=_default_email_to, help='Separados por coma')
        visit_threshold = fields.Integer(string='Umbral de Visitas Críticas', default=_default_threshold)
        same_issue_days = fields.Integer(string='Días para Considerar Mismo Problema', default=_default_days)
        
        # NUEVOS campos para configuración de umbrales de alertas
        post_installation_alert = fields.Integer(string='Alerta de Tasa Post-Instalación (%)', default=20,
                                            help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-instalación')
        post_maintenance_alert = fields.Integer(string='Alerta de Tasa Post-Mantenimiento (%)', default=25,
                                            help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-mantenimiento')
        post_repair_alert = fields.Integer(string='Alerta de Tasa Post-Reparación (%)', default=25,
                                        help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-reparación')
        post_review_alert = fields.Integer(string='Alerta de Tasa Post-Revisión (%)', default=25,
                                        help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-revisión')
        
        def save_settings(self):
            """Guarda la configuración en valores predeterminados"""
            self.ensure_one()
            
            IrDefault = self.env['ir.default']
            IrDefault.set('equipment.visit.report', 'recipient_ids', self.recipient_ids.ids)
            IrDefault.set('equipment.visit.report', 'email_to', self.email_to)
            IrDefault.set('equipment.visit.report', 'visit_threshold', self.visit_threshold)
            IrDefault.set('equipment.visit.report', 'same_issue_days', self.same_issue_days)
            
            # Guardar nuevas configuraciones
            IrDefault.set('equipment.visit.report', 'post_installation_alert', self.post_installation_alert)
            IrDefault.set('equipment.visit.report', 'post_maintenance_alert', self.post_maintenance_alert)
            IrDefault.set('equipment.visit.report', 'post_repair_alert', self.post_repair_alert)
            IrDefault.set('equipment.visit.report', 'post_review_alert', self.post_review_alert)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Configuración guardada correctamente.'),
                    'type': 'success',
                    'sticky': False,
                }
            }


class EquipmentTechnicianDashboard(models.Model):
        _name = 'equipment.technician.dashboard'
        _description = 'Dashboard de Desempeño de Técnicos'
        _rec_name = 'date_range'
        
        date_range = fields.Char(string='Rango de Fechas', required=True)
        date_from = fields.Date(string='Fecha Desde', required=True)
        date_to = fields.Date(string='Fecha Hasta', required=True)
        
        user_id = fields.Many2one('res.users', string='Generado por', default=lambda self: self.env.user)
        technician_id = fields.Many2one('res.users', string='Técnico', domain=[('share', '=', False)])
        
        # Métricas de desempeño
        total_visits = fields.Integer(string='Visitas Totales', readonly=True)
        resolution_rate = fields.Float(string='Tasa de Resolución (%)', readonly=True)
        repeat_visits = fields.Integer(string='Visitas Repetidas', readonly=True)
        repeat_rate = fields.Float(string='Tasa de Repetición (%)', readonly=True)
        
        # Métricas por tipo de servicio
        post_installation_rate = fields.Float(string='Tasa Post-Instalación (%)', readonly=True)
        post_maintenance_rate = fields.Float(string='Tasa Post-Mantenimiento (%)', readonly=True)
        post_repair_rate = fields.Float(string='Tasa Post-Reparación (%)', readonly=True)
        post_review_rate = fields.Float(string='Tasa Post-Revisión (%)', readonly=True)
        
        # Estado de rendimiento
        performance_state = fields.Selection([
            ('excellent', 'Excelente'),
            ('good', 'Bueno'),
            ('average', 'Regular'),
            ('poor', 'Deficiente'),
            ('critical', 'Crítico')
        ], string='Estado de Rendimiento', readonly=True)
        
        # Equipos problemáticos
        problematic_equipment_ids = fields.Text(string='Equipos Problemáticos', readonly=True)
        
        # Datos para gráficos
        chart_data = fields.Text(string='Datos de Gráficos', readonly=True)
        
        @api.model
        def create_dashboard(self, technician_id, date_from, date_to):
            """Crea un dashboard para un técnico específico en un rango de fechas"""
            dashboard = self.create({
                'technician_id': technician_id,
                'date_from': date_from,
                'date_to': date_to,
                'date_range': f"{date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}"
            })
            
            # Calcular métricas
            dashboard._calculate_metrics()
            
            return dashboard
        
        def _calculate_metrics(self):
            """Calcula todas las métricas de rendimiento del técnico"""
            self.ensure_one()
            
            if not self.technician_id:
                return
            
            # Obtener todas las visitas de este técnico en el período
            tickets = self.env['ticket.alquiler'].search([
                ('agenda', '>=', self.date_from),
                ('agenda', '<=', self.date_to),
                ('responsable', '=', self.technician_id.id),
                ('product_alquiler', '!=', False)
            ])
            
            # Métricas básicas
            total_visits = len(tickets)
            
            if total_visits == 0:
                # No hay visitas para evaluar
                self.write({
                    'total_visits': 0,
                    'resolution_rate': 0,
                    'repeat_visits': 0,
                    'repeat_rate': 0,
                    'post_installation_rate': 0,
                    'post_maintenance_rate': 0,
                    'post_repair_rate': 0,
                    'post_review_rate': 0,
                    'performance_state': 'average',  # Neutral
                    'problematic_equipment_ids': json.dumps([]),
                    'chart_data': json.dumps({})
                })
                return
            
            # Agrupar tickets por equipo
            equipment_visits = {}
            
            for ticket in tickets:
                eq_key = (ticket.product_alquiler.id, ticket.serie_id_r or '')
                
                if eq_key not in equipment_visits:
                    equipment_visits[eq_key] = {
                        'model': ticket.product_alquiler.name.name if ticket.product_alquiler.name else 'Sin modelo',
                        'serie': ticket.serie_id_r or 'Sin serie',
                        'partner': ticket.partner_id.name if ticket.partner_id else 'Sin cliente',
                        'visits': []
                    }
                
                equipment_visits[eq_key]['visits'].append({
                    'id': ticket.id,
                    'date': ticket.agenda,
                    'description': ticket.description,
                    'tipo_servicio': ticket.tipo_servicio_id if hasattr(ticket, 'tipo_servicio_id') else 'sin_especificar'
                })
            
            # Analizar patrones de visitas
            repeat_visits = 0
            post_installation = 0
            post_maintenance = 0
            post_repair = 0
            post_review = 0
            total_installations = 0
            total_maintenances = 0
            total_repairs = 0
            total_reviews = 0
            problematic_equipment = []
            
            # Configuración de días para considerar visitas cercanas
            same_issue_days = self.env['ir.default'].get('equipment.visit.report', 'same_issue_days') or 7
            
            for eq_key, eq_data in equipment_visits.items():
                if len(eq_data['visits']) > 1:
                    # Ordenar visitas por fecha
                    sorted_visits = sorted(eq_data['visits'], key=lambda x: x['date'] or fields.Datetime.now())
                    
                    is_problematic = False
                    
                    # Analizar secuencia de visitas
                    for i in range(1, len(sorted_visits)):
                        current = sorted_visits[i]
                        prev = sorted_visits[i-1]
                        
                        # Verificar que ambas fechas existen
                        if current['date'] and prev['date']:
                            days_diff = (current['date'] - prev['date']).days
                            
                            # Si es una visita en plazo corto
                            if days_diff <= same_issue_days:
                                repeat_visits += 1
                                is_problematic = True
                                
                                # Analizar por tipo de servicio previo
                                prev_service = prev['tipo_servicio']
                                
                                if prev_service == 'instalacion':
                                    post_installation += 1
                                elif prev_service in ['mantenimiento_preventivo', 'mantenimiento_correctivo']:
                                    post_maintenance += 1
                                elif prev_service in ['cambio_repuestos']:
                                    post_repair += 1
                                elif prev_service in ['revision']:
                                    post_review += 1
                    
                    if is_problematic:
                        problematic_equipment.append({
                            'model': eq_data['model'],
                            'serie': eq_data['serie'],
                            'partner': eq_data['partner'],
                            'visits': len(sorted_visits),
                            'last_visit': sorted_visits[-1]['date'].strftime('%d/%m/%Y') if sorted_visits[-1]['date'] else 'Sin fecha'
                        })
                
                # Contar tipos de servicio realizados
                for visit in eq_data['visits']:
                    service_type = visit['tipo_servicio']
                    
                    if service_type == 'instalacion':
                        total_installations += 1
                    elif service_type in ['mantenimiento_preventivo', 'mantenimiento_correctivo']:
                        total_maintenances += 1
                    elif service_type in ['cambio_repuestos']:
                        total_repairs += 1
                    elif service_type in ['revision']:
                        total_reviews += 1
            
            # Calcular tasas
            resolution_rate = ((total_visits - repeat_visits) / total_visits) * 100 if total_visits > 0 else 0
            repeat_rate = (repeat_visits / total_visits) * 100 if total_visits > 0 else 0
            
            post_installation_rate = (post_installation / total_installations) * 100 if total_installations > 0 else 0
            post_maintenance_rate = (post_maintenance / total_maintenances) * 100 if total_maintenances > 0 else 0
            post_repair_rate = (post_repair / total_repairs) * 100 if total_repairs > 0 else 0
            post_review_rate = (post_review / total_reviews) * 100 if total_reviews > 0 else 0
            
            # Determinar estado de rendimiento
            performance_state = 'good'  # Por defecto
            
            # Obtener umbrales de alerta
            post_installation_alert = self.env['ir.default'].get('equipment.visit.report', 'post_installation_alert') or 20
            post_maintenance_alert = self.env['ir.default'].get('equipment.visit.report', 'post_maintenance_alert') or 25
            post_repair_alert = self.env['ir.default'].get('equipment.visit.report', 'post_repair_alert') or 25
            post_review_alert = self.env['ir.default'].get('equipment.visit.report', 'post_review_alert') or 25
            
            # Evaluar rendimiento
            if repeat_rate < 10 and resolution_rate > 90:
                performance_state = 'excellent'
            elif repeat_rate > 30 or len(problematic_equipment) >= 5:
                performance_state = 'critical'
            elif (repeat_rate > 20 or 
                post_installation_rate > post_installation_alert or 
                post_maintenance_rate > post_maintenance_alert or
                post_repair_rate > post_repair_alert or
                post_review_rate > post_review_alert):
                performance_state = 'poor'
            elif repeat_rate > 15 or len(problematic_equipment) >= 3:
                performance_state = 'average'
            
            # Preparar datos para gráficos
            chart_data = {
                'servicios': {
                    'labels': ['Instalaciones', 'Mantenimientos', 'Reparaciones', 'Revisiones', 'Otros'],
                    'data': [
                        total_installations,
                        total_maintenances,
                        total_repairs,
                        total_reviews,
                        total_visits - (total_installations + total_maintenances + total_repairs + total_reviews)
                    ]
                },
                'repeticiones': {
                    'labels': ['Primera Visita', 'Visitas Repetidas'],
                    'data': [total_visits - repeat_visits, repeat_visits]
                },
                'tasas_post_servicio': {
                    'labels': ['Post-Instalación', 'Post-Mantenimiento', 'Post-Reparación', 'Post-Revisión'],
                    'data': [post_installation_rate, post_maintenance_rate, post_repair_rate, post_review_rate]
                }
            }
            
            # Guardar resultados
            self.write({
                'total_visits': total_visits,
                'resolution_rate': resolution_rate,
                'repeat_visits': repeat_visits,
                'repeat_rate': repeat_rate,
                'post_installation_rate': post_installation_rate,
                'post_maintenance_rate': post_maintenance_rate,
                'post_repair_rate': post_repair_rate,
                'post_review_rate': post_review_rate,
                'performance_state': performance_state,
                'problematic_equipment_ids': json.dumps(problematic_equipment),
                'chart_data': json.dumps(chart_data)
            })
    

class EquipmentVisitReportSettings(models.TransientModel):
    _name = 'equipment.visit.report.settings'
    _description = 'Configuración de Informes de Visitas Técnicas'
    
    def _default_recipient_ids(self):
        return self.env['ir.default'].get('equipment.visit.report', 'recipient_ids')
    
    def _default_email_to(self):
        return self.env['ir.default'].get('equipment.visit.report', 'email_to')
    
    def _default_threshold(self):
        return self.env['ir.default'].get('equipment.visit.report', 'visit_threshold') or 3
    
    def _default_days(self):
        return self.env['ir.default'].get('equipment.visit.report', 'same_issue_days') or 7
    
    # Nuevos campos para umbrales de alerta
    def _default_post_installation_alert(self):
        return self.env['ir.default'].get('equipment.visit.report', 'post_installation_alert') or 20
    
    def _default_post_maintenance_alert(self):
        return self.env['ir.default'].get('equipment.visit.report', 'post_maintenance_alert') or 25
    
    def _default_post_repair_alert(self):
        return self.env['ir.default'].get('equipment.visit.report', 'post_repair_alert') or 25
    
    def _default_post_review_alert(self):
        return self.env['ir.default'].get('equipment.visit.report', 'post_review_alert') or 25
    
    recipient_ids = fields.Many2many('res.users', string='Destinatarios Predeterminados', default=_default_recipient_ids)
    email_to = fields.Char(string='Emails Adicionales', default=_default_email_to, help='Separados por coma')
    visit_threshold = fields.Integer(string='Umbral de Visitas Críticas', default=_default_threshold)
    same_issue_days = fields.Integer(string='Días para Considerar Mismo Problema', default=_default_days)
    
    # Nuevos campos para configuración de alertas
    post_installation_alert = fields.Integer(string='Alerta de Tasa Post-Instalación (%)', default=_default_post_installation_alert,
                                          help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-instalación')
    post_maintenance_alert = fields.Integer(string='Alerta de Tasa Post-Mantenimiento (%)', default=_default_post_maintenance_alert,
                                         help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-mantenimiento')
    post_repair_alert = fields.Integer(string='Alerta de Tasa Post-Reparación (%)', default=_default_post_repair_alert,
                                     help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-reparación')
    post_review_alert = fields.Integer(string='Alerta de Tasa Post-Revisión (%)', default=_default_post_review_alert,
                                     help='Porcentaje a partir del cual se considera problemático un técnico por visitas post-revisión')
    
    def save_settings(self):
        """Guarda la configuración en valores predeterminados"""
        self.ensure_one()
        
        IrDefault = self.env['ir.default']
        IrDefault.set('equipment.visit.report', 'recipient_ids', self.recipient_ids.ids)
        IrDefault.set('equipment.visit.report', 'email_to', self.email_to)
        IrDefault.set('equipment.visit.report', 'visit_threshold', self.visit_threshold)
        IrDefault.set('equipment.visit.report', 'same_issue_days', self.same_issue_days)
        
        # Guardar nuevas configuraciones
        IrDefault.set('equipment.visit.report', 'post_installation_alert', self.post_installation_alert)
        IrDefault.set('equipment.visit.report', 'post_maintenance_alert', self.post_maintenance_alert)
        IrDefault.set('equipment.visit.report', 'post_repair_alert', self.post_repair_alert)
        IrDefault.set('equipment.visit.report', 'post_review_alert', self.post_review_alert)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Configuración guardada correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }


# Corregir el nombre del modelo para que coincida con la vista XML
class EquipmentTechnicianPerformanceReport(models.Model):
    _name = 'equipment.technician.performance.report'
    _description = 'Informe de Desempeño de Técnicos'
    _rec_name = 'date_range'
    
    date_range = fields.Char(string='Rango de Fechas', required=True)
    date_from = fields.Date(string='Fecha Desde', required=True)
    date_to = fields.Date(string='Fecha Hasta', required=True)
    
    user_id = fields.Many2one('res.users', string='Generado por', default=lambda self: self.env.user)
    technician_id = fields.Many2one('res.users', string='Técnico', domain=[('share', '=', False)])
    
    # Métricas de desempeño
    total_visits = fields.Integer(string='Visitas Totales', readonly=True)
    resolution_rate = fields.Float(string='Tasa de Resolución (%)', readonly=True)
    repeat_visits = fields.Integer(string='Visitas Repetidas', readonly=True)
    repeat_rate = fields.Float(string='Tasa de Repetición (%)', readonly=True)
    
    # Métricas por tipo de servicio
    post_installation_rate = fields.Float(string='Tasa Post-Instalación (%)', readonly=True)
    post_maintenance_rate = fields.Float(string='Tasa Post-Mantenimiento (%)', readonly=True)
    post_repair_rate = fields.Float(string='Tasa Post-Reparación (%)', readonly=True)
    post_review_rate = fields.Float(string='Tasa Post-Revisión (%)', readonly=True)
    
    # Estado de rendimiento
    performance_state = fields.Selection([
        ('excellent', 'Excelente'),
        ('good', 'Bueno'),
        ('average', 'Regular'),
        ('poor', 'Deficiente'),
        ('critical', 'Crítico')
    ], string='Estado de Rendimiento', readonly=True)
    
    # Equipos problemáticos
    problematic_equipment_ids = fields.Text(string='Equipos Problemáticos', readonly=True)
    
    # Datos para gráficos
    chart_data = fields.Text(string='Datos de Gráficos', readonly=True)
    
    @api.model
    def create_report(self, technician_id, date_from, date_to):
        """Crea un informe para un técnico específico en un rango de fechas"""
        report = self.create({
            'technician_id': technician_id,
            'date_from': date_from,
            'date_to': date_to,
            'date_range': f"{date_from.strftime('%d/%m/%Y')} - {date_to.strftime('%d/%m/%Y')}"
        })
        
        # Calcular métricas
        report._calculate_metrics()
        
        return report
    
    def _calculate_metrics(self):
        """Calcula todas las métricas de rendimiento del técnico"""
        self.ensure_one()
        
        if not self.technician_id:
            return
        
        # Obtener todas las visitas de este técnico en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('responsable', '=', self.technician_id.id),
            ('product_alquiler', '!=', False)
        ])
        
        # Resto del código igual que antes...
        # (Se implementa la misma lógica de análisis de técnicos)
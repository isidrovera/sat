from odoo import api, fields, models, _
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
    
    def action_generate_report(self):
        """Genera el informe de visitas técnicas"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo puede generarse un informe que esté en estado Borrador.'))
        
        # Calcula las estadísticas generales
        self._compute_general_statistics()
        
        # Genera los datos para los gráficos
        self._generate_chart_data()
        
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
    
    def action_send_report(self):
        """Envía el informe por correo electrónico a los destinatarios configurados"""
        self.ensure_one()
        if self.state != 'generated':
            raise UserError(_('Solo puede enviarse un informe que esté en estado Generado.'))
        
        # Esta función solo marca el reporte como enviado
        # La lógica real de envío de correo estará en el XML del template
        self.write({
            'state': 'sent'
        })
        
        # Aquí iría el código para llamar al template de correo, pero esto se manejará por XML
        return True
    
    def _compute_general_statistics(self):
        """Calcula las estadísticas generales del reporte"""
        self.ensure_one()
        
        # Obtener todas las visitas técnicas en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', '!=', False)
        ])
        
        # Total de visitas
        total_visits = len(tickets)
        
        # Equipos recurrentes y críticos
        equipment_visits = {}
        critical_equipment = 0
        
        for ticket in tickets:
            # Clave compuesta de equipo y serie para identificar cada equipo único
            equipment_key = (ticket.product_alquiler.id, ticket.serie_id_r)
            
            if equipment_key not in equipment_visits:
                equipment_visits[equipment_key] = {
                    'visits': [],
                    'count': 0,
                    'partner_id': ticket.partner_id.id,
                    'partner_name': ticket.partner_id.name,
                }
            
            equipment_visits[equipment_key]['visits'].append({
                'id': ticket.id,
                'date': ticket.agenda if ticket.agenda else None,  # Store as datetime object, not string
                'description': ticket.description,
                'responsable': ticket.responsable.id if ticket.responsable else False
            })
            equipment_visits[equipment_key]['count'] += 1
        
        # Contar equipos con múltiples visitas
        recurring_equipment = 0
        all_visits_by_partner = {}
        
        for eq_key, eq_data in equipment_visits.items():
            if eq_data['count'] > 1:
                recurring_equipment += 1
            
            if eq_data['count'] >= self.visit_threshold:
                critical_equipment += 1
            
            # Contabilizar visitas por cliente
            partner_id = eq_data['partner_id']
            if partner_id not in all_visits_by_partner:
                all_visits_by_partner[partner_id] = {
                    'count': 0,
                    'name': eq_data['partner_name']
                }
            all_visits_by_partner[partner_id]['count'] += eq_data['count']
        
        # Encontrar el cliente con más visitas
        top_client_id = False
        top_client_count = 0
        
        for partner_id, partner_data in all_visits_by_partner.items():
            if partner_data['count'] > top_client_count:
                top_client_id = partner_id
                top_client_count = partner_data['count']
        
        # Calcular tasa de resolución en primera visita
        first_visits = 0
        recurring_issues = 0
        
        for eq_key, eq_data in equipment_visits.items():
            if len(eq_data['visits']) == 1:
                first_visits += 1
            else:
                # Ordenar visitas por fecha
                sorted_visits = sorted(eq_data['visits'], key=lambda x: x['date'] or fields.Datetime.now())
                
                for i in range(1, len(sorted_visits)):
                    current_visit = sorted_visits[i]
                    prev_visit = sorted_visits[i-1]
                    
                    # Verificar que ambas fechas existen
                    if current_visit['date'] and prev_visit['date']:
                        # Ambas fechas son objetos datetime, se pueden restar directamente
                        days_diff = (current_visit['date'] - prev_visit['date']).days
                        if days_diff <= self.same_issue_days and current_visit['description'] == prev_visit['description']:
                            recurring_issues += 1
        
        # Calcular tasa de resolución en primera visita
        resolution_rate = 0
        if total_visits > 0:
            resolution_rate = (first_visits / total_visits) * 100
        
        # Calcular tiempo promedio de respuesta
        avg_response_time = 0
        response_times = []
        
        tickets_with_create = tickets.filtered(lambda t: t.create_date and t.agenda)
        for ticket in tickets_with_create:
            time_diff = (ticket.agenda - fields.Datetime.from_string(ticket.create_date)).total_seconds() / 86400  # días
            response_times.append(time_diff)
        
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
        
        # Actualizar los valores en el registro
        self.write({
            'total_visits': total_visits,
            'recurring_equipment_count': recurring_equipment,
            'critical_equipment_count': critical_equipment,
            'first_visit_resolution_rate': resolution_rate,
            'average_response_time': avg_response_time,
            'top_client_id': top_client_id,
            'top_client_visit_count': top_client_count,
        })
    
    def _generate_chart_data(self):
        """Genera los datos para los gráficos en formato JSON"""
        self.ensure_one()
        
        # Obtener todas las visitas técnicas en el período
        tickets = self.env['ticket.alquiler'].search([
            ('agenda', '>=', self.date_from),
            ('agenda', '<=', self.date_to),
            ('product_alquiler', '!=', False)
        ])
        
        # 1. Datos para gráfico de barras: equipos con más visitas
        equipment_count = {}
        for ticket in tickets:
            equipment_key = ticket.product_alquiler.name.name if ticket.product_alquiler.name else 'Sin modelo'
            if equipment_key not in equipment_count:
                equipment_count[equipment_key] = 0
            equipment_count[equipment_key] += 1
        
        # Ordenar por cantidad de visitas (descendente)
        equipment_count = dict(sorted(equipment_count.items(), key=lambda item: item[1], reverse=True)[:10])
        
        equipment_chart_data = {
            'labels': list(equipment_count.keys()),
            'data': list(equipment_count.values()),
            'critical_threshold': self.visit_threshold,
        }
        
        # 2. Datos para gráfico circular: distribución por cliente
        client_count = {}
        for ticket in tickets:
            client_name = ticket.partner_id.name if ticket.partner_id else 'Sin cliente'
            if client_name not in client_count:
                client_count[client_name] = 0
            client_count[client_name] += 1
        
        # Ordenar por cantidad de visitas (descendente)
        client_count = dict(sorted(client_count.items(), key=lambda item: item[1], reverse=True))
        
        # Si hay más de 5 clientes, agrupar los restantes en "Otros"
        if len(client_count) > 5:
            top_clients = dict(list(client_count.items())[:4])
            others_sum = sum(list(client_count.values())[4:])
            top_clients['Otros'] = others_sum
            client_count = top_clients
        
        client_chart_data = {
            'labels': list(client_count.keys()),
            'data': list(client_count.values()),
        }
        
        # 3. Datos para línea de tiempo: equipos críticos
        timeline_data = []
        
        # Obtener equipos críticos
        equipment_visits = {}
        
        for ticket in tickets:
            eq_key = (ticket.product_alquiler.id, ticket.serie_id_r)
            
            if eq_key not in equipment_visits:
                equipment_visits[eq_key] = {
                    'model': ticket.product_alquiler.name.name if ticket.product_alquiler.name else 'Sin modelo',
                    'serie': ticket.serie_id_r or 'Sin serie',
                    'partner': ticket.partner_id.name if ticket.partner_id else 'Sin cliente',
                    'visits': []
                }
            
            equipment_visits[eq_key]['visits'].append({
                'id': ticket.id,
                'date': ticket.agenda if ticket.agenda else None,  # Store as datetime object
                'problem': ticket.description or 'Sin descripción',
                'technician': ticket.responsable.name if ticket.responsable else 'Sin técnico',
            })
        
        # Filtrar equipos críticos y prepararlos para la línea de tiempo
        for eq_key, eq_data in equipment_visits.items():
            if len(eq_data['visits']) >= self.visit_threshold:
                # Ordenar visitas por fecha
                eq_data['visits'] = sorted(eq_data['visits'], key=lambda x: x['date'] or fields.Datetime.now())
                
                # Determinar si las visitas son por el mismo problema
                for i in range(1, len(eq_data['visits'])):
                    current = eq_data['visits'][i]
                    prev = eq_data['visits'][i-1]
                    
                    # Verificar que ambas fechas existen
                    if current['date'] and prev['date']:
                        # Ambas fechas son objetos datetime, se pueden restar directamente
                        days_diff = (current['date'] - prev['date']).days
                        
                        # Determinar si es el mismo problema basado en la descripción y el tiempo
                        if days_diff <= self.same_issue_days and current['problem'] == prev['problem']:
                            current['same_problem'] = True
                        else:
                            current['same_problem'] = False
                    else:
                        current['same_problem'] = False
                
                # Marcar la primera visita como no recurrente
                if eq_data['visits']:
                    eq_data['visits'][0]['same_problem'] = False
                
                # Convertir los objetos datetime a strings para la serialización JSON
                for visit in eq_data['visits']:
                    if visit['date']:
                        visit['date'] = visit['date'].strftime('%Y-%m-%d')
                    else:
                        visit['date'] = None
                
                timeline_data.append({
                    'model': eq_data['model'],
                    'serie': eq_data['serie'],
                    'partner': eq_data['partner'],
                    'visits': eq_data['visits']
                })
        
        # 4. Datos para la tabla detallada
        table_data = []
        
        for eq_key, eq_data in equipment_visits.items():
            if len(eq_data['visits']) > 1:
                # Ordenar visitas por fecha - considerando que ahora son strings
                sorted_visits = sorted(eq_data['visits'], key=lambda x: x['date'] or "")
                
                # Agrupar problemas similares
                problems = {}
                for visit in sorted_visits:
                    if visit['problem'] not in problems:
                        problems[visit['problem']] = 0
                    problems[visit['problem']] += 1
                
                # Encontrar problema más común
                common_problem = max(problems.items(), key=lambda x: x[1])[0] if problems else 'Varios'
                
                # Recopilar fechas de visita - asegurarse de que son strings
                visit_dates = []
                for v in sorted_visits:
                    if v['date']:
                        # Si la fecha ya es un string, usarla directamente
                        if isinstance(v['date'], str):
                            date_str = v['date']
                            # Convertir el formato si es necesario (de YYYY-MM-DD a DD/MM/YYYY)
                            if '-' in date_str:
                                try:
                                    parts = date_str.split('-')
                                    date_str = f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else date_str
                                except:
                                    pass
                            visit_dates.append(date_str)
                        # Si la fecha es un objeto datetime, convertirlo
                        else:
                            visit_dates.append(v['date'].strftime('%d/%m/%Y'))
                
                # Determinar si hay visitas cercanas (menos de X días entre visitas consecutivas)
                # Esto ya se calculó anteriormente cuando se determinó 'same_problem'
                close_visits = any(v.get('same_problem', False) for v in sorted_visits if v != sorted_visits[0])
                
                table_data.append({
                    'partner': eq_data['partner'],
                    'model': eq_data['model'],
                    'serie': eq_data['serie'],
                    'problem': common_problem,
                    'dates': visit_dates,
                    'technicians': list(set([v['technician'] for v in sorted_visits])),
                    'visit_count': len(sorted_visits),
                    'is_critical': len(sorted_visits) >= self.visit_threshold,
                    'has_close_visits': close_visits
                })
        
        # Ordenar tabla por cantidad de visitas (descendente)
        table_data = sorted(table_data, key=lambda x: x['visit_count'], reverse=True)
        
        # 5. Análisis especial para equipos críticos
        special_analysis = []
        
        for entry in table_data:
            if entry['is_critical']:
                # Este análisis requeriría más datos históricos para ser más completo
                # Se pueden agregar más análisis basados en datos históricos disponibles
                special_analysis.append({
                    'model': entry['model'],
                    'serie': entry['serie'],
                    'partner': entry['partner'],
                    'visit_count': entry['visit_count'],
                    'common_problem': entry['problem'],
                    'has_close_visits': entry['has_close_visits'],
                    # Aquí podrían agregarse más análisis como tendencias históricas
                })
        
        # Combinar todos los datos en un único objeto JSON
        chart_data = {
            'equipment_chart': equipment_chart_data,
            'client_chart': client_chart_data,
            'timeline': timeline_data,
            'table': table_data,
            'special_analysis': special_analysis
        }
        
        # Guardar datos en formato JSON
        self.chart_data = json.dumps(chart_data)
    
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
    
    def export_excel_report(self):
        """Exporta los datos del reporte a un archivo Excel"""
        self.ensure_one()
        
        if not self.chart_data:
            raise UserError(_("Primero debe generar el reporte."))
        
        try:
            # Crear un dataframe para cada sección del reporte
            data = json.loads(self.chart_data)
            
            # Crear un archivo Excel con varias hojas
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # 1. Hoja de resumen
                summary_data = {
                    'Métrica': [
                        'Total de Visitas',
                        'Equipos Recurrentes',
                        'Equipos Críticos',
                        'Tasa de Resolución Primera Visita (%)',
                        'Tiempo Promedio de Respuesta (días)',
                        'Cliente con Más Visitas',
                        'Visitas del Cliente Principal'
                    ],
                    'Valor': [
                        self.total_visits,
                        self.recurring_equipment_count,
                        self.critical_equipment_count,
                        round(self.first_visit_resolution_rate, 2),
                        round(self.average_response_time, 2),
                        self.top_client_id.name if self.top_client_id else 'N/A',
                        self.top_client_visit_count or 0
                    ]
                }
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, sheet_name='Resumen', index=False)
                
                # 2. Hoja de equipos con más visitas
                equipment_data = {
                    'Modelo': data['equipment_chart']['labels'],
                    'Visitas': data['equipment_chart']['data']
                }
                df_equipment = pd.DataFrame(equipment_data)
                df_equipment.to_excel(writer, sheet_name='Equipos', index=False)
                
                # 3. Hoja de distribución por cliente
                client_data = {
                    'Cliente': data['client_chart']['labels'],
                    'Visitas': data['client_chart']['data']
                }
                df_client = pd.DataFrame(client_data)
                df_client.to_excel(writer, sheet_name='Clientes', index=False)
                
                # 4. Hoja de tabla detallada
                table_rows = []
                for item in data['table']:
                    table_rows.append({
                        'Cliente': item['partner'],
                        'Modelo': item['model'],
                        'Serie': item['serie'],
                        'Problema Principal': item['problem'],
                        'Fechas de Visita': ', '.join(item['dates']),
                        'Técnicos': ', '.join(item['technicians']),
                        'Total Visitas': item['visit_count'],
                        'Es Crítico': 'Sí' if item['is_critical'] else 'No',
                        'Visitas Cercanas': 'Sí' if item['has_close_visits'] else 'No'
                    })
                
                if table_rows:
                    df_table = pd.DataFrame(table_rows)
                    df_table.to_excel(writer, sheet_name='Detalles', index=False)
                
                # 5. Hoja de análisis especial
                analysis_rows = []
                for item in data['special_analysis']:
                    analysis_rows.append({
                        'Cliente': item['partner'],
                        'Modelo': item['model'],
                        'Serie': item['serie'],
                        'Problema Común': item['common_problem'],
                        'Total Visitas': item['visit_count'],
                        'Visitas Cercanas': 'Sí' if item['has_close_visits'] else 'No',
                        'Recomendación': 'Revisar a fondo / Considerar reemplazo' if item['visit_count'] >= 5 else 'Verificar mantenimiento preventivo'
                    })
                
                if analysis_rows:
                    df_analysis = pd.DataFrame(analysis_rows)
                    df_analysis.to_excel(writer, sheet_name='Análisis Especial', index=False)
                
                # Mejorar formato de las hojas
                workbook = writer.book
                
                # Formato para encabezados
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#2c3e50',
                    'font_color': 'white',
                    'border': 1
                })
                
                # Formato para celdas críticas
                critical_format = workbook.add_format({
                    'bg_color': '#ffebee',
                    'font_color': '#e74c3c'
                })
                
                # Aplicar formatos a cada hoja
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    for col_num, value in enumerate(worksheet.table.columns):
                        worksheet.write(0, col_num, value, header_format)
                    
                    # Ajustar anchos de columna
                    worksheet.autofit()
                    
                    # Aplicar formato condicional para valores críticos en la hoja de detalles
                    if sheet_name == 'Detalles':
                        worksheet.conditional_format('G2:G1000', {
                            'type': 'cell',
                            'criteria': '>=',
                            'value': data['equipment_chart']['critical_threshold'],
                            'format': critical_format
                        })
            
            # Generar el archivo para descargar
            output.seek(0)
            file_data = output.getvalue()
            file_name = f'informe_visitas_{self.date_from.strftime("%Y%m")}_{self.date_to.strftime("%Y%m")}.xlsx'
            
            self.write({
                'report_data': base64.b64encode(file_data),
                'report_filename': file_name
            })
            
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/equipment.visit.report/{self.id}/report_data/{file_name}?download=true',
                'target': 'self',
            }
            
        except Exception as e:
            raise UserError(_("Error al generar archivo Excel: %s") % str(e))

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
    
    def save_settings(self):
        """Guarda la configuración en valores predeterminados"""
        self.ensure_one()
        
        IrDefault = self.env['ir.default']
        IrDefault.set('equipment.visit.report', 'recipient_ids', self.recipient_ids.ids)
        IrDefault.set('equipment.visit.report', 'email_to', self.email_to)
        IrDefault.set('equipment.visit.report', 'visit_threshold', self.visit_threshold)
        IrDefault.set('equipment.visit.report', 'same_issue_days', self.same_issue_days)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Configuración guardada correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }
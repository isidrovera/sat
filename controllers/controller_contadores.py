# -*- coding: utf-8 -*-
import json
from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class ContadorDashboardController(http.Controller):
    
    @http.route(['/dashboard/contador', '/<string:lang>/dashboard/contador'], 
            type='http', auth='user', website=True, multilang=True)
    def dashboard_main(self, page=1, search=None, **kwargs):
        """
        Ruta principal del dashboard de contadores
        """
        try:
            page = int(page)
            items_per_page = 20
            
            # Obtener modelo
            ContadorModel = request.env['contador.automatico']
            
            # Construir dominio de búsqueda
            domain = [('serie_detectada', '!=', False)]
            
            if search:
                domain.extend([
                    '|', '|',
                    ('cliente_detectado', 'ilike', search),
                    ('serie_detectada', 'ilike', search),
                    ('tipo_equipo_detectado', 'ilike', search)
                ])
            
            # Obtener estadísticas
            estadisticas = ContadorModel.obtener_estadisticas_dashboard()
            
            # Contar total de registros
            total_equipos = ContadorModel.search_count(domain)
            
            # Calcular paginación
            offset = (page - 1) * items_per_page
            total_pages = (total_equipos + items_per_page - 1) // items_per_page
            
            # Obtener equipos para la página actual
            equipos_raw = ContadorModel.search(domain, 
                                             limit=items_per_page, 
                                             offset=offset, 
                                             order='create_date desc')
            
            # Formatear datos de equipos
            equipos = []
            for equipo in equipos_raw:
                equipos.append({
                    'id': equipo.id,
                    'cliente_detectado': equipo.cliente_detectado or 'Sin cliente',
                    'serie_detectada': equipo.serie_detectada or 'Sin serie',
                    'tipo_equipo_detectado': equipo.tipo_equipo_detectado or 'N/A',
                    'contador_bn_actual': equipo.contador_bn_detectado or 0,
                    'contador_color_actual': equipo.contador_color_detectado or 0,
                    'contador_total_actual': (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0),
                    'estado_ultimo': equipo.estado or 'pendiente',
                    'ultima_actualizacion_formatted': self._format_datetime(equipo.create_date),
                })
            
            # Datos para el template
            values = {
                'estadisticas': estadisticas,
                'equipos': equipos,
                'total_equipos': total_equipos,
                'current_page': page,
                'total_pages': total_pages,
                'search_query': search,
                'ultima_actualizacion': self._format_datetime(datetime.now()),
                'page_title': 'Dashboard de Contadores',
            }
            
            return request.render('sat.contador_dashboard_template', values)
            
        except Exception as e:
            _logger.error(f"Error en dashboard principal: {e}")
            return request.render('web.http_error', {
                'status_code': 500,
                'status_message': 'Error interno del servidor',
                'error_message': f'Error cargando dashboard: {str(e)}'
            })
    
    @http.route('/dashboard/contador/refresh', type='http', auth='user', website=True)
    def dashboard_refresh(self, **kwargs):
        """
        Refresca los datos del dashboard
        """
        try:
            # Ejecutar actualización de datos
            ContadorModel = request.env['contador.automatico']
            ContadorModel.cron_procesar_correos_perdidos()
            
            # Mensaje de éxito
            request.session['dashboard_message'] = {
                'type': 'success',
                'text': 'Dashboard actualizado correctamente'
            }
            
        except Exception as e:
            _logger.error(f"Error refrescando dashboard: {e}")
            request.session['dashboard_message'] = {
                'type': 'danger',
                'text': f'Error actualizando: {str(e)}'
            }
        
        # Redirigir de vuelta al dashboard
        return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/stats', type='http', auth='user', website=True)
    def dashboard_stats(self, **kwargs):
        """
        Página de estadísticas detalladas
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Obtener estadísticas completas
            estadisticas = ContadorModel.obtener_estadisticas_dashboard()
            
            # Estadísticas adicionales
            stats_adicionales = {
                'registros_por_estado': ContadorModel.get_equipos_por_estado(),
                'equipos_por_tipo': ContadorModel.get_equipos_por_tipo(),
                'actividad_semanal': ContadorModel.get_actividad_semanal(),
            }
            
            values = {
                'estadisticas': estadisticas,
                'stats_adicionales': stats_adicionales,
                'page_title': 'Estadísticas Detalladas',
            }
            
            return request.render('sat.contador_dashboard_stats_template', values)
            
        except Exception as e:
            _logger.error(f"Error en estadísticas: {e}")
            return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/diagnostico', type='http', auth='user', website=True)
    def dashboard_diagnostico(self, **kwargs):
        """
        Página de diagnóstico del sistema
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Ejecutar diagnóstico
            diagnostico = ContadorModel.diagnosticar_sistema()
            
            values = {
                'diagnostico': diagnostico,
                'page_title': 'Diagnóstico del Sistema',
            }
            
            return request.render('sat.contador_dashboard_diagnostico_template', values)
            
        except Exception as e:
            _logger.error(f"Error en diagnóstico: {e}")
            return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/detalle/<int:equipo_id>', type='http', auth='user', website=True)
    def dashboard_detalle(self, equipo_id, **kwargs):
        """
        Página de detalle de un equipo específico
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Obtener detalle del equipo
            detalle = ContadorModel.obtener_detalle_equipo(equipo_id)
            
            if not detalle:
                return request.not_found()
            
            values = {
                'equipo': detalle,
                'page_title': f'Detalle Equipo {detalle.get("serie_detectada", "Sin serie")}',
            }
            
            return request.render('sat.contador_dashboard_detalle_template', values)
            
        except Exception as e:
            _logger.error(f"Error en detalle: {e}")
            return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/historial/<int:equipo_id>', type='http', auth='user', website=True)
    def dashboard_historial(self, equipo_id, **kwargs):
        """
        Página de historial de un equipo específico
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Obtener historial del equipo
            equipo = ContadorModel.browse(equipo_id)
            if not equipo.exists():
                return request.not_found()
            
            # Buscar todos los registros del mismo equipo
            historial = ContadorModel.search([
                ('serie_detectada', '=', equipo.serie_detectada)
            ], order='create_date desc', limit=50)
            
            # Formatear historial
            historial_formateado = []
            for registro in historial:
                historial_formateado.append({
                    'fecha': self._format_datetime(registro.create_date),
                    'contador_bn': registro.contador_bn_detectado or 0,
                    'contador_color': registro.contador_color_detectado or 0,
                    'contador_total': (registro.contador_bn_detectado or 0) + (registro.contador_color_detectado or 0),
                    'estado': registro.estado,
                    'remitente': registro.remitente,
                })
            
            values = {
                'equipo': {
                    'id': equipo.id,
                    'serie': equipo.serie_detectada,
                    'cliente': equipo.cliente_detectado,
                    'tipo': equipo.tipo_equipo_detectado,
                },
                'historial': historial_formateado,
                'page_title': f'Historial {equipo.serie_detectada or "Sin serie"}',
            }
            
            return request.render('sat.contador_dashboard_historial_template', values)
            
        except Exception as e:
            _logger.error(f"Error en historial: {e}")
            return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/api/stats', type='json', auth='user')
    def api_get_stats(self, **kwargs):
        """
        API JSON para obtener estadísticas
        """
        try:
            ContadorModel = request.env['contador.automatico']
            estadisticas = ContadorModel.obtener_estadisticas_dashboard()
            
            return {
                'success': True,
                'data': estadisticas
            }
            
        except Exception as e:
            _logger.error(f"Error en API stats: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/dashboard/contador/api/equipos', type='json', auth='user')
    def api_get_equipos(self, limit=20, offset=0, search=None, **kwargs):
        """
        API JSON para obtener equipos
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Construir dominio
            domain = [('serie_detectada', '!=', False)]
            if search:
                domain.extend([
                    '|', '|',
                    ('cliente_detectado', 'ilike', search),
                    ('serie_detectada', 'ilike', search),
                    ('tipo_equipo_detectado', 'ilike', search)
                ])
            
            # Obtener equipos
            equipos = ContadorModel.search(domain, 
                                         limit=limit, 
                                         offset=offset, 
                                         order='create_date desc')
            
            # Formatear respuesta
            equipos_data = []
            for equipo in equipos:
                equipos_data.append({
                    'id': equipo.id,
                    'cliente': equipo.cliente_detectado,
                    'serie': equipo.serie_detectada,
                    'tipo': equipo.tipo_equipo_detectado,
                    'contador_bn': equipo.contador_bn_detectado or 0,
                    'contador_color': equipo.contador_color_detectado or 0,
                    'contador_total': (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0),
                    'estado': equipo.estado,
                    'fecha': equipo.create_date.isoformat() if equipo.create_date else None,
                })
            
            return {
                'success': True,
                'data': equipos_data,
                'total': ContadorModel.search_count(domain)
            }
            
        except Exception as e:
            _logger.error(f"Error en API equipos: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/dashboard/contador/export/excel', type='http', auth='user')
    def export_excel(self, search=None, **kwargs):
        """
        Exportar datos a Excel
        """
        try:
            import xlsxwriter
            import io
            
            ContadorModel = request.env['contador.automatico']
            
            # Construir dominio
            domain = [('serie_detectada', '!=', False)]
            if search:
                domain.extend([
                    '|', '|',
                    ('cliente_detectado', 'ilike', search),
                    ('serie_detectada', 'ilike', search),
                    ('tipo_equipo_detectado', 'ilike', search)
                ])
            
            # Obtener todos los equipos
            equipos = ContadorModel.search(domain, order='create_date desc')
            
            # Crear archivo Excel en memoria
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('Dashboard Contadores')
            
            # Formatos
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            cell_format = workbook.add_format({'border': 1})
            
            # Headers
            headers = [
                'Cliente', 'Serie', 'Tipo', 'Contador B/N', 
                'Contador Color', 'Total', 'Estado', 'Fecha'
            ]
            
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)
            
            # Datos
            for row, equipo in enumerate(equipos, 1):
                worksheet.write(row, 0, equipo.cliente_detectado or '', cell_format)
                worksheet.write(row, 1, equipo.serie_detectada or '', cell_format)
                worksheet.write(row, 2, equipo.tipo_equipo_detectado or '', cell_format)
                worksheet.write(row, 3, equipo.contador_bn_detectado or 0, cell_format)
                worksheet.write(row, 4, equipo.contador_color_detectado or 0, cell_format)
                worksheet.write(row, 5, (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0), cell_format)
                worksheet.write(row, 6, equipo.estado or '', cell_format)
                worksheet.write(row, 7, self._format_datetime(equipo.create_date), cell_format)
            
            # Ajustar ancho de columnas
            worksheet.set_column('A:H', 15)
            
            workbook.close()
            output.seek(0)
            
            # Preparar respuesta
            filename = f'dashboard_contadores_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            
            return request.make_response(
                output.getvalue(),
                headers=[
                    ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                    ('Content-Disposition', f'attachment; filename={filename}')
                ]
            )
            
        except Exception as e:
            _logger.error(f"Error exportando Excel: {e}")
            return request.redirect('/dashboard/contador')
    
    def _format_datetime(self, dt):
        """
        Formatea datetime para mostrar
        """
        if not dt:
            return 'N/A'
        
        try:
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            
            return dt.strftime('%d/%m/%Y %H:%M')
        except:
            return str(dt)
    
    def _get_time_ago(self, dt):
        """
        Obtiene tiempo transcurrido en formato legible
        """
        if not dt:
            return ''
        
        try:
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            
            now = datetime.now()
            diff = now - dt
            
            if diff.days > 0:
                return f'Hace {diff.days} días'
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f'Hace {hours} horas'
            elif diff.seconds > 60:
                minutes = diff.seconds // 60
                return f'Hace {minutes} minutos'
            else:
                return 'Hace unos momentos'
                
        except:
            return ''
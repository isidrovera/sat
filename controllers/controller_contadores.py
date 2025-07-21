# -*- coding: utf-8 -*-
import json
from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class ContadorDashboardController(http.Controller):
    
    @http.route('/dashboard/contador', type='http', auth='user', website=True)
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
            try:
                estadisticas = ContadorModel.obtener_estadisticas_dashboard()
            except AttributeError:
                # Si no existe el método, crear estadísticas básicas
                estadisticas = self._get_estadisticas_basicas(ContadorModel)
            
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
            
            # Formatear datos de equipos como objetos simples para el template
            equipos = []
            for equipo in equipos_raw:
                # Crear un objeto simple que funcione con el template
                equipo_data = type('obj', (object,), {
                    'id': equipo.id,
                    'cliente_detectado': equipo.cliente_detectado or 'Sin cliente',
                    'serie_detectada': equipo.serie_detectada or 'Sin serie',
                    'tipo_equipo_detectado': equipo.tipo_equipo_detectado or 'N/A',
                    'contador_bn_actual': equipo.contador_bn_detectado or 0,
                    'contador_color_actual': equipo.contador_color_detectado or 0,
                    'contador_total_actual': (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0),
                    'estado_ultimo': equipo.estado or 'pendiente',
                    'ultima_actualizacion_formatted': self._format_datetime(equipo.create_date),
                })()
                equipos.append(equipo_data)
            
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
    
    def _get_estadisticas_basicas(self, ContadorModel):
        """
        Genera estadísticas básicas si no existe el método en el modelo
        """
        try:
            # Obtener fecha de hoy y hace una semana
            hoy = datetime.now().date()
            hace_semana = hoy - timedelta(days=7)
            
            # Contar equipos únicos por período
            equipos_hoy = ContadorModel.search([
                ('create_date', '>=', hoy),
                ('serie_detectada', '!=', False)
            ])
            
            equipos_semana = ContadorModel.search([
                ('create_date', '>=', hace_semana),
                ('serie_detectada', '!=', False)
            ])
            
            # Contar equipos únicos por serie
            series_hoy = set()
            series_semana = set()
            
            for equipo in equipos_hoy:
                if equipo.serie_detectada:
                    series_hoy.add(equipo.serie_detectada)
            
            for equipo in equipos_semana:
                if equipo.serie_detectada:
                    series_semana.add(equipo.serie_detectada)
            
            # Total de equipos únicos en el sistema
            total_equipos = ContadorModel.search_count([('serie_detectada', '!=', False)])
            
            # Calcular eficiencia (equipos procesados vs total)
            equipos_procesados = ContadorModel.search_count([
                ('estado', '=', 'procesado'),
                ('serie_detectada', '!=', False)
            ])
            
            eficiencia = round((equipos_procesados / total_equipos * 100) if total_equipos > 0 else 0, 1)
            
            return {
                'equipos_unicos_hoy': len(series_hoy),
                'equipos_unicos_semana': len(series_semana),
                'total_equipos_sistema': total_equipos,
                'eficiencia_sistema': eficiencia,
            }
            
        except Exception as e:
            _logger.error(f"Error calculando estadísticas básicas: {e}")
            return {
                'equipos_unicos_hoy': 0,
                'equipos_unicos_semana': 0,
                'total_equipos_sistema': 0,
                'eficiencia_sistema': 0,
            }
    
    @http.route('/dashboard/contador/refresh', type='http', auth='user', website=True)
    def dashboard_refresh(self, **kwargs):
        """
        Refresca los datos del dashboard
        """
        try:
            # Ejecutar actualización de datos
            ContadorModel = request.env['contador.automatico']
            
            # Verificar si existe el método de procesamiento
            if hasattr(ContadorModel, 'cron_procesar_correos_perdidos'):
                ContadorModel.cron_procesar_correos_perdidos()
            else:
                _logger.warning("Método cron_procesar_correos_perdidos no encontrado en el modelo")
            
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
            try:
                estadisticas = ContadorModel.obtener_estadisticas_dashboard()
            except AttributeError:
                estadisticas = self._get_estadisticas_basicas(ContadorModel)
            
            # Estadísticas adicionales
            stats_adicionales = {
                'registros_por_estado': self._get_equipos_por_estado(ContadorModel),
                'equipos_por_tipo': self._get_equipos_por_tipo(ContadorModel),
                'actividad_semanal': self._get_actividad_semanal(ContadorModel),
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
    
    def _get_equipos_por_estado(self, ContadorModel):
        """Obtiene conteo de equipos por estado"""
        try:
            estados = ContadorModel.read_group(
                [('serie_detectada', '!=', False)],
                ['estado'],
                ['estado']
            )
            return {estado['estado']: estado['estado_count'] for estado in estados}
        except:
            return {}
    
    def _get_equipos_por_tipo(self, ContadorModel):
        """Obtiene conteo de equipos por tipo"""
        try:
            tipos = ContadorModel.read_group(
                [('serie_detectada', '!=', False)],
                ['tipo_equipo_detectado'],
                ['tipo_equipo_detectado']
            )
            return {tipo['tipo_equipo_detectado']: tipo['tipo_equipo_detectado_count'] for tipo in tipos}
        except:
            return {}
    
    def _get_actividad_semanal(self, ContadorModel):
        """Obtiene actividad de la última semana"""
        try:
            hace_semana = datetime.now() - timedelta(days=7)
            registros = ContadorModel.search([
                ('create_date', '>=', hace_semana),
                ('serie_detectada', '!=', False)
            ])
            
            actividad = {}
            for registro in registros:
                fecha = registro.create_date.date()
                if fecha not in actividad:
                    actividad[fecha] = 0
                actividad[fecha] += 1
            
            return actividad
        except:
            return {}
    
    @http.route('/dashboard/contador/diagnostico', type='http', auth='user', website=True)
    def dashboard_diagnostico(self, **kwargs):
        """
        Página de diagnóstico del sistema
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Ejecutar diagnóstico básico
            diagnostico = self._diagnosticar_sistema_basico(ContadorModel)
            
            values = {
                'diagnostico': diagnostico,
                'page_title': 'Diagnóstico del Sistema',
            }
            
            return request.render('sat.contador_dashboard_diagnostico_template', values)
            
        except Exception as e:
            _logger.error(f"Error en diagnóstico: {e}")
            return request.redirect('/dashboard/contador')
    
    def _diagnosticar_sistema_basico(self, ContadorModel):
        """Diagnóstico básico del sistema"""
        try:
            total_registros = ContadorModel.search_count([])
            registros_con_serie = ContadorModel.search_count([('serie_detectada', '!=', False)])
            registros_sin_serie = total_registros - registros_con_serie
            
            # Registros por estado
            estados = ['procesado', 'pendiente', 'error']
            conteo_estados = {}
            for estado in estados:
                conteo_estados[estado] = ContadorModel.search_count([('estado', '=', estado)])
            
            return {
                'total_registros': total_registros,
                'registros_con_serie': registros_con_serie,
                'registros_sin_serie': registros_sin_serie,
                'estados': conteo_estados,
                'porcentaje_procesados': round((conteo_estados.get('procesado', 0) / total_registros * 100) if total_registros > 0 else 0, 1)
            }
        except Exception as e:
            _logger.error(f"Error en diagnóstico básico: {e}")
            return {}
    
    @http.route('/dashboard/contador/detalle/<int:equipo_id>', type='http', auth='user', website=True)
    def dashboard_detalle(self, equipo_id, **kwargs):
        """
        Página de detalle de un equipo específico
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Obtener equipo
            equipo = ContadorModel.browse(equipo_id)
            if not equipo.exists():
                return request.not_found()
            
            # Preparar detalle
            detalle = {
                'id': equipo.id,
                'serie_detectada': equipo.serie_detectada or 'Sin serie',
                'cliente_detectado': equipo.cliente_detectado or 'Sin cliente',
                'tipo_equipo_detectado': equipo.tipo_equipo_detectado or 'N/A',
                'contador_bn_detectado': equipo.contador_bn_detectado or 0,
                'contador_color_detectado': equipo.contador_color_detectado or 0,
                'estado': equipo.estado or 'pendiente',
                'create_date': self._format_datetime(equipo.create_date),
                'remitente': getattr(equipo, 'remitente', 'N/A'),
            }
            
            values = {
                'equipo': detalle,
                'page_title': f'Detalle Equipo {detalle["serie_detectada"]}',
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
            
            # Obtener equipo
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
                    'remitente': getattr(registro, 'remitente', 'N/A'),
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
            try:
                estadisticas = ContadorModel.obtener_estadisticas_dashboard()
            except AttributeError:
                estadisticas = self._get_estadisticas_basicas(ContadorModel)
            
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
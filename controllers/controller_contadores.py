# -*- coding: utf-8 -*-
import json
from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class ContadorDashboardController(http.Controller):
    
    @http.route('/dashboard/contador', type='http', auth='user', website=True)
    def dashboard_main(self, page=1, search=None, filter_type=None, **kwargs):
        """
        Ruta principal del dashboard de contadores moderno
        """
        try:
            page = int(page)
            items_per_page = 20
            
            # Obtener modelo
            ContadorModel = request.env['contador.automatico']
            
            # Construir dominio de búsqueda
            domain = [('serie_detectada', '!=', False)]
            
            # Aplicar filtro de búsqueda
            if search:
                domain.extend([
                    '|', '|',
                    ('cliente_detectado', 'ilike', search),
                    ('serie_detectada', 'ilike', search),
                    ('tipo_equipo_detectado', 'ilike', search)
                ])
            
            # Aplicar filtros específicos
            if filter_type:
                domain.extend(self._get_filter_domain(filter_type))
            
            # Obtener estadísticas
            estadisticas = self._get_estadisticas_completas(ContadorModel)
            
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
            equipos = self._format_equipos_data(equipos_raw)
            
            # Obtener conteos para filtros
            filter_counts = self._get_filter_counts(ContadorModel)
            
            # Datos para el template
            values = {
                'estadisticas': estadisticas,
                'equipos': equipos,
                'total_equipos': total_equipos,
                'current_page': page,
                'total_pages': total_pages,
                'search_query': search,
                'filter_type': filter_type,
                'filter_counts': filter_counts,
                'ultima_actualizacion': self._format_datetime(datetime.now()),
                'page_title': 'Dashboard de Contadores',
                'has_prev_page': page > 1,
                'has_next_page': page < total_pages,
                'prev_page': page - 1 if page > 1 else 1,
                'next_page': page + 1 if page < total_pages else total_pages,
            }
            
            return request.render('sat.contador_dashboard_template', values)
            
        except Exception as e:
            _logger.error(f"Error en dashboard principal: {e}")
            return self._render_error('Error cargando dashboard', str(e))
    
    def _get_filter_domain(self, filter_type):
        """
        Retorna el dominio para aplicar filtros específicos
        """
        domain = []
        
        if filter_type == 'hoy':
            hoy = datetime.now().date()
            domain.append(('create_date', '>=', hoy))
        elif filter_type == 'color':
            domain.append(('tipo_equipo_detectado', 'ilike', 'color'))
        elif filter_type == 'mono':
            domain.extend([
                '|',
                ('tipo_equipo_detectado', 'ilike', 'monocromatica'),
                ('tipo_equipo_detectado', 'ilike', 'mono')
            ])
        elif filter_type == 'procesado':
            domain.append(('estado', '=', 'procesado'))
        elif filter_type == 'pendiente':
            domain.append(('estado', '=', 'pendiente'))
        elif filter_type == 'error':
            domain.append(('estado', '=', 'error'))
        
        return domain
    
    def _format_equipos_data(self, equipos_raw):
        """
        Formatea los datos de equipos para el template
        """
        equipos = []
        for equipo in equipos_raw:
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
                'tiempo_relativo': self._get_relative_time(equipo.create_date),
                'remitente': getattr(equipo, 'remitente', 'N/A'),
            })()
            equipos.append(equipo_data)
        
        return equipos
    
    @http.route('/dashboard/contador/api/equipos', type='json', auth='user', methods=['GET', 'POST'])
    def api_get_equipos(self, limit=20, offset=0, search=None, filter_type=None, sort_by=None, sort_order='desc', **kwargs):
        """
        API JSON mejorada para obtener equipos con filtros avanzados
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Construir dominio base
            domain = [('serie_detectada', '!=', False)]
            
            # Aplicar filtro de búsqueda
            if search:
                domain.extend([
                    '|', '|',
                    ('cliente_detectado', 'ilike', search),
                    ('serie_detectada', 'ilike', search),
                    ('tipo_equipo_detectado', 'ilike', search)
                ])
            
            # Aplicar filtros específicos
            if filter_type and filter_type != 'all':
                domain.extend(self._get_filter_domain(filter_type))
            
            # Construir orden
            order_fields = {
                'cliente': 'cliente_detectado',
                'serie': 'serie_detectada',
                'fecha': 'create_date',
                'estado': 'estado'
            }
            
            order_field = order_fields.get(sort_by, 'create_date')
            order = f"{order_field} {sort_order}"
            
            # Obtener equipos
            total = ContadorModel.search_count(domain)
            equipos = ContadorModel.search(domain, 
                                         limit=limit, 
                                         offset=offset, 
                                         order=order)
            
            # Formatear respuesta
            equipos_data = []
            for equipo in equipos:
                equipos_data.append({
                    'id': equipo.id,
                    'cliente': equipo.cliente_detectado or 'Sin cliente',
                    'serie': equipo.serie_detectada or 'Sin serie',
                    'tipo': equipo.tipo_equipo_detectado or 'N/A',
                    'contador_bn': equipo.contador_bn_detectado or 0,
                    'contador_color': equipo.contador_color_detectado or 0,
                    'contador_total': (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0),
                    'estado': equipo.estado or 'pendiente',
                    'fecha': equipo.create_date.isoformat() if equipo.create_date else None,
                    'fecha_formateada': self._format_datetime(equipo.create_date),
                    'tiempo_relativo': self._get_relative_time(equipo.create_date),
                    'remitente': getattr(equipo, 'remitente', 'N/A'),
                })
            
            # Obtener conteos para filtros
            filter_counts = self._get_filter_counts(ContadorModel)
            
            return {
                'success': True,
                'data': equipos_data,
                'total': total,
                'filter_counts': filter_counts,
                'pagination': {
                    'current_page': (offset // limit) + 1,
                    'total_pages': (total + limit - 1) // limit,
                    'has_next': (offset + limit) < total,
                    'has_prev': offset > 0,
                    'items_per_page': limit
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en API equipos: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Error al obtener equipos'
            }
    
    @http.route('/dashboard/contador/api/stats', type='json', auth='user')
    def api_get_stats(self, **kwargs):
        """
        API JSON para obtener estadísticas en tiempo real
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Obtener estadísticas completas
            estadisticas = self._get_estadisticas_completas(ContadorModel)
            
            # Estadísticas adicionales para gráficos
            stats_adicionales = {
                'equipos_por_estado': self._get_equipos_por_estado(ContadorModel),
                'equipos_por_tipo': self._get_equipos_por_tipo(ContadorModel),
                'actividad_semanal': self._get_actividad_semanal(ContadorModel),
                'tendencias': self._get_tendencias(ContadorModel),
                'top_clientes': self._get_top_clientes(ContadorModel),
            }
            
            return {
                'success': True,
                'data': {
                    'estadisticas_principales': estadisticas,
                    'estadisticas_adicionales': stats_adicionales,
                    'timestamp': datetime.now().isoformat(),
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en API stats: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/dashboard/contador/api/filters', type='json', auth='user')
    def api_get_filter_counts(self, **kwargs):
        """
        API para obtener conteos de filtros actualizados
        """
        try:
            ContadorModel = request.env['contador.automatico']
            filter_counts = self._get_filter_counts(ContadorModel)
            
            return {
                'success': True,
                'data': filter_counts
            }
        except Exception as e:
            _logger.error(f"Error obteniendo conteos de filtros: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/dashboard/contador/refresh', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def dashboard_refresh(self, **kwargs):
        """
        Endpoint para refrescar datos del dashboard
        """
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Ejecutar actualización de datos si el método existe
            if hasattr(ContadorModel, 'cron_procesar_correos_perdidos'):
                result = ContadorModel.cron_procesar_correos_perdidos()
                mensaje = 'Dashboard actualizado correctamente'
                tipo = 'success'
            else:
                mensaje = 'Actualización manual completada'
                tipo = 'info'
                _logger.warning("Método cron_procesar_correos_perdidos no encontrado")
            
            # Si es petición AJAX, devolver JSON
            if request.httprequest.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {
                    'success': True,
                    'message': mensaje,
                    'timestamp': datetime.now().isoformat(),
                    'processed_count': getattr(result, 'processed_count', 0) if hasattr(result, 'processed_count') else 0
                }
            
            # Si es petición normal, redirigir con mensaje
            request.session['dashboard_message'] = {
                'type': tipo,
                'text': mensaje
            }
            
        except Exception as e:
            _logger.error(f"Error refrescando dashboard: {e}")
            
            if request.httprequest.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {
                    'success': False,
                    'error': str(e)
                }
            
            request.session['dashboard_message'] = {
                'type': 'danger',
                'text': f'Error actualizando: {str(e)}'
            }
        
        return request.redirect('/dashboard/contador')
    
    def _get_estadisticas_completas(self, ContadorModel):
        """
        Obtiene estadísticas completas del sistema
        """
        try:
            # Fechas de referencia
            hoy = datetime.now().date()
            ayer = hoy - timedelta(days=1)
            hace_semana = hoy - timedelta(days=7)
            hace_mes = hoy - timedelta(days=30)
            
            # Equipos únicos por período
            equipos_hoy = ContadorModel.search([
                ('create_date', '>=', hoy),
                ('serie_detectada', '!=', False)
            ])
            
            equipos_ayer = ContadorModel.search([
                ('create_date', '>=', ayer),
                ('create_date', '<', hoy),
                ('serie_detectada', '!=', False)
            ])
            
            equipos_semana = ContadorModel.search([
                ('create_date', '>=', hace_semana),
                ('serie_detectada', '!=', False)
            ])
            
            equipos_mes = ContadorModel.search([
                ('create_date', '>=', hace_mes),
                ('serie_detectada', '!=', False)
            ])
            
            # Contar equipos únicos por serie
            series_hoy = set(e.serie_detectada for e in equipos_hoy if e.serie_detectada)
            series_ayer = set(e.serie_detectada for e in equipos_ayer if e.serie_detectada)
            series_semana = set(e.serie_detectada for e in equipos_semana if e.serie_detectada)
            series_mes = set(e.serie_detectada for e in equipos_mes if e.serie_detectada)
            
            # Total de equipos únicos
            total_equipos = ContadorModel.search_count([('serie_detectada', '!=', False)])
            
            # Conteos por estado
            equipos_procesados = ContadorModel.search_count([
                ('estado', '=', 'procesado'),
                ('serie_detectada', '!=', False)
            ])
            
            equipos_pendientes = ContadorModel.search_count([
                ('estado', '=', 'pendiente'),
                ('serie_detectada', '!=', False)
            ])
            
            equipos_error = ContadorModel.search_count([
                ('estado', '=', 'error'),
                ('serie_detectada', '!=', False)
            ])
            
            # Calcular eficiencia y tendencias
            eficiencia = round((equipos_procesados / total_equipos * 100) if total_equipos > 0 else 0, 1)
            
            # Tendencias (comparación con ayer)
            tendencia_hoy = len(series_hoy) - len(series_ayer)
            porcentaje_tendencia = round((tendencia_hoy / len(series_ayer) * 100) if len(series_ayer) > 0 else 0, 1)
            
            return {
                'equipos_unicos_hoy': len(series_hoy),
                'equipos_unicos_semana': len(series_semana),
                'equipos_unicos_mes': len(series_mes),
                'total_equipos_sistema': total_equipos,
                'eficiencia_sistema': eficiencia,
                'equipos_procesados': equipos_procesados,
                'equipos_pendientes': equipos_pendientes,
                'equipos_error': equipos_error,
                'tendencia_hoy': tendencia_hoy,
                'porcentaje_tendencia': porcentaje_tendencia,
                'total_registros_hoy': len(equipos_hoy),
                'total_registros_semana': len(equipos_semana),
            }
            
        except Exception as e:
            _logger.error(f"Error calculando estadísticas completas: {e}")
            return self._get_estadisticas_basicas()
    
    def _get_estadisticas_basicas(self):
        """
        Estadísticas básicas en caso de error
        """
        return {
            'equipos_unicos_hoy': 0,
            'equipos_unicos_semana': 0,
            'equipos_unicos_mes': 0,
            'total_equipos_sistema': 0,
            'eficiencia_sistema': 0,
            'equipos_procesados': 0,
            'equipos_pendientes': 0,
            'equipos_error': 0,
            'tendencia_hoy': 0,
            'porcentaje_tendencia': 0,
            'total_registros_hoy': 0,
            'total_registros_semana': 0,
        }
    
    def _get_filter_counts(self, ContadorModel):
        """
        Obtiene conteos para todos los filtros
        """
        try:
            hoy = datetime.now().date()
            
            counts = {
                'all': ContadorModel.search_count([('serie_detectada', '!=', False)]),
                'hoy': ContadorModel.search_count([
                    ('create_date', '>=', hoy),
                    ('serie_detectada', '!=', False)
                ]),
                'color': ContadorModel.search_count([
                    ('tipo_equipo_detectado', 'ilike', 'color'),
                    ('serie_detectada', '!=', False)
                ]),
                'mono': ContadorModel.search_count([
                    '|',
                    ('tipo_equipo_detectado', 'ilike', 'monocromatica'),
                    ('tipo_equipo_detectado', 'ilike', 'mono'),
                    ('serie_detectada', '!=', False)
                ]),
                'procesado': ContadorModel.search_count([
                    ('estado', '=', 'procesado'),
                    ('serie_detectada', '!=', False)
                ]),
                'pendiente': ContadorModel.search_count([
                    ('estado', '=', 'pendiente'),
                    ('serie_detectada', '!=', False)
                ]),
                'error': ContadorModel.search_count([
                    ('estado', '=', 'error'),
                    ('serie_detectada', '!=', False)
                ]),
            }
            
            return counts
            
        except Exception as e:
            _logger.error(f"Error obteniendo conteos de filtros: {e}")
            return {'all': 0, 'hoy': 0, 'color': 0, 'mono': 0, 'procesado': 0, 'pendiente': 0, 'error': 0}
    
    def _get_equipos_por_estado(self, ContadorModel):
        """Obtiene distribución de equipos por estado"""
        try:
            estados = ContadorModel.read_group(
                [('serie_detectada', '!=', False)],
                ['estado'],
                ['estado']
            )
            return {estado['estado'] or 'sin_estado': estado['estado_count'] for estado in estados}
        except Exception as e:
            _logger.error(f"Error obteniendo equipos por estado: {e}")
            return {}
    
    def _get_equipos_por_tipo(self, ContadorModel):
        """Obtiene distribución de equipos por tipo"""
        try:
            tipos = ContadorModel.read_group(
                [('serie_detectada', '!=', False)],
                ['tipo_equipo_detectado'],
                ['tipo_equipo_detectado']
            )
            return {tipo['tipo_equipo_detectado'] or 'sin_tipo': tipo['tipo_equipo_detectado_count'] for tipo in tipos}
        except Exception as e:
            _logger.error(f"Error obteniendo equipos por tipo: {e}")
            return {}
    
    def _get_actividad_semanal(self, ContadorModel):
        """Obtiene actividad de los últimos 7 días"""
        try:
            hace_semana = datetime.now() - timedelta(days=7)
            registros = ContadorModel.search([
                ('create_date', '>=', hace_semana),
                ('serie_detectada', '!=', False)
            ])
            
            actividad = {}
            for i in range(7):
                fecha = (datetime.now() - timedelta(days=i)).date()
                actividad[fecha.isoformat()] = 0
            
            for registro in registros:
                fecha = registro.create_date.date().isoformat()
                if fecha in actividad:
                    actividad[fecha] += 1
            
            return actividad
        except Exception as e:
            _logger.error(f"Error obteniendo actividad semanal: {e}")
            return {}
    
    def _get_tendencias(self, ContadorModel):
        """Calcula tendencias de crecimiento"""
        try:
            ahora = datetime.now()
            hace_24h = ahora - timedelta(hours=24)
            hace_48h = ahora - timedelta(hours=48)
            
            registros_24h = ContadorModel.search_count([
                ('create_date', '>=', hace_24h),
                ('serie_detectada', '!=', False)
            ])
            
            registros_48h = ContadorModel.search_count([
                ('create_date', '>=', hace_48h),
                ('create_date', '<', hace_24h),
                ('serie_detectada', '!=', False)
            ])
            
            tendencia = registros_24h - registros_48h
            porcentaje = round((tendencia / registros_48h * 100) if registros_48h > 0 else 0, 1)
            
            return {
                'registros_24h': registros_24h,
                'registros_48h': registros_48h,
                'diferencia': tendencia,
                'porcentaje': porcentaje
            }
        except Exception as e:
            _logger.error(f"Error calculando tendencias: {e}")
            return {}
    
    def _get_top_clientes(self, ContadorModel, limit=5):
        """Obtiene top clientes por número de equipos"""
        try:
            clientes = ContadorModel.read_group(
                [('serie_detectada', '!=', False), ('cliente_detectado', '!=', False)],
                ['cliente_detectado'],
                ['cliente_detectado'],
                limit=limit,
                orderby='cliente_detectado_count desc'
            )
            return [{
                'cliente': cliente['cliente_detectado'],
                'count': cliente['cliente_detectado_count']
            } for cliente in clientes]
        except Exception as e:
            _logger.error(f"Error obteniendo top clientes: {e}")
            return []
    
    def _format_datetime(self, dt):
        """Formatea datetime para mostrar"""
        if not dt:
            return 'N/A'
        
        try:
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            
            return dt.strftime('%d/%m/%Y %H:%M')
        except:
            return str(dt)
    
    def _get_relative_time(self, dt):
        """Obtiene tiempo transcurrido en formato legible"""
        if not dt:
            return ''
        
        try:
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            
            now = datetime.now()
            if dt.tzinfo:
                now = now.replace(tzinfo=dt.tzinfo)
                
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
                
        except Exception as e:
            _logger.error(f"Error calculando tiempo relativo: {e}")
            return ''
    
    def _render_error(self, title, message):
        """Renderiza página de error"""
        values = {
            'error_title': title,
            'error_message': message,
            'page_title': 'Error - Dashboard'
        }
        return request.render('web.http_error', values)
    
    # Rutas adicionales para páginas específicas
    
    @http.route('/dashboard/contador/detalle/<int:equipo_id>', type='http', auth='user', website=True)
    def dashboard_detalle(self, equipo_id, **kwargs):
        """Página de detalle de un equipo específico"""
        try:
            ContadorModel = request.env['contador.automatico']
            equipo = ContadorModel.browse(equipo_id)
            
            if not equipo.exists():
                return request.not_found()
            
            # Obtener historial del equipo
            historial = ContadorModel.search([
                ('serie_detectada', '=', equipo.serie_detectada)
            ], order='create_date desc', limit=20)
            
            detalle = {
                'equipo': equipo,
                'historial': historial,
                'page_title': f'Detalle - {equipo.serie_detectada or "Sin serie"}'
            }
            
            return request.render('sat.contador_detalle_template', detalle)
            
        except Exception as e:
            _logger.error(f"Error en detalle: {e}")
            return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/export/excel', type='http', auth='user')
    def export_excel(self, search=None, filter_type=None, **kwargs):
        """Exportar datos a Excel"""
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
            
            if filter_type and filter_type != 'all':
                domain.extend(self._get_filter_domain(filter_type))
            
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
                'border': 1,
                'align': 'center'
            })
            
            cell_format = workbook.add_format({'border': 1})
            number_format = workbook.add_format({'border': 1, 'num_format': '#,##0'})
            
            # Headers
            headers = [
                'Cliente', 'Serie', 'Tipo', 'Contador B/N', 
                'Contador Color', 'Total', 'Estado', 'Fecha Creación', 'Remitente'
            ]
            
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)
            
            # Datos
            for row, equipo in enumerate(equipos, 1):
                worksheet.write(row, 0, equipo.cliente_detectado or '', cell_format)
                worksheet.write(row, 1, equipo.serie_detectada or '', cell_format)
                worksheet.write(row, 2, equipo.tipo_equipo_detectado or '', cell_format)
                worksheet.write(row, 3, equipo.contador_bn_detectado or 0, number_format)
                worksheet.write(row, 4, equipo.contador_color_detectado or 0, number_format)
                worksheet.write(row, 5, (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0), number_format)
                worksheet.write(row, 6, equipo.estado or '', cell_format)
                worksheet.write(row, 7, self._format_datetime(equipo.create_date), cell_format)
                worksheet.write(row, 8, getattr(equipo, 'remitente', '') or '', cell_format)
            
            # Ajustar ancho de columnas
            worksheet.set_column('A:I', 15)
            
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
    
    @http.route('/dashboard/contador/stats', type='http', auth='user', website=True)
    def dashboard_stats(self, **kwargs):
        """Página de estadísticas detalladas"""
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Obtener estadísticas completas
            estadisticas = self._get_estadisticas_completas(ContadorModel)
            
            # Estadísticas adicionales para gráficos
            stats_adicionales = {
                'equipos_por_estado': self._get_equipos_por_estado(ContadorModel),
                'equipos_por_tipo': self._get_equipos_por_tipo(ContadorModel),
                'actividad_semanal': self._get_actividad_semanal(ContadorModel),
                'tendencias': self._get_tendencias(ContadorModel),
                'top_clientes': self._get_top_clientes(ContadorModel),
                'actividad_mensual': self._get_actividad_mensual(ContadorModel),
                'resumen_contadores': self._get_resumen_contadores(ContadorModel),
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
        """Página de diagnóstico del sistema"""
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Ejecutar diagnóstico completo
            diagnostico = self._diagnosticar_sistema_completo(ContadorModel)
            
            values = {
                'diagnostico': diagnostico,
                'page_title': 'Diagnóstico del Sistema',
            }
            
            return request.render('sat.contador_dashboard_diagnostico_template', values)
            
        except Exception as e:
            _logger.error(f"Error en diagnóstico: {e}")
            return request.redirect('/dashboard/contador')
    
    def _get_actividad_mensual(self, ContadorModel):
        """Obtiene actividad de los últimos 30 días"""
        try:
            hace_mes = datetime.now() - timedelta(days=30)
            registros = ContadorModel.search([
                ('create_date', '>=', hace_mes),
                ('serie_detectada', '!=', False)
            ])
            
            actividad = {}
            for i in range(30):
                fecha = (datetime.now() - timedelta(days=i)).date()
                actividad[fecha.isoformat()] = 0
            
            for registro in registros:
                fecha = registro.create_date.date().isoformat()
                if fecha in actividad:
                    actividad[fecha] += 1
            
            return actividad
        except Exception as e:
            _logger.error(f"Error obteniendo actividad mensual: {e}")
            return {}
    
    def _get_resumen_contadores(self, ContadorModel):
        """Obtiene resumen de contadores totales"""
        try:
            equipos = ContadorModel.search([('serie_detectada', '!=', False)])
            
            total_bn = sum(e.contador_bn_detectado or 0 for e in equipos)
            total_color = sum(e.contador_color_detectado or 0 for e in equipos)
            total_general = total_bn + total_color
            
            promedio_bn = round(total_bn / len(equipos) if equipos else 0, 2)
            promedio_color = round(total_color / len(equipos) if equipos else 0, 2)
            
            return {
                'total_bn': total_bn,
                'total_color': total_color,
                'total_general': total_general,
                'promedio_bn': promedio_bn,
                'promedio_color': promedio_color,
                'equipos_count': len(equipos)
            }
        except Exception as e:
            _logger.error(f"Error obteniendo resumen contadores: {e}")
            return {}
    
    def _diagnosticar_sistema_completo(self, ContadorModel):
        """Diagnóstico completo del sistema"""
        try:
            # Conteos básicos
            total_registros = ContadorModel.search_count([])
            registros_con_serie = ContadorModel.search_count([('serie_detectada', '!=', False)])
            registros_sin_serie = total_registros - registros_con_serie
            
            # Registros por estado
            estados = ['procesado', 'pendiente', 'error']
            conteo_estados = {}
            for estado in estados:
                conteo_estados[estado] = ContadorModel.search_count([('estado', '=', estado)])
            
            # Análisis de calidad de datos
            registros_sin_cliente = ContadorModel.search_count([
                ('cliente_detectado', '=', False),
                ('serie_detectada', '!=', False)
            ])
            
            registros_sin_tipo = ContadorModel.search_count([
                ('tipo_equipo_detectado', '=', False),
                ('serie_detectada', '!=', False)
            ])
            
            registros_sin_contadores = ContadorModel.search_count([
                ('contador_bn_detectado', '=', 0),
                ('contador_color_detectado', '=', 0),
                ('serie_detectada', '!=', False)
            ])
            
            # Análisis temporal
            hoy = datetime.now().date()
            registros_hoy = ContadorModel.search_count([('create_date', '>=', hoy)])
            
            hace_semana = hoy - timedelta(days=7)
            registros_semana = ContadorModel.search_count([('create_date', '>=', hace_semana)])
            
            # Problemas detectados
            problemas = []
            
            if registros_sin_serie > (total_registros * 0.1):  # Más del 10%
                problemas.append({
                    'tipo': 'warning',
                    'mensaje': f'Alto porcentaje de registros sin serie detectada: {registros_sin_serie}/{total_registros} ({round(registros_sin_serie/total_registros*100, 1)}%)'
                })
            
            if conteo_estados.get('error', 0) > (total_registros * 0.05):  # Más del 5%
                problemas.append({
                    'tipo': 'danger',
                    'mensaje': f'Alto porcentaje de errores: {conteo_estados["error"]}/{total_registros} ({round(conteo_estados["error"]/total_registros*100, 1)}%)'
                })
            
            if registros_sin_contadores > (registros_con_serie * 0.2):  # Más del 20%
                problemas.append({
                    'tipo': 'warning',
                    'mensaje': f'Muchos equipos sin contadores: {registros_sin_contadores}/{registros_con_serie} ({round(registros_sin_contadores/registros_con_serie*100, 1)}%)'
                })
            
            if registros_hoy == 0:
                problemas.append({
                    'tipo': 'info',
                    'mensaje': 'No se han procesado registros hoy'
                })
            
            # Recomendaciones
            recomendaciones = []
            
            if conteo_estados.get('pendiente', 0) > 10:
                recomendaciones.append('Ejecutar procesamiento de correos pendientes')
            
            if registros_sin_cliente > 5:
                recomendaciones.append('Revisar configuración de detección de clientes')
            
            if registros_sin_tipo > 5:
                recomendaciones.append('Actualizar patrones de detección de tipos de equipos')
            
            # Métricas de rendimiento
            porcentaje_procesados = round((conteo_estados.get('procesado', 0) / total_registros * 100) if total_registros > 0 else 0, 1)
            porcentaje_calidad = round(((registros_con_serie - registros_sin_cliente - registros_sin_tipo) / registros_con_serie * 100) if registros_con_serie > 0 else 0, 1)
            
            # Estado general del sistema
            if porcentaje_procesados >= 90 and len(problemas) == 0:
                estado_sistema = 'excelente'
            elif porcentaje_procesados >= 75 and len([p for p in problemas if p['tipo'] == 'danger']) == 0:
                estado_sistema = 'bueno'
            elif porcentaje_procesados >= 50:
                estado_sistema = 'regular'
            else:
                estado_sistema = 'critico'
            
            return {
                'total_registros': total_registros,
                'registros_con_serie': registros_con_serie,
                'registros_sin_serie': registros_sin_serie,
                'estados': conteo_estados,
                'registros_sin_cliente': registros_sin_cliente,
                'registros_sin_tipo': registros_sin_tipo,
                'registros_sin_contadores': registros_sin_contadores,
                'registros_hoy': registros_hoy,
                'registros_semana': registros_semana,
                'porcentaje_procesados': porcentaje_procesados,
                'porcentaje_calidad': porcentaje_calidad,
                'problemas': problemas,
                'recomendaciones': recomendaciones,
                'estado_sistema': estado_sistema,
                'timestamp': datetime.now().isoformat(),
            }
            
        except Exception as e:
            _logger.error(f"Error en diagnóstico completo: {e}")
            return {
                'error': str(e),
                'estado_sistema': 'error',
                'timestamp': datetime.now().isoformat(),
            }
    
    # Rutas adicionales para funcionalidades específicas
    
    @http.route('/dashboard/contador/search/suggestions', type='json', auth='user')
    def search_suggestions(self, query=None, limit=10, **kwargs):
        """API para sugerencias de búsqueda"""
        try:
            if not query or len(query) < 2:
                return {'success': True, 'suggestions': []}
            
            ContadorModel = request.env['contador.automatico']
            
            # Buscar clientes
            clientes = ContadorModel.search([
                ('cliente_detectado', 'ilike', query),
                ('cliente_detectado', '!=', False)
            ], limit=limit//2)
            
            # Buscar series
            series = ContadorModel.search([
                ('serie_detectada', 'ilike', query),
                ('serie_detectada', '!=', False)
            ], limit=limit//2)
            
            suggestions = []
            
            # Agregar clientes únicos
            clientes_unicos = set()
            for cliente in clientes:
                if cliente.cliente_detectado and cliente.cliente_detectado not in clientes_unicos:
                    suggestions.append({
                        'type': 'cliente',
                        'value': cliente.cliente_detectado,
                        'label': f'Cliente: {cliente.cliente_detectado}'
                    })
                    clientes_unicos.add(cliente.cliente_detectado)
            
            # Agregar series únicas
            series_unicos = set()
            for serie in series:
                if serie.serie_detectada and serie.serie_detectada not in series_unicos:
                    suggestions.append({
                        'type': 'serie',
                        'value': serie.serie_detectada,
                        'label': f'Serie: {serie.serie_detectada}'
                    })
                    series_unicos.add(serie.serie_detectada)
            
            return {
                'success': True,
                'suggestions': suggestions[:limit]
            }
            
        except Exception as e:
            _logger.error(f"Error en sugerencias de búsqueda: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/dashboard/contador/bulk-action', type='json', auth='user', methods=['POST'])
    def bulk_action(self, action=None, equipment_ids=None, **kwargs):
        """API para acciones en lote"""
        try:
            if not action or not equipment_ids:
                return {
                    'success': False,
                    'error': 'Acción y IDs de equipos son requeridos'
                }
            
            ContadorModel = request.env['contador.automatico']
            equipos = ContadorModel.browse(equipment_ids)
            
            result = {'success': True, 'processed': 0, 'errors': []}
            
            if action == 'mark_processed':
                for equipo in equipos:
                    try:
                        equipo.write({'estado': 'procesado'})
                        result['processed'] += 1
                    except Exception as e:
                        result['errors'].append(f'Error procesando equipo {equipo.id}: {str(e)}')
                        
            elif action == 'mark_pending':
                for equipo in equipos:
                    try:
                        equipo.write({'estado': 'pendiente'})
                        result['processed'] += 1
                    except Exception as e:
                        result['errors'].append(f'Error procesando equipo {equipo.id}: {str(e)}')
                        
            elif action == 'delete':
                try:
                    equipos.unlink()
                    result['processed'] = len(equipment_ids)
                except Exception as e:
                    result['errors'].append(f'Error eliminando equipos: {str(e)}')
                    
            else:
                return {
                    'success': False,
                    'error': f'Acción no válida: {action}'
                }
            
            return result
            
        except Exception as e:
            _logger.error(f"Error en acción en lote: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/dashboard/contador/export/csv', type='http', auth='user')
    def export_csv(self, search=None, filter_type=None, **kwargs):
        """Exportar datos a CSV"""
        try:
            import csv
            import io
            
            ContadorModel = request.env['contador.automatico']
            
            # Construir dominio (mismo que Excel)
            domain = [('serie_detectada', '!=', False)]
            
            if search:
                domain.extend([
                    '|', '|',
                    ('cliente_detectado', 'ilike', search),
                    ('serie_detectada', 'ilike', search),
                    ('tipo_equipo_detectado', 'ilike', search)
                ])
            
            if filter_type and filter_type != 'all':
                domain.extend(self._get_filter_domain(filter_type))
            
            # Obtener equipos
            equipos = ContadorModel.search(domain, order='create_date desc')
            
            # Crear CSV en memoria
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            headers = [
                'Cliente', 'Serie', 'Tipo', 'Contador B/N', 
                'Contador Color', 'Total', 'Estado', 'Fecha Creación', 'Remitente'
            ]
            writer.writerow(headers)
            
            # Datos
            for equipo in equipos:
                writer.writerow([
                    equipo.cliente_detectado or '',
                    equipo.serie_detectada or '',
                    equipo.tipo_equipo_detectado or '',
                    equipo.contador_bn_detectado or 0,
                    equipo.contador_color_detectado or 0,
                    (equipo.contador_bn_detectado or 0) + (equipo.contador_color_detectado or 0),
                    equipo.estado or '',
                    self._format_datetime(equipo.create_date),
                    getattr(equipo, 'remitente', '') or ''
                ])
            
            # Preparar respuesta
            filename = f'dashboard_contadores_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            return request.make_response(
                output.getvalue(),
                headers=[
                    ('Content-Type', 'text/csv'),
                    ('Content-Disposition', f'attachment; filename={filename}')
                ]
            )
            
        except Exception as e:
            _logger.error(f"Error exportando CSV: {e}")
            return request.redirect('/dashboard/contador')
    
    @http.route('/dashboard/contador/api/health', type='json', auth='user')
    def api_health_check(self, **kwargs):
        """API para verificar el estado del sistema"""
        try:
            ContadorModel = request.env['contador.automatico']
            
            # Verificaciones básicas
            total_registros = ContadorModel.search_count([])
            ultimo_registro = ContadorModel.search([], limit=1, order='create_date desc')
            
            # Estado del sistema
            health_status = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'total_records': total_registros,
                'last_record_date': self._format_datetime(ultimo_registro.create_date) if ultimo_registro else None,
                'services': {
                    'database': 'ok',
                    'model': 'ok'
                }
            }
            
            # Verificar si hay registros recientes (últimas 24 horas)
            hace_24h = datetime.now() - timedelta(hours=24)
            registros_recientes = ContadorModel.search_count([('create_date', '>=', hace_24h)])
            
            if registros_recientes == 0:
                health_status['status'] = 'warning'
                health_status['warnings'] = ['No hay registros en las últimas 24 horas']
            
            return {
                'success': True,
                'data': health_status
            }
            
        except Exception as e:
            _logger.error(f"Error en health check: {e}")
            return {
                'success': False,
                'error': str(e),
                'status': 'error'
            }
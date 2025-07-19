# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class ContadorAutomatico(models.Model):
    _inherit = 'contador.automatico'

    # Campos adicionales que podrían ser necesarios para el dashboard
    estado_ultimo = fields.Selection([
        ('procesado', 'Procesado'),
        ('pendiente', 'Pendiente'),
        ('error', 'Error'),
        ('manual', 'Manual')
    ], string='Estado Último', default='pendiente')

    ultima_actualizacion = fields.Datetime(
        string='Última Actualización',
        default=fields.Datetime.now
    )

    @api.model
    def obtener_estadisticas_dashboard(self):
        """
        Método que coincide con la llamada del JavaScript.
        Devuelve estadísticas para el dashboard.
        """
        try:
            hoy = fields.Date.today()
            hace_7 = hoy - timedelta(days=7)
            hace_24h = fields.Datetime.now() - timedelta(hours=24)

            # Equipos únicos procesados hoy (últimas 24 horas)
            domain_hoy = [
                ('create_date', '>=', hace_24h),
                ('estado', '=', 'procesado'),
                ('serie_detectada', '!=', False),
            ]
            regs_hoy = self.search(domain_hoy)
            series_hoy = set(regs_hoy.mapped('serie_detectada'))

            # Equipos únicos procesados en últimos 7 días
            domain_sem = [
                ('create_date', '>=', hace_7),
                ('estado', '=', 'procesado'),
                ('serie_detectada', '!=', False),
            ]
            regs_sem = self.search(domain_sem)
            series_sem = set(regs_sem.mapped('serie_detectada'))

            # Total de equipos en el sistema
            # Ajusta según tu modelo de equipos
            total_equipos = len(set(self.search([('serie_detectada', '!=', False)]).mapped('serie_detectada')))

            # Cálculo de eficiencia últimos 7 días
            tot_reg7 = self.search_count([('create_date', '>=', hace_7)])
            ok7 = self.search_count([
                ('create_date', '>=', hace_7), 
                ('estado', '=', 'procesado')
            ])
            eficiencia = (ok7 / tot_reg7 * 100) if tot_reg7 else 0.0

            return {
                'equipos_unicos_hoy': len(series_hoy),
                'equipos_unicos_semana': len(series_sem),
                'total_equipos_sistema': total_equipos,
                'eficiencia_sistema': round(eficiencia, 1),
                'total_registros_semana': len(regs_sem),
                'estado_sistema': 'optimo' if eficiencia >= 90 
                                 else 'atencion' if eficiencia >= 70 
                                 else 'critico',
            }
        except Exception as e:
            _logger.error(f"Error en obtener_estadisticas_dashboard: {e}")
            return {
                'equipos_unicos_hoy': 0,
                'equipos_unicos_semana': 0,
                'total_equipos_sistema': 0,
                'eficiencia_sistema': 0,
                'total_registros_semana': 0,
                'estado_sistema': 'critico',
            }

    @api.model
    def obtener_lista_equipos_dashboard(self, limit=100):
        """
        Método que coincide con la llamada del JavaScript.
        Devuelve lista de equipos para el dashboard.
        """
        try:
            domain = [
                ('serie_detectada', '!=', False),
            ]
            
            # Obtener el último registro de cada serie
            all_regs = self.search(domain, order='create_date desc')
            unique_series = {}
            
            for rec in all_regs:
                serie = rec.serie_detectada
                if serie not in unique_series:
                    unique_series[serie] = rec
                if len(unique_series) >= limit:
                    break

            result = []
            for rec in unique_series.values():
                # Mapear campos existentes a los que espera el JavaScript
                equipo_data = {
                    'id': rec.id,
                    'serie_detectada': rec.serie_detectada or 'Sin serie',
                    'cliente_detectado': rec.cliente_detectado or 'Cliente no detectado',
                    'tipo_equipo_detectado': rec.tipo_equipo_detectado or 'No detectado',
                    # Mapear contadores existentes
                    'contador_bn_actual': rec.contador_bn_detectado or 0,
                    'contador_color_actual': rec.contador_color_detectado or 0,
                    'contador_total_actual': rec.contador_total_detectado or 0,
                    # Usar create_date como fecha de actualización
                    'ultima_actualizacion': rec.create_date.isoformat() if rec.create_date else '',
                    'estado_ultimo': rec.estado or 'pendiente',
                }
                result.append(equipo_data)
            
            # Ordenar por fecha descendente
            result.sort(key=lambda x: x['ultima_actualizacion'], reverse=True)
            return result
            
        except Exception as e:
            _logger.error(f"Error en obtener_lista_equipos_dashboard: {e}")
            return []

    @api.model
    def obtener_detalle_equipo(self, equipo_id):
        """
        Método que coincide con la llamada del JavaScript.
        Devuelve el detalle completo de un equipo específico.
        """
        try:
            equipo = self.browse(equipo_id)
            if not equipo.exists():
                return {}

            return {
                'id': equipo.id,
                'serie_detectada': equipo.serie_detectada or 'Sin serie',
                'cliente_detectado': equipo.cliente_detectado or 'Cliente no detectado',
                'tipo_equipo_detectado': equipo.tipo_equipo_detectado or 'No detectado',
                # Mapear contadores existentes
                'contador_bn_actual': equipo.contador_bn_detectado or 0,
                'contador_color_actual': equipo.contador_color_detectado or 0,
                'contador_total_actual': equipo.contador_total_detectado or 0,
                # Usar create_date como última actualización
                'ultima_actualizacion': equipo.create_date.isoformat() if equipo.create_date else '',
                'estado_ultimo': equipo.estado or 'pendiente',
                'archivo_origen': equipo.name or '',
                'create_date': equipo.create_date.isoformat() if equipo.create_date else '',
                'write_date': equipo.write_date.isoformat() if equipo.write_date else '',
                # Información adicional del modelo existente
                'remitente': equipo.remitente or '',
                'marca_detectada': equipo.marca_detectada or '',
                'idioma_detectado': equipo.idioma_detectado or '',
                'confianza_deteccion': equipo.confianza_deteccion or 0,
            }
        except Exception as e:
            _logger.error(f"Error en obtener_detalle_equipo: {e}")
            return {}

    def refresh_dashboard(self):
        """
        Método para refrescar el dashboard manualmente.
        Debe ser un método de instancia, no @api.model
        """
        # Aquí podrías agregar lógica adicional como:
        # - Limpiar caché
        # - Recalcular estadísticas
        # - Actualizar registros
        
        # Retornar una acción que recargue la vista actual
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def action_refresh_dashboard_data(self):
        """
        Método específico para refrescar datos del dashboard via RPC
        """
        try:
            # Forzar recarga de datos
            estadisticas = self.obtener_estadisticas_dashboard()
            equipos = self.obtener_lista_equipos_dashboard()
            
            return {
                'success': True,
                'estadisticas': estadisticas,
                'equipos': equipos,
                'message': 'Dashboard actualizado correctamente'
            }
        except Exception as e:
            _logger.error(f"Error actualizando dashboard: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    # Métodos adicionales de utilidad para el dashboard

    @api.model
    def get_equipos_por_tipo(self):
        """
        Obtiene estadísticas de equipos por tipo (color vs monocromático)
        """
        try:
            domain_color = [
                ('tipo_equipo_detectado', '=', 'color'),
                ('serie_detectada', '!=', False)
            ]
            domain_mono = [
                ('tipo_equipo_detectado', '=', 'monocromatica'),
                ('serie_detectada', '!=', False)
            ]
            
            equipos_color = len(set(self.search(domain_color).mapped('serie_detectada')))
            equipos_mono = len(set(self.search(domain_mono).mapped('serie_detectada')))
            
            return {
                'color': equipos_color,
                'monocromatica': equipos_mono,
                'total': equipos_color + equipos_mono
            }
        except Exception as e:
            _logger.error(f"Error en get_equipos_por_tipo: {e}")
            return {'color': 0, 'monocromatica': 0, 'total': 0}

    @api.model
    def get_equipos_por_estado(self):
        """
        Obtiene estadísticas de equipos por estado
        """
        try:
            estados = ['procesado', 'pendiente', 'error', 'manual']
            result = {}
            
            for estado in estados:
                count = self.search_count([('estado', '=', estado)])
                result[estado] = count
                
            return result
        except Exception as e:
            _logger.error(f"Error en get_equipos_por_estado: {e}")
            return {'procesado': 0, 'pendiente': 0, 'error': 0, 'manual': 0}

    @api.model
    def get_actividad_semanal(self):
        """
        Obtiene la actividad de los últimos 7 días
        """
        try:
            actividad = []
            hoy = fields.Date.today()
            
            for i in range(7):
                fecha = hoy - timedelta(days=i)
                fecha_inicio = datetime.combine(fecha, datetime.min.time())
                fecha_fin = datetime.combine(fecha, datetime.max.time())
                
                count = self.search_count([
                    ('create_date', '>=', fecha_inicio),
                    ('create_date', '<=', fecha_fin),
                    ('estado', '=', 'procesado')
                ])
                
                actividad.append({
                    'fecha': fecha.strftime('%Y-%m-%d'),
                    'fecha_corta': fecha.strftime('%d/%m'),
                    'dia_semana': fecha.strftime('%A'),
                    'registros': count
                })
                
            return list(reversed(actividad))  # Orden cronológico
        except Exception as e:
            _logger.error(f"Error en get_actividad_semanal: {e}")
            return []

    # Métodos para compatibilidad con código existente
    @api.model
    def get_dashboard_stats(self):
        """Alias para compatibilidad"""
        return self.obtener_estadisticas_dashboard()

    @api.model
    def get_dashboard_list(self, limit=100):
        """Alias para compatibilidad"""
        return self.obtener_lista_equipos_dashboard(limit)
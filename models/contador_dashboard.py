from odoo import models, fields, api, tools
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)

class ContadorDashboard(models.Model):
    _name = 'contador.dashboard'
    _description = 'Dashboard de Contadores - Vista Resumen'
    _auto = False  # Vista virtual, no crea tabla

    # Campos virtuales para el dashboard
    serie_detectada = fields.Char('Serie')
    cliente_detectado = fields.Char('Cliente')
    tipo_equipo_detectado = fields.Selection([
        ('color', 'Color'), 
        ('monocromatica', 'Monocromática')
    ], string='Tipo Equipo')
    contador_total_actual = fields.Integer('Contador Total')
    contador_bn_actual = fields.Integer('Contador B/N')
    contador_color_actual = fields.Integer('Contador Color')
    ultima_actualizacion = fields.Datetime('Última Actualización')
    copias_hoy = fields.Integer('Copias Hoy')
    estado_ultimo = fields.Selection([
        ('procesado', 'Procesado'),
        ('manual', 'Manual'),
        ('error', 'Error')
    ], string='Estado')

    def init(self):
        """
        Vista SQL para obtener última actualización por equipo
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT DISTINCT ON (serie_detectada)
                    ROW_NUMBER() OVER() AS id,
                    serie_detectada,
                    cliente_detectado,
                    tipo_equipo_detectado,
                    contador_total_detectado AS contador_total_actual,
                    contador_bn_detectado AS contador_bn_actual,
                    contador_color_detectado AS contador_color_actual,
                    create_date AS ultima_actualizacion,
                    estado AS estado_ultimo,
                    0 AS copias_hoy
                FROM contador_automatico
                WHERE serie_detectada IS NOT NULL 
                AND estado = 'procesado'
                ORDER BY serie_detectada, create_date DESC
            )
        """ % self._table)

    @api.model
    def obtener_estadisticas_dashboard(self):
        """
        Obtiene estadísticas generales para el dashboard
        """
        try:
            hoy = fields.Date.today()
            hace_7_dias = hoy - timedelta(days=7)
            
            # Equipos únicos actualizados hoy
            equipos_hoy = self.env['contador.automatico'].search([
                ('create_date', '>=', hoy),
                ('serie_detectada', '!=', False),
                ('estado', '=', 'procesado')
            ])
            
            series_hoy = set(r.serie_detectada for r in equipos_hoy if r.serie_detectada)
            
            # Equipos únicos esta semana
            equipos_semana = self.env['contador.automatico'].search([
                ('create_date', '>=', hace_7_dias),
                ('serie_detectada', '!=', False),
                ('estado', '=', 'procesado')
            ])
            
            series_semana = set(r.serie_detectada for r in equipos_semana if r.serie_detectada)
            
            # Total equipos en sistema
            total_equipos = self.env['alquiler'].search_count([])
            
            # Eficiencia del sistema (últimos 7 días)
            total_registros = self.env['contador.automatico'].search_count([
                ('create_date', '>=', hace_7_dias)
            ])
            
            registros_exitosos = self.env['contador.automatico'].search_count([
                ('create_date', '>=', hace_7_dias),
                ('estado', '=', 'procesado')
            ])
            
            eficiencia = (registros_exitosos / total_registros * 100) if total_registros > 0 else 0
            
            return {
                'equipos_unicos_hoy': len(series_hoy),
                'equipos_unicos_semana': len(series_semana),
                'total_equipos_sistema': total_equipos,
                'total_registros_semana': len(equipos_semana),
                'eficiencia_sistema': round(eficiencia, 1),
                'estado_sistema': 'optimo' if eficiencia >= 90 else 'atencion' if eficiencia >= 70 else 'critico'
            }
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo estadísticas dashboard: {e}")
            return {
                'error': str(e),
                'equipos_unicos_hoy': 0,
                'equipos_unicos_semana': 0,
                'total_equipos_sistema': 0,
                'eficiencia_sistema': 0
            }
    @api.model
    def obtener_lista_equipos_dashboard(self):
        """
        Método para obtener lista de equipos para el dashboard
        (Requerido por el JavaScript)
        """
        try:
            # Usar la vista SQL que ya tienes definida
            equipos_records = self.search([], limit=100, order='ultima_actualizacion desc')
            
            equipos = []
            for record in equipos_records:
                equipos.append({
                    'id': record.id,
                    'cliente_detectado': record.cliente_detectado or 'Cliente no detectado',
                    'serie_detectada': record.serie_detectada or 'Sin serie',
                    'tipo_equipo_detectado': record.tipo_equipo_detectado or 'No detectado',
                    'contador_bn_actual': record.contador_bn_actual or 0,
                    'contador_color_actual': record.contador_color_actual or 0,
                    'contador_total_actual': record.contador_total_actual or 0,
                    'ultima_actualizacion': record.ultima_actualizacion.isoformat() if record.ultima_actualizacion else fields.Datetime.now().isoformat(),
                    'estado_ultimo': record.estado_ultimo or 'pendiente'
                })
            
            _logger.info(f"📊 Dashboard: {len(equipos)} equipos obtenidos para la lista")
            return equipos
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo lista equipos dashboard: {e}")
            return []

    @api.model
    def obtener_detalle_equipo(self, equipo_id):
        """
        Método para obtener detalle específico de un equipo
        (Requerido por el JavaScript para el modal)
        """
        try:
            equipo = self.browse(equipo_id)
            if not equipo.exists():
                return {}
            
            return {
                'id': equipo.id,
                'cliente_detectado': equipo.cliente_detectado or 'Cliente no detectado',
                'serie_detectada': equipo.serie_detectada or 'Sin serie',
                'tipo_equipo_detectado': equipo.tipo_equipo_detectado or 'No detectado',
                'contador_bn_actual': equipo.contador_bn_actual or 0,
                'contador_color_actual': equipo.contador_color_actual or 0,
                'contador_total_actual': equipo.contador_total_actual or 0,
                'ultima_actualizacion': equipo.ultima_actualizacion.isoformat() if equipo.ultima_actualizacion else fields.Datetime.now().isoformat(),
                'estado_ultimo': equipo.estado_ultimo or 'pendiente'
            }
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo detalle equipo {equipo_id}: {e}")
            return {}
    def filter_all(self):
        """Filtro: Todos los equipos"""
        return {'type': 'ir.actions.act_window_close'}

    def filter_hoy(self):
        """Filtro: Equipos actualizados hoy"""
        return {'type': 'ir.actions.act_window_close'}

    def filter_color(self):
        """Filtro: Equipos color"""
        return {'type': 'ir.actions.act_window_close'}

    def filter_mono(self):
        """Filtro: Equipos monocromáticos"""
        return {'type': 'ir.actions.act_window_close'}

    def close_modal(self):
        """Cerrar modal"""
        return {'type': 'ir.actions.act_window_close'}

    def close_modal_footer(self):
        """Cerrar modal desde footer"""
        return {'type': 'ir.actions.act_window_close'}

    def view_history(self):
        """Ver historial del equipo"""
        return {'type': 'ir.actions.act_window_close'}

    def floating_refresh(self):
        """Refresh flotante"""
        return self.refresh_dashboard()
    def action_ver_detalle_equipo(self):
        """
        Abre el detalle completo del equipo seleccionado
        """
        return {
            'type': 'ir.actions.act_window',
            'name': f'Detalle: {self.cliente_detectado} - {self.serie_detectada}',
            'res_model': 'contador.detalle',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_serie': self.serie_detectada,
                'default_cliente': self.cliente_detectado,
                'form_view_initial_mode': 'readonly',
            }
        }


    def refresh_dashboard(self):
        """
        Método para refrescar el dashboard
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

class ContadorDetalle(models.TransientModel):
    _name = 'contador.detalle'
    _description = 'Detalle completo de equipo'

    serie = fields.Char('Serie', readonly=True)
    cliente = fields.Char('Cliente', readonly=True)
    fecha_inicio = fields.Date('Fecha Inicio', default=lambda self: fields.Date.today() - timedelta(days=30))
    fecha_fin = fields.Date('Fecha Fin', default=fields.Date.today)
    
    # Información del equipo
    equipo_info = fields.Html('Información del Equipo', compute='_compute_equipo_info')
    historial_ids = fields.One2many(
        'contador.automatico', 
        compute='_compute_historial',
        string='Historial de Lecturas'
    )

    @api.depends('serie', 'fecha_inicio', 'fecha_fin')
    def _compute_historial(self):
        """
        Obtiene el historial de lecturas del equipo
        """
        for record in self:
            if record.serie:
                historial = self.env['contador.automatico'].search([
                    ('serie_detectada', '=', record.serie),
                    ('estado', '=', 'procesado'),
                    ('create_date', '>=', record.fecha_inicio),
                    ('create_date', '<=', record.fecha_fin)
                ], order='create_date desc')
                
                record.historial_ids = historial
            else:
                record.historial_ids = False

    @api.depends('serie')
    def _compute_equipo_info(self):
        """
        Genera información resumida del equipo
        """
        for record in self:
            if record.serie:
                # Buscar último registro
                ultimo_registro = self.env['contador.automatico'].search([
                    ('serie_detectada', '=', record.serie),
                    ('estado', '=', 'procesado')
                ], order='create_date desc', limit=1)
                
                if ultimo_registro:
                    html = f"""
                    <div class="row">
                        <div class="col-md-6">
                            <h4>📊 Contadores Actuales</h4>
                            <p><strong>Total:</strong> {ultimo_registro.contador_total_detectado or 0:,}</p>
                            <p><strong>B/N:</strong> {ultimo_registro.contador_bn_detectado or 0:,}</p>
                            <p><strong>Color:</strong> {ultimo_registro.contador_color_detectado or 0:,}</p>
                            <p><strong>Scan:</strong> {ultimo_registro.contador_scan_detectado or 0:,}</p>
                        </div>
                        <div class="col-md-6">
                            <h4>ℹ️ Información</h4>
                            <p><strong>Tipo:</strong> {ultimo_registro.tipo_equipo_detectado or 'No detectado'}</p>
                            <p><strong>Marca:</strong> {ultimo_registro.marca_detectada or 'No detectada'}</p>
                            <p><strong>Última actualización:</strong> {ultimo_registro.create_date.strftime('%d/%m/%Y %H:%M')}</p>
                        </div>
                    </div>
                    """
                    record.equipo_info = html
                else:
                    record.equipo_info = "<p>No se encontró información del equipo.</p>"
            else:
                record.equipo_info = ""

    def calcular_copias_periodo(self):
        """
        Calcula las copias realizadas en el período seleccionado
        """
        if not self.serie:
            return
        
        registros = self.historial_ids.sorted('create_date')
        if len(registros) < 2:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Se necesitan al menos 2 lecturas para calcular copias',
                    'type': 'warning'
                }
            }
        
        primer_registro = registros[0]
        ultimo_registro = registros[-1]
        
        copias_bn = max(0, (ultimo_registro.contador_bn_detectado or 0) - (primer_registro.contador_bn_detectado or 0))
        copias_color = max(0, (ultimo_registro.contador_color_detectado or 0) - (primer_registro.contador_color_detectado or 0))
        copias_total = copias_bn + copias_color
        
        dias = (self.fecha_fin - self.fecha_inicio).days + 1
        promedio_diario = copias_total / dias if dias > 0 else 0
        
        mensaje = f"""
        📊 Copias realizadas del {self.fecha_inicio.strftime('%d/%m/%Y')} al {self.fecha_fin.strftime('%d/%m/%Y')}:
        
        • B/N: {copias_bn:,} copias
        • Color: {copias_color:,} copias  
        • Total: {copias_total:,} copias
        • Promedio diario: {promedio_diario:.0f} copias
        • Período: {dias} días
        """
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': mensaje,
                'type': 'success',
                'sticky': True
            }
        }
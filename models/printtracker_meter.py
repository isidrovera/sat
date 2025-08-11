from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)


class PrintTrackerMeter(models.Model):
    _name = 'printtracker.meter'
    _description = 'Lecturas de Medidores PrintTracker'
    _order = 'reading_date desc'

    # Identificación
    pt_meter_id = fields.Char('ID PrintTracker', required=True, index=True)
    device_id = fields.Many2one('alquiler', string='Equipo',
                               required=True, index=True)
    
    # Fecha y estado
    reading_date = fields.Datetime('Fecha de Lectura', required=True, index=True)
    console_status = fields.Char('Estado Consola')
    
    # Contadores de páginas - Life (contadores reales de vida del equipo)
    total_pages_life = fields.Integer('Total Páginas (Life)')
    black_pages_life = fields.Integer('Páginas Negras (Life)')
    color_pages_life = fields.Integer('Páginas Color (Life)')
    
    # Contadores equivalentes (páginas equivalentes para facturación)
    total_pages_equiv = fields.Integer('Total Páginas (Equiv)')
    black_pages_equiv = fields.Integer('Páginas Negras (Equiv)')
    color_pages_equiv = fields.Integer('Páginas Color (Equiv)')
    
    # Contadores adicionales
    scan_pages = fields.Integer('Páginas Escaneadas')
    fax_pages = fields.Integer('Páginas de Fax')
    copy_pages = fields.Integer('Páginas Copiadas')
    
    # Control de sincronización
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    sync_source = fields.Selection([
        ('api', 'API PrintTracker'),
        ('manual', 'Manual'),
        ('import', 'Importación'),
        ('counter_automatic', 'Sistema Automático Contadores')
    ], string='Origen', default='api')
    
    # Campos calculados
    pages_increment = fields.Integer('Incremento Total', 
                                   compute='_compute_increments', store=True)
    black_increment = fields.Integer('Incremento Negro',
                                    compute='_compute_increments', store=True)
    color_increment = fields.Integer('Incremento Color',
                                    compute='_compute_increments', store=True)
    
    @api.depends('device_id', 'total_pages_life', 'black_pages_life', 'color_pages_life')
    def _compute_increments(self):
        """Calcula incrementos respecto a la lectura anterior"""
        for meter in self:
            if not meter.device_id:
                meter.pages_increment = 0
                meter.black_increment = 0
                meter.color_increment = 0
                continue
                
            # Buscar lectura anterior
            previous_meter = self.search([
                ('device_id', '=', meter.device_id.id),
                ('reading_date', '<', meter.reading_date)
            ], limit=1, order='reading_date desc')
            
            if previous_meter:
                meter.pages_increment = (meter.total_pages_life or 0) - (previous_meter.total_pages_life or 0)
                meter.black_increment = (meter.black_pages_life or 0) - (previous_meter.black_pages_life or 0)
                meter.color_increment = (meter.color_pages_life or 0) - (previous_meter.color_pages_life or 0)
            else:
                # Primera lectura
                meter.pages_increment = meter.total_pages_life or 0
                meter.black_increment = meter.black_pages_life or 0
                meter.color_increment = meter.color_pages_life or 0
    def debug_write_issue(self, meter_data, device):
        """
        NUEVO: Diagnóstico para identificar por qué write() resetea contadores
        """
        try:
            _logger.info(f"🔍 === DIAGNÓSTICO DETALLADO WRITE() ===")
            
            # 1. VERIFICAR ESTADO ACTUAL DEL EQUIPO
            _logger.info(f"📊 Estado ANTES de cualquier operación:")
            _logger.info(f"   ID: {device.id}")
            _logger.info(f"   Serie: {device.serie}")
            _logger.info(f"   contador_bn: {device.contador_bn}")
            _logger.info(f"   contador_color: {device.contador_color}")
            _logger.info(f"   contador_scan: {device.contador_scan}")
            
            # 2. PREPARAR VALORES EXACTOS
            page_counts = meter_data.get('pageCounts', {})
            life_counts = page_counts.get('life', {})
            
            valores_nuevos = {
                'contador_bn': life_counts.get('totalBlack', {}).get('value', 0),
                'contador_color': life_counts.get('totalColor', {}).get('value', 0),
                'contador_scan': 0,
                'fecha_ultima_actualizacion': fields.Datetime.now()
            }
            
            _logger.info(f"📊 Valores a escribir: {valores_nuevos}")
            
            # 3. VERIFICAR DEFINICIÓN DE CAMPOS
            _logger.info(f"🔍 === VERIFICANDO DEFINICIÓN DE CAMPOS ===")
            
            field_info = device.fields_get(['contador_bn', 'contador_color', 'contador_scan'])
            for field_name, field_data in field_info.items():
                _logger.info(f"📋 {field_name}:")
                _logger.info(f"   Tipo: {field_data.get('type')}")
                _logger.info(f"   Store: {field_data.get('store', True)}")
                _logger.info(f"   Readonly: {field_data.get('readonly', False)}")
                _logger.info(f"   Required: {field_data.get('required', False)}")
                
                # ❌ PROBLEMA COMÚN: Campos computados sin store
                if 'compute' in field_data and not field_data.get('store', True):
                    _logger.error(f"❌ PROBLEMA: {field_name} es computado sin store=True")
                    _logger.error(f"💡 SOLUCIÓN: Los campos computados sin store se recalculan y pierden valores")
            
            # 4. PROBAR WRITE MÍNIMO
            _logger.info(f"🧪 === PRUEBA 1: WRITE MÍNIMO ===")
            try:
                # Solo actualizar fecha para probar write básico
                device.write({'fecha_ultima_actualizacion': fields.Datetime.now()})
                _logger.info(f"✅ Write mínimo exitoso")
                
                # Verificar que los contadores NO se perdieron
                device.refresh()
                _logger.info(f"📊 Después de write mínimo:")
                _logger.info(f"   contador_bn: {device.contador_bn}")
                _logger.info(f"   contador_color: {device.contador_color}")
                _logger.info(f"   contador_scan: {device.contador_scan}")
                
                if device.contador_bn == 0 and device.contador_color == 0 and device.contador_scan == 0:
                    _logger.error(f"❌ PROBLEMA CONFIRMADO: Write mínimo resetea contadores")
                    _logger.error(f"💡 Probable causa: Campos computados o método write() personalizado")
                    return False
                else:
                    _logger.info(f"✅ Write mínimo preserva contadores")
                    
            except Exception as write_error:
                _logger.error(f"❌ Error en write mínimo: {write_error}")
                return False
            
            # 5. VERIFICAR MÉTODO WRITE PERSONALIZADO
            _logger.info(f"🔍 === VERIFICANDO MÉTODO WRITE PERSONALIZADO ===")
            
            alquiler_model = type(device)
            if hasattr(alquiler_model, 'write'):
                import inspect
                write_method = getattr(alquiler_model, 'write')
                
                # Verificar si el write está sobrescrito
                if write_method.__module__ != 'odoo.models':
                    _logger.warning(f"⚠️ ENCONTRADO: write() personalizado en {write_method.__module__}")
                    _logger.warning(f"🔍 Archivo: {inspect.getfile(write_method)}")
                    _logger.warning(f"💡 REVISAR: El write personalizado puede estar interfiriendo")
                else:
                    _logger.info(f"✅ write() usa el método estándar de Odoo")
            
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error en diagnóstico: {e}")
            return False
    
    def update_device_counters_safe(self):
        """
        NUEVO: Actualización segura con múltiples estrategias
        """
        try:
            _logger.info(f"💾 === ACTUALIZACIÓN SEGURA DE CONTADORES ===")
            
            if not self.device_id:
                _logger.error("❌ No hay device_id asociado")
                return False
            
            # Buscar equipo
            equipo = self.env['alquiler'].search([('serie', '=', self.device_id.serie)], limit=1)
            if not equipo:
                _logger.error(f"❌ No se encontró equipo con serie: {self.device_id.serie}")
                return False
            
            _logger.info(f"🎯 Equipo encontrado: {equipo.serie} (ID: {equipo.id})")
            
            # Preparar valores
            nuevos_valores = {
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'fecha_ultima_actualizacion': self.reading_date or fields.Datetime.now()
            }
            
            # ✅ ESTRATEGIA 1: Contexto que deshabilita recálculos
            try:
                _logger.info(f"📝 Intentando actualización con contexto seguro...")
                
                equipo_ctx = equipo.with_context(
                    # Desactivar recompute de campos computados
                    recompute=False,
                    # Sin validaciones de tracking si causan problemas
                    tracking_disable=True,
                    # Sin mail tracking
                    mail_notrack=True,
                    # Marcar como actualización automática
                    automatic_update=True
                )
                
                equipo_ctx.write(nuevos_valores)
                
                # Verificar resultado
                equipo.refresh()
                
                if (equipo.contador_bn == nuevos_valores['contador_bn'] and 
                    equipo.contador_color == nuevos_valores['contador_color']):
                    _logger.info(f"✅ Actualización exitosa con contexto seguro")
                    return True
                else:
                    _logger.warning(f"⚠️ Contexto seguro no preservó valores")
                    
            except Exception as ctx_error:
                _logger.warning(f"⚠️ Error con contexto seguro: {ctx_error}")
            
            # ✅ ESTRATEGIA 2: Actualización campo por campo
            try:
                _logger.info(f"📝 Intentando actualización campo por campo...")
                
                success_count = 0
                
                # BN
                if nuevos_valores['contador_bn'] > 0:
                    equipo.write({'contador_bn': nuevos_valores['contador_bn']})
                    equipo.refresh()
                    if equipo.contador_bn == nuevos_valores['contador_bn']:
                        success_count += 1
                        _logger.info(f"✅ contador_bn actualizado: {equipo.contador_bn}")
                    else:
                        _logger.error(f"❌ contador_bn falló")
                
                # Color
                if nuevos_valores['contador_color'] >= 0:
                    equipo.write({'contador_color': nuevos_valores['contador_color']})
                    equipo.refresh()
                    if equipo.contador_color == nuevos_valores['contador_color']:
                        success_count += 1
                        _logger.info(f"✅ contador_color actualizado: {equipo.contador_color}")
                    else:
                        _logger.error(f"❌ contador_color falló")
                
                # Fecha
                equipo.write({'fecha_ultima_actualizacion': nuevos_valores['fecha_ultima_actualizacion']})
                success_count += 1
                
                if success_count >= 2:
                    _logger.info(f"✅ Actualización campo por campo exitosa ({success_count}/3)")
                    return True
                    
            except Exception as field_error:
                _logger.error(f"❌ Error en actualización campo por campo: {field_error}")
            
            # Si llegamos aquí, hay un problema serio
            _logger.error(f"❌ === TODAS LAS ESTRATEGIAS DE ACTUALIZACIÓN FALLARON ===")
            _logger.error(f"💡 RECOMENDACIÓN: Revisar modelo 'alquiler' por:")
            _logger.error(f"   1. Método write() personalizado problemático")
            _logger.error(f"   2. Campos computados que se recalculan")
            _logger.error(f"   3. Constrains que validan valores")
            _logger.error(f"   4. Triggers que modifican datos")
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error en actualización segura: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False
   
    def update_device_counters(self):
        """
        MÉTODO DEFINITIVO: Actualiza contadores con manejo específico de tracking
        CORRECCIÓN: Desactiva tracking temporalmente para evitar conflictos
        """
        try:
            _logger.info(f"💾 === INICIANDO ACTUALIZACIÓN PRINTTRACKER DEFINITIVA ===")
            
            if not self.device_id:
                _logger.error("❌ No hay device_id asociado al medidor")
                return False
            
            # Buscar equipo por serie
            serie_equipo = self.device_id.serie
            if not serie_equipo:
                _logger.error("❌ El dispositivo no tiene serie definida")
                return False
            
            equipo = self.env['alquiler'].search([('serie', '=', serie_equipo)], limit=1)
            if not equipo:
                _logger.error(f"❌ No se encontró equipo con serie: {serie_equipo}")
                return False
            
            _logger.info(f"🎯 Equipo encontrado: ID={equipo.id}, Serie={serie_equipo}")
            
            # Preparar nuevos valores
            nuevos_valores = {
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'contador_scan': self.scan_pages or 0,
                'fecha_ultima_actualizacion': self.reading_date or fields.Datetime.now()
            }
            
            _logger.info(f"📊 Valores a actualizar: {nuevos_valores}")
            
            # ✅ ESTRATEGIA DEFINITIVA: Write con tracking desactivado
            try:
                _logger.info(f"📝 Estrategia 1: Write con tracking desactivado...")
                
                # Contexto que desactiva COMPLETAMENTE el tracking y mail
                equipo_no_track = equipo.sudo().with_context(
                    tracking_disable=True,       # Sin tracking
                    mail_notrack=True,          # Sin mail
                    mail_create_nosubscribe=True, # Sin suscripciones
                    mail_create_nolog=True,     # Sin log en chatter
                    no_reset_password=True,     # Sin reset password
                    import_file=True,           # Simular importación
                    install_mode=True,          # Modo instalación
                    active_test=False           # Sin test activo
                )
                
                # Ejecutar write
                equipo_no_track.write(nuevos_valores)
                _logger.info(f"✅ Write sin tracking ejecutado")
                
                # ✅ VERIFICACIÓN INMEDIATA con búsqueda fresca
                equipo_fresh = self.env['alquiler'].browse(equipo.id)
                equipo_fresh.invalidate_cache()
                
                _logger.info(f"📊 Verificación inmediata:")
                _logger.info(f"   BN: {equipo_fresh.contador_bn}")
                _logger.info(f"   Color: {equipo_fresh.contador_color}")
                _logger.info(f"   Scan: {equipo_fresh.contador_scan}")
                
                # Verificar si funcionó
                if (equipo_fresh.contador_bn == nuevos_valores['contador_bn'] and 
                    equipo_fresh.contador_color == nuevos_valores['contador_color']):
                    _logger.info(f"🎉 ÉXITO: Valores actualizados correctamente")
                    return True
                else:
                    _logger.error(f"❌ Falló estrategia 1, probando estrategia 2...")
                    
            except Exception as strategy1_error:
                _logger.error(f"❌ Error en estrategia 1: {strategy1_error}")
            
            # ✅ ESTRATEGIA 2: Update field por field con commit
            try:
                _logger.info(f"📝 Estrategia 2: Actualización campo por campo con commit...")
                
                success_fields = []
                
                # BN
                if nuevos_valores['contador_bn'] > 0:
                    equipo.sudo().write({'contador_bn': nuevos_valores['contador_bn']})
                    self.env.cr.commit()  # Commit inmediato
                    
                    equipo.invalidate_cache()
                    if equipo.contador_bn == nuevos_valores['contador_bn']:
                        success_fields.append('contador_bn')
                        _logger.info(f"✅ contador_bn actualizado: {equipo.contador_bn}")
                
                # Color
                if nuevos_valores['contador_color'] >= 0:
                    equipo.sudo().write({'contador_color': nuevos_valores['contador_color']})
                    self.env.cr.commit()  # Commit inmediato
                    
                    equipo.invalidate_cache()
                    if equipo.contador_color == nuevos_valores['contador_color']:
                        success_fields.append('contador_color')
                        _logger.info(f"✅ contador_color actualizado: {equipo.contador_color}")
                
                # Scan
                if nuevos_valores['contador_scan'] >= 0:
                    equipo.sudo().write({'contador_scan': nuevos_valores['contador_scan']})
                    self.env.cr.commit()  # Commit inmediato
                    
                    equipo.invalidate_cache()
                    if equipo.contador_scan == nuevos_valores['contador_scan']:
                        success_fields.append('contador_scan')
                        _logger.info(f"✅ contador_scan actualizado: {equipo.contador_scan}")
                
                # Fecha
                equipo.sudo().write({'fecha_ultima_actualizacion': nuevos_valores['fecha_ultima_actualizacion']})
                self.env.cr.commit()
                success_fields.append('fecha_ultima_actualizacion')
                
                if len(success_fields) >= 3:  # Al menos 3 campos actualizados
                    _logger.info(f"🎉 ÉXITO: Estrategia 2 funcionó - {len(success_fields)} campos")
                    return True
                else:
                    _logger.error(f"❌ Estrategia 2 parcial: solo {len(success_fields)} campos")
                    
            except Exception as strategy2_error:
                _logger.error(f"❌ Error en estrategia 2: {strategy2_error}")
            
            # ✅ ESTRATEGIA 3: SQL directo como último recurso (SOLO LOGGING)
            _logger.error(f"❌ TODAS LAS ESTRATEGIAS ORM FALLARON")
            _logger.error(f"💡 DIAGNÓSTICO NECESARIO:")
            _logger.error(f"   1. Verificar permisos del usuario")
            _logger.error(f"   2. Revisar si hay triggers en la base de datos")
            _logger.error(f"   3. Verificar constrains del modelo")
            _logger.error(f"   4. Revisar módulos que hereden de 'alquiler'")
            
            # Log de información técnica para diagnóstico
            _logger.error(f"📋 Info técnica del equipo:")
            _logger.error(f"   ID: {equipo.id}")
            _logger.error(f"   Modelo: {equipo._name}")
            _logger.error(f"   Usuario: {self.env.user.login}")
            _logger.error(f"   Compañía: {self.env.company.name}")
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error general en actualización: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    @api.model
    def get_latest_for_device(self, device_id):
        """Obtiene la lectura más reciente para un equipo"""
        return self.search([
            ('device_id', '=', device_id)
        ], limit=1, order='reading_date desc')
    
    def get_reading_summary(self):
        """Retorna resumen de la lectura en formato dict"""
        return {
            'device_serial': self.device_id.serie if self.device_id else 'N/A',
            'reading_date': self.reading_date,
            'total_pages': self.total_pages_life,
            'black_pages': self.black_pages_life,
            'color_pages': self.color_pages_life,
            'scan_pages': self.scan_pages,
            'increments': {
                'total': self.pages_increment,
                'black': self.black_increment,
                'color': self.color_increment
            }
        }


from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class Reparaciones(models.Model):
    _inherit = 'reparaciones.reparaciones'
    migration_status = fields.Selection([
        ('pending', 'Pendiente de migración'),
        ('migrated', 'Migrado'),
        ('error', 'Error en migración'),
    ], string='Estado de Migración', default='pending', index=True, 
       help="Estado actual de migración del checklist a evaluaciones")

    migration_date = fields.Datetime(
        string='Fecha de Migración', 
        readonly=True,
        help="Fecha y hora en que se ejecutó la migración"
    )

    migration_count = fields.Integer(
        string='Evaluaciones Migradas', 
        readonly=True, 
        default=0,
        help="Cantidad de evaluaciones creadas durante la migración"
    )
    evaluacion_ids = fields.One2many(
        'reparacion.componente.evaluacion', 
        'reparacion_id', 
        string='Evaluaciones de Componentes',
        help="Evaluaciones individuales de cada componente de la máquina"
    )
    
    accesorio_eval_ids = fields.One2many(
        'reparacion.accesorio.evaluacion',
        'reparacion_id',
        string='Evaluaciones de Accesorios',
        help="Evaluaciones de accesorios instalados en la máquina"
    )
    def action_migrar_checklist_a_evaluaciones(self):
        """Migra los campos selection clásicos a evaluaciones M2O (componentes Y accesorios)."""
        
        # FILTRAR: Solo migrar registros pendientes o con error
        records_to_migrate = self.filtered(lambda r: r.migration_status in ('pending', 'error'))
        
        if not records_to_migrate:
            raise UserError("No hay registros pendientes de migración.")
        
        _logger.info(f"Iniciando migración de {len(records_to_migrate)} registros")
        
        # ===== MODELOS PARA COMPONENTES =====
        Tipo = self.env['componente.tipo']
        Estado = self.env['componente.estado']
        Color = self.env['color.tipo']
        Eval = self.env['reparacion.componente.evaluacion']

        # ===== MODELOS PARA ACCESORIOS =====
        AccesorioTipo = self.env['accesorio.tipo']
        AccesorioEstado = self.env['accesorio.estado']
        AccesorioEval = self.env['reparacion.accesorio.evaluacion']

        # ========================================
        # MAPEO COMPLETO DE COMPONENTES
        # ========================================
        FIELD_TO_TIPO = {
            # === FUNCIONES ===
            'copia_id':         ('FUNCION_COPIA',     None, 'Función de Copia'),
            'impresion_id':     ('FUNCION_IMPRESION', None, 'Función de Impresión'),
            'impresion_usb_id': ('FUNCION_USB_PRINT', None, 'Función Impresión USB'),
            'scaner_smb_id':    ('FUNCION_SCAN_SMB',  None, 'Función Escaneo SMB'),
            'scaner_usb_id':    ('FUNCION_SCAN_USB',  None, 'Función Escaneo USB'),
            'scaner_ftp_id':    ('FUNCION_SCAN_FTP',  None, 'Función Escaneo FTP'),
            'scaner_mail_id':   ('FUNCION_SCAN_MAIL', None, 'Función Escaneo Email'),
            
            # === COMPONENTES MECÁNICOS ===
            'bypass_id':     ('BYPASS',      None, 'Bandeja Bypass'),
            'tray1_id':      ('TRAY',        None, 'Bandeja 1'),
            'tray2_id':      ('TRAY',        None, 'Bandeja 2'),
            'tray3_id':      ('TRAY',        None, 'Bandeja 3'),
            'tray4_id':      ('TRAY',        None, 'Bandeja 4'),
            'adf_id':        ('ADF',         None, 'ADF'),
            'finalizador_id':('FINISHER',    None, 'Finalizador'),
            'tacho_id':      ('WASTE_TONER', None, 'Contenedor de Residuos'),
            
            # === COMPONENTES DE IMPRESIÓN ===
            'fusora_id':     ('FUSORA',         None, 'Unidad Fusora'),
            'rodillo_id':    ('TRANSFER_ROLLER', None, 'Rodillo de Transferencia'),
            'calor_id':      ('FUSORA',         None, 'Sensores de Calor (Fusora)'),
            'transfer_id':   ('FAJA',           None, 'Banda de Transferencia'),
            'optico_id':     ('OPTICO',         None, 'Componentes Ópticos'),
            
            # === CONSUMIBLES - TÓNERS ===
            'toner_black_id':   ('TONER_SYSTEM', 'k', 'Tóner Negro'),
            'toner_magenta_id': ('TONER_SYSTEM', 'm', 'Tóner Magenta'),
            'toner_cyan_id':    ('TONER_SYSTEM', 'c', 'Tóner Cyan'),
            'toner_yellow_id':  ('TONER_SYSTEM', 'y', 'Tóner Amarillo'),
            
            # === CONSUMIBLES - UNIDADES DE IMAGEN ===
            'black_id':      ('UI',          'k', 'Unidad de Imagen Negro'),
            'magenta_id':    ('UI',          'm', 'Unidad de Imagen Magenta'),
            'cyan_id':       ('UI',          'c', 'Unidad de Imagen Cyan'),
            'yellow_id':     ('UI',          'y', 'Unidad de Imagen Amarillo'),
            
            # === CONSUMIBLES - DEVELOPERS ===
            'developerk_id': ('DEVELOPER',   'k', 'Revelador Negro'),
            'developerm_id': ('DEVELOPER',   'm', 'Revelador Magenta'),
            'developerc_id': ('DEVELOPER',   'c', 'Revelador Cyan'),
            'developery_id': ('DEVELOPER',   'y', 'Revelador Amarillo'),
        }

        # ========================================
        # MAPEO DE VALORES A ESTADOS (COMPONENTES)
        # ========================================
        VAL_TO_ESTADO = {
            # === ESTADOS GENERALES DE COMPONENTES ===
            'requiere_cambio': 'requiere_cambio',
            'cambio_de_repuestos': 'cambio_de_repuestos',
            'regular': 'regular',
            'gastada_pero_puede_trabajar': 'gastada_pero_puede_trabajar',
            'mantenimiento': 'mantenimiento',
            'sin_revisar': 'sin_revisar',
            'revisado': 'revisado',
            'nuevo': 'nuevo',
            'no_aplica': 'no_aplica',
            
            # === ESTADOS DE FUNCIONES ===
            'correcto': 'correcto',
            'sin_probar': 'sin_probar',
            'falla': 'falla',
            
            # === ESTADOS ESPECÍFICOS DE TÓNERS ===
            'vacio': 'vacio',
            'bajo': 'bajo',
            'sin_botella': 'sin_botella',
            
            # === NORMALIZACIÓN PARA CAMPOS SÍ/NO ===
            'si': 'revisado',
            'no': 'sin_revisar',
        }

        # ========================================
        # MAPEO DE ACCESORIOS
        # ========================================
        FIELD_TO_ACCESORIO = {
            'lct_id': 'lct',
            'ot_id': 'ot',
            'hdd_id': 'hdd',
            'adf_simple_id': 'adf_simple',  
            'adf_dual_id': 'adf_dual',     
            'finalizador_interno_id': 'finisher_int',
            'finalizador_externo_id': 'finisher_ext',
            'mueble_id': 'mueble',
            'panel_smart_id': 'panel_smart',
            'panel_normal_id': 'panel_normal',
            'wi_fi_id': 'wifi',
            'cable_poder_id': 'cable_poder',
        }

        # ========================================
        # MAPEO DE VALORES A ESTADOS (ACCESORIOS)
        # ========================================
        VAL_TO_ACCESORIO_ESTADO = {
            'si': 'instalado_operativo',
            'no': 'no_instalado',
            'no_aplica': 'no_aplica',
        }

        migrated_count = 0
        error_count = 0

        for rec in records_to_migrate:
            try:
                _logger.info(f"Migrando reparación ID: {rec.id}")
                
                # ========================================
                # PARTE 1: MIGRAR COMPONENTES
                # ========================================
                componentes_vals = []
                
                for field_name, (tipo_code, color_code, obs) in FIELD_TO_TIPO.items():
                    if field_name not in rec._fields:
                        continue
                    value = getattr(rec, field_name, False)
                    if not value:
                        continue

                    estado_code = VAL_TO_ESTADO.get(value)
                    if not estado_code:
                        _logger.warning(f"Estado no reconocido '{value}' para campo {field_name}")
                        continue

                    tipo = Tipo.search([('code', '=', tipo_code)], limit=1)
                    if not tipo:
                        _logger.warning(f"Tipo no encontrado: {tipo_code}")
                        continue
                    
                    estado = Estado.search([('code', '=', estado_code)], limit=1)
                    if not estado:
                        _logger.warning(f"Estado no encontrado: {estado_code}")
                        continue

                    color_id = False
                    if color_code:
                        color = Color.search([('code', '=', color_code)], limit=1)
                        color_id = color.id if color else False

                    # Evitar duplicados exactos (mismo tipo/color)
                    dup_domain = [
                        ('reparacion_id', '=', rec.id),
                        ('componente_tipo_id', '=', tipo.id),
                    ]
                    if color_id:
                        dup_domain.append(('color_id', '=', color_id))
                    
                    exists = Eval.search(dup_domain, limit=1)
                    if exists:
                        exists.estado_id = estado.id
                        if obs and not exists.observaciones:
                            exists.observaciones = obs
                        continue

                    componentes_vals.append({
                        'reparacion_id': rec.id,
                        'componente_tipo_id': tipo.id,
                        'estado_id': estado.id,
                        'color_id': color_id,
                        'observaciones': obs or False,
                    })

                # CREAR EVALUACIONES DE COMPONENTES
                componentes_creados = 0
                if componentes_vals:
                    created_evals = Eval.create(componentes_vals)
                    componentes_creados = len(created_evals)
                    _logger.info(f"Creadas {componentes_creados} evaluaciones de componentes para reparación {rec.id}")

                # ========================================
                # PARTE 2: MIGRAR ACCESORIOS
                # ========================================
                accesorios_vals = []
                
                for field_name, tipo_code in FIELD_TO_ACCESORIO.items():
                    if field_name not in rec._fields:
                        continue
                    value = getattr(rec, field_name, False)
                    if not value:
                        continue
                    
                    estado_code = VAL_TO_ACCESORIO_ESTADO.get(value)
                    if not estado_code:
                        _logger.warning(f"Estado de accesorio no reconocido '{value}' para campo {field_name}")
                        continue
                    
                    tipo = AccesorioTipo.search([('code', '=', tipo_code)], limit=1)
                    if not tipo:
                        _logger.warning(f"Tipo de accesorio no encontrado: {tipo_code}")
                        continue
                    
                    estado = AccesorioEstado.search([('code', '=', estado_code)], limit=1)
                    if not estado:
                        _logger.warning(f"Estado de accesorio no encontrado: {estado_code}")
                        continue
                    
                    # Evitar duplicados
                    exists = AccesorioEval.search([
                        ('reparacion_id', '=', rec.id),
                        ('tipo_id', '=', tipo.id)
                    ], limit=1)
                    
                    if exists:
                        exists.estado_id = estado.id
                        continue
                    
                    accesorios_vals.append({
                        'reparacion_id': rec.id,
                        'tipo_id': tipo.id,
                        'estado_id': estado.id,
                    })

                # CREAR EVALUACIONES DE ACCESORIOS
                accesorios_creados = 0
                if accesorios_vals:
                    created_accs = AccesorioEval.create(accesorios_vals)
                    accesorios_creados = len(created_accs)
                    _logger.info(f"Creadas {accesorios_creados} evaluaciones de accesorios para reparación {rec.id}")

                # ========================================
                # MARCAR COMO MIGRADO
                # ========================================
                total_evaluaciones = componentes_creados + accesorios_creados
                
                rec.write({
                    'migration_status': 'migrated',
                    'migration_date': fields.Datetime.now(),
                    'migration_count': total_evaluaciones
                })
                
                migrated_count += 1
                
            except Exception as e:
                _logger.error(f"Error migrando reparación {rec.id}: {e}")
                # MARCAR COMO ERROR
                rec.write({
                    'migration_status': 'error',
                    'migration_date': fields.Datetime.now(),
                })
                error_count += 1

        # ========================================
        # RESULTADO FINAL
        # ========================================
        message = f"Migración completada:\n"
        message += f"• Migrados exitosamente: {migrated_count}\n"
        message += f"• Errores: {error_count}\n"
        message += f"• Total procesados: {migrated_count + error_count}"
        
        _logger.info(message)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migración Completada',
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': False,
            }
        }

    def action_reset_migration_status(self):
        """Resetea el estado de migración para poder volver a migrar."""
        self.write({
            'migration_status': 'pending',
            'migration_date': False,
            'migration_count': 0
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Estado Reseteado',
                'message': f'Se reseteó el estado de migración de {len(self)} registros',
                'type': 'success',
            }
        }
        
    def action_reset_all_migration_finalizados(self):
        """Resetea el estado de migración de TODOS los registros finalizados del sistema."""
        
        registros_finalizados = self.search([('estado_id', '=', 'finalizado')])
        
        if not registros_finalizados:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin registros',
                    'message': 'No hay registros finalizados en el sistema',
                    'type': 'warning',
                }
            }
        
        registros_finalizados.write({
            'migration_status': 'pending',
            'migration_date': False,
            'migration_count': 0
        })
        
        _logger.info(f"Reseteados TODOS los {len(registros_finalizados)} registros finalizados del sistema")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migración Reseteada',
                'message': f'Se resetearon {len(registros_finalizados)} registros finalizados en todo el sistema',
                'type': 'success',
                'sticky': True,
            }
        }
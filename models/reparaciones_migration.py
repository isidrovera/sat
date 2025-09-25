from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class Reparaciones(models.Model):
    _inherit = 'reparaciones.reparaciones'

    # CAMPO DE CONTROL DE MIGRACIÓN
    migration_status = fields.Selection([
        ('pending', 'Pendiente de migración'),
        ('migrated', 'Migrado'),
        ('error', 'Error en migración'),
    ], string='Estado de Migración', default='pending', index=True)
    
    migration_date = fields.Datetime(string='Fecha de Migración', readonly=True)
    migration_count = fields.Integer(string='Evaluaciones Migradas', readonly=True, default=0)

    evaluacion_ids = fields.One2many(
        'reparacion.componente.evaluacion', 'reparacion_id', string='Evaluaciones'
    )

    def action_migrar_checklist_a_evaluaciones(self):
        """Migra los campos selection clásicos a evaluaciones M2O."""
        # FILTRAR: Solo migrar registros pendientes o con error
        records_to_migrate = self.filtered(lambda r: r.migration_status in ('pending', 'error'))
        
        if not records_to_migrate:
            raise UserError("No hay registros pendientes de migración.")
        
        _logger.info(f"Iniciando migración de {len(records_to_migrate)} registros")
        
        Tipo = self.env['componente.tipo']
        Estado = self.env['componente.estado']
        Color = self.env['color.tipo']
        Eval = self.env['reparacion.componente.evaluacion']

        # MAPEO COMPLETO: campo -> (code tipo componente, code color opcional, observación opcional)
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

        # MAPEO COMPLETO: valor selection -> code estado
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

        migrated_count = 0
        error_count = 0

        for rec in records_to_migrate:
            try:
                _logger.info(f"Migrando reparación ID: {rec.id}")
                
                create_vals = []
                evaluaciones_creadas = 0
                
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

                    # evita duplicados exactos (mismo tipo/color)
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

                    create_vals.append({
                        'reparacion_id': rec.id,
                        'componente_tipo_id': tipo.id,
                        'estado_id': estado.id,
                        'color_id': color_id,
                        'observaciones': obs or False,
                    })

                # CREAR EVALUACIONES
                if create_vals:
                    created_evals = Eval.create(create_vals)
                    evaluaciones_creadas = len(created_evals)
                    _logger.info(f"Creadas {evaluaciones_creadas} evaluaciones para reparación {rec.id}")

                # MARCAR COMO MIGRADO
                rec.write({
                    'migration_status': 'migrated',
                    'migration_date': fields.Datetime.now(),
                    'migration_count': evaluaciones_creadas
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
                # NO hacer raise para que continúe con los otros registros

        # RESULTADO FINAL
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

    def action_seed_evaluaciones_desde_modelo(self):
        """Crea evaluaciones basadas en los componentes del modelo de la máquina."""
        Eval = self.env['reparacion.componente.evaluacion']
        for rec in self:
            modelo = rec.maquina_id
            if not modelo:
                continue
            comp_lines = self.env['modelo.maquina.componente'].search([('modelo_id', '=', modelo.id)])
            to_create = []
            for line in comp_lines:
                dup_domain = [
                    ('reparacion_id', '=', rec.id),
                    ('componente_tipo_id', '=', line.tipo_id.id),
                ]
                if line.color_id:
                    dup_domain.append(('color_id', '=', line.color_id.id))
                exists = Eval.search(dup_domain, limit=1)
                if exists:
                    if line.estado_sugerido_id and not exists.estado_id:
                        exists.estado_id = line.estado_sugerido_id.id
                    continue

                to_create.append({
                    'reparacion_id': rec.id,
                    'componente_tipo_id': line.tipo_id.id,
                    'color_id': line.color_id.id if line.color_id else False,
                    'estado_id': line.estado_sugerido_id.id if line.estado_sugerido_id else False,
                    'observaciones': line.frase_desgaste or False,
                })
            if to_create:
                Eval.create(to_create)
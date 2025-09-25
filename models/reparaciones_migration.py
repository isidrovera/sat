from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class Reparaciones(models.Model):
    _inherit = 'reparaciones.reparaciones'

    evaluacion_ids = fields.One2many(
        'reparacion.componente.evaluacion', 'reparacion_id', string='Evaluaciones'
    )

    def action_migrar_checklist_a_evaluaciones(self):
        """Migra los campos selection clásicos a evaluaciones M2O."""
        Tipo = self.env['componente.tipo']
        Estado = self.env['componente.estado']
        Color = self.env['color.tipo']
        Eval = self.env['reparacion.componente.evaluacion']

        # mapa: campo -> (code tipo componente, code color opcional, observación opcional)
        FIELD_TO_TIPO = {
            # IU (unidad de imagen)
            'black_id':      ('UI',          'k', 'Unidad de imagen K'),
            'cyan_id':       ('UI',          'c', 'Unidad de imagen C'),
            'magenta_id':    ('UI',          'm', 'Unidad de imagen M'),
            'yellow_id':     ('UI',          'y', 'Unidad de imagen Y'),
            # Developer
            'developerk_id': ('DEVELOPER',   'k', 'Developer K'),
            'developerc_id': ('DEVELOPER',   'c', 'Developer C'),
            'developerm_id': ('DEVELOPER',   'm', 'Developer M'),
            'developery_id': ('DEVELOPER',   'y', 'Developer Y'),
            # Módulos y transporte
            'transfer_id':   ('FAJA',        None, 'Faja/Banda de transferencia (ITB)'),
            'fusora_id':     ('FUSORA',      None, 'Fusora'),
            'rodillo_id':    ('FUSORA',      None, 'Rodillo de presión (Fusora)'),
            'calor_id':      ('FUSORA',      None, 'Rodillo de calor (Fusora)'),
            'adf_id':        ('ADF',         None, 'ADF'),
            'finalizador_id':('FINISHER',    None, 'Finalizador'),
            'optico_id':     ('OPTICO',      None, 'Óptico'),
            'bypass_id':     ('BYPASS',      None, 'Bypass'),
            'tray1_id':      ('TRAY',        None, 'Bandeja 1'),
            'tray2_id':      ('TRAY',        None, 'Bandeja 2'),
            'tray3_id':      ('TRAY',        None, 'Bandeja 3'),
            'tray4_id':      ('TRAY',        None, 'Bandeja 4'),
            'tacho_id':      ('WASTE_TONER', None, 'Depósito de residuos'),
        }

        # mapa: valor selection -> code estado (usará componente.estado.code)
        VAL_TO_ESTADO = {
            'requiere_cambio': 'requiere_cambio',
            'cambio_de_repuestos': 'cambio_de_repuestos',
            'regular': 'regular',
            'gastada_pero_puede_trabajar': 'gastada_pero_puede_trabajar',
            'mantenimiento': 'mantenimiento',
            'sin_revisar': 'sin_revisar',
            'revisado': 'revisado',
            'nuevo': 'nuevo',
            'no_aplica': 'no_aplica',
            # Normalización para campos sí/no
            'si': 'revisado',
            'no': 'sin_revisar',
        }

        for rec in self:
            _logger.info(f"Migrando reparación ID: {rec.id}")
            
            # opcional: no duplicar si ya hay evaluaciones (quita si prefieres re-migrar)
            # if rec.evaluacion_ids:
            #     continue

            create_vals = []
            for field_name, (tipo_code, color_code, obs) in FIELD_TO_TIPO.items():
                if field_name not in rec._fields:
                    continue
                value = getattr(rec, field_name, False)
                if not value:
                    continue

                estado_code = VAL_TO_ESTADO.get(value)
                if not estado_code:
                    continue  # valor que no mapeamos

                tipo = Tipo.search([('code', '=', tipo_code)], limit=1)
                if not tipo:
                    _logger.warning(f"No se encontró tipo de componente con code: {tipo_code}")
                    continue
                estado = Estado.search([('code', '=', estado_code)], limit=1)
                if not estado:
                    _logger.warning(f"No se encontró estado de componente con code: {estado_code}")
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
                    # si ya existe, opcionalmente actualiza estado si el nuevo es más crítico
                    exists.estado_id = estado.id
                    if obs and not exists.observaciones:
                        exists.observaciones = obs
                    continue

                val = {
                    'reparacion_id': rec.id,
                    'componente_tipo_id': tipo.id,
                    'estado_id': estado.id,
                    'color_id': color_id,
                    'observaciones': obs or False,
                }
                _logger.info(f"Preparando crear evaluación: {val}")
                create_vals.append(val)

            if create_vals:
                try:
                    created_evals = Eval.create(create_vals)
                    _logger.info(f"Creadas {len(created_evals)} evaluaciones para reparación {rec.id}")
                except Exception as e:
                    _logger.error(f"Error creando evaluaciones para reparación {rec.id}: {e}")
                    raise

    def action_seed_evaluaciones_desde_modelo(self):
        """Crea evaluaciones basadas en los componentes del modelo de la máquina."""
        Eval = self.env['reparacion.componente.evaluacion']
        for rec in self:
            # CORREGIDO: usar el objeto completo, no solo .name
            modelo = rec.maquina_id  # Este debe ser el objeto completo
            if not modelo:
                _logger.warning(f"Reparación {rec.id} no tiene máquina asignada")
                continue
                
            _logger.info(f"Procesando modelo: {modelo.name} para reparación {rec.id}")
            
            # componentes del modelo
            comp_lines = self.env['modelo.maquina.componente'].search([('modelo_id', '=', modelo.id)])
            _logger.info(f"Encontrados {len(comp_lines)} componentes para el modelo {modelo.name}")
            
            to_create = []
            for line in comp_lines:
                # evita duplicados (mismo tipo y color)
                dup_domain = [
                    ('reparacion_id', '=', rec.id),
                    ('componente_tipo_id', '=', line.tipo_id.id),
                ]
                if line.color_id:
                    dup_domain.append(('color_id', '=', line.color_id.id))
                    
                exists = Eval.search(dup_domain, limit=1)
                if exists:
                    # si no tiene estado, pon el sugerido
                    if line.estado_sugerido_id and not exists.estado_id:
                        exists.estado_id = line.estado_sugerido_id.id
                    continue

                val = {
                    'reparacion_id': rec.id,
                    'componente_tipo_id': line.tipo_id.id,
                    'color_id': line.color_id.id if line.color_id else False,
                    'estado_id': line.estado_sugerido_id.id if line.estado_sugerido_id else False,
                    'observaciones': line.frase_desgaste or False,
                }
                _logger.info(f"Preparando crear evaluación desde modelo: {val}")
                to_create.append(val)
                
            if to_create:
                try:
                    created_evals = Eval.create(to_create)
                    _logger.info(f"Creadas {len(created_evals)} evaluaciones desde modelo para reparación {rec.id}")
                except Exception as e:
                    _logger.error(f"Error creando evaluaciones desde modelo para reparación {rec.id}: {e}")
                    raise
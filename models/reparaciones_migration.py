from odoo import models, fields, api_
from odoo.exceptions import UserError

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
                    continue
                estado = Estado.search([('code', '=', estado_code)], limit=1)
                if not estado:
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

                create_vals.append({
                    'reparacion_id': rec.id,
                    'componente_tipo_id': tipo.id,
                    'estado_id': estado.id,
                    'color_id': color_id,
                    'observaciones': obs or False,
                })

            if create_vals:
                Eval.create(create_vals)
class Reparaciones(models.Model):
    _inherit = 'reparaciones.reparaciones'

    def action_seed_evaluaciones_desde_modelo(self):
        Eval = self.env['reparacion.componente.evaluacion']
        for rec in self:
            modelo = rec.maquina_id and rec.maquina_id.name  # tu campo: Many2one a modelo.maquina en sat.sat.name
            if not modelo:
                continue
            # componentes del modelo
            comp_lines = self.env['modelo.maquina.componente'].search([('modelo_id', '=', modelo.id)])
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

                to_create.append({
                    'reparacion_id': rec.id,
                    'componente_tipo_id': line.tipo_id.id,
                    'color_id': line.color_id.id if line.color_id else False,
                    'estado_id': line.estado_sugerido_id.id if line.estado_sugerido_id else False,
                    'observaciones': line.frase_desgaste or False,
                })
            if to_create:
                Eval.create(to_create)

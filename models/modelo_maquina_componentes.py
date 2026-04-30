# models/modelo_maquina_componentes.py
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ModeloMaquinaComponente(models.Model):
    _name = 'modelo.maquina.componente'
    _description = 'Plantilla de componentes por modelo de máquina'
    _order = 'prioridad, tipo_id, color'
    _rec_name = 'display_name'

    # Relaciones principales
    modelo_id = fields.Many2one(
        'modelo.maquina',
        required=True,
        ondelete='cascade',
        index=True,
        string='Modelo'
    )

    tipo_id = fields.Many2one(
        'componente.tipo',
        required=True,
        ondelete='restrict',
        index=True,
        string='Tipo de componente'
    )

    # Atributos
    color = fields.Selection(
        [('k', 'K'), ('c', 'C'), ('m', 'M'), ('y', 'Y')],
        string='Color'
    )
    estado_sugerido_id = fields.Many2one(
        'componente.estado',
        string='Estado sugerido',
        ondelete='restrict'
    )

    # vida útil / prioridad / frases
    vida_util_paginas = fields.Integer(string='Vida útil (pág.)')
    vida_util_meses = fields.Integer(string='Vida útil (meses)')
    prioridad = fields.Selection(
        [('1', 'Crítico'), ('2', 'Medio'), ('3', 'Bajo')],
        default='1',
        string='Prioridad',
        required=True,
        index=True
    )
    frase_desgaste = fields.Char(string='Frase de desgaste (opcional)')
    frase_cambio = fields.Char(string='Frase de cambio (opcional)')

    # Subpartes sugeridas (líneas hijas)
    detalle_ids = fields.One2many(
        'modelo.maquina.componente.subparte',
        'componente_id',
        string='Subpartes sugeridas'
    )

    # utilidades UI
    display_name = fields.Char(
        compute='_compute_display_name',
        store=False
    )

    # --------- Computados / Onchange / Reglas ---------
    @api.depends('tipo_id', 'color')
    def _compute_display_name(self):
        _logger.debug(
            "[mmc._compute_display_name] recalculando para %s registro(s)",
            len(self)
        )
        for rec in self:
            name = rec.tipo_id.name if rec.tipo_id else ''
            if rec.tipo_id and getattr(rec.tipo_id, 'is_color_sensitive', False) and rec.color:
                name = f"{name} ({rec.color.upper()})"
            rec.display_name = name or '—'

    @api.onchange('tipo_id')
    def _onchange_tipo_color(self):
        for rec in self:
            sensitive = bool(rec.tipo_id and getattr(rec.tipo_id, 'is_color_sensitive', False))
            _logger.info(
                "[mmc._onchange_tipo_color] id=%s tipo=%s sensible_color=%s color_actual=%s",
                rec.id, rec.tipo_id.name if rec.tipo_id else None,
                sensitive, rec.color
            )
            if rec.tipo_id and not sensitive:
                rec.color = False
                _logger.info("[mmc._onchange_tipo_color] color limpiado (tipo no sensible)")

    @api.constrains('tipo_id', 'color')
    def _check_color_requirement(self):
        _logger.info(
            "[mmc._check_color_requirement] validando %s registro(s) ids=%s",
            len(self), self.ids
        )
        for rec in self:
            sensitive = bool(rec.tipo_id and getattr(rec.tipo_id, 'is_color_sensitive', False))
            _logger.debug(
                "[mmc._check_color_requirement] id=%s tipo=%s sensible=%s color=%s",
                rec.id, rec.tipo_id.name if rec.tipo_id else None,
                sensitive, rec.color
            )
            if sensitive and not rec.color:
                _logger.warning(
                    "[mmc._check_color_requirement] FALLO: id=%s tipo=%s requiere color y no lo tiene",
                    rec.id, rec.tipo_id.name
                )
                raise ValidationError("Este tipo de componente requiere color (K/C/M/Y).")

    # ----- Refuerzos de integridad en create/write -----
    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(
            "[mmc.create] === ENTRADA === %s registro(s) | vals_list=%s",
            len(vals_list), vals_list
        )

        for idx, vals in enumerate(vals_list):
            tipo = None
            if 'tipo_id' in vals and vals['tipo_id']:
                tipo = self.env['componente.tipo'].browse(vals['tipo_id'])
                _logger.debug(
                    "[mmc.create] vals[%s] tipo=%s sensible_color=%s",
                    idx, tipo.name,
                    getattr(tipo, 'is_color_sensitive', False)
                )
            if tipo and not getattr(tipo, 'is_color_sensitive', False):
                if vals.get('color'):
                    _logger.info(
                        "[mmc.create] vals[%s] limpiando color=%s (tipo no sensible)",
                        idx, vals.get('color')
                    )
                vals['color'] = False

            # Si vienen detalle_ids embebidos en el create, lo registramos
            if 'detalle_ids' in vals:
                _logger.info(
                    "[mmc.create] vals[%s] viene con detalle_ids=%s",
                    idx, vals['detalle_ids']
                )

        records = super().create(vals_list)
        _logger.info(
            "[mmc.create] super() creó ids=%s",
            records.ids
        )

        records._check_color_requirement()

        # Estado final
        for rec in records:
            _logger.info(
                "[mmc.create] === FIN === id=%s | tipo=%s color=%s | detalle_ids(%s)=%s",
                rec.id,
                rec.tipo_id.name if rec.tipo_id else None,
                rec.color,
                len(rec.detalle_ids),
                [(d.id, d.subparte_id.code) for d in rec.detalle_ids]
            )
        return records

    def write(self, vals):
        _logger.info(
            "[mmc.write] === ENTRADA === ids=%s | vals=%s",
            self.ids, vals
        )

        if 'detalle_ids' in vals:
            _logger.info(
                "[mmc.write] vals contiene comandos O2M en detalle_ids: %s",
                vals['detalle_ids']
            )
            # Detalle por comando
            for cmd in vals['detalle_ids']:
                if isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
                    op = cmd[0]
                    cmd_label = {
                        0: 'CREATE', 1: 'UPDATE', 2: 'DELETE',
                        3: 'UNLINK', 4: 'LINK', 5: 'CLEAR', 6: 'REPLACE_ALL'
                    }.get(op, f'UNKNOWN({op})')
                    _logger.info(
                        "[mmc.write] -- comando O2M=%s contenido=%s",
                        cmd_label, cmd
                    )

        # Estado previo
        for rec in self:
            _logger.debug(
                "[mmc.write] estado previo id=%s | detalle_ids actuales(%s)=%s",
                rec.id, len(rec.detalle_ids),
                [(d.id, d.subparte_id.code) for d in rec.detalle_ids]
            )

        res = super().write(vals)
        _logger.info("[mmc.write] super().write() retornó %s", res)

        # Limpieza color si tipo no es sensible
        for rec in self:
            if rec.tipo_id and not getattr(rec.tipo_id, 'is_color_sensitive', False) and rec.color:
                _logger.info(
                    "[mmc.write] limpiando color en id=%s (tipo no sensible)",
                    rec.id
                )
                super(ModeloMaquinaComponente, rec).write({'color': False})

        self._check_color_requirement()

        # Estado final
        for rec in self:
            _logger.info(
                "[mmc.write] === FIN === id=%s | detalle_ids(%s)=%s",
                rec.id, len(rec.detalle_ids),
                [(d.id, d.subparte_id.code, d.cantidad) for d in rec.detalle_ids]
            )

        return res

    def unlink(self):
        info = [(r.id, r.modelo_id.name, r.tipo_id.name, r.color) for r in self]
        _logger.info(
            "[mmc.unlink] eliminando %s registro(s): %s",
            len(self), info
        )
        return super().unlink()

    _sql_constraints = [
        (
            'uniq_modelo_tipo_color',
            'unique(modelo_id, tipo_id, color)',
            'Ya existe este tipo/color de componente para el modelo.'
        )
    ]


class ModeloMaquinaComponenteSubparte(models.Model):
    _name = 'modelo.maquina.componente.subparte'
    _description = 'Subparte sugerida para un componente de modelo'
    _order = 'subparte_id'

    componente_id = fields.Many2one(
        'modelo.maquina.componente',
        required=True,
        ondelete='cascade',
        index=True,
        string='Componente'
    )

    subparte_id = fields.Many2one(
        'componente.subparte',
        required=True,
        ondelete='restrict',
        index=True,
        string='Subparte'
    )

    cantidad = fields.Float(string='Cantidad', default=1.0)
    nota = fields.Char(string='Nota')

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(
            "[mmcs.create] === ENTRADA === %s registro(s) | vals_list=%s",
            len(vals_list), vals_list
        )

        # Validación pre-create
        for idx, vals in enumerate(vals_list):
            if not vals.get('componente_id'):
                _logger.warning(
                    "[mmcs.create] vals[%s] SIN componente_id: %s",
                    idx, vals
                )
            if not vals.get('subparte_id'):
                _logger.warning(
                    "[mmcs.create] vals[%s] SIN subparte_id: %s",
                    idx, vals
                )

        records = super().create(vals_list)

        for rec in records:
            _logger.info(
                "[mmcs.create] creado id=%s | componente_id=%s | subparte=%s (id=%s) | cantidad=%s",
                rec.id,
                rec.componente_id.id,
                rec.subparte_id.code if rec.subparte_id else None,
                rec.subparte_id.id if rec.subparte_id else None,
                rec.cantidad
            )
        _logger.info(
            "[mmcs.create] === FIN === ids creados=%s",
            records.ids
        )
        return records

    def write(self, vals):
        _logger.info(
            "[mmcs.write] === ENTRADA === ids=%s | vals=%s",
            self.ids, vals
        )

        for rec in self:
            _logger.debug(
                "[mmcs.write] previo id=%s | componente=%s | subparte=%s | cantidad=%s",
                rec.id,
                rec.componente_id.id,
                rec.subparte_id.code if rec.subparte_id else None,
                rec.cantidad
            )

        res = super().write(vals)
        _logger.info("[mmcs.write] super().write() retornó %s", res)

        for rec in self:
            _logger.info(
                "[mmcs.write] === FIN === id=%s | componente=%s | subparte=%s | cantidad=%s",
                rec.id,
                rec.componente_id.id,
                rec.subparte_id.code if rec.subparte_id else None,
                rec.cantidad
            )
        return res

    def unlink(self):
        info = [
            {
                'id': r.id,
                'componente_id': r.componente_id.id,
                'subparte_code': r.subparte_id.code if r.subparte_id else None,
                'cantidad': r.cantidad,
            }
            for r in self
        ]
        _logger.info(
            "[mmcs.unlink] === ELIMINANDO === %s registro(s): %s",
            len(self), info
        )
        res = super().unlink()
        _logger.info("[mmcs.unlink] === FIN === eliminados (retorno=%s)", res)
        return res

    _sql_constraints = [
        (
            'uniq_componente_subparte',
            'unique(componente_id, subparte_id)',
            'La subparte ya está listada para este componente.'
        )
    ]



class ModelosMaquin(models.Model):
    _inherit = 'modelo.maquina'

    componente_line_ids = fields.One2many(
        'modelo.maquina.componente',
        'modelo_id',
        string='Componentes del modelo'
    )

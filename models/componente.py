# models/componente.py
from odoo import models, fields

class ComponenteTipo(models.Model):
    _name = 'componente.tipo'
    _description = 'Tipo de Componente (IU, Fusora, Faja, ADF, Tray, etc.)'

    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Clave corta: IU, FUSORA, FAJA, ADF, TRAY, OPTICO, FINISHER, RED, ESCANER ...")
    is_color_sensitive = fields.Boolean(string="Difiere por color (K/C/M/Y)", default=False)
    is_critical = fields.Boolean(string="Crítico (puede dejar no operativo)", default=True)
    sequence = fields.Integer(default=10)

class ComponenteSubparte(models.Model):
    _name = 'componente.subparte'
    _description = 'Subparte técnica del componente (ej. Tambor, Cuchilla, Rodillo presión)'

    name = fields.Char(required=True)

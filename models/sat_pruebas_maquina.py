# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SatPruebaMaquina(models.Model):
    _name = 'sat.prueba.maquina'
    _description = 'Pruebas técnicas de máquina (control de contadores)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # =========================
    # RELACIONES
    # =========================
    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    tecnico_id = fields.Many2one(
        'hr.employee',
        string='Técnico',
        tracking=True
    )

    # =========================
    # FECHAS
    # =========================
    fecha_inicio = fields.Datetime(
        string='Fecha inicio',
        default=fields.Datetime.now,
        tracking=True
    )

    fecha_ultima_actualizacion = fields.Datetime(
        string='Última actualización SNMP',
        tracking=True
    )

    # =========================
    # CONTADORES INICIALES (SNAPSHOT)
    # =========================
    contador_inicial_total = fields.Integer(string='Inicial Total')
    contador_inicial_bn = fields.Integer(string='Inicial BN')
    contador_inicial_color = fields.Integer(string='Inicial Color')
    contador_inicial_impresiones = fields.Integer(string='Inicial Impresiones')
    contador_inicial_copias = fields.Integer(string='Inicial Copias')
    contador_inicial_scanner = fields.Integer(string='Inicial Scanner')
    contador_inicial_duplex = fields.Integer(string='Inicial Duplex')

    # =========================
    # CONTADORES ACTUALES (SNMP)
    # =========================
    contador_actual_total = fields.Integer(string='Actual Total', tracking=True)
    contador_actual_bn = fields.Integer(string='Actual BN')
    contador_actual_color = fields.Integer(string='Actual Color')

    contador_impresiones = fields.Integer(string='Impresiones')
    contador_copias = fields.Integer(string='Copias')
    contador_scanner = fields.Integer(string='Scanner')
    contador_duplex = fields.Integer(string='Duplex')

    # =========================
    # VALIDACIÓN AUTOMÁTICA
    # =========================
    prueba_impresion_ok = fields.Boolean(
        string='✔ Impresión',
        compute='_compute_pruebas',
        store=True
    )

    prueba_copia_ok = fields.Boolean(
        string='✔ Copia',
        compute='_compute_pruebas',
        store=True
    )

    prueba_scanner_ok = fields.Boolean(
        string='✔ Scanner',
        compute='_compute_pruebas',
        store=True
    )

    prueba_color_ok = fields.Boolean(
        string='✔ Color',
        compute='_compute_pruebas',
        store=True
    )

    prueba_duplex_ok = fields.Boolean(
        string='✔ Duplex',
        compute='_compute_pruebas',
        store=True
    )

    # =========================
    # TONER
    # =========================
    toner_negro = fields.Float(string='Tóner Negro (%)')
    toner_cyan = fields.Float(string='Tóner Cyan (%)')
    toner_magenta = fields.Float(string='Tóner Magenta (%)')
    toner_amarillo = fields.Float(string='Tóner Amarillo (%)')

    # =========================
    # ESTADO GENERAL
    # =========================
    estado_prueba = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En proceso'),
        ('completado', 'Completado'),
        ('incompleto', 'Incompleto'),
    ], string='Estado de prueba', default='pendiente', tracking=True)

    nivel_prueba = fields.Selection([
        ('basico', 'Básico (Impresión + Copia)'),
        ('intermedio', 'Intermedio (+ Duplex)'),
        ('avanzado', 'Avanzado (+ Scanner/Color)'),
    ], string='Nivel de prueba', compute='_compute_nivel_prueba', store=True)
    estado_toner = fields.Selection([
        ('ok', 'OK'),
        ('bajo', 'Bajo'),
        ('critico', 'Crítico')
    ], compute="_compute_estado_toner", store=True)
    # =========================
    # EVIDENCIA
    # =========================
    foto_prueba = fields.Binary(string='Foto de prueba')
    observaciones = fields.Text(string='Observaciones')

    # =========================
    # COMPUTE: VALIDACIONES
    # =========================
    @api.depends(
        'contador_impresiones',
        'contador_copias',
        'contador_scanner',
        'contador_duplex',
        'contador_actual_color',
        'contador_inicial_impresiones',
        'contador_inicial_copias',
        'contador_inicial_scanner',
        'contador_inicial_duplex',
        'contador_inicial_color'
    )
    def _compute_pruebas(self):
        for rec in self:

            # ✔ OBLIGATORIOS (comparando contra inicial)
            rec.prueba_impresion_ok = rec.contador_impresiones > rec.contador_inicial_impresiones
            rec.prueba_copia_ok = rec.contador_copias > rec.contador_inicial_copias

            # ✔ OPCIONALES
            rec.prueba_scanner_ok = rec.contador_scanner > rec.contador_inicial_scanner
            rec.prueba_color_ok = rec.contador_actual_color > rec.contador_inicial_color
            rec.prueba_duplex_ok = rec.contador_duplex > rec.contador_inicial_duplex

            # =========================
            # ESTADO AUTOMÁTICO
            # =========================
            if not rec.contador_actual_total:
                rec.estado_prueba = 'pendiente'
            else:
                # SOLO impresión + copia son obligatorios
                if rec.prueba_impresion_ok and rec.prueba_copia_ok:
                    rec.estado_prueba = 'completado'
                else:
                    rec.estado_prueba = 'incompleto'

    # =========================
    # COMPUTE: NIVEL DE PRUEBA
    # =========================
    @api.depends(
        'prueba_impresion_ok',
        'prueba_copia_ok',
        'prueba_duplex_ok',
        'prueba_scanner_ok',
        'prueba_color_ok'
    )
    def _compute_nivel_prueba(self):
        for rec in self:

            if rec.prueba_impresion_ok and rec.prueba_copia_ok:
                if rec.prueba_duplex_ok:
                    if rec.prueba_scanner_ok or rec.prueba_color_ok:
                        rec.nivel_prueba = 'avanzado'
                    else:
                        rec.nivel_prueba = 'intermedio'
                else:
                    rec.nivel_prueba = 'basico'
            else:
                rec.nivel_prueba = False


    def _compute_estado_toner(self):
        for rec in self:
            niveles = [
                rec.toner_black,
                rec.toner_cyan,
                rec.toner_magenta,
                rec.toner_yellow
            ]
            niveles = [n for n in niveles if n is not None]

            if not niveles:
                rec.estado_toner = 'ok'
                continue

            minimo = min(niveles)

            if minimo <= 10:
                rec.estado_toner = 'critico'
            elif minimo <= 25:
                rec.estado_toner = 'bajo'
            else:
                rec.estado_toner = 'ok'
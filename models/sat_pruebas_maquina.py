# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SatPruebaMaquina(models.Model):
    _name = 'sat.prueba.maquina'
    _description = 'Pruebas técnicas de máquina (control de contadores)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_ultima_actualizacion desc, id desc'

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
    # CONTROL HISTÓRICO
    # =========================
    es_snapshot = fields.Boolean(
        string='Es snapshot inicial',
        default=False,
        tracking=True
    )

    origen = fields.Selection([
        ('inicio', 'Inicio'),
        ('snmp', 'SNMP'),
        ('manual', 'Manual'),
    ], string='Origen', default='snmp', tracking=True)

    # =========================
    # CONTADORES INICIALES (SNAPSHOT)
    # =========================
    contador_inicial_total = fields.Integer(string='Inicial Total', tracking=True)
    contador_inicial_bn = fields.Integer(string='Inicial BN', tracking=True)
    contador_inicial_color = fields.Integer(string='Inicial Color', tracking=True)
    contador_inicial_impresiones = fields.Integer(string='Inicial Impresiones', tracking=True)
    contador_inicial_copias = fields.Integer(string='Inicial Copias', tracking=True)
    contador_inicial_scanner = fields.Integer(string='Inicial Scanner', tracking=True)
    contador_inicial_duplex = fields.Integer(string='Inicial Duplex', tracking=True)

    # =========================
    # CONTADORES ACTUALES (SNMP)
    # =========================
    contador_actual_total = fields.Integer(string='Actual Total', tracking=True)
    contador_actual_bn = fields.Integer(string='Actual BN', tracking=True)
    contador_actual_color = fields.Integer(string='Actual Color', tracking=True)

    contador_impresiones = fields.Integer(string='Impresiones', tracking=True)
    contador_copias = fields.Integer(string='Copias', tracking=True)
    contador_scanner = fields.Integer(string='Scanner', tracking=True)
    contador_duplex = fields.Integer(string='Duplex', tracking=True)

    # =========================
    # DELTAS (AUDITORÍA) — computed + tracking
    # tracking=True en campos compute+store sí funciona en Odoo 18:
    # registra en chatter cada vez que el delta cambia
    # =========================
    delta_total = fields.Integer(
        string='Δ Total',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )
    delta_bn = fields.Integer(
        string='Δ BN',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )
    delta_color = fields.Integer(
        string='Δ Color',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )
    delta_impresiones = fields.Integer(
        string='Δ Impresiones',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )
    delta_copias = fields.Integer(
        string='Δ Copias',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )
    delta_scanner = fields.Integer(
        string='Δ Scanner',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )
    delta_duplex = fields.Integer(
        string='Δ Duplex',
        compute='_compute_deltas',
        store=True,
        tracking=True
    )

    # =========================
    # VALIDACIÓN AUTOMÁTICA
    # =========================
    prueba_impresion_ok = fields.Boolean(
        string='✔ Impresión',
        compute='_compute_pruebas',
        store=True,
        tracking=True
    )

    prueba_copia_ok = fields.Boolean(
        string='✔ Copia',
        compute='_compute_pruebas',
        store=True,
        tracking=True
    )

    prueba_scanner_ok = fields.Boolean(
        string='✔ Scanner',
        compute='_compute_pruebas',
        store=True,
        tracking=True
    )

    prueba_color_ok = fields.Boolean(
        string='✔ Color',
        compute='_compute_pruebas',
        store=True,
        tracking=True
    )

    prueba_duplex_ok = fields.Boolean(
        string='✔ Duplex',
        compute='_compute_pruebas',
        store=True,
        tracking=True
    )

    # Separado de _compute_pruebas para evitar dependencia circular
    estado_prueba = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En proceso'),
        ('completado', 'Completado'),
        ('incompleto', 'Incompleto'),
    ], string='Estado de prueba', default='pendiente',
       compute='_compute_estado_prueba',
       store=True,
       tracking=True)

    nivel_prueba = fields.Selection([
        ('basico', 'Básico (Impresión + Copia)'),
        ('intermedio', 'Intermedio (+ Duplex)'),
        ('avanzado', 'Avanzado (+ Scanner/Color)'),
    ], string='Nivel de prueba',
       compute='_compute_nivel_prueba',
       store=True,
       tracking=True)

    # =========================
    # TONER
    # =========================
    toner_negro = fields.Float(string='Tóner Negro (%)', tracking=True)
    toner_cyan = fields.Float(string='Tóner Cyan (%)', tracking=True)
    toner_magenta = fields.Float(string='Tóner Magenta (%)', tracking=True)
    toner_amarillo = fields.Float(string='Tóner Amarillo (%)', tracking=True)

    estado_toner = fields.Selection([
        ('ok', 'OK'),
        ('bajo', 'Bajo'),
        ('critico', 'Crítico')
    ], compute='_compute_estado_toner',
       store=True,
       tracking=True)

    # =========================
    # EVIDENCIA
    # =========================
    foto_prueba = fields.Binary(string='Foto de prueba')
    observaciones = fields.Text(string='Observaciones', tracking=True)

    # =========================
    # COMPUTE: DELTAS
    # actual - inicial (puede ser negativo si el snapshot se tomó mal)
    # =========================
    @api.depends(
        'contador_actual_total', 'contador_inicial_total',
        'contador_actual_bn', 'contador_inicial_bn',
        'contador_actual_color', 'contador_inicial_color',
        'contador_impresiones', 'contador_inicial_impresiones',
        'contador_copias', 'contador_inicial_copias',
        'contador_scanner', 'contador_inicial_scanner',
        'contador_duplex', 'contador_inicial_duplex',
    )
    def _compute_deltas(self):
        for rec in self:
            rec.delta_total = rec.contador_actual_total - rec.contador_inicial_total
            rec.delta_bn = rec.contador_actual_bn - rec.contador_inicial_bn
            rec.delta_color = rec.contador_actual_color - rec.contador_inicial_color
            rec.delta_impresiones = rec.contador_impresiones - rec.contador_inicial_impresiones
            rec.delta_copias = rec.contador_copias - rec.contador_inicial_copias
            rec.delta_scanner = rec.contador_scanner - rec.contador_inicial_scanner
            rec.delta_duplex = rec.contador_duplex - rec.contador_inicial_duplex

    # =========================
    # COMPUTE: VALIDACIONES (solo booleanos)
    # Usa los deltas para saber si hubo actividad real
    # =========================
    @api.depends(
        'delta_impresiones',
        'delta_copias',
        'delta_scanner',
        'delta_color',
        'delta_duplex',
    )
    def _compute_pruebas(self):
        for rec in self:
            rec.prueba_impresion_ok = rec.delta_impresiones > 0
            rec.prueba_copia_ok = rec.delta_copias > 0
            rec.prueba_scanner_ok = rec.delta_scanner > 0
            rec.prueba_color_ok = rec.delta_color > 0
            rec.prueba_duplex_ok = rec.delta_duplex > 0

    # =========================
    # COMPUTE: ESTADO PRUEBA (separado para evitar ciclo)
    # =========================
    @api.depends(
        'contador_actual_total',
        'prueba_impresion_ok',
        'prueba_copia_ok',
    )
    def _compute_estado_prueba(self):
        for rec in self:
            if not rec.contador_actual_total:
                rec.estado_prueba = 'pendiente'
            elif rec.prueba_impresion_ok and rec.prueba_copia_ok:
                rec.estado_prueba = 'completado'
            elif rec.prueba_impresion_ok or rec.prueba_copia_ok:
                rec.estado_prueba = 'en_proceso'
            else:
                rec.estado_prueba = 'incompleto'

    # =========================
    # COMPUTE: NIVEL
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

    # =========================
    # COMPUTE: TONER
    # =========================
    @api.depends('toner_negro', 'toner_cyan', 'toner_magenta', 'toner_amarillo')
    def _compute_estado_toner(self):
        for rec in self:
            niveles = [
                rec.toner_negro,
                rec.toner_cyan,
                rec.toner_magenta,
                rec.toner_amarillo
            ]
            # Ignorar ceros (máquina BN no tiene tóner color)
            niveles = [n for n in niveles if n and n > 0]

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
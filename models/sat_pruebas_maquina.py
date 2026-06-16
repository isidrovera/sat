# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


# ==========================================================
# HELPERS GENERALES
# ==========================================================

def _to_int(value):
    """
    Convierte valores SNMP/Odoo a entero seguro.
    Mantiene 0 cuando no hay valor usable.
    """
    try:
        if value in (None, False, ''):
            return 0

        if isinstance(value, bool):
            return int(value)

        if isinstance(value, (int, float)):
            return int(value)

        text = str(value).strip()
        if not text:
            return 0

        # Permite negativos, aunque normalmente no deben llegar para contadores.
        m = re.search(r'-?\d+', text.replace(',', ''))
        return int(m.group(0)) if m else 0

    except Exception:
        return 0


def _to_float_or_false(value):
    """
    Convierte valores SNMP a float.
    Retorna False cuando el valor no existe.
    Respeta 0 como valor válido.
    """
    try:
        if value is None or value is False:
            return False

        if isinstance(value, str):
            text = value.replace(',', '').strip()
            if text == '':
                return False

            m = re.search(r'-?\d+(?:\.\d+)?', text)
            return float(m.group(0)) if m else False

        if isinstance(value, bool):
            return float(int(value))

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).replace(',', '').strip()
        if not text:
            return False

        m = re.search(r'-?\d+(?:\.\d+)?', text)
        return float(m.group(0)) if m else False

    except Exception:
        return False


def _to_text(value):
    if value in (None, False):
        return ''
    return str(value).strip()


def _json_dumps(value):
    try:
        return json.dumps(value or {}, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return str(value or '')


def _json_loads(value):
    if not value:
        return {}

    if isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except Exception:
        return {}


def _safe_get_number(data, *keys):
    """
    Busca en un dict varias claves posibles y devuelve int o 0.
    """
    data = data or {}

    for key in keys:
        if key in data and data.get(key) not in (None, False, ''):
            return _to_int(data.get(key))

    return 0


def _safe_get_float(data, *keys):
    """
    Busca en un dict varias claves posibles y devuelve float o False.
    """
    data = data or {}

    for key in keys:
        if key in data and data.get(key) not in (None, False, ''):
            return _to_float_or_false(data.get(key))

    return False


# ==========================================================
# MODELO PRINCIPAL: PRUEBA DE MÁQUINA
# ==========================================================

class SatPruebaMaquina(models.Model):
    _name = 'sat.prueba.maquina'
    _description = 'Pruebas técnicas de máquina (control SNMP completo)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_ultima_actualizacion desc, id desc'

    # ======================================================
    # RELACIONES
    # ======================================================
    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
    )

    tecnico_id = fields.Many2one(
        'hr.employee',
        string='Técnico',
        tracking=True,
        index=True,
    )

    # ======================================================
    # FECHAS / CONTROL
    # ======================================================
    fecha_inicio = fields.Datetime(
        string='Fecha inicio',
        default=fields.Datetime.now,
        tracking=True,
        index=True,
    )

    fecha_snapshot_snmp = fields.Datetime(
        string='Fecha snapshot inicial SNMP',
        tracking=True,
        copy=False,
    )

    fecha_ultima_actualizacion = fields.Datetime(
        string='Última actualización SNMP',
        tracking=True,
        copy=False,
        index=True,
    )

    es_snapshot = fields.Boolean(
        string='Es snapshot inicial',
        default=False,
        tracking=True,
        copy=False,
    )

    origen = fields.Selection([
        ('inicio', 'Inicio'),
        ('snmp', 'SNMP'),
        ('manual', 'Manual'),
    ], string='Origen', default='snmp', tracking=True)

    # ======================================================
    # IDENTIFICACIÓN SNMP
    # ======================================================
    snmp_ip = fields.Char(
        string='IP SNMP',
        tracking=True,
        copy=False,
        index=True,
    )

    snmp_serie = fields.Char(
        string='Serie SNMP',
        tracking=True,
        copy=False,
        index=True,
    )

    snmp_marca = fields.Char(
        string='Marca SNMP',
        tracking=True,
        copy=False,
        index=True,
    )

    snmp_modelo = fields.Char(
        string='Modelo SNMP',
        tracking=True,
        copy=False,
        index=True,
    )

    snmp_enterprise_id = fields.Char(
        string='Enterprise ID',
        tracking=True,
        copy=False,
    )

    snmp_config = fields.Char(
        string='Configuración SNMP usada',
        tracking=True,
        copy=False,
    )

    snmp_summary_file = fields.Char(
        string='Archivo resumen SNMP',
        copy=False,
    )

    raw_payload_json = fields.Text(
        string='Payload SNMP completo',
        copy=False,
    )

    raw_summary_text = fields.Text(
        string='Resumen TXT completo',
        copy=False,
    )

    # ======================================================
    # CONTADORES INICIALES - RESUMEN
    # ======================================================
    contador_inicial_total = fields.Integer(string='Inicial Total', tracking=True)
    contador_inicial_bn = fields.Integer(string='Inicial B/N', tracking=True)
    contador_inicial_color = fields.Integer(string='Inicial Color', tracking=True)

    contador_inicial_impresiones = fields.Integer(string='Inicial Impresiones', tracking=True)
    contador_inicial_copias = fields.Integer(string='Inicial Copias', tracking=True)
    contador_inicial_scanner = fields.Integer(string='Inicial Scanner', tracking=True)
    contador_inicial_duplex = fields.Integer(string='Inicial Dúplex', tracking=True)

    # ======================================================
    # CONTADORES INICIALES - DETALLE COLOR / B/N
    # ======================================================
    contador_inicial_copias_bn = fields.Integer(string='Inicial Copias B/N', tracking=True)
    contador_inicial_impresiones_bn = fields.Integer(string='Inicial Impresiones B/N', tracking=True)

    contador_inicial_copias_color = fields.Integer(string='Inicial Copias Color', tracking=True)
    contador_inicial_impresiones_color = fields.Integer(string='Inicial Impresiones Color', tracking=True)

    contador_inicial_fax = fields.Integer(string='Inicial Fax', tracking=True)
    contador_inicial_gran_total = fields.Integer(string='Inicial Gran Total', tracking=True)

    # ======================================================
    # CONTADORES ACTUALES - RESUMEN
    # ======================================================
    contador_actual_total = fields.Integer(string='Actual Total', tracking=True)
    contador_actual_bn = fields.Integer(string='Actual B/N', tracking=True)
    contador_actual_color = fields.Integer(string='Actual Color', tracking=True)

    contador_impresiones = fields.Integer(string='Impresiones', tracking=True)
    contador_copias = fields.Integer(string='Copias', tracking=True)
    contador_scanner = fields.Integer(string='Scanner', tracking=True)
    contador_duplex = fields.Integer(string='Dúplex', tracking=True)

    # ======================================================
    # CONTADORES ACTUALES - DETALLE COLOR / B/N
    # ======================================================
    contador_actual_copias_bn = fields.Integer(string='Actual Copias B/N', tracking=True)
    contador_actual_impresiones_bn = fields.Integer(string='Actual Impresiones B/N', tracking=True)

    contador_actual_copias_color = fields.Integer(string='Actual Copias Color', tracking=True)
    contador_actual_impresiones_color = fields.Integer(string='Actual Impresiones Color', tracking=True)

    contador_fax = fields.Integer(string='Fax', tracking=True)
    contador_gran_total = fields.Integer(string='Gran Total', tracking=True)

    # ======================================================
    # DELTAS - RESUMEN
    # ======================================================
    delta_total = fields.Integer(
        string='Δ Total',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_bn = fields.Integer(
        string='Δ B/N',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_color = fields.Integer(
        string='Δ Color',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_impresiones = fields.Integer(
        string='Δ Impresiones',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_copias = fields.Integer(
        string='Δ Copias',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_scanner = fields.Integer(
        string='Δ Scanner',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_duplex = fields.Integer(
        string='Δ Dúplex',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    # ======================================================
    # DELTAS - DETALLE COLOR / B/N
    # ======================================================
    delta_copias_bn = fields.Integer(
        string='Δ Copias B/N',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_impresiones_bn = fields.Integer(
        string='Δ Impresiones B/N',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_copias_color = fields.Integer(
        string='Δ Copias Color',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_impresiones_color = fields.Integer(
        string='Δ Impresiones Color',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_fax = fields.Integer(
        string='Δ Fax',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    delta_gran_total = fields.Integer(
        string='Δ Gran Total',
        compute='_compute_deltas',
        store=True,
        tracking=True,
    )

    # ======================================================
    # TÓNER INICIAL
    # ======================================================
    toner_inicial_negro = fields.Float(string='Inicial Tóner Negro (%)', tracking=True)
    toner_inicial_cyan = fields.Float(string='Inicial Tóner Cyan (%)', tracking=True)
    toner_inicial_magenta = fields.Float(string='Inicial Tóner Magenta (%)', tracking=True)
    toner_inicial_amarillo = fields.Float(string='Inicial Tóner Amarillo (%)', tracking=True)

    # ======================================================
    # TÓNER ACTUAL
    # ======================================================
    toner_negro = fields.Float(string='Tóner Negro (%)', tracking=True)
    toner_cyan = fields.Float(string='Tóner Cyan (%)', tracking=True)
    toner_magenta = fields.Float(string='Tóner Magenta (%)', tracking=True)
    toner_amarillo = fields.Float(string='Tóner Amarillo (%)', tracking=True)

    # ======================================================
    # DELTA TÓNER
    # ======================================================
    delta_toner_negro = fields.Float(
        string='Δ Tóner Negro',
        compute='_compute_toner_deltas',
        store=True,
        tracking=True,
    )

    delta_toner_cyan = fields.Float(
        string='Δ Tóner Cyan',
        compute='_compute_toner_deltas',
        store=True,
        tracking=True,
    )

    delta_toner_magenta = fields.Float(
        string='Δ Tóner Magenta',
        compute='_compute_toner_deltas',
        store=True,
        tracking=True,
    )

    delta_toner_amarillo = fields.Float(
        string='Δ Tóner Amarillo',
        compute='_compute_toner_deltas',
        store=True,
        tracking=True,
    )

    estado_toner = fields.Selection([
        ('ok', 'OK'),
        ('bajo', 'Bajo'),
        ('critico', 'Crítico'),
        ('sin_datos', 'Sin datos'),
    ], compute='_compute_estado_toner',
       store=True,
       tracking=True)

    # ======================================================
    # VALIDACIÓN DE PRUEBAS
    # ======================================================
    prueba_impresion_ok = fields.Boolean(
        string='✔ Impresión',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_copia_ok = fields.Boolean(
        string='✔ Copia',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_scanner_ok = fields.Boolean(
        string='✔ Scanner',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_color_ok = fields.Boolean(
        string='✔ Color',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_bn_ok = fields.Boolean(
        string='✔ B/N',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_duplex_ok = fields.Boolean(
        string='✔ Dúplex',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_copia_bn_ok = fields.Boolean(
        string='✔ Copia B/N',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_copia_color_ok = fields.Boolean(
        string='✔ Copia Color',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_impresion_bn_ok = fields.Boolean(
        string='✔ Impresión B/N',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    prueba_impresion_color_ok = fields.Boolean(
        string='✔ Impresión Color',
        compute='_compute_pruebas',
        store=True,
        tracking=True,
    )

    tiene_alertas_snmp = fields.Boolean(
        string='Tiene alertas SNMP',
        compute='_compute_alertas_resumen',
        store=True,
        tracking=True,
    )

    cantidad_alertas_snmp = fields.Integer(
        string='Cantidad alertas SNMP',
        compute='_compute_alertas_resumen',
        store=True,
        tracking=True,
    )

    estado_prueba = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En proceso'),
        ('completado', 'Completado'),
        ('incompleto', 'Incompleto'),
        ('con_alertas', 'Con alertas'),
    ], string='Estado de prueba',
       default='pendiente',
       compute='_compute_estado_prueba',
       store=True,
       tracking=True)

    nivel_prueba = fields.Selection([
        ('sin_prueba', 'Sin prueba'),
        ('basico', 'Básico'),
        ('intermedio', 'Intermedio'),
        ('avanzado', 'Avanzado'),
        ('completo', 'Completo'),
    ], string='Nivel de prueba',
       compute='_compute_nivel_prueba',
       store=True,
       tracking=True)

    resumen_prueba = fields.Text(
        string='Resumen de prueba',
        compute='_compute_resumen_prueba',
        store=True,
    )

    # ======================================================
    # EVIDENCIA
    # ======================================================
    foto_prueba = fields.Binary(string='Foto de prueba')
    observaciones = fields.Text(string='Observaciones', tracking=True)

    # ======================================================
    # LÍNEAS / HISTORIAL SNMP
    # ======================================================
    snmp_log_ids = fields.One2many(
        'sat.prueba.maquina.snmp.log',
        'prueba_id',
        string='Historial SNMP',
        copy=False,
    )

    snmp_detalle_ids = fields.One2many(
        'sat.prueba.maquina.snmp.detalle',
        'prueba_id',
        string='Detalle SNMP completo',
        copy=False,
    )

    snmp_alerta_ids = fields.One2many(
        'sat.prueba.maquina.snmp.alerta',
        'prueba_id',
        string='Alertas SNMP',
        copy=False,
    )

    # ======================================================
    # COMPUTE: DELTAS
    # ======================================================
    @api.depends(
        'contador_actual_total', 'contador_inicial_total',
        'contador_actual_bn', 'contador_inicial_bn',
        'contador_actual_color', 'contador_inicial_color',
        'contador_impresiones', 'contador_inicial_impresiones',
        'contador_copias', 'contador_inicial_copias',
        'contador_scanner', 'contador_inicial_scanner',
        'contador_duplex', 'contador_inicial_duplex',
        'contador_actual_copias_bn', 'contador_inicial_copias_bn',
        'contador_actual_impresiones_bn', 'contador_inicial_impresiones_bn',
        'contador_actual_copias_color', 'contador_inicial_copias_color',
        'contador_actual_impresiones_color', 'contador_inicial_impresiones_color',
        'contador_fax', 'contador_inicial_fax',
        'contador_gran_total', 'contador_inicial_gran_total',
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

            rec.delta_copias_bn = rec.contador_actual_copias_bn - rec.contador_inicial_copias_bn
            rec.delta_impresiones_bn = rec.contador_actual_impresiones_bn - rec.contador_inicial_impresiones_bn
            rec.delta_copias_color = rec.contador_actual_copias_color - rec.contador_inicial_copias_color
            rec.delta_impresiones_color = rec.contador_actual_impresiones_color - rec.contador_inicial_impresiones_color

            rec.delta_fax = rec.contador_fax - rec.contador_inicial_fax
            rec.delta_gran_total = rec.contador_gran_total - rec.contador_inicial_gran_total

    # ======================================================
    # COMPUTE: DELTA TÓNER
    # ======================================================
    @api.depends(
        'toner_negro', 'toner_inicial_negro',
        'toner_cyan', 'toner_inicial_cyan',
        'toner_magenta', 'toner_inicial_magenta',
        'toner_amarillo', 'toner_inicial_amarillo',
    )
    def _compute_toner_deltas(self):
        for rec in self:
            rec.delta_toner_negro = rec.toner_negro - rec.toner_inicial_negro
            rec.delta_toner_cyan = rec.toner_cyan - rec.toner_inicial_cyan
            rec.delta_toner_magenta = rec.toner_magenta - rec.toner_inicial_magenta
            rec.delta_toner_amarillo = rec.toner_amarillo - rec.toner_inicial_amarillo

    # ======================================================
    # COMPUTE: PRUEBAS
    # ======================================================
    @api.depends(
        'delta_impresiones',
        'delta_copias',
        'delta_scanner',
        'delta_color',
        'delta_bn',
        'delta_duplex',
        'delta_copias_bn',
        'delta_copias_color',
        'delta_impresiones_bn',
        'delta_impresiones_color',
    )
    def _compute_pruebas(self):
        for rec in self:
            rec.prueba_impresion_ok = (
                rec.delta_impresiones > 0
                or rec.delta_impresiones_bn > 0
                or rec.delta_impresiones_color > 0
            )

            rec.prueba_copia_ok = (
                rec.delta_copias > 0
                or rec.delta_copias_bn > 0
                or rec.delta_copias_color > 0
            )

            rec.prueba_scanner_ok = rec.delta_scanner > 0

            rec.prueba_color_ok = (
                rec.delta_color > 0
                or rec.delta_copias_color > 0
                or rec.delta_impresiones_color > 0
            )

            rec.prueba_bn_ok = (
                rec.delta_bn > 0
                or rec.delta_copias_bn > 0
                or rec.delta_impresiones_bn > 0
            )

            rec.prueba_duplex_ok = rec.delta_duplex > 0

            rec.prueba_copia_bn_ok = rec.delta_copias_bn > 0
            rec.prueba_copia_color_ok = rec.delta_copias_color > 0
            rec.prueba_impresion_bn_ok = rec.delta_impresiones_bn > 0
            rec.prueba_impresion_color_ok = rec.delta_impresiones_color > 0

    # ======================================================
    # COMPUTE: ALERTAS
    # ======================================================
    @api.depends('snmp_alerta_ids', 'snmp_alerta_ids.activa')
    def _compute_alertas_resumen(self):
        for rec in self:
            alertas = rec.snmp_alerta_ids.filtered(lambda a: a.activa)
            rec.cantidad_alertas_snmp = len(alertas)
            rec.tiene_alertas_snmp = bool(alertas)

    # ======================================================
    # COMPUTE: ESTADO PRUEBA
    # ======================================================
    @api.depends(
        'contador_actual_total',
        'prueba_impresion_ok',
        'prueba_copia_ok',
        'prueba_scanner_ok',
        'prueba_color_ok',
        'prueba_bn_ok',
        'prueba_duplex_ok',
        'tiene_alertas_snmp',
    )
    def _compute_estado_prueba(self):
        for rec in self:
            if rec.tiene_alertas_snmp:
                rec.estado_prueba = 'con_alertas'
            elif not rec.contador_actual_total:
                rec.estado_prueba = 'pendiente'
            elif rec.prueba_impresion_ok and rec.prueba_copia_ok:
                rec.estado_prueba = 'completado'
            elif (
                rec.prueba_impresion_ok
                or rec.prueba_copia_ok
                or rec.prueba_scanner_ok
                or rec.prueba_color_ok
                or rec.prueba_bn_ok
                or rec.prueba_duplex_ok
            ):
                rec.estado_prueba = 'en_proceso'
            else:
                rec.estado_prueba = 'incompleto'

    # ======================================================
    # COMPUTE: NIVEL
    # ======================================================
    @api.depends(
        'prueba_impresion_ok',
        'prueba_copia_ok',
        'prueba_duplex_ok',
        'prueba_scanner_ok',
        'prueba_color_ok',
        'prueba_bn_ok',
    )
    def _compute_nivel_prueba(self):
        for rec in self:
            total_ok = 0

            if rec.prueba_impresion_ok:
                total_ok += 1
            if rec.prueba_copia_ok:
                total_ok += 1
            if rec.prueba_scanner_ok:
                total_ok += 1
            if rec.prueba_duplex_ok:
                total_ok += 1
            if rec.prueba_color_ok:
                total_ok += 1
            if rec.prueba_bn_ok:
                total_ok += 1

            if total_ok <= 0:
                rec.nivel_prueba = 'sin_prueba'
            elif total_ok <= 2:
                rec.nivel_prueba = 'basico'
            elif total_ok <= 4:
                rec.nivel_prueba = 'intermedio'
            elif total_ok == 5:
                rec.nivel_prueba = 'avanzado'
            else:
                rec.nivel_prueba = 'completo'

    # ======================================================
    # COMPUTE: ESTADO TÓNER
    # ======================================================
    @api.depends('toner_negro', 'toner_cyan', 'toner_magenta', 'toner_amarillo')
    def _compute_estado_toner(self):
        for rec in self:
            niveles = [
                rec.toner_negro,
                rec.toner_cyan,
                rec.toner_magenta,
                rec.toner_amarillo,
            ]

            # Ignorar vacíos, pero NO ignorar 0 si existe porque 0 puede ser tóner vacío.
            niveles_validos = []
            for n in niveles:
                if n is not False and n is not None:
                    try:
                        niveles_validos.append(float(n))
                    except Exception:
                        pass

            if not niveles_validos:
                rec.estado_toner = 'sin_datos'
                continue

            minimo = min(niveles_validos)

            if minimo <= 10:
                rec.estado_toner = 'critico'
            elif minimo <= 25:
                rec.estado_toner = 'bajo'
            else:
                rec.estado_toner = 'ok'

    # ======================================================
    # COMPUTE: RESUMEN PRUEBA
    # ======================================================
    @api.depends(
        'delta_copias',
        'delta_impresiones',
        'delta_scanner',
        'delta_duplex',
        'delta_bn',
        'delta_color',
        'delta_copias_bn',
        'delta_copias_color',
        'delta_impresiones_bn',
        'delta_impresiones_color',
        'cantidad_alertas_snmp',
        'estado_toner',
    )
    def _compute_resumen_prueba(self):
        for rec in self:
            lineas = []

            lineas.append("Resumen automático de prueba SNMP:")
            lineas.append("")

            lineas.append("Contadores:")
            lineas.append("• Copias total: %s" % rec.delta_copias)
            lineas.append("• Impresiones total: %s" % rec.delta_impresiones)
            lineas.append("• Scanner: %s" % rec.delta_scanner)
            lineas.append("• Dúplex: %s" % rec.delta_duplex)
            lineas.append("• B/N total: %s" % rec.delta_bn)
            lineas.append("• Color total: %s" % rec.delta_color)
            lineas.append("• Copias B/N: %s" % rec.delta_copias_bn)
            lineas.append("• Copias Color: %s" % rec.delta_copias_color)
            lineas.append("• Impresiones B/N: %s" % rec.delta_impresiones_bn)
            lineas.append("• Impresiones Color: %s" % rec.delta_impresiones_color)
            lineas.append("")

            lineas.append("Resultado:")
            lineas.append("• Copia: %s" % ("Probado" if rec.prueba_copia_ok else "No probado"))
            lineas.append("• Impresión: %s" % ("Probado" if rec.prueba_impresion_ok else "No probado"))
            lineas.append("• Scanner: %s" % ("Probado" if rec.prueba_scanner_ok else "No probado"))
            lineas.append("• Dúplex: %s" % ("Probado" if rec.prueba_duplex_ok else "No probado"))
            lineas.append("• B/N: %s" % ("Probado" if rec.prueba_bn_ok else "No probado"))
            lineas.append("• Color: %s" % ("Probado" if rec.prueba_color_ok else "No probado"))
            lineas.append("")

            lineas.append("Tóner: %s" % (rec.estado_toner or 'Sin datos'))
            lineas.append("Alertas SNMP activas: %s" % rec.cantidad_alertas_snmp)

            rec.resumen_prueba = "\n".join(lineas)

    # ======================================================
    # MÉTODO PRINCIPAL PARA APLICAR PAYLOAD SNMP COMPLETO
    # ======================================================
    def aplicar_snmp_payload(self, counters=None, toner=None, payload=None):
        """
        Método central para actualizar la prueba con TODO lo obtenido por SNMP.

        Este método está preparado para recibir:
          - counters
          - toner
          - payload completo

        Payload puede contener:
          - counters
          - toner
          - raw_counters
          - supplies
          - raw_supplies
          - units
          - accessories
          - trays
          - alerts
          - raw_alerts
          - summary_text
        """
        for rec in self:
            rec._aplicar_snmp_payload_one(
                counters=counters or {},
                toner=toner or {},
                payload=payload or {},
            )

    def _aplicar_snmp_payload_one(self, counters=None, toner=None, payload=None):
        self.ensure_one()

        counters = counters or {}
        toner = toner or {}
        payload = payload or {}

        now = fields.Datetime.now()

        # Si payload trae counters/toner, tienen prioridad sobre los argumentos.
        if isinstance(payload.get('counters'), dict):
            counters = payload.get('counters') or counters

        if isinstance(payload.get('toner'), dict):
            toner = payload.get('toner') or toner

        vals_actuales = self._preparar_valores_actuales_snmp(
            counters=counters,
            toner=toner,
            payload=payload,
            now=now,
        )

        _logger.info(
            "[PRUEBA SNMP MAPEO] Prueba ID=%s | Máquina ID=%s | Serie=%s | "
            "total=%s | copias=%s | impresiones=%s | scanner=%s | duplex=%s | "
            "bn=%s | color=%s | copy_bw=%s | print_bw=%s | copy_color=%s | print_color=%s | "
            "toner K=%s C=%s M=%s Y=%s",
            self.id,
            self.maquina_id.id,
            payload.get('serial'),
            vals_actuales.get('contador_actual_total'),
            vals_actuales.get('contador_copias'),
            vals_actuales.get('contador_impresiones'),
            vals_actuales.get('contador_scanner'),
            vals_actuales.get('contador_duplex'),
            vals_actuales.get('contador_actual_bn'),
            vals_actuales.get('contador_actual_color'),
            vals_actuales.get('contador_actual_copias_bn'),
            vals_actuales.get('contador_actual_impresiones_bn'),
            vals_actuales.get('contador_actual_copias_color'),
            vals_actuales.get('contador_actual_impresiones_color'),
            vals_actuales.get('toner_negro'),
            vals_actuales.get('toner_cyan'),
            vals_actuales.get('toner_magenta'),
            vals_actuales.get('toner_amarillo'),
        )

        vals_iniciales = {}
        if not self.fecha_snapshot_snmp:
            vals_iniciales = self._preparar_valores_iniciales_desde_actuales(vals_actuales, now)

        vals = {}
        vals.update(vals_iniciales)
        vals.update(vals_actuales)

        _logger.info(
            "[PRUEBA SNMP WRITE] prueba=%s maquina=%s | vals_keys=%s | vals=%s",
            self.id,
            self.maquina_id.id,
            sorted(list(vals.keys())),
            vals,
        )

        self.sudo().write(vals)

        _logger.info(
            "[PRUEBA SNMP WRITE OK] prueba=%s maquina=%s | total=%s copias=%s impresiones=%s scanner=%s duplex=%s bn=%s color=%s",
            self.id,
            self.maquina_id.id,
            self.contador_actual_total,
            self.contador_copias,
            self.contador_impresiones,
            self.contador_scanner,
            self.contador_duplex,
            self.contador_actual_bn,
            self.contador_actual_color,
        )

        # Guardar log por cada lectura.
        log = self._crear_log_snmp(
            counters=counters,
            toner=toner,
            payload=payload,
            now=now,
        )

        # Guardar detalle completo por líneas.
        self._actualizar_detalle_snmp(
            counters=counters,
            toner=toner,
            payload=payload,
            log=log,
        )

        # Guardar alertas activas.
        self._actualizar_alertas_snmp(
            payload=payload,
            log=log,
        )

        self.message_post(
            body=(
                "Lectura SNMP registrada en prueba.<br/>"
                "Total: <b>%s</b><br/>"
                "Copias: <b>%s</b><br/>"
                "Impresiones: <b>%s</b><br/>"
                "Scanner: <b>%s</b><br/>"
                "Dúplex: <b>%s</b><br/>"
                "Copias B/N: <b>%s</b><br/>"
                "Impresiones B/N: <b>%s</b><br/>"
                "Copias Color: <b>%s</b><br/>"
                "Impresiones Color: <b>%s</b>"
            ) % (
                vals_actuales.get('contador_actual_total', 0),
                vals_actuales.get('contador_copias', 0),
                vals_actuales.get('contador_impresiones', 0),
                vals_actuales.get('contador_scanner', 0),
                vals_actuales.get('contador_duplex', 0),
                vals_actuales.get('contador_actual_copias_bn', 0),
                vals_actuales.get('contador_actual_impresiones_bn', 0),
                vals_actuales.get('contador_actual_copias_color', 0),
                vals_actuales.get('contador_actual_impresiones_color', 0),
            ),
            subtype_xmlid='mail.mt_note',
        )

        return True

    def _preparar_valores_actuales_snmp(self, counters=None, toner=None, payload=None, now=None):
        """
        Mapea payload SNMP completo a campos de sat.prueba.maquina.

        Versión reforzada con logs:
        - Busca valores en counters, payload y raw_counters.
        - Respeta 0 como valor válido.
        - Registra qué llaves llegaron.
        - Registra de qué origen salió cada contador.
        - Registra qué contadores quedaron en 0 para poder revisar alias/OID.
        """
        counters = counters or {}
        toner = toner or {}
        payload = payload or {}
        now = now or fields.Datetime.now()

        if not isinstance(counters, dict):
            _logger.warning(
                "[PRUEBA SNMP MAPEO] counters no es dict | prueba=%s | tipo=%s | valor=%s",
                self.id,
                type(counters).__name__,
                counters,
            )
            counters = {}

        if not isinstance(toner, dict):
            _logger.warning(
                "[PRUEBA SNMP MAPEO] toner no es dict | prueba=%s | tipo=%s | valor=%s",
                self.id,
                type(toner).__name__,
                toner,
            )
            toner = {}

        if not isinstance(payload, dict):
            _logger.warning(
                "[PRUEBA SNMP MAPEO] payload no es dict | prueba=%s | tipo=%s | valor=%s",
                self.id,
                type(payload).__name__,
                payload,
            )
            payload = {}

        # Si payload trae counters/toner, también los combinamos aquí.
        payload_counters = payload.get('counters') if isinstance(payload.get('counters'), dict) else {}
        payload_toner = payload.get('toner') if isinstance(payload.get('toner'), dict) else {}
        raw_counters = payload.get('raw_counters') or counters.get('raw') or {}

        if not isinstance(raw_counters, dict):
            raw_counters = {}

        _logger.info(
            "[PRUEBA SNMP INPUT] prueba=%s maquina=%s serie=%s | payload_keys=%s | counters_keys=%s | "
            "payload_counters_keys=%s | toner_keys=%s | payload_toner_keys=%s | raw_counters_count=%s",
            self.id,
            self.maquina_id.id,
            payload.get('serial'),
            sorted(list(payload.keys())),
            sorted(list(counters.keys())),
            sorted(list(payload_counters.keys())),
            sorted(list(toner.keys())),
            sorted(list(payload_toner.keys())),
            len(raw_counters),
        )

        def _valid(value):
            return value is not None and value is not False and value != ''

        def _norm_key(value):
            value = _to_text(value).lower()
            value = value.replace('-', '_').replace(' ', '_').replace('/', '_')
            value = re.sub(r'[^a-z0-9_]+', '_', value)
            value = re.sub(r'_+', '_', value).strip('_')
            return value

        def _raw_value(data):
            if isinstance(data, dict):
                for k in (
                    'value', 'valor', 'counter', 'count', 'level',
                    'current', 'valor_actual', 'valor_actual_numero',
                ):
                    if k in data and _valid(data.get(k)):
                        return data.get(k)
            return data

        def _raw_meta(data):
            if isinstance(data, dict):
                return {
                    'oid': data.get('oid') or data.get('oid_value') or data.get('oid_counter') or '',
                    'source_name': data.get('source_name') or data.get('origen') or data.get('name') or '',
                    'oid_name': data.get('oid_name') or '',
                    'unit': data.get('unit') or data.get('unidad') or '',
                }
            return {}

        # Construye una bolsa de búsqueda con prioridad.
        # No se usa dict simple porque una misma clave puede venir de varios orígenes.
        candidates = []

        for key, value in counters.items():
            if key == 'raw':
                continue
            candidates.append({
                'origin': 'arg.counters',
                'key': key,
                'norm': _norm_key(key),
                'value': value,
                'meta': {},
            })

        for key, value in payload_counters.items():
            if key == 'raw':
                continue
            candidates.append({
                'origin': 'payload.counters',
                'key': key,
                'norm': _norm_key(key),
                'value': value,
                'meta': {},
            })

        # También revisar top-level porque el intake manda total_counter, copy_counter, etc.
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                continue
            candidates.append({
                'origin': 'payload.top',
                'key': key,
                'norm': _norm_key(key),
                'value': value,
                'meta': {},
            })

        # raw_counters: puede venir por nombre humano o por source_name.
        for name, data in raw_counters.items():
            meta = _raw_meta(data)
            value = _raw_value(data)
            raw_names = [
                name,
                meta.get('source_name'),
                meta.get('oid_name'),
            ]
            for raw_name in raw_names:
                if not raw_name:
                    continue
                candidates.append({
                    'origin': 'payload.raw_counters',
                    'key': raw_name,
                    'norm': _norm_key(raw_name),
                    'value': value,
                    'meta': meta,
                })

        def _find_number(field_label, aliases, contains_aliases=None):
            aliases_norm = [_norm_key(a) for a in aliases]
            contains_norm = [_norm_key(a) for a in (contains_aliases or [])]

            # 1) exacto por prioridad de inserción.
            for alias in aliases_norm:
                for c in candidates:
                    if c.get('norm') == alias and _valid(c.get('value')):
                        value = _to_int(c.get('value'))
                        _logger.info(
                            "[PRUEBA SNMP FOUND] prueba=%s campo=%s valor=%s | alias=%s | origen=%s | key=%s | meta=%s",
                            self.id,
                            field_label,
                            value,
                            alias,
                            c.get('origin'),
                            c.get('key'),
                            c.get('meta'),
                        )
                        return value

            # 2) contiene alias, solo para raw/humano.
            for alias in contains_norm:
                for c in candidates:
                    norm = c.get('norm') or ''
                    if alias and alias in norm and _valid(c.get('value')):
                        value = _to_int(c.get('value'))
                        _logger.info(
                            "[PRUEBA SNMP FOUND CONTAINS] prueba=%s campo=%s valor=%s | alias=%s | origen=%s | key=%s | meta=%s",
                            self.id,
                            field_label,
                            value,
                            alias,
                            c.get('origin'),
                            c.get('key'),
                            c.get('meta'),
                        )
                        return value

            _logger.warning(
                "[PRUEBA SNMP MISSING] prueba=%s campo=%s sin valor | aliases=%s | contains=%s | available_norm_keys=%s",
                self.id,
                field_label,
                aliases,
                contains_aliases or [],
                sorted(list(set([c.get('norm') for c in candidates if c.get('norm')]))),
            )
            return 0

        def _find_toner(field_label, aliases):
            sources = []

            for key, value in toner.items():
                sources.append(('arg.toner', key, _norm_key(key), value))

            for key, value in payload_toner.items():
                sources.append(('payload.toner', key, _norm_key(key), value))

            # Algunos agentes mandan toner_black como top-level.
            for key, value in payload.items():
                if isinstance(value, (dict, list)):
                    continue
                sources.append(('payload.top', key, _norm_key(key), value))

            aliases_norm = [_norm_key(a) for a in aliases]
            for alias in aliases_norm:
                for origin, key, norm, value in sources:
                    if norm == alias and _valid(value):
                        result = _to_float_or_false(value)
                        _logger.info(
                            "[PRUEBA SNMP TONER FOUND] prueba=%s campo=%s valor=%s | alias=%s | origen=%s | key=%s",
                            self.id,
                            field_label,
                            result,
                            alias,
                            origin,
                            key,
                        )
                        return result

            _logger.warning(
                "[PRUEBA SNMP TONER MISSING] prueba=%s campo=%s sin valor | aliases=%s | toner_keys=%s | payload_toner_keys=%s",
                self.id,
                field_label,
                aliases,
                sorted(list(toner.keys())),
                sorted(list(payload_toner.keys())),
            )
            return False

        total = _find_number(
            'contador_actual_total',
            ['total', 'total_counter', 'page_count', 'meter_total', 'counter_total'],
            ['total page', 'page count', 'total counter', 'meter total'],
        )

        copies = _find_number(
            'contador_copias',
            ['copy', 'copy_total', 'copies', 'copy_counter', 'copias', 'contador_copias'],
            ['copy', 'copies', 'copias'],
        )

        prints = _find_number(
            'contador_impresiones',
            ['print', 'print_total', 'prints', 'print_counter', 'impresiones', 'contador_impresiones'],
            ['print', 'prints', 'impresion', 'impresiones'],
        )

        scans = _find_number(
            'contador_scanner',
            ['scan', 'scanner', 'scans', 'scan_counter', 'contador_scanner', 'contador_scan'],
            ['scan', 'scanner'],
        )

        duplex = _find_number(
            'contador_duplex',
            ['duplex', 'duplex_total', 'two_sided', 'two_sided_total', 'duplex_counter', 'contador_duplex'],
            ['duplex', 'two sided', 'two_sided', '2 sided', 'doble cara'],
        )

        bw = _find_number(
            'contador_actual_bn',
            ['bw', 'bw_total', 'bn', 'black_white', 'mono', 'mono_total', 'bw_counter', 'contador_bn'],
            ['black white', 'black_white', 'mono', 'b_w', 'bn', 'b/n'],
        )

        color = _find_number(
            'contador_actual_color',
            ['color', 'color_total', 'full_color', 'color_counter', 'contador_color'],
            ['full color', 'full_color', 'color'],
        )

        copy_bw = _find_number(
            'contador_actual_copias_bn',
            ['copy_bw', 'copies_bw', 'copy_black', 'copies_black', 'copy_bn', 'copias_bn'],
            ['copy black', 'copies black', 'copy bw', 'copy b_w', 'copias bn', 'copias b/n'],
        )

        print_bw = _find_number(
            'contador_actual_impresiones_bn',
            ['print_bw', 'prints_bw', 'print_black', 'prints_black', 'print_bn', 'impresiones_bn'],
            ['print black', 'prints black', 'print bw', 'print b_w', 'impresiones bn', 'impresiones b/n'],
        )

        copy_color = _find_number(
            'contador_actual_copias_color',
            ['copy_color', 'copies_color', 'copias_color'],
            ['copy color', 'copies color', 'copias color'],
        )

        print_color = _find_number(
            'contador_actual_impresiones_color',
            ['print_color', 'prints_color', 'print_full_color', 'prints_full_color', 'impresiones_color'],
            ['print color', 'prints color', 'print full color', 'impresiones color'],
        )

        fax = _find_number(
            'contador_fax',
            ['fax', 'fax_total', 'fax_counter', 'contador_fax'],
            ['fax'],
        )

        gran_total = _find_number(
            'contador_gran_total',
            ['grand_total', 'gran_total', 'grand_total_counter', 'total_general'],
            ['grand total', 'gran total'],
        )

        toner_black = _find_toner(
            'toner_negro',
            ['black', 'k', 'negro', 'toner_black', 'toner_negro'],
        )
        toner_cyan = _find_toner(
            'toner_cyan',
            ['cyan', 'c', 'toner_cyan'],
        )
        toner_magenta = _find_toner(
            'toner_magenta',
            ['magenta', 'm', 'toner_magenta'],
        )
        toner_yellow = _find_toner(
            'toner_amarillo',
            ['yellow', 'y', 'amarillo', 'toner_yellow', 'toner_amarillo'],
        )

        vals = {
            'fecha_ultima_actualizacion': now,
            'origen': 'snmp',

            'snmp_ip': _to_text(payload.get('ip')),
            'snmp_serie': _to_text(payload.get('serial')),
            'snmp_marca': _to_text(payload.get('brand')),
            'snmp_modelo': _to_text(payload.get('model') or payload.get('model_raw')),
            'snmp_enterprise_id': _to_text(payload.get('enterprise_id')),
            'snmp_config': _to_text(payload.get('snmp_config')),
            'snmp_summary_file': _to_text(payload.get('summary_file')),

            'raw_payload_json': _json_dumps(payload),
            'raw_summary_text': _to_text(payload.get('summary_text')),

            'contador_actual_total': total,
            'contador_actual_bn': bw,
            'contador_actual_color': color,
            'contador_impresiones': prints,
            'contador_copias': copies,
            'contador_scanner': scans,
            'contador_duplex': duplex,

            'contador_actual_copias_bn': copy_bw,
            'contador_actual_impresiones_bn': print_bw,
            'contador_actual_copias_color': copy_color,
            'contador_actual_impresiones_color': print_color,

            'contador_fax': fax,
            'contador_gran_total': gran_total,
        }

        if toner_black is not False:
            vals['toner_negro'] = toner_black
        if toner_cyan is not False:
            vals['toner_cyan'] = toner_cyan
        if toner_magenta is not False:
            vals['toner_magenta'] = toner_magenta
        if toner_yellow is not False:
            vals['toner_amarillo'] = toner_yellow

        _logger.info(
            "[PRUEBA SNMP VALS FINAL] prueba=%s maquina=%s | vals=%s",
            self.id,
            self.maquina_id.id,
            vals,
        )

        faltantes = [
            k for k in [
                'contador_actual_total',
                'contador_actual_bn',
                'contador_actual_color',
                'contador_impresiones',
                'contador_copias',
                'contador_scanner',
                'contador_duplex',
                'contador_actual_copias_bn',
                'contador_actual_impresiones_bn',
                'contador_actual_copias_color',
                'contador_actual_impresiones_color',
            ]
            if not vals.get(k)
        ]

        if faltantes:
            _logger.warning(
                "[PRUEBA SNMP VALS CERO] prueba=%s maquina=%s | campos_en_cero=%s | revisar aliases/OID en raw_payload_json y snmp_detalle_ids",
                self.id,
                self.maquina_id.id,
                faltantes,
            )

        return vals
    def _preparar_valores_iniciales_desde_actuales(self, vals_actuales, now):
        """
        Toma snapshot inicial SNMP solo la primera vez.
        """
        vals = {
            'fecha_snapshot_snmp': now,
            'es_snapshot': True,

            'contador_inicial_total': vals_actuales.get('contador_actual_total', 0),
            'contador_inicial_bn': vals_actuales.get('contador_actual_bn', 0),
            'contador_inicial_color': vals_actuales.get('contador_actual_color', 0),
            'contador_inicial_impresiones': vals_actuales.get('contador_impresiones', 0),
            'contador_inicial_copias': vals_actuales.get('contador_copias', 0),
            'contador_inicial_scanner': vals_actuales.get('contador_scanner', 0),
            'contador_inicial_duplex': vals_actuales.get('contador_duplex', 0),

            'contador_inicial_copias_bn': vals_actuales.get('contador_actual_copias_bn', 0),
            'contador_inicial_impresiones_bn': vals_actuales.get('contador_actual_impresiones_bn', 0),
            'contador_inicial_copias_color': vals_actuales.get('contador_actual_copias_color', 0),
            'contador_inicial_impresiones_color': vals_actuales.get('contador_actual_impresiones_color', 0),

            'contador_inicial_fax': vals_actuales.get('contador_fax', 0),
            'contador_inicial_gran_total': vals_actuales.get('contador_gran_total', 0),
        }

        if 'toner_negro' in vals_actuales:
            vals['toner_inicial_negro'] = vals_actuales.get('toner_negro') or 0.0
        if 'toner_cyan' in vals_actuales:
            vals['toner_inicial_cyan'] = vals_actuales.get('toner_cyan') or 0.0
        if 'toner_magenta' in vals_actuales:
            vals['toner_inicial_magenta'] = vals_actuales.get('toner_magenta') or 0.0
        if 'toner_amarillo' in vals_actuales:
            vals['toner_inicial_amarillo'] = vals_actuales.get('toner_amarillo') or 0.0

        return vals

    def _crear_log_snmp(self, counters=None, toner=None, payload=None, now=None):
        self.ensure_one()

        counters = counters or {}
        toner = toner or {}
        payload = payload or {}
        now = now or fields.Datetime.now()

        Log = self.env['sat.prueba.maquina.snmp.log'].sudo()

        vals = {
            'prueba_id': self.id,
            'maquina_id': self.maquina_id.id,
            'reparacion_id': self.reparacion_id.id,
            'fecha': now,

            'ip': _to_text(payload.get('ip')),
            'serie': _to_text(payload.get('serial')),
            'marca': _to_text(payload.get('brand')),
            'modelo': _to_text(payload.get('model')),
            'enterprise_id': _to_text(payload.get('enterprise_id')),
            'snmp_config': _to_text(payload.get('snmp_config')),

            'total': self.contador_actual_total,
            'bn': self.contador_actual_bn,
            'color': self.contador_actual_color,
            'copias': self.contador_copias,
            'impresiones': self.contador_impresiones,
            'scanner': self.contador_scanner,
            'duplex': self.contador_duplex,

            'copias_bn': self.contador_actual_copias_bn,
            'impresiones_bn': self.contador_actual_impresiones_bn,
            'copias_color': self.contador_actual_copias_color,
            'impresiones_color': self.contador_actual_impresiones_color,

            'toner_negro': self.toner_negro,
            'toner_cyan': self.toner_cyan,
            'toner_magenta': self.toner_magenta,
            'toner_amarillo': self.toner_amarillo,

            'alertas_count': 0,
            'payload_json': _json_dumps(payload),
            'counters_json': _json_dumps(counters),
            'toner_json': _json_dumps(toner),
            'summary_text': _to_text(payload.get('summary_text')),
        }

        _logger.info(
            "[PRUEBA SNMP LOG CREATE] prueba=%s maquina=%s | total=%s copias=%s impresiones=%s scanner=%s duplex=%s bn=%s color=%s",
            self.id,
            self.maquina_id.id,
            vals.get('total'),
            vals.get('copias'),
            vals.get('impresiones'),
            vals.get('scanner'),
            vals.get('duplex'),
            vals.get('bn'),
            vals.get('color'),
        )

        log = Log.create(vals)

        _logger.info(
            "[PRUEBA SNMP LOG OK] prueba=%s maquina=%s | log_id=%s",
            self.id,
            self.maquina_id.id,
            log.id,
        )

        return log

    # ======================================================
    # DETALLE SNMP COMPLETO
    # ======================================================
    def _line_key(self, categoria, nombre, oid=None, source_name=None):
        base = "%s|%s|%s|%s" % (
            _to_text(categoria).lower(),
            _to_text(nombre).lower(),
            _to_text(oid).lower(),
            _to_text(source_name).lower(),
        )
        return base[:250]

    def _actualizar_detalle_snmp(self, counters=None, toner=None, payload=None, log=None):
        self.ensure_one()

        payload = payload or {}
        counters = counters or {}
        toner = toner or {}

        items = []

        # 1) Contadores normalizados.
        for key, value in counters.items():
            if key == 'raw':
                continue

            items.append({
                'categoria': 'contador',
                'grupo': 'normalizado',
                'nombre': key,
                'valor': value,
                'unidad': '',
                'oid': '',
                'source_name': 'payload.counters',
                'raw': {
                    'key': key,
                    'value': value,
                },
            })

        # 2) Contadores crudos.
        raw_counters = payload.get('raw_counters') or counters.get('raw') or {}
        if isinstance(raw_counters, dict):
            for name, data in raw_counters.items():
                data = data or {}
                if isinstance(data, dict):
                    value = data.get('value')
                    oid = data.get('oid') or data.get('oid_value')
                    oid_name = data.get('oid_name')
                    source_name = data.get('source_name') or data.get('origen')
                    unidad = data.get('unit') or data.get('unidad') or ''
                else:
                    value = data
                    oid = ''
                    oid_name = ''
                    source_name = ''
                    unidad = ''

                items.append({
                    'categoria': 'contador',
                    'grupo': 'raw',
                    'nombre': name,
                    'valor': value,
                    'unidad': unidad,
                    'oid': oid,
                    'oid_name': oid_name,
                    'source_name': source_name,
                    'raw': data,
                })

        # 3) Tóner normalizado.
        for color_key, value in toner.items():
            items.append({
                'categoria': 'toner',
                'grupo': 'normalizado',
                'nombre': color_key,
                'valor': value,
                'unidad': '%',
                'oid': '',
                'source_name': 'payload.toner',
                'raw': {
                    'key': color_key,
                    'value': value,
                },
            })

        # 4) Consumibles / unidades / accesorios / bandejas / sistema.
        bloques = [
            ('consumible', 'supplies'),
            ('consumible', 'raw_supplies'),
            ('unidad', 'units'),
            ('unidad', 'raw_units'),
            ('accesorio', 'accessories'),
            ('accesorio', 'raw_accessories'),
            ('bandeja', 'trays'),
            ('bandeja', 'raw_trays'),
            ('sistema', 'system'),
            ('sistema', 'raw_system'),
        ]

        for categoria, payload_key in bloques:
            data = payload.get(payload_key)

            if isinstance(data, dict):
                for name, value_data in data.items():
                    if isinstance(value_data, dict):
                        value = (
                            value_data.get('value')
                            if 'value' in value_data
                            else value_data.get('level')
                        )
                        unidad = value_data.get('unit') or value_data.get('unidad') or ''
                        oid = (
                            value_data.get('oid')
                            or value_data.get('oid_value')
                            or value_data.get('oid_level')
                        )
                        oid_name = value_data.get('oid_name')
                        source_name = value_data.get('source_name') or value_data.get('origen') or payload_key
                    else:
                        value = value_data
                        unidad = ''
                        oid = ''
                        oid_name = ''
                        source_name = payload_key

                    items.append({
                        'categoria': categoria,
                        'grupo': payload_key,
                        'nombre': name,
                        'valor': value,
                        'unidad': unidad,
                        'oid': oid,
                        'oid_name': oid_name,
                        'source_name': source_name,
                        'raw': value_data,
                    })

            elif isinstance(data, list):
                for idx, row in enumerate(data, start=1):
                    if isinstance(row, dict):
                        name = row.get('name') or row.get('description') or row.get('descripcion') or str(idx)
                        value = row.get('value') if 'value' in row else row.get('level')
                        unidad = row.get('unit') or row.get('unidad') or ''
                        oid = row.get('oid') or row.get('oid_value') or row.get('oid_level')
                        oid_name = row.get('oid_name')
                        source_name = row.get('source_name') or row.get('origen') or payload_key
                    else:
                        name = str(idx)
                        value = row
                        unidad = ''
                        oid = ''
                        oid_name = ''
                        source_name = payload_key

                    items.append({
                        'categoria': categoria,
                        'grupo': payload_key,
                        'nombre': name,
                        'valor': value,
                        'unidad': unidad,
                        'oid': oid,
                        'oid_name': oid_name,
                        'source_name': source_name,
                        'raw': row,
                    })

        Detalle = self.env['sat.prueba.maquina.snmp.detalle'].sudo()

        _logger.info(
            "[PRUEBA SNMP DETALLE START] prueba=%s maquina=%s | items=%s | counters=%s | toner=%s | raw_counters=%s",
            self.id,
            self.maquina_id.id,
            len(items),
            len(counters or {}),
            len(toner or {}),
            len(raw_counters) if isinstance(raw_counters, dict) else 0,
        )

        detalle_creados = 0
        detalle_actualizados = 0

        for item in items:
            categoria = _to_text(item.get('categoria')) or 'otro'
            nombre = _to_text(item.get('nombre')) or 'Sin nombre'
            oid = _to_text(item.get('oid'))
            source_name = _to_text(item.get('source_name'))

            key = self._line_key(categoria, nombre, oid=oid, source_name=source_name)
            number = _to_float_or_false(item.get('valor'))
            value_text = _to_text(item.get('valor'))

            detalle = Detalle.search([
                ('prueba_id', '=', self.id),
                ('key', '=', key),
            ], limit=1)

            vals = {
                'prueba_id': self.id,
                'maquina_id': self.maquina_id.id,
                'reparacion_id': self.reparacion_id.id,
                'log_id': log.id if log else False,

                'key': key,
                'fecha_ultima_lectura': fields.Datetime.now(),
                'categoria': categoria,
                'grupo': _to_text(item.get('grupo')),
                'nombre': nombre,
                'unidad': _to_text(item.get('unidad')),
                'oid': oid,
                'oid_name': _to_text(item.get('oid_name')),
                'source_name': source_name,

                'valor_actual_texto': value_text,
                'valor_actual_numero': number if number is not False else 0.0,
                'tiene_valor_numerico': number is not False,

                'raw_json': _json_dumps(item.get('raw')),
                'activa': True,
            }

            if detalle:
                detalle.write(vals)
                detalle_actualizados += 1
            else:
                vals.update({
                    'fecha_inicial': fields.Datetime.now(),
                    'valor_inicial_texto': value_text,
                    'valor_inicial_numero': number if number is not False else 0.0,
                })
                Detalle.create(vals)
                detalle_creados += 1

        _logger.info(
            "[PRUEBA SNMP DETALLE OK] prueba=%s maquina=%s | creados=%s | actualizados=%s | total_items=%s",
            self.id,
            self.maquina_id.id,
            detalle_creados,
            detalle_actualizados,
            len(items),
        )

    # ======================================================
    # ALERTAS SNMP
    # ======================================================
    def _actualizar_alertas_snmp(self, payload=None, log=None):
        self.ensure_one()

        payload = payload or {}

        Alert = self.env['sat.prueba.maquina.snmp.alerta'].sudo()

        # Desactivar alertas anteriores; si vuelven a llegar, se reactivan.
        self.snmp_alerta_ids.write({'activa': False})

        raw_alerts = payload.get('alerts')
        if raw_alerts is None:
            raw_alerts = payload.get('raw_alerts')

        alert_items = []

        if isinstance(raw_alerts, list):
            alert_items = raw_alerts

        elif isinstance(raw_alerts, dict):
            for key, value in raw_alerts.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault('key', key)
                    alert_items.append(row)
                else:
                    alert_items.append({
                        'key': key,
                        'description': value,
                    })

        elif isinstance(raw_alerts, str) and raw_alerts.strip():
            alert_items.append({
                'description': raw_alerts.strip(),
            })

        _logger.info(
            "[PRUEBA SNMP ALERTAS START] prueba=%s maquina=%s | alert_items=%s | raw_type=%s",
            self.id,
            self.maquina_id.id,
            len(alert_items),
            type(raw_alerts).__name__,
        )

        # Si no hay alertas, no crear falsa alerta.
        if not alert_items:
            if log:
                log.write({'alertas_count': 0})
            _logger.info(
                "[PRUEBA SNMP ALERTAS OK] prueba=%s maquina=%s | sin_alertas",
                self.id,
                self.maquina_id.id,
            )
            return

        count = 0

        for idx, item in enumerate(alert_items, start=1):
            if not isinstance(item, dict):
                item = {
                    'description': item,
                }

            descripcion = (
                item.get('description')
                or item.get('descripcion')
                or item.get('message')
                or item.get('mensaje')
                or item.get('name')
                or item.get('key')
                or ('Alerta %s' % idx)
            )

            descripcion = _to_text(descripcion)

            if not descripcion:
                continue

            key = self._line_key(
                'alerta',
                descripcion,
                oid=item.get('oid') or item.get('oid_description'),
                source_name=item.get('source_name') or item.get('origen'),
            )

            alerta = Alert.search([
                ('prueba_id', '=', self.id),
                ('key', '=', key),
            ], limit=1)

            vals = {
                'prueba_id': self.id,
                'maquina_id': self.maquina_id.id,
                'reparacion_id': self.reparacion_id.id,
                'log_id': log.id if log else False,

                'key': key,
                'fecha': fields.Datetime.now(),
                'activa': True,

                'descripcion': descripcion,
                'codigo': _to_text(item.get('code') or item.get('codigo')),
                'severidad': _to_text(item.get('severity') or item.get('severidad')),
                'grupo': _to_text(item.get('group') or item.get('grupo')),
                'ubicacion': _to_text(item.get('location') or item.get('ubicacion')),
                'oid': _to_text(item.get('oid') or item.get('oid_description')),
                'source_name': _to_text(item.get('source_name') or item.get('origen')),
                'raw_json': _json_dumps(item),
            }

            if alerta:
                alerta.write(vals)
            else:
                Alert.create(vals)

            count += 1

        if log:
            log.write({'alertas_count': count})

        _logger.info(
            "[PRUEBA SNMP ALERTAS OK] prueba=%s maquina=%s | activas=%s",
            self.id,
            self.maquina_id.id,
            count,
        )


# ==========================================================
# HISTORIAL SNMP POR LECTURA
# ==========================================================

class SatPruebaMaquinaSnmpLog(models.Model):
    _name = 'sat.prueba.maquina.snmp.log'
    _description = 'Historial de lecturas SNMP en prueba técnica'
    _order = 'fecha desc, id desc'

    prueba_id = fields.Many2one(
        'sat.prueba.maquina',
        string='Prueba',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        ondelete='cascade',
        index=True,
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        ondelete='cascade',
        index=True,
    )

    fecha = fields.Datetime(
        string='Fecha lectura',
        default=fields.Datetime.now,
        index=True,
    )

    ip = fields.Char(string='IP')
    serie = fields.Char(string='Serie', index=True)
    marca = fields.Char(string='Marca')
    modelo = fields.Char(string='Modelo')
    enterprise_id = fields.Char(string='Enterprise ID')
    snmp_config = fields.Char(string='SNMP usado')

    total = fields.Integer(string='Total')
    bn = fields.Integer(string='B/N')
    color = fields.Integer(string='Color')
    copias = fields.Integer(string='Copias')
    impresiones = fields.Integer(string='Impresiones')
    scanner = fields.Integer(string='Scanner')
    duplex = fields.Integer(string='Dúplex')

    copias_bn = fields.Integer(string='Copias B/N')
    impresiones_bn = fields.Integer(string='Impresiones B/N')
    copias_color = fields.Integer(string='Copias Color')
    impresiones_color = fields.Integer(string='Impresiones Color')

    toner_negro = fields.Float(string='Tóner Negro')
    toner_cyan = fields.Float(string='Tóner Cyan')
    toner_magenta = fields.Float(string='Tóner Magenta')
    toner_amarillo = fields.Float(string='Tóner Amarillo')

    alertas_count = fields.Integer(string='Alertas')

    payload_json = fields.Text(string='Payload JSON')
    counters_json = fields.Text(string='Counters JSON')
    toner_json = fields.Text(string='Toner JSON')
    summary_text = fields.Text(string='Resumen TXT')

    detalle_ids = fields.One2many(
        'sat.prueba.maquina.snmp.detalle',
        'log_id',
        string='Detalle SNMP',
    )

    alerta_ids = fields.One2many(
        'sat.prueba.maquina.snmp.alerta',
        'log_id',
        string='Alertas SNMP',
    )


# ==========================================================
# DETALLE COMPLETO SNMP POR OID / DATO
# ==========================================================

class SatPruebaMaquinaSnmpDetalle(models.Model):
    _name = 'sat.prueba.maquina.snmp.detalle'
    _description = 'Detalle SNMP completo por prueba'
    _order = 'categoria, grupo, nombre, id'

    prueba_id = fields.Many2one(
        'sat.prueba.maquina',
        string='Prueba',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        ondelete='cascade',
        index=True,
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        ondelete='cascade',
        index=True,
    )

    log_id = fields.Many2one(
        'sat.prueba.maquina.snmp.log',
        string='Lectura SNMP',
        ondelete='set null',
        index=True,
    )

    key = fields.Char(
        string='Clave técnica',
        required=True,
        index=True,
    )

    fecha_inicial = fields.Datetime(
        string='Fecha inicial',
        default=fields.Datetime.now,
    )

    fecha_ultima_lectura = fields.Datetime(
        string='Última lectura',
        default=fields.Datetime.now,
        index=True,
    )

    categoria = fields.Selection([
        ('contador', 'Contador'),
        ('toner', 'Tóner'),
        ('consumible', 'Consumible'),
        ('unidad', 'Unidad'),
        ('accesorio', 'Accesorio'),
        ('bandeja', 'Bandeja'),
        ('alerta', 'Alerta'),
        ('sistema', 'Sistema'),
        ('otro', 'Otro'),
    ], string='Categoría', default='otro', index=True)

    grupo = fields.Char(string='Grupo')
    nombre = fields.Char(string='Nombre', required=True, index=True)

    unidad = fields.Char(string='Unidad')

    oid = fields.Char(string='OID valor', index=True)
    oid_name = fields.Char(string='OID nombre')
    source_name = fields.Char(string='Origen / Nombre SNMP')

    valor_inicial_texto = fields.Char(string='Valor inicial texto')
    valor_actual_texto = fields.Char(string='Valor actual texto')

    valor_inicial_numero = fields.Float(string='Valor inicial número')
    valor_actual_numero = fields.Float(string='Valor actual número')

    delta_numero = fields.Float(
        string='Delta',
        compute='_compute_delta_numero',
        store=True,
    )

    tiene_valor_numerico = fields.Boolean(string='Tiene valor numérico')
    activa = fields.Boolean(string='Activo', default=True)

    raw_json = fields.Text(string='Raw JSON')

    @api.depends('valor_actual_numero', 'valor_inicial_numero')
    def _compute_delta_numero(self):
        for rec in self:
            rec.delta_numero = rec.valor_actual_numero - rec.valor_inicial_numero


# ==========================================================
# ALERTAS SNMP
# ==========================================================

class SatPruebaMaquinaSnmpAlerta(models.Model):
    _name = 'sat.prueba.maquina.snmp.alerta'
    _description = 'Alertas SNMP detectadas durante prueba'
    _order = 'activa desc, fecha desc, id desc'

    prueba_id = fields.Many2one(
        'sat.prueba.maquina',
        string='Prueba',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        ondelete='cascade',
        index=True,
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        ondelete='cascade',
        index=True,
    )

    log_id = fields.Many2one(
        'sat.prueba.maquina.snmp.log',
        string='Lectura SNMP',
        ondelete='set null',
        index=True,
    )

    key = fields.Char(string='Clave técnica', required=True, index=True)
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now, index=True)

    activa = fields.Boolean(string='Activa', default=True, index=True)

    descripcion = fields.Char(string='Descripción', required=True)
    codigo = fields.Char(string='Código')
    severidad = fields.Char(string='Severidad')
    grupo = fields.Char(string='Grupo')
    ubicacion = fields.Char(string='Ubicación')

    oid = fields.Char(string='OID')
    source_name = fields.Char(string='Origen')

    raw_json = fields.Text(string='Raw JSON')
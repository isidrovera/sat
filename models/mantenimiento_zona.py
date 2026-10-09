# -*- coding: utf-8 -*-
import logging
import re
import unicodedata

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


def _normalizar_ubicacion(valor):
    """Normaliza nombres para comparar distritos y alias sin falsos parciales."""
    if not valor:
        return ''
    texto = unicodedata.normalize('NFKD', str(valor))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'[^a-z0-9]+', ' ', texto.casefold()).strip()
    return re.sub(r'\s+', ' ', texto)


class MantenimientoZona(models.Model):
    _name = 'mantenimiento.zona'
    _description = 'Zona operativa de mantenimiento'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Zona', required=True, tracking=True,
        help='Nombre de la zona operativa. Ej: Lima Norte, Lima Centro, Callao.'
    )
    sequence = fields.Integer(
        string='Secuencia', default=10,
        help='Orden de visualización de la zona.'
    )
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    color = fields.Integer(string='Color', default=0)
    descripcion = fields.Text(string='Descripción', help='Notas internas sobre esta zona.')
    distrito_ids = fields.One2many(
        'mantenimiento.zona.distrito', 'zona_id', string='Distritos'
    )
    tecnico_ids = fields.Many2many(
        'res.users', 'mantenimiento_zona_res_users_rel',
        'zona_id', 'user_id', string='Técnicos preferidos', tracking=True,
        help='Técnicos recomendados para atender esta zona.'
    )
    flexible = fields.Boolean(
        string='Zona flexible', default=False, tracking=True,
        help='Si está activo, el planificador puede asignar técnicos de otras zonas cuando no haya disponibilidad.'
    )
    distrito_count = fields.Integer(
        string='Cantidad de distritos', compute='_compute_counts', store=False
    )
    equipo_count = fields.Integer(
        string='Máquinas', compute='_compute_counts', store=False
    )
    tecnico_count = fields.Integer(
        string='Técnicos', compute='_compute_counts', store=False
    )

    @api.model
    def _mapa_distritos(self):
        """Retorna nombre normalizado -> zonas activas; detecta ambigüedades."""
        registros = self.env['mantenimiento.zona.distrito'].search([
            ('active', '=', True), ('zona_id.active', '=', True)
        ])
        mapa = {}
        for registro in registros:
            for nombre in registro._get_nombres_busqueda():
                clave = _normalizar_ubicacion(nombre)
                if clave:
                    mapa.setdefault(clave, set()).add(registro.zona_id.id)
        return mapa

    @api.model
    def _resolver_zona_por_distrito(self, distrito, mapa=None):
        """Retorna zona solamente cuando existe una única coincidencia."""
        clave = _normalizar_ubicacion(distrito)
        if not clave:
            return self.browse()
        ids = (mapa if mapa is not None else self._mapa_distritos()).get(clave, set())
        return self.browse(next(iter(ids))) if len(ids) == 1 else self.browse()

    @api.model
    def _extraer_distrito_de_direccion(self, direccion, mapa=None):
        """Reconoce distrito como palabra/frase completa; nunca usa zona genérica."""
        texto = _normalizar_ubicacion(direccion)
        if not texto:
            return ''
        mapa = mapa if mapa is not None else self._mapa_distritos()
        coincidencias = []
        for nombre, zona_ids in mapa.items():
            # Descartar topónimos genéricos, abreviaciones y nombres ambiguos.
            if nombre in ('lima', 'peru', 'callao provincia') or len(nombre) < 4 or len(zona_ids) != 1:
                continue
            if re.search(r'(?<!\w)' + re.escape(nombre) + r'(?!\w)', texto):
                coincidencias.append(nombre)
        if not coincidencias:
            return ''
        # Si hay nombres solapados, preferir el más específico; si apuntan a
        # distintas zonas no decidir automáticamente.
        coincidencias.sort(key=len, reverse=True)
        principales = [x for x in coincidencias if not any(
            x != y and re.search(r'(?<!\w)' + re.escape(x) + r'(?!\w)', y)
            for y in coincidencias
        )]
        zonas = {next(iter(mapa[x])) for x in principales}
        return principales[0] if len(zonas) == 1 else ''

    @api.depends('distrito_ids', 'distrito_ids.name', 'distrito_ids.alias',
                 'distrito_ids.active', 'tecnico_ids')
    def _compute_counts(self):
        Alquiler = self.env['alquiler']
        for rec in self:
            rec.distrito_count = len(rec.distrito_ids)
            rec.tecnico_count = len(rec.tecnico_ids)
            nombres = []
            for distrito in rec.distrito_ids.filtered('active'):
                nombres.extend(distrito._get_nombres_busqueda())
            rec.equipo_count = Alquiler.search_count([
                ('distrito', 'in', list(set(nombres))),
                ('control_mantenimiento', '=', True),
                ('estado_alquiler_id', '=', 'alquilada'),
            ]) if nombres else 0

    @api.constrains('name')
    def _check_name_unique(self):
        for rec in self:
            if not rec.name:
                continue
            existe = self.search_count([
                ('id', '!=', rec.id), ('name', '=ilike', rec.name.strip()),
            ])
            if existe:
                raise ValidationError(
                    _("Ya existe una zona con el nombre '%s'.") % rec.name
                )

    def action_ver_maquinas(self):
        self.ensure_one()
        nombres = []
        for distrito in self.distrito_ids.filtered('active'):
            nombres.extend(distrito._get_nombres_busqueda())
        domain = [
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ]
        domain.append(('distrito', 'in', list(set(nombres))) if nombres else ('id', '=', 0))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas de %s') % self.name,
            'res_model': 'alquiler', 'view_mode': 'list,form',
            'domain': domain,
            'context': {'default_control_mantenimiento': True},
        }

    def action_ver_distritos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Distritos de %s') % self.name,
            'res_model': 'mantenimiento.zona.distrito',
            'view_mode': 'list,form',
            'domain': [('zona_id', '=', self.id)],
            'context': {'default_zona_id': self.id},
        }

    def action_actualizar_zonas_maquinas(self):
        """Reclasifica las líneas pendientes desde sus equipos sin tocar tickets.

        No hay campo zona_id confirmado en alquiler: la relación de zona se
        guarda en mantenimiento.planificador.linea. Solo se corrige el distrito
        del equipo si está vacío o es genérico y la dirección es inequívoca.
        """
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Solo un administrador puede ejecutar la actualización masiva.'))

        mapa = self._mapa_distritos()
        Alquiler = self.env['alquiler']
        Linea = self.env['mantenimiento.planificador.linea']
        equipos = Alquiler.search([('control_mantenimiento', '=', True),
                                  ('estado_alquiler_id', '=', 'alquilada')])
        revisados = distritos_actualizados = lineas_actualizadas = ambiguos = sin_zona = 0
        for equipo in equipos:
            revisados += 1
            distrito_original = equipo.distrito or ''
            distrito = distrito_original
            clave = _normalizar_ubicacion(distrito)
            if not clave or clave in ('lima', 'peru', 'provincia de lima', 'lima metropolitana'):
                direccion = equipo.direccion_completa if 'direccion_completa' in Alquiler._fields else False
                if not direccion and 'direccion' in Alquiler._fields:
                    direccion = equipo.direccion
                distrito_extraido = self._extraer_distrito_de_direccion(direccion, mapa)
                if distrito_extraido:
                    distrito = distrito_extraido
            ids = mapa.get(_normalizar_ubicacion(distrito), set())
            if len(ids) > 1:
                ambiguos += 1
                _logger.warning('[ZONAS] Distrito ambiguo equipo=%s distrito=%s zonas=%s',
                                equipo.id, distrito, sorted(ids))
                continue
            if not ids:
                sin_zona += 1
                _logger.info('[ZONAS] Sin zona equipo=%s distrito=%s', equipo.id, distrito)
                continue
            if distrito != distrito_original:
                equipo.write({'distrito': distrito})
                distritos_actualizados += 1
            zona_id = next(iter(ids))
            lineas = Linea.search([
                ('equipo_id', '=', equipo.id),
                ('estado', 'in', ['pendiente', 'confirmado', 'sin_cupo', 'reasignar']),
                ('ticket_id', '=', False),
            ])
            for linea in lineas:
                if linea.fecha_programada or linea.tecnico_id:
                    continue
                vals = {}
                if linea.zona_id.id != zona_id:
                    vals['zona_id'] = zona_id
                if linea.distrito != distrito:
                    vals['distrito'] = distrito
                if vals:
                    linea.write(vals)
                    lineas_actualizadas += 1

        resumen = _(
            'Máquinas revisadas: %(total)s. Distritos corregidos: %(distritos)s. '
            'Líneas pendientes actualizadas: %(lineas)s. '
            'Distritos ambiguos: %(ambiguos)s. Sin zona identificable: %(sin_zona)s.'
        ) % {
            'total': revisados, 'distritos': distritos_actualizados,
            'lineas': lineas_actualizadas, 'ambiguos': ambiguos,
            'sin_zona': sin_zona,
        }
        _logger.info('[ZONAS] %s', resumen)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Actualización de zonas finalizada'),
                       'message': resumen, 'type': 'success', 'sticky': True},
        }


class MantenimientoZonaDistrito(models.Model):
    _name = 'mantenimiento.zona.distrito'
    _description = 'Distrito asociado a zona de mantenimiento'
    _order = 'zona_id, name'

    name = fields.Char(
        string='Distrito', required=True, index=True,
        help='Nombre del distrito tal como se usará para relacionarlo con las máquinas.'
    )
    zona_id = fields.Many2one(
        'mantenimiento.zona', string='Zona', required=True,
        ondelete='cascade', index=True
    )
    active = fields.Boolean(string='Activo', default=True)
    alias = fields.Char(
        string='Alias / variaciones',
        help='Variaciones posibles del nombre del distrito separadas por coma. Ej: Surco, Santiago de Surco, Distrito de Santiago de Surco.'
    )
    provincia = fields.Char(string='Provincia', default='Lima')
    departamento = fields.Char(string='Departamento', default='Lima')
    pais = fields.Char(string='País', default='Perú')
    sequence = fields.Integer(string='Secuencia', default=10)
    equipo_count = fields.Integer(
        string='Máquinas', compute='_compute_equipo_count', store=False
    )

    @api.depends('name', 'alias')
    def _compute_equipo_count(self):
        Alquiler = self.env['alquiler']
        for rec in self:
            nombres = rec._get_nombres_busqueda()
            rec.equipo_count = Alquiler.search_count([
                ('distrito', 'in', nombres),
                ('control_mantenimiento', '=', True),
                ('estado_alquiler_id', '=', 'alquilada'),
            ])

    def _get_nombres_busqueda(self):
        self.ensure_one()
        nombres = []
        if self.name and self.name.strip():
            nombres.append(self.name.strip())
        if self.alias:
            for alias in self.alias.split(','):
                if alias.strip():
                    nombres.append(alias.strip())
        return list(dict.fromkeys(nombres))

    @api.constrains('name', 'alias', 'zona_id', 'active')
    def _check_distrito_unique(self):
        # No permitir nombres/alias cruzados entre zonas activas, ni dentro
        # de la misma zona. Validación normalizada, no solo =ilike.
        registros = self.search([('active', '=', True), ('zona_id.active', '=', True)])
        encontrados = {}
        for registro in registros:
            for nombre in registro._get_nombres_busqueda():
                clave = _normalizar_ubicacion(nombre)
                anterior = encontrados.get(clave)
                if clave and anterior and anterior.id != registro.id:
                    raise ValidationError(_(
                        "El distrito o alias '%(distrito)s' se repite en "
                        "'%(zona1)s' y '%(zona2)s'. Revise la configuración."
                    ) % {'distrito': nombre, 'zona1': anterior.zona_id.name,
                         'zona2': registro.zona_id.name})
                if clave:
                    encontrados[clave] = registro

    def action_ver_maquinas(self):
        self.ensure_one()
        nombres = self._get_nombres_busqueda()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas en %s') % self.name,
            'res_model': 'alquiler', 'view_mode': 'list,form',
            'domain': [
                ('distrito', 'in', nombres),
                ('control_mantenimiento', '=', True),
                ('estado_alquiler_id', '=', 'alquilada'),
            ],
        }

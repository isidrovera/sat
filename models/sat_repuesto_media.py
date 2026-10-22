# -*- coding: utf-8 -*-
"""Presentación de compatibilidades y medios, sin modificar los maestros SAT."""
from collections import defaultdict
from markupsafe import Markup, escape
from odoo import api, fields, models


class SatRepuestoCompatibilidadMedia(models.Model):
    _inherit = 'sat.repuesto.compatibilidad'

    foto_principal_url = fields.Char(
        string='Vista previa principal', compute='_compute_foto_principal_url',
        compute_sudo=False,
    )
    modelos_por_marca_html = fields.Html(
        string='Equipos compatibles por marca',
        compute='_compute_modelos_por_marca_html',
        sanitize=False, compute_sudo=False,
    )

    @api.depends('foto_ids', 'foto_ids.principal', 'foto_ids.mime_type',
                 'foto_ids.sharepoint_item_id')
    def _compute_foto_principal_url(self):
        for record in self:
            imagenes = record.foto_ids.filtered(
                lambda f: (f.mime_type or '').lower().startswith('image/')
                and (f.mime_type or '').lower() != 'image/svg+xml'
                and bool(f.sharepoint_item_id)
            )
            principal = imagenes.filtered('principal')[:1] or imagenes[:1]
            record.foto_principal_url = (
                '/sat/repuestos/media/%d?size=medium' % principal.id
                if principal else False
            )

    @api.depends('modelo_maquina_ids', 'modelo_maquina_ids.name',
                 'modelo_maquina_ids.marca_id', 'modelo_maquina_ids.marca_id.name')
    def _compute_modelos_por_marca_html(self):
        """Presenta TODOS los modelos, ordenados por marca, con HTML escapado.

        No limita el número ni construye compatibilidades nuevas.
        """
        for record in self:
            grupos = defaultdict(list)
            for modelo in record.modelo_maquina_ids:
                marca = modelo.marca_id.name or 'Marca no indicada'
                grupos[marca].append(modelo.name or 'Sin nombre')

            if not grupos:
                record.modelos_por_marca_html = Markup(
                    '<div class="text-muted small">Sin modelos compatibles registrados</div>'
                )
                continue

            parts = []
            for marca in sorted(grupos, key=str.casefold):
                parts.append(
                    '<div class="mb-2">'
                    '<div class="d-flex align-items-center gap-2 mb-2">'
                    '<i class="fa fa-print text-primary" aria-hidden="true"></i>'
                    '<strong class="small">%s</strong>'
                    '<span class="text-muted small">(%s)</span>'
                    '</div><div class="d-flex flex-wrap gap-1">'
                    % (escape(marca), len(grupos[marca]))
                )
                for modelo in sorted(grupos[marca], key=str.casefold):
                    parts.append(
                        '<span class="badge rounded-pill border '
                        'bg-primary-subtle text-primary-emphasis ' 
                        'fw-medium py-2 px-2">%s</span>' % escape(modelo)
                    )
                parts.append('</div></div>')
            record.modelos_por_marca_html = Markup(''.join(str(x) for x in parts))


class SatRepuestoFotoMedia(models.Model):
    _inherit = 'sat.repuesto.foto'

    media_url = fields.Char(
        string='Vista previa', compute='_compute_media_url', compute_sudo=False,
    )
    media_tipo = fields.Selection(
        [('imagen', 'Imagen'), ('video', 'Video'), ('otro', 'Documento')],
        string='Tipo de archivo', compute='_compute_media_url', compute_sudo=False,
    )

    @api.depends('mime_type', 'sharepoint_item_id')
    def _compute_media_url(self):
        for record in self:
            mime = (record.mime_type or '').lower()
            record.media_tipo = (
                'imagen' if mime.startswith('image/')
                else 'video' if mime.startswith('video/') else 'otro'
            )
            record.media_url = (
                '/sat/repuestos/media/%d' % record.id
                if record.id and record.sharepoint_item_id else False
            )

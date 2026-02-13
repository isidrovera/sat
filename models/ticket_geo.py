# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TicketAlquilerGeo(models.Model):
    """Herencia de ticket.alquiler para mostrar datos de geolocalización del equipo."""
    _inherit = 'ticket.alquiler'

    # ─── Campos related desde el equipo (alquiler) ────────────────────
    equipo_latitud = fields.Float(
        string='Latitud',
        related='product_alquiler.latitud',
        readonly=True,
        store=True,
    )
    equipo_longitud = fields.Float(
        string='Longitud',
        related='product_alquiler.longitud',
        readonly=True,
        store=True,
    )
    equipo_distrito = fields.Char(
        string='Distrito',
        related='product_alquiler.distrito',
        readonly=True,
        store=True,
    )
    equipo_provincia = fields.Char(
        string='Provincia',
        related='product_alquiler.provincia',
        readonly=True,
        store=True,
    )
    equipo_departamento = fields.Char(
        string='Departamento',
        related='product_alquiler.departamento',
        readonly=True,
        store=True,
    )
    equipo_direccion_completa = fields.Char(
        string='Dirección completa',
        related='product_alquiler.direccion_completa',
        readonly=True,
        store=True,
    )
    equipo_nombre_establecimiento = fields.Char(
        string='Establecimiento',
        related='product_alquiler.nombre_establecimiento',
        readonly=True,
        store=True,
    )
    equipo_direccion_referencia = fields.Char(
        string='Referencia',
        related='product_alquiler.direccion_referencia',
        readonly=True,
        store=True,
    )
    equipo_tiene_coordenadas = fields.Boolean(
        string='Tiene coordenadas',
        related='product_alquiler.tiene_coordenadas',
        readonly=True,
    )

    # ─── URL de Google Maps (computado) ───────────────────────────────
    google_maps_url = fields.Char(
        string='URL Google Maps',
        compute='_compute_google_maps_url',
        store=True,
    )
    google_maps_nav_url = fields.Char(
        string='URL Navegación',
        compute='_compute_google_maps_url',
        store=True,
    )

    @api.depends('equipo_latitud', 'equipo_longitud')
    def _compute_google_maps_url(self):
        for rec in self:
            if rec.equipo_latitud and rec.equipo_longitud:
                rec.google_maps_url = (
                    f"https://www.google.com/maps?q="
                    f"{rec.equipo_latitud},{rec.equipo_longitud}"
                )
                # URL de navegación con directions (abre GPS del celular)
                rec.google_maps_nav_url = (
                    f"https://www.google.com/maps/dir/?api=1"
                    f"&destination={rec.equipo_latitud},{rec.equipo_longitud}"
                    f"&travelmode=driving"
                )
            else:
                rec.google_maps_url = False
                rec.google_maps_nav_url = False

    # ─── Acciones ─────────────────────────────────────────────────────

    def action_abrir_mapa_equipo(self):
        """Abre la ubicación del equipo en Google Maps."""
        self.ensure_one()
        if not self.google_maps_url:
            raise UserError("El equipo no tiene coordenadas registradas.")
        return {
            'type': 'ir.actions.act_url',
            'url': self.google_maps_url,
            'target': 'new',
        }

    def action_navegar_a_equipo(self):
        """Abre navegación GPS hacia la ubicación del equipo.
        En celular abre la app de Google Maps con ruta directa."""
        self.ensure_one()
        if not self.google_maps_nav_url:
            raise UserError("El equipo no tiene coordenadas registradas.")
        return {
            'type': 'ir.actions.act_url',
            'url': self.google_maps_nav_url,
            'target': 'new',
        }

    # ─── Override create_ticket en alquiler para pasar datos geo ──────

    # Nota: El método create_ticket del modelo 'alquiler' ya pasa
    # 'direccion_id_r': self.direccion al crear el ticket.
    # Con los campos related, el ticket hereda automáticamente los datos
    # geo del equipo. No necesitamos override adicional.

    # ─── Helper para incluir ubicación en eventos de calendario ───────

    def crear_evento_calendario(self):
        """Override para incluir URL del mapa en la descripción del evento."""
        self.ensure_one()

        # Si hay coordenadas, enriquecer la dirección del evento
        if self.equipo_tiene_coordenadas and self.google_maps_url:
            _logger.info(
                "[GEO] Enriqueciendo evento calendario ticket %s con URL mapa: %s",
                self.name, self.google_maps_url
            )

        # Llamar al método original
        result = super().crear_evento_calendario()

        # Actualizar el evento con la URL del mapa si existe
        if result and self.calendar_event_id and self.google_maps_url:
            descripcion_actual = self.calendar_event_id.description or ''
            if self.google_maps_url not in descripcion_actual:
                self.calendar_event_id.write({
                    'description': (
                        f"{descripcion_actual}\n\n"
                        f"📍 Ubicación en mapa: {self.google_maps_url}\n"
                        f"🧭 Navegar: {self.google_maps_nav_url}"
                    ),
                    'location': self.equipo_direccion_completa or self.direccion_id_r or 'NA',
                })

        return result
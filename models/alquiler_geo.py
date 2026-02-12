# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class UnidadAlquilerGeo(models.Model):
    """Herencia del modelo alquiler para agregar geolocalización."""
    _inherit = 'alquiler'

    # ─── Dirección desglosada ──────────────────────────────────────────
    direccion_calle = fields.Char(
        string='Calle / Dirección',
        tracking=True,
    )
    direccion_referencia = fields.Char(
        string='Referencia',
        tracking=True,
        help='Ej: Frente al parque, piso 3, etc.',
    )
    nombre_establecimiento = fields.Char(
        string='Nombre del establecimiento',
        tracking=True,
        help='Nombre de la empresa o local (si aplica)',
    )
    distrito = fields.Char(string='Distrito', tracking=True)
    provincia = fields.Char(string='Provincia', tracking=True)
    departamento = fields.Char(string='Departamento', tracking=True)
    codigo_postal = fields.Char(string='Código Postal', tracking=True)
    pais = fields.Char(string='País', default='Perú', tracking=True)

    # ─── Coordenadas ──────────────────────────────────────────────────
    latitud = fields.Float(string='Latitud', digits=(16, 8), tracking=True)
    longitud = fields.Float(string='Longitud', digits=(16, 8), tracking=True)

    # ─── Metadata ─────────────────────────────────────────────────────
    google_place_id = fields.Char(string='Google Place ID')
    ubicacion_manual = fields.Boolean(
        string='Ubicación marcada manualmente',
        default=False,
    )

    # ─── Computados ───────────────────────────────────────────────────
    direccion_completa = fields.Char(
        string='Dirección completa',
        compute='_compute_direccion_completa',
        store=True,
    )
    tiene_coordenadas = fields.Boolean(
        string='Tiene coordenadas',
        compute='_compute_tiene_coordenadas',
        store=True,
    )

    @api.depends('direccion_calle', 'distrito', 'provincia', 'departamento',
                 'nombre_establecimiento')
    def _compute_direccion_completa(self):
        for rec in self:
            partes = [p for p in [
                rec.nombre_establecimiento,
                rec.direccion_calle,
                rec.distrito,
                rec.provincia,
                rec.departamento,
            ] if p]
            rec.direccion_completa = ', '.join(partes) or False

    @api.depends('latitud', 'longitud')
    def _compute_tiene_coordenadas(self):
        for rec in self:
            rec.tiene_coordenadas = bool(rec.latitud and rec.longitud)

    # ─── Helpers privados ─────────────────────────────────────────────

    def _get_google_api_key(self):
        """Obtiene la API Key de Google Maps desde parámetros del sistema."""
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'alquiler_geo.google_maps_api_key', ''
        )
        if not api_key:
            raise UserError(
                "No se ha configurado la API Key de Google Maps.\n"
                "Configurar en: Ajustes → Parámetros del Sistema → "
                "alquiler_geo.google_maps_api_key"
            )
        return api_key

    def _extraer_componentes_direccion(self, address_components):
        """Extrae distrito, provincia, departamento y código postal
        desde los address_components de Google."""
        vals = {}
        for comp in address_components:
            types = comp.get('types', [])
            name = comp.get('long_name', '')
            if 'locality' in types:
                vals['distrito'] = name
            elif 'administrative_area_level_2' in types:
                vals['provincia'] = name
            elif 'administrative_area_level_1' in types:
                vals['departamento'] = name
            elif 'postal_code' in types:
                vals['codigo_postal'] = name
            elif 'country' in types:
                vals['pais'] = name
        return vals

    # ─── Acciones ─────────────────────────────────────────────────────

    def action_abrir_en_google_maps(self):
        """Abre la ubicación en Google Maps en pestaña nueva."""
        self.ensure_one()
        if not self.tiene_coordenadas:
            raise UserError("No hay coordenadas registradas para este equipo.")
        url = f"https://www.google.com/maps?q={self.latitud},{self.longitud}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_geocodificar_direccion(self):
        """Obtiene coordenadas a partir de la dirección escrita."""
        self.ensure_one()
        api_key = self._get_google_api_key()

        direccion = self.direccion_completa or self.direccion
        if not direccion:
            raise UserError("No hay dirección para geocodificar.")

        try:
            resp = requests.get(
                'https://maps.googleapis.com/maps/api/geocode/json',
                params={
                    'address': direccion,
                    'key': api_key,
                    'components': 'country:PE',
                    'language': 'es',
                },
                timeout=10,
            )
            data = resp.json()

            if data.get('status') != 'OK' or not data.get('results'):
                raise UserError(
                    f"No se encontró la dirección.\n"
                    f"Respuesta de Google: {data.get('status')}"
                )

            result = data['results'][0]
            location = result['geometry']['location']
            vals = {
                'latitud': location['lat'],
                'longitud': location['lng'],
                'google_place_id': result.get('place_id', ''),
                'ubicacion_manual': False,
            }
            vals.update(self._extraer_componentes_direccion(
                result.get('address_components', [])
            ))
            self.write(vals)
            self.message_post(
                body="📍 Dirección geocodificada exitosamente.",
                message_type='notification',
            )

        except requests.exceptions.RequestException as e:
            raise UserError(f"Error de conexión con Google: {str(e)}")

    def action_geocodificar_inverso(self):
        """Obtiene la dirección a partir de coordenadas (reverse geocoding)."""
        self.ensure_one()
        if not self.tiene_coordenadas:
            raise UserError("No hay coordenadas para buscar la dirección.")

        api_key = self._get_google_api_key()

        try:
            resp = requests.get(
                'https://maps.googleapis.com/maps/api/geocode/json',
                params={
                    'latlng': f"{self.latitud},{self.longitud}",
                    'key': api_key,
                    'language': 'es',
                },
                timeout=10,
            )
            data = resp.json()

            if data.get('status') != 'OK' or not data.get('results'):
                raise UserError(
                    f"No se encontró dirección para estas coordenadas.\n"
                    f"Respuesta: {data.get('status')}"
                )

            result = data['results'][0]
            vals = {
                'direccion_calle': result.get('formatted_address', ''),
                'google_place_id': result.get('place_id', ''),
                'ubicacion_manual': True,
            }
            vals.update(self._extraer_componentes_direccion(
                result.get('address_components', [])
            ))
            self.write(vals)
            self.message_post(
                body="📍 Dirección obtenida desde coordenadas.",
                message_type='notification',
            )

        except requests.exceptions.RequestException as e:
            raise UserError(f"Error de conexión con Google: {str(e)}")

    # ─── RPC para el widget JS (Places Autocomplete) ──────────────────

    @api.model
    def get_google_maps_api_key(self):
        """Retorna la API Key para uso en el widget JS del frontend.
        Solo usuarios internos pueden obtenerla."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'alquiler_geo.google_maps_api_key', ''
        )

    def action_aplicar_place_data(self, place_data):
        """Recibe los datos del Place seleccionado en el widget JS
        y actualiza los campos del registro.

        El widget usa Places Autocomplete con types=['geocode', 'establishment']
        para que busque TANTO direcciones como nombres de empresas/locales.

        :param place_data: dict con las claves:
            - name: nombre del establecimiento (si es negocio/empresa)
            - formatted_address: dirección formateada
            - lat, lng: coordenadas
            - place_id: Google Place ID
            - address_components: lista de componentes
        """
        self.ensure_one()
        vals = {
            'latitud': place_data.get('lat', 0),
            'longitud': place_data.get('lng', 0),
            'google_place_id': place_data.get('place_id', ''),
            'direccion_calle': place_data.get('formatted_address', ''),
            'ubicacion_manual': False,
        }

        # Si el resultado tiene nombre de establecimiento (es un negocio)
        # Google devuelve el name distinto al formatted_address en esos casos
        place_name = place_data.get('name', '')
        formatted = place_data.get('formatted_address', '')
        if place_name and place_name not in formatted:
            vals['nombre_establecimiento'] = place_name

        # Extraer componentes de dirección
        vals.update(self._extraer_componentes_direccion(
            place_data.get('address_components', [])
        ))

        self.write(vals)
        return True

    def action_aplicar_coordenadas_manuales(self, lat, lng):
        """Aplica coordenadas marcadas manualmente en el mapa
        y ejecuta reverse geocoding para llenar la dirección.

        :param lat: float latitud
        :param lng: float longitud
        """
        self.ensure_one()
        self.write({
            'latitud': lat,
            'longitud': lng,
            'ubicacion_manual': True,
        })
        # Intentar reverse geocoding automático
        try:
            self.action_geocodificar_inverso()
        except UserError as e:
            _logger.warning(
                "Reverse geocoding falló para equipo %s: %s", self.id, str(e)
            )
        return True
/** @odoo-module **/

import { Component, useRef, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Widget GeoMapWidget
 * 
 * Muestra un campo de búsqueda con Google Places Autocomplete
 * (busca por dirección Y por nombre de empresa/establecimiento)
 * + un mapa interactivo de Google Maps donde se puede marcar manualmente.
 *
 * Al seleccionar un resultado o marcar en el mapa, llama al RPC del modelo
 * para actualizar todos los campos de geolocalización.
 *
 * Uso en XML:
 *   <field name="latitud" widget="geo_map_widget"/>
 */
class GeoMapWidget extends Component {
    static template = "alquiler_geo.GeoMapWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.mapContainerRef = useRef("mapContainer");
        this.searchInputRef = useRef("searchInput");

        this.state = useState({
            apiLoaded: false,
            loading: true,
            error: null,
            lat: 0,
            lng: 0,
            direccionCompleta: "",
            nombreEstablecimiento: "",
            tieneCoords: false,
            modoManual: false,
        });

        // Referencias a objetos de Google Maps
        this.map = null;
        this.marker = null;
        this.autocomplete = null;
        this.geocoder = null;

        // Centro por defecto: Lima, Perú
        this.defaultCenter = { lat: -12.0464, lng: -77.0428 };
        this.defaultZoom = 12;
        this.markerZoom = 17;

        onMounted(() => this._onMounted());
        onWillUnmount(() => this._onWillUnmount());
    }

    // ─── Lifecycle ───────────────────────────────────────────────────

    async _onMounted() {
        try {
            // Leer coordenadas actuales del registro
            await this._loadCurrentCoords();

            // Cargar Google Maps API
            const apiKey = await this._getApiKey();
            if (!apiKey) {
                this.state.error = "No se ha configurado la API Key de Google Maps.";
                this.state.loading = false;
                return;
            }
            await this._loadGoogleMapsScript(apiKey);
            this.state.apiLoaded = true;

            // Inicializar mapa y autocomplete
            this._initMap();
            this._initAutocomplete();

            this.state.loading = false;
        } catch (e) {
            console.error("GeoMapWidget error:", e);
            this.state.error = e.message || "Error al cargar el mapa.";
            this.state.loading = false;
        }
    }

    _onWillUnmount() {
        // Limpiar listeners del autocomplete
        if (this.autocomplete) {
            google.maps.event.clearInstanceListeners(this.autocomplete);
        }
        if (this.map) {
            google.maps.event.clearInstanceListeners(this.map);
        }
    }

    // ─── Carga de datos actuales ─────────────────────────────────────

    async _loadCurrentCoords() {
        const record = this.props.record;
        if (!record || !record.data) return;

        const lat = record.data.latitud || 0;
        const lng = record.data.longitud || 0;
        const direccion = record.data.direccion_completa || record.data.direccion || "";
        const nombre = record.data.nombre_establecimiento || "";

        this.state.lat = lat;
        this.state.lng = lng;
        this.state.direccionCompleta = direccion;
        this.state.nombreEstablecimiento = nombre;
        this.state.tieneCoords = !!(lat && lng);
    }

    // ─── Google Maps API Key ─────────────────────────────────────────

    async _getApiKey() {
        try {
            return await this.orm.call("alquiler", "get_google_maps_api_key", []);
        } catch {
            return null;
        }
    }

    // ─── Cargar script de Google Maps ────────────────────────────────

    _loadGoogleMapsScript(apiKey) {
        return new Promise((resolve, reject) => {
            // Si ya está cargado, resolver directo
            if (window.google && window.google.maps && window.google.maps.places) {
                resolve();
                return;
            }

            // Si ya hay un script cargando, esperar
            if (window._geoMapWidgetLoading) {
                window._geoMapWidgetCallbacks = window._geoMapWidgetCallbacks || [];
                window._geoMapWidgetCallbacks.push(resolve);
                return;
            }

            window._geoMapWidgetLoading = true;
            window._geoMapWidgetCallbacks = [];

            // Callback global
            window._geoMapWidgetReady = () => {
                window._geoMapWidgetLoading = false;
                resolve();
                // Resolver callbacks de otras instancias esperando
                (window._geoMapWidgetCallbacks || []).forEach(cb => cb());
                window._geoMapWidgetCallbacks = [];
            };

            const script = document.createElement("script");
            script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&callback=_geoMapWidgetReady`;
            script.async = true;
            script.defer = true;
            script.onerror = () => {
                window._geoMapWidgetLoading = false;
                reject(new Error("No se pudo cargar Google Maps."));
            };
            document.head.appendChild(script);
        });
    }

    // ─── Inicializar mapa ────────────────────────────────────────────

    _initMap() {
        const container = this.mapContainerRef.el;
        if (!container) return;

        const center = this.state.tieneCoords
            ? { lat: this.state.lat, lng: this.state.lng }
            : this.defaultCenter;

        const zoom = this.state.tieneCoords ? this.markerZoom : this.defaultZoom;

        this.map = new google.maps.Map(container, {
            center,
            zoom,
            mapTypeControl: true,
            mapTypeControlOptions: {
                style: google.maps.MapTypeControlStyle.DROPDOWN_MENU,
            },
            streetViewControl: false,
            fullscreenControl: true,
            zoomControl: true,
            styles: [
                {
                    featureType: "poi",
                    stylers: [{ visibility: "simplified" }],
                },
            ],
        });

        this.geocoder = new google.maps.Geocoder();

        // Si ya hay coordenadas, poner marker
        if (this.state.tieneCoords) {
            this._setMarker(center);
        }

        // Click en mapa = marcar manual
        this.map.addListener("click", (e) => {
            if (this.props.readonly) return;
            const pos = { lat: e.latLng.lat(), lng: e.latLng.lng() };
            this._setMarker(pos);
            this.state.modoManual = true;
            this._reverseGeocode(pos);
        });
    }

    // ─── Inicializar Autocomplete ────────────────────────────────────

    _initAutocomplete() {
        const input = this.searchInputRef.el;
        if (!input || this.props.readonly) return;

        this.autocomplete = new google.maps.places.Autocomplete(input, {
            // 'geocode' = direcciones, 'establishment' = negocios/empresas
            types: [],
            componentRestrictions: { country: "pe" },
            fields: [
                "place_id",
                "name",
                "formatted_address",
                "geometry",
                "address_components",
                "types",
            ],
        });

        // Vincular al mapa para sesgar resultados al área visible
        this.autocomplete.bindTo("bounds", this.map);

        this.autocomplete.addListener("place_changed", () => {
            const place = this.autocomplete.getPlace();
            if (!place || !place.geometry) {
                this.notification.add("No se encontró la ubicación seleccionada.", {
                    type: "warning",
                });
                return;
            }
            this._applyPlace(place);
        });
    }

    // ─── Aplicar resultado de Places ─────────────────────────────────

    async _applyPlace(place) {
        const lat = place.geometry.location.lat();
        const lng = place.geometry.location.lng();

        // Actualizar mapa
        const pos = { lat, lng };
        this._setMarker(pos);
        this.map.setCenter(pos);
        this.map.setZoom(this.markerZoom);

        // Actualizar estado local
        this.state.lat = lat;
        this.state.lng = lng;
        this.state.tieneCoords = true;
        this.state.modoManual = false;
        this.state.direccionCompleta = place.formatted_address || "";
        this.state.nombreEstablecimiento = "";

        // Detectar si es establecimiento
        const isEstablishment = (place.types || []).some(t =>
            ["establishment", "point_of_interest", "store", "food", "health"].includes(t)
        );
        if (isEstablishment && place.name && place.name !== place.formatted_address) {
            this.state.nombreEstablecimiento = place.name;
        }

        // Enviar datos al servidor via RPC
        await this._saveToServer({
            name: place.name || "",
            formatted_address: place.formatted_address || "",
            lat,
            lng,
            place_id: place.place_id || "",
            address_components: (place.address_components || []).map(c => ({
                long_name: c.long_name,
                short_name: c.short_name,
                types: c.types,
            })),
        });
    }

    // ─── Reverse Geocode (marcar manual) ─────────────────────────────

    async _reverseGeocode(pos) {
        if (!this.geocoder) return;

        this.state.lat = pos.lat;
        this.state.lng = pos.lng;
        this.state.tieneCoords = true;

        try {
            const response = await this.geocoder.geocode({ location: pos });
            if (response.results && response.results.length > 0) {
                const result = response.results[0];
                this.state.direccionCompleta = result.formatted_address || "";

                // Actualizar input de búsqueda con la dirección encontrada
                const input = this.searchInputRef.el;
                if (input) {
                    input.value = result.formatted_address || "";
                }

                // Guardar en servidor
                await this._saveToServer({
                    name: "",
                    formatted_address: result.formatted_address || "",
                    lat: pos.lat,
                    lng: pos.lng,
                    place_id: result.place_id || "",
                    address_components: (result.address_components || []).map(c => ({
                        long_name: c.long_name,
                        short_name: c.short_name,
                        types: c.types,
                    })),
                });
            } else {
                // Solo guardar coordenadas
                await this._saveCoordsOnly(pos);
            }
        } catch (e) {
            console.warn("Reverse geocode falló:", e);
            await this._saveCoordsOnly(pos);
        }
    }

    // ─── Guardar en servidor ─────────────────────────────────────────

    async _saveToServer(placeData) {
        const resId = this.props.record.resId;
        if (!resId) {
            // Registro nuevo, aún no guardado — actualizar campos en el form
            this._updateFormFields(placeData);
            return;
        }

        try {
            await this.orm.call("alquiler", "action_aplicar_place_data", [[resId], placeData]);
            // Recargar el registro para reflejar cambios
            await this.props.record.load();
            this.notification.add("📍 Ubicación actualizada correctamente.", {
                type: "success",
            });
        } catch (e) {
            console.error("Error guardando ubicación:", e);
            this.notification.add("Error al guardar la ubicación.", {
                type: "danger",
            });
        }
    }

    async _saveCoordsOnly(pos) {
        const resId = this.props.record.resId;
        if (!resId) return;

        try {
            await this.orm.call("alquiler", "action_aplicar_coordenadas_manuales", [
                [resId],
                pos.lat,
                pos.lng,
            ]);
            await this.props.record.load();
            this.notification.add("📍 Coordenadas guardadas.", { type: "success" });
        } catch (e) {
            console.error("Error guardando coordenadas:", e);
            this.notification.add("Error al guardar coordenadas.", { type: "danger" });
        }
    }

    /**
     * Para registros nuevos (sin resId), actualizar directamente los campos del form.
     */
    _updateFormFields(placeData) {
        const record = this.props.record;
        if (!record) return;

        const updates = {
            latitud: placeData.lat || 0,
            longitud: placeData.lng || 0,
            google_place_id: placeData.place_id || "",
            direccion_calle: placeData.formatted_address || "",
            ubicacion_manual: false,
        };

        // Nombre de establecimiento
        if (placeData.name && placeData.name !== placeData.formatted_address) {
            updates.nombre_establecimiento = placeData.name;
        }

        // Extraer componentes
        for (const comp of placeData.address_components || []) {
            const types = comp.types || [];
            if (types.includes("locality")) {
                updates.distrito = comp.long_name;
            } else if (types.includes("administrative_area_level_2")) {
                updates.provincia = comp.long_name;
            } else if (types.includes("administrative_area_level_1")) {
                updates.departamento = comp.long_name;
            } else if (types.includes("postal_code")) {
                updates.codigo_postal = comp.long_name;
            }
        }

        // Aplicar cada campo que exista en el modelo
        for (const [field, value] of Object.entries(updates)) {
            try {
                if (record.fields[field]) {
                    record.update({ [field]: value });
                }
            } catch (e) {
                // Campo no disponible en la vista, ignorar
            }
        }
    }

    // ─── Marker helpers ──────────────────────────────────────────────

    _setMarker(pos) {
        if (this.marker) {
            this.marker.setPosition(pos);
        } else {
            this.marker = new google.maps.Marker({
                position: pos,
                map: this.map,
                draggable: !this.props.readonly,
                animation: google.maps.Animation.DROP,
                title: "Ubicación del equipo",
            });

            // Arrastrar marker = nueva ubicación
            if (!this.props.readonly) {
                this.marker.addListener("dragend", (e) => {
                    const newPos = { lat: e.latLng.lat(), lng: e.latLng.lng() };
                    this.state.modoManual = true;
                    this._reverseGeocode(newPos);
                });
            }
        }
        this.map.panTo(pos);
    }

    // ─── Acciones del template ───────────────────────────────────────

    onClickOpenGoogleMaps() {
        if (!this.state.tieneCoords) return;
        const url = `https://www.google.com/maps?q=${this.state.lat},${this.state.lng}`;
        window.open(url, "_blank");
    }

    onClickCenterMap() {
        if (this.state.tieneCoords && this.map) {
            const pos = { lat: this.state.lat, lng: this.state.lng };
            this.map.setCenter(pos);
            this.map.setZoom(this.markerZoom);
        }
    }

    onClickClearLocation() {
        if (this.props.readonly) return;
        if (this.marker) {
            this.marker.setMap(null);
            this.marker = null;
        }
        this.state.lat = 0;
        this.state.lng = 0;
        this.state.tieneCoords = false;
        this.state.direccionCompleta = "";
        this.state.nombreEstablecimiento = "";
        this.state.modoManual = false;

        const input = this.searchInputRef.el;
        if (input) input.value = "";

        if (this.map) {
            this.map.setCenter(this.defaultCenter);
            this.map.setZoom(this.defaultZoom);
        }

        // Limpiar campos en el registro
        const record = this.props.record;
        if (record) {
            const fieldsToReset = [
                "latitud", "longitud", "distrito", "provincia",
                "departamento", "codigo_postal", "direccion_calle",
                "nombre_establecimiento", "google_place_id",
            ];
            for (const field of fieldsToReset) {
                try {
                    if (record.fields[field]) {
                        const def = record.fields[field].type === "float" ? 0
                            : record.fields[field].type === "boolean" ? false
                            : "";
                        record.update({ [field]: def });
                    }
                } catch (e) { /* ignorar */ }
            }
        }
    }
}

// Template y registro
GeoMapWidget.template = "alquiler_geo.GeoMapWidget";

registry.category("fields").add("geo_map_widget", {
    component: GeoMapWidget,
    supportedTypes: ["float"],
    extractProps: ({ attrs }) => ({
        readonly: attrs.readonly === "1",
    }),
});
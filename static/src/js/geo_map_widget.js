/** @odoo-module **/

import { Component, useRef, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class GeoMapWidget extends Component {
    static template = "alquiler_geo.GeoMapWidget";
    static props = { ...standardFieldProps };

    setup() {
        console.log("🗺️ [GeoMapWidget] setup() iniciado");
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

        this.map = null;
        this.marker = null;
        this.autocomplete = null;
        this.geocoder = null;

        this.defaultCenter = { lat: -12.0464, lng: -77.0428 };
        this.defaultZoom = 12;
        this.markerZoom = 17;

        onMounted(() => this._onMounted());
        onWillUnmount(() => this._onWillUnmount());
    }

    // ─── Lifecycle ───────────────────────────────────────────────────

    async _onMounted() {
        console.log("🗺️ [GeoMapWidget] _onMounted() iniciado");
        try {
            // Paso 1: Leer coordenadas
            console.log("🗺️ [Paso 1] Cargando coordenadas actuales...");
            await this._loadCurrentCoords();
            console.log("🗺️ [Paso 1] Coordenadas:", {
                lat: this.state.lat,
                lng: this.state.lng,
                tieneCoords: this.state.tieneCoords,
            });

            // Paso 2: Obtener API Key
            console.log("🗺️ [Paso 2] Obteniendo API Key...");
            const apiKey = await this._getApiKey();
            console.log("🗺️ [Paso 2] API Key obtenida:", apiKey ? `${apiKey.substring(0, 8)}...` : "NULL/VACÍA");
            if (!apiKey) {
                this.state.error = "No se ha configurado la API Key de Google Maps.";
                this.state.loading = false;
                console.error("🗺️ [Paso 2] ❌ Sin API Key, abortando.");
                return;
            }

            // Paso 3: Cargar script
            console.log("🗺️ [Paso 3] Cargando script de Google Maps...");
            console.log("🗺️ [Paso 3] google.maps ya existe?", !!(window.google && window.google.maps));
            await this._loadGoogleMapsScript(apiKey);
            console.log("🗺️ [Paso 3] ✅ Script cargado. google.maps:", !!window.google?.maps);
            console.log("🗺️ [Paso 3] google.maps.places:", !!window.google?.maps?.places);
            this.state.apiLoaded = true;

            // Paso 4: Inicializar mapa
            console.log("🗺️ [Paso 4] Inicializando mapa...");
            console.log("🗺️ [Paso 4] mapContainerRef.el:", this.mapContainerRef.el);
            console.log("🗺️ [Paso 4] Dimensiones container:", {
                width: this.mapContainerRef.el?.offsetWidth,
                height: this.mapContainerRef.el?.offsetHeight,
            });
            this._initMap();
            console.log("🗺️ [Paso 4] Mapa creado:", !!this.map);

            // Paso 5: Inicializar autocomplete
            console.log("🗺️ [Paso 5] Inicializando autocomplete...");
            console.log("🗺️ [Paso 5] searchInputRef.el:", this.searchInputRef.el);
            console.log("🗺️ [Paso 5] props.readonly:", this.props.readonly);
            this._initAutocomplete();
            console.log("🗺️ [Paso 5] Autocomplete creado:", !!this.autocomplete);

            this.state.loading = false;
            console.log("🗺️ ✅ Widget inicializado correctamente");
        } catch (e) {
            console.error("🗺️ ❌ Error en _onMounted:", e);
            console.error("🗺️ Stack:", e.stack);
            this.state.error = e.message || "Error al cargar el mapa.";
            this.state.loading = false;
        }
    }

    _onWillUnmount() {
        console.log("🗺️ [GeoMapWidget] _onWillUnmount()");
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
        console.log("🗺️ [loadCoords] record:", !!record);
        console.log("🗺️ [loadCoords] record.data:", record?.data);
        if (!record || !record.data) return;

        const lat = record.data.latitud || 0;
        const lng = record.data.longitud || 0;
        const direccion = record.data.direccion_completa || record.data.direccion || "";
        const nombre = record.data.nombre_establecimiento || "";

        console.log("🗺️ [loadCoords] Datos leídos:", { lat, lng, direccion, nombre });

        this.state.lat = lat;
        this.state.lng = lng;
        this.state.direccionCompleta = direccion;
        this.state.nombreEstablecimiento = nombre;
        this.state.tieneCoords = !!(lat && lng);
    }

    // ─── Google Maps API Key ─────────────────────────────────────────

    async _getApiKey() {
        try {
            console.log("🗺️ [getApiKey] Llamando RPC alquiler.get_google_maps_api_key...");
            const key = await this.orm.call("alquiler", "get_google_maps_api_key", []);
            console.log("🗺️ [getApiKey] Respuesta RPC:", key ? `"${key.substring(0, 8)}..." (len=${key.length})` : key);
            return key;
        } catch (e) {
            console.error("🗺️ [getApiKey] ❌ Error RPC:", e);
            return null;
        }
    }

    // ─── Cargar script de Google Maps ────────────────────────────────

    _loadGoogleMapsScript(apiKey) {
        return new Promise((resolve, reject) => {
            if (window.google && window.google.maps && window.google.maps.places) {
                console.log("🗺️ [loadScript] Ya cargado, resolviendo directo");
                resolve();
                return;
            }

            if (window._geoMapWidgetLoading) {
                console.log("🗺️ [loadScript] Otro widget ya está cargando, esperando...");
                window._geoMapWidgetCallbacks = window._geoMapWidgetCallbacks || [];
                window._geoMapWidgetCallbacks.push(resolve);
                return;
            }

            window._geoMapWidgetLoading = true;
            window._geoMapWidgetCallbacks = [];

            window._geoMapWidgetReady = () => {
                console.log("🗺️ [loadScript] ✅ Callback _geoMapWidgetReady ejecutado");
                window._geoMapWidgetLoading = false;
                resolve();
                (window._geoMapWidgetCallbacks || []).forEach(cb => cb());
                window._geoMapWidgetCallbacks = [];
            };

            const scriptUrl = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&callback=_geoMapWidgetReady`;
            console.log("🗺️ [loadScript] Cargando script:", scriptUrl.replace(apiKey, "***"));

            const script = document.createElement("script");
            script.src = scriptUrl;
            script.async = true;
            script.defer = true;
            script.onerror = (e) => {
                console.error("🗺️ [loadScript] ❌ Error cargando script:", e);
                window._geoMapWidgetLoading = false;
                reject(new Error("No se pudo cargar Google Maps."));
            };
            document.head.appendChild(script);
        });
    }

    // ─── Inicializar mapa ────────────────────────────────────────────

    _initMap() {
        const container = this.mapContainerRef.el;
        if (!container) {
            console.error("🗺️ [initMap] ❌ Container no encontrado!");
            return;
        }

        console.log("🗺️ [initMap] Container OK, dimensiones:", container.offsetWidth, "x", container.offsetHeight);

        const center = this.state.tieneCoords
            ? { lat: this.state.lat, lng: this.state.lng }
            : this.defaultCenter;

        const zoom = this.state.tieneCoords ? this.markerZoom : this.defaultZoom;
        console.log("🗺️ [initMap] Center:", center, "Zoom:", zoom);

        try {
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
            console.log("🗺️ [initMap] ✅ google.maps.Map creado:", !!this.map);
        } catch (e) {
            console.error("🗺️ [initMap] ❌ Error creando mapa:", e);
            return;
        }

        this.geocoder = new google.maps.Geocoder();
        console.log("🗺️ [initMap] Geocoder creado:", !!this.geocoder);

        if (this.state.tieneCoords) {
            console.log("🗺️ [initMap] Colocando marker en coords existentes");
            this._setMarker(center);
        }

        this.map.addListener("click", (e) => {
            console.log("🗺️ [map:click] Click en mapa:", e.latLng.lat(), e.latLng.lng());
            if (this.props.readonly) {
                console.log("🗺️ [map:click] Modo readonly, ignorando");
                return;
            }
            const pos = { lat: e.latLng.lat(), lng: e.latLng.lng() };
            this._setMarker(pos);
            this.state.modoManual = true;
            this._reverseGeocode(pos);
        });
        console.log("🗺️ [initMap] Listener de click registrado");
    }

    // ─── Inicializar Autocomplete ────────────────────────────────────

    _initAutocomplete() {
        const input = this.searchInputRef.el;
        if (!input) {
            console.error("🗺️ [initAutocomplete] ❌ Input no encontrado!");
            return;
        }
        if (this.props.readonly) {
            console.log("🗺️ [initAutocomplete] Modo readonly, no se crea autocomplete");
            return;
        }

        console.log("🗺️ [initAutocomplete] Input encontrado, creando Autocomplete...");
        console.log("🗺️ [initAutocomplete] google.maps.places disponible:", !!google.maps.places);
        console.log("🗺️ [initAutocomplete] google.maps.places.Autocomplete:", !!google.maps.places?.Autocomplete);

        try {
            this.autocomplete = new google.maps.places.Autocomplete(input, {
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
            console.log("🗺️ [initAutocomplete] ✅ Autocomplete creado");

            this.autocomplete.bindTo("bounds", this.map);
            console.log("🗺️ [initAutocomplete] Bounds vinculados al mapa");

            this.autocomplete.addListener("place_changed", () => {
                console.log("🗺️ [autocomplete:place_changed] Lugar seleccionado");
                const place = this.autocomplete.getPlace();
                console.log("🗺️ [autocomplete:place_changed] Place:", place);
                if (!place || !place.geometry) {
                    console.warn("🗺️ [autocomplete:place_changed] ⚠️ Sin geometría");
                    this.notification.add("No se encontró la ubicación seleccionada.", {
                        type: "warning",
                    });
                    return;
                }
                this._applyPlace(place);
            });
            console.log("🗺️ [initAutocomplete] Listener place_changed registrado");
        } catch (e) {
            console.error("🗺️ [initAutocomplete] ❌ Error:", e);
        }
    }

    // ─── Aplicar resultado de Places ─────────────────────────────────

    async _applyPlace(place) {
        console.log("🗺️ [applyPlace] Aplicando lugar:", place.name, place.formatted_address);
        const lat = place.geometry.location.lat();
        const lng = place.geometry.location.lng();

        const pos = { lat, lng };
        this._setMarker(pos);
        this.map.setCenter(pos);
        this.map.setZoom(this.markerZoom);

        this.state.lat = lat;
        this.state.lng = lng;
        this.state.tieneCoords = true;
        this.state.modoManual = false;
        this.state.direccionCompleta = place.formatted_address || "";
        this.state.nombreEstablecimiento = "";

        const isEstablishment = (place.types || []).some(t =>
            ["establishment", "point_of_interest", "store", "food", "health"].includes(t)
        );
        if (isEstablishment && place.name && place.name !== place.formatted_address) {
            this.state.nombreEstablecimiento = place.name;
        }

        const placeData = {
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
        };
        console.log("🗺️ [applyPlace] Guardando en servidor:", placeData);
        await this._saveToServer(placeData);
    }

    // ─── Reverse Geocode ─────────────────────────────────────────────

    async _reverseGeocode(pos) {
        console.log("🗺️ [reverseGeocode] Pos:", pos);
        if (!this.geocoder) {
            console.error("🗺️ [reverseGeocode] ❌ Sin geocoder");
            return;
        }

        this.state.lat = pos.lat;
        this.state.lng = pos.lng;
        this.state.tieneCoords = true;

        try {
            const response = await this.geocoder.geocode({ location: pos });
            console.log("🗺️ [reverseGeocode] Resultados:", response.results?.length);
            if (response.results && response.results.length > 0) {
                const result = response.results[0];
                console.log("🗺️ [reverseGeocode] Dirección:", result.formatted_address);
                this.state.direccionCompleta = result.formatted_address || "";

                const input = this.searchInputRef.el;
                if (input) input.value = result.formatted_address || "";

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
                await this._saveCoordsOnly(pos);
            }
        } catch (e) {
            console.warn("🗺️ [reverseGeocode] ⚠️ Falló:", e);
            await this._saveCoordsOnly(pos);
        }
    }

    // ─── Guardar en servidor ─────────────────────────────────────────

    async _saveToServer(placeData) {
        const resId = this.props.record.resId;
        console.log("🗺️ [saveToServer] resId:", resId);
        if (!resId) {
            console.log("🗺️ [saveToServer] Sin resId, actualizando campos del form");
            this._updateFormFields(placeData);
            return;
        }

        try {
            console.log("🗺️ [saveToServer] Llamando action_aplicar_place_data...");
            await this.orm.call("alquiler", "action_aplicar_place_data", [[resId], placeData]);
            console.log("🗺️ [saveToServer] ✅ Guardado OK, recargando registro...");
            await this.props.record.load();
            this.notification.add("📍 Ubicación actualizada correctamente.", { type: "success" });
        } catch (e) {
            console.error("🗺️ [saveToServer] ❌ Error:", e);
            this.notification.add("Error al guardar la ubicación.", { type: "danger" });
        }
    }

    async _saveCoordsOnly(pos) {
        const resId = this.props.record.resId;
        console.log("🗺️ [saveCoordsOnly] resId:", resId, "pos:", pos);
        if (!resId) return;

        try {
            await this.orm.call("alquiler", "action_aplicar_coordenadas_manuales", [
                [resId], pos.lat, pos.lng,
            ]);
            await this.props.record.load();
            this.notification.add("📍 Coordenadas guardadas.", { type: "success" });
        } catch (e) {
            console.error("🗺️ [saveCoordsOnly] ❌ Error:", e);
            this.notification.add("Error al guardar coordenadas.", { type: "danger" });
        }
    }

    _updateFormFields(placeData) {
        console.log("🗺️ [updateFormFields] placeData:", placeData);
        const record = this.props.record;
        if (!record) return;

        const updates = {
            latitud: placeData.lat || 0,
            longitud: placeData.lng || 0,
            google_place_id: placeData.place_id || "",
            direccion_calle: placeData.formatted_address || "",
            ubicacion_manual: false,
        };

        if (placeData.name && placeData.name !== placeData.formatted_address) {
            updates.nombre_establecimiento = placeData.name;
        }

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

        console.log("🗺️ [updateFormFields] Updates a aplicar:", updates);
        console.log("🗺️ [updateFormFields] Campos disponibles:", Object.keys(record.fields || {}));

        for (const [field, value] of Object.entries(updates)) {
            try {
                if (record.fields[field]) {
                    record.update({ [field]: value });
                    console.log("🗺️ [updateFormFields] ✅ Campo actualizado:", field, "=", value);
                } else {
                    console.log("🗺️ [updateFormFields] ⚠️ Campo no existe en vista:", field);
                }
            } catch (e) {
                console.warn("🗺️ [updateFormFields] ❌ Error en campo", field, ":", e);
            }
        }
    }

    // ─── Marker helpers ──────────────────────────────────────────────

    _setMarker(pos) {
        console.log("🗺️ [setMarker] Pos:", pos, "Marker existe:", !!this.marker);
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

            if (!this.props.readonly) {
                this.marker.addListener("dragend", (e) => {
                    console.log("🗺️ [marker:dragend] Nueva pos:", e.latLng.lat(), e.latLng.lng());
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
        console.log("🗺️ [openGoogleMaps] URL:", url);
        window.open(url, "_blank");
    }

    onClickCenterMap() {
        if (this.state.tieneCoords && this.map) {
            const pos = { lat: this.state.lat, lng: this.state.lng };
            console.log("🗺️ [centerMap] Centrando en:", pos);
            this.map.setCenter(pos);
            this.map.setZoom(this.markerZoom);
        }
    }

    onClickClearLocation() {
        console.log("🗺️ [clearLocation] Limpiando ubicación");
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

GeoMapWidget.template = "alquiler_geo.GeoMapWidget";

registry.category("fields").add("geo_map_widget", {
    component: GeoMapWidget,
    supportedTypes: ["float"],
    extractProps: ({ attrs }) => ({
        readonly: attrs.readonly === "1",
    }),
});
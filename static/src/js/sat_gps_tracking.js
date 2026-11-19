
/**
 * Seguimiento GPS de visitas SAT.
 *
 * Consume exclusivamente la API autorizada de Odoo.
 * No expone credenciales de Traccar.
 */

(function () {
    'use strict';

    const root = document.getElementById('sat_gps_tracking');

    if (!root) {
        return;
    }

    const shell = document.getElementById('sat_gps_map_shell');
    const status = document.getElementById('sat_gps_status');
    const cards = document.getElementById('sat_gps_tecnicos');

    const fitButton = document.getElementById('sat_gps_fit');
    const destinationButton = document.getElementById('sat_gps_destination');
    const fullscreenButton = document.getElementById('sat_gps_fullscreen');

    const sourceUrl = root.dataset.url;
    const tilesUrl = root.dataset.tilesUrl;

    const statusBox = status.closest('.sat-status');

    if (
        !window.maplibregl ||
        !sourceUrl ||
        !tilesUrl
    ) {
        status.textContent =
            'No se pudo iniciar el mapa. Revise la configuración GPS.';

        if (statusBox) {
            statusBox.classList.add('sat-error');
        }

        return;
    }

    // =====================================================
    // MAPA
    // =====================================================

    const map = new maplibregl.Map({
        container: 'sat_gps_map',

        style: {
            version: 8,

            sources: {
                osm: {
                    type: 'raster',
                    tiles: [tilesUrl],
                    tileSize: 256,

                    attribution:
                        '© OpenStreetMap contributors',
                },
            },

            layers: [{
                id: 'osm',
                type: 'raster',
                source: 'osm',
            }],
        },

        center: [-77.0428, -12.0464],
        zoom: 11,
        maxZoom: 19,
        attributionControl: true,
    });

    map.addControl(
        new maplibregl.NavigationControl({
            showCompass: false,
        }),
        'top-right'
    );

    // =====================================================
    // CONFIGURACIÓN
    // =====================================================

    const colors = [
        '#2563eb',
        '#16a34a',
        '#9333ea',
        '#ea580c',
        '#0891b2',
        '#db2777',
    ];

    const markers = new Map();
    const sources = new Set();

    let lastData = null;
    let selectedId = null;

    let didFit = false;
    let stopped = false;
    let pending = false;
    let mapReady = false;

    // =====================================================
    // VALIDACIONES
    // =====================================================

    function valid(point) {
        return (
            Array.isArray(point) &&
            point.length === 2 &&
            point.every(
                value =>
                    typeof value === 'number' &&
                    Number.isFinite(value)
            ) &&
            point[0] >= -180 &&
            point[0] <= 180 &&
            point[1] >= -90 &&
            point[1] <= 90
        );
    }

    function coordinates(tecnico) {
        return {
            loc: valid(tecnico.ultima_posicion)
                ? tecnico.ultima_posicion
                : null,

            path: Array.isArray(tecnico.recorrido)
                ? tecnico.recorrido.filter(valid)
                : [],
        };
    }

    function localTime(value) {
        if (!value) {
            return 'Sin hora GPS';
        }

        const date = new Date(value);

        if (Number.isNaN(date.getTime())) {
            return String(value);
        }

        return date.toLocaleString('es-PE', {
            timeZone: 'America/Lima',
            dateStyle: 'short',
            timeStyle: 'short',
        });
    }

    function setStatus(message, error = false) {
        status.textContent = message;

        if (statusBox) {
            statusBox.classList.toggle(
                'sat-error',
                Boolean(error)
            );
        }
    }

    // =====================================================
    // CÁMARA DEL MAPA
    // =====================================================

    function cameraBounds(points, maxZoom = 15) {
        const good = points.filter(valid);

        if (!good.length) {
            return false;
        }

        if (good.length === 1) {
            map.easeTo({
                center: good[0],
                zoom: Math.min(maxZoom, 15),
                duration: 600,
            });

            return true;
        }

        const bounds = new maplibregl.LngLatBounds(
            good[0],
            good[0]
        );

        good.forEach(point => {
            bounds.extend(point);
        });

        map.fitBounds(bounds, {
            padding: {
                top: 100,
                bottom: 60,
                left: 35,
                right: 35,
            },

            maxZoom: maxZoom,
            duration: 600,
        });

        return true;
    }

    // =====================================================
    // VER TODO EL RECORRIDO
    // =====================================================

    function focusAll() {
        if (!lastData) {
            return;
        }

        const points = [];

        if (valid(lastData.destino)) {
            points.push(lastData.destino);
        }

        (lastData.tecnicos || []).forEach(tecnico => {
            const data = coordinates(tecnico);

            points.push(...data.path);

            if (data.loc) {
                points.push(data.loc);
            }
        });

        cameraBounds(points);
    }

    // =====================================================
    // VISTA INICIAL AUTOMÁTICA
    // =====================================================

    function focusInitial(data) {
        const points = [];

        // Priorizar la ubicación del cliente.
        if (valid(data.destino)) {
            points.push(data.destino);
        }

        // Agregar la posición conocida de cada técnico.
        (data.tecnicos || []).forEach(tecnico => {
            const {loc, path} = coordinates(tecnico);

            if (loc) {
                points.push(loc);
            } else if (path.length) {
                points.push(path[path.length - 1]);
            }
        });

        // Evitar que recorridos largos alejen
        // demasiado el mapa al abrirlo.
        cameraBounds(points, 15);
    }

    // =====================================================
    // MARCADORES PERSONALIZADOS
    // =====================================================

    function makeMarker(type, label, color) {
        const element = document.createElement('div');

        element.className = 'sat-gps-marker';

        const icon = document.createElement('span');

        icon.className = 'sat-gps-marker-icon';
        icon.style.backgroundColor = color;

        if (type === 'company') {
            icon.textContent = '🏢';
        } else {
            icon.textContent = '👨‍🔧';
        }

        icon.setAttribute(
            'aria-hidden',
            'true'
        );

        const name = document.createElement('span');

        name.className = 'sat-gps-marker-name';
        name.textContent = label;

        element.append(
            icon,
            name
        );

        return element;
    }

    // =====================================================
    // SELECCIONAR TÉCNICO
    // =====================================================

    function focusTechnician(id) {
        if (!lastData) {
            return;
        }

        const technician = (
            lastData.tecnicos || []
        ).find(
            tecnico =>
                String(tecnico.id) === String(id)
        );

        if (!technician) {
            return;
        }

        selectedId = String(id);

        const {loc, path} = coordinates(technician);

        const points = loc
            ? [...path, loc]
            : path;

        if (!cameraBounds(points, 16)) {
            setStatus(
                'Todavía no se recibieron coordenadas de este técnico.'
            );
        }

        renderCards(lastData.tecnicos || []);

        updateVisibility();
    }

    // =====================================================
    // MOSTRAR / OCULTAR TÉCNICOS
    // =====================================================

    function updateVisibility() {
        sources.forEach(id => {
            if (!map.getLayer(id)) {
                return;
            }

            const technicianId = id.slice(
                'ruta-'.length
            );

            const visible = (
                !selectedId ||
                selectedId === technicianId
            );

            map.setLayoutProperty(
                id,
                'visibility',
                visible ? 'visible' : 'none'
            );
        });

        markers.forEach((marker, id) => {
            if (id === 'destino') {
                return;
            }

            const visible = (
                !selectedId ||
                selectedId === id
            );

            marker.getElement().style.display = (
                visible ? '' : 'none'
            );
        });
    }

    // =====================================================
    // DIBUJAR RECORRIDO Y TÉCNICO
    // =====================================================

    function drawRoute(tecnico, index) {
        const id = 'ruta-' + tecnico.id;

        const {path, loc} = coordinates(tecnico);

        const color = colors[
            index % colors.length
        ];

        const line = {
            type: 'Feature',

            properties: {},

            geometry: {
                type: 'LineString',
                coordinates: path,
            },
        };

        // Actualizar recorrido existente.
        if (map.getSource(id)) {
            map.getSource(id).setData(line);
        } else if (path.length >= 2) {
            map.addSource(id, {
                type: 'geojson',
                data: line,
            });

            map.addLayer({
                id: id,
                type: 'line',
                source: id,

                paint: {
                    'line-color': color,
                    'line-width': 5,
                    'line-opacity': 0.88,
                },
            });

            sources.add(id);
        }

        const key = String(tecnico.id);

        // -------------------------------------------------
        // MARCADOR DEL TÉCNICO
        // -------------------------------------------------

        if (loc) {
            if (markers.has(key)) {
                markers.get(key).setLngLat(loc);
            } else {
                const marker = new maplibregl.Marker({
                    element: makeMarker(
                        'technician',
                        tecnico.nombre || 'Técnico',
                        color
                    ),

                    anchor: 'bottom',
                })
                    .setLngLat(loc)
                    .setPopup(
                        new maplibregl.Popup().setText(
                            tecnico.nombre || 'Técnico'
                        )
                    )
                    .addTo(map);

                markers.set(
                    key,
                    marker
                );
            }

            const element = markers.get(
                key
            ).getElement();

            const reciente = Boolean(
                tecnico.gps_en_vivo
            );

            // Diferenciar GPS reciente e histórico.
            element.classList.toggle(
                'sat-gps-marker-old',
                !reciente
            );

            const label = element.querySelector(
                '.sat-gps-marker-name'
            );

            if (label) {
                label.textContent = (
                    tecnico.nombre || 'Técnico'
                ) + (
                    reciente
                        ? ''
                        : ' · Última ubicación'
                );
            }

        } else if (markers.has(key)) {
            markers.get(key).remove();

            markers.delete(key);
        }
    }

    // =====================================================
    // TARJETAS DE TÉCNICOS
    // =====================================================

    function renderCards(technicians) {
        cards.replaceChildren();

        technicians.forEach((tecnico, index) => {
            const color = colors[
                index % colors.length
            ];

            const {loc, path} = coordinates(tecnico);

            const card = document.createElement(
                'article'
            );

            card.className = 'sat-tech-card';

            const top = document.createElement(
                'div'
            );

            top.className = 'sat-tech-top';

            const avatar = document.createElement(
                'span'
            );

            avatar.className = 'sat-avatar';
            avatar.style.backgroundColor = color;

            avatar.textContent = (
                tecnico.nombre || 'T'
            ).trim().charAt(0).toUpperCase();

            const info = document.createElement(
                'div'
            );

            const name = document.createElement(
                'div'
            );

            name.className = 'sat-tech-name';
            name.textContent = (
                tecnico.nombre || 'Técnico'
            );

            const state = document.createElement(
                'div'
            );

            state.className = 'sat-tech-state';

            let gpsEstado;

            if (tecnico.gps_en_vivo) {
                gpsEstado = '● GPS reciente';
            } else if (loc) {
                gpsEstado = '◷ Última ubicación conocida';
            } else {
                gpsEstado = '○ Sin GPS disponible';
            }

            state.textContent = (
                gpsEstado +
                ' · ' +
                String(
                    tecnico.estado || 'Sin estado'
                ).replace(/_/g, ' ')
            );

            info.append(
                name,
                state
            );

            top.append(
                avatar,
                info
            );

            const meta = document.createElement(
                'div'
            );

            meta.className = 'sat-tech-meta';

            meta.textContent = (
                'Última señal: ' +
                localTime(tecnico.actualizado) +
                ' · ' +
                path.length +
                ' puntos registrados'
            );

            const action = document.createElement(
                'button'
            );

            action.type = 'button';
            action.className = 'sat-tech-action';

            const selected = (
                selectedId === String(tecnico.id)
            );

            action.textContent = selected
                ? '✓ Técnico seleccionado · Ver recorrido'
                : '⌖ Ubicar y ver recorrido';

            action.disabled = (
                !loc &&
                !path.length
            );

            action.addEventListener(
                'click',
                () => focusTechnician(tecnico.id)
            );

            card.append(
                top,
                meta,
                action
            );

            cards.append(card);
        });
    }

    // =====================================================
    // ACTUALIZAR MAPA
    // =====================================================

    function draw(data) {
        lastData = data;

        // -------------------------------------------------
        // CLIENTE / EMPRESA
        // -------------------------------------------------

        const dest = valid(data.destino)
            ? data.destino
            : null;

        const cliente = (
            data.cliente || 'Cliente'
        );

        if (dest) {
            if (markers.has('destino')) {
                const marker = markers.get(
                    'destino'
                );

                marker.setLngLat(dest);

                const label = marker.getElement()
                    .querySelector(
                        '.sat-gps-marker-name'
                    );

                if (label) {
                    label.textContent = cliente;
                }

            } else {
                const marker = new maplibregl.Marker({
                    element: makeMarker(
                        'company',
                        cliente,
                        '#dc2626'
                    ),

                    anchor: 'bottom',
                })
                    .setLngLat(dest)
                    .setPopup(
                        new maplibregl.Popup()
                            .setText(cliente)
                    )
                    .addTo(map);

                markers.set(
                    'destino',
                    marker
                );
            }
        }

        // -------------------------------------------------
        // TÉCNICOS
        // -------------------------------------------------

        const technicians = Array.isArray(
            data.tecnicos
        )
            ? data.tecnicos
            : [];

        const liveIds = new Set(
            technicians.map(
                tecnico => String(tecnico.id)
            )
        );

        if (
            selectedId &&
            !liveIds.has(selectedId)
        ) {
            selectedId = null;
        }

        technicians.forEach(drawRoute);

        // Retirar rutas que ya no corresponden.
        sources.forEach(id => {
            const tecnicoId = id.slice(
                'ruta-'.length
            );

            if (liveIds.has(tecnicoId)) {
                return;
            }

            if (map.getLayer(id)) {
                map.removeLayer(id);
            }

            if (map.getSource(id)) {
                map.removeSource(id);
            }

            sources.delete(id);
        });

        // Retirar marcadores que ya no corresponden.
        markers.forEach((marker, id) => {
            if (
                id === 'destino' ||
                liveIds.has(id)
            ) {
                return;
            }

            marker.remove();
            markers.delete(id);
        });

        renderCards(technicians);

        updateVisibility();

        destinationButton.disabled = !dest;

        // Primera carga: centrar automáticamente.
        if (!didFit) {
            focusInitial(data);
            didFit = true;
        }

        const message = technicians.length
            ? (
                'Seguimiento actualizado · ' +
                technicians.length +
                ' técnico(s) en esta visita.'
            )
            : (
                'Aún no hay técnicos con ' +
                'seguimiento disponible.'
            );

        setStatus(message);
    }

    // =====================================================
    // CONSULTAR ODOO CADA 15 SEGUNDOS
    // =====================================================

    async function refresh() {
        if (
            stopped ||
            pending
        ) {
            return;
        }

        pending = true;

        try {
            const response = await fetch(
                sourceUrl,
                {
                    credentials: 'same-origin',
                    cache: 'no-store',
                }
            );

            if (!response.ok) {
                if (
                    response.status === 403 ||
                    response.status === 404
                ) {
                    stopped = true;

                    setStatus(
                        'Este enlace ha caducado o ' +
                        'ya no tiene permiso de seguimiento.',
                        true
                    );

                    return;
                }

                throw new Error(
                    'HTTP ' + response.status
                );
            }

            const data = await response.json();

            if (mapReady) {
                draw(data);
            } else {
                lastData = data;
            }

        } catch (error) {
            setStatus(
                'No se pudo actualizar el GPS. ' +
                'Se conserva la última posición disponible.',
                true
            );

        } finally {
            pending = false;
        }
    }

    // =====================================================
    // BOTÓN VER TODO
    // =====================================================

    fitButton.addEventListener(
        'click',
        () => {
            selectedId = null;

            renderCards(
                lastData
                    ? lastData.tecnicos || []
                    : []
            );

            updateVisibility();

            focusAll();
        }
    );

    // =====================================================
    // BOTÓN DESTINO
    // =====================================================

    destinationButton.addEventListener(
        'click',
        () => {
            if (
                lastData &&
                valid(lastData.destino)
            ) {
                cameraBounds(
                    [lastData.destino],
                    16
                );
            }
        }
    );

    // =====================================================
    // PANTALLA COMPLETA
    // =====================================================

    function syncFullscreen() {
        const full = (
            document.fullscreenElement === shell ||
            shell.classList.contains(
                'sat-fullscreen'
            )
        );

        fullscreenButton.textContent = full
            ? '✕ Salir de pantalla completa'
            : '⛶ Pantalla completa';

        fullscreenButton.setAttribute(
            'aria-pressed',
            String(full)
        );

        fullscreenButton.setAttribute(
            'aria-label',
            full
                ? 'Salir de pantalla completa'
                : 'Activar pantalla completa'
        );

        window.setTimeout(
            () => map.resize(),
            80
        );
    }

    fullscreenButton.addEventListener(
        'click',
        async () => {
            try {
                if (
                    document.fullscreenElement === shell
                ) {
                    await document.exitFullscreen();

                } else if (
                    shell.classList.contains(
                        'sat-fullscreen'
                    )
                ) {
                    shell.classList.remove(
                        'sat-fullscreen'
                    );

                    document.body.classList.remove(
                        'sat-map-lock'
                    );

                } else if (
                    shell.requestFullscreen
                ) {
                    await shell.requestFullscreen();

                } else {
                    shell.classList.add(
                        'sat-fullscreen'
                    );

                    document.body.classList.add(
                        'sat-map-lock'
                    );
                }

            } catch (error) {
                shell.classList.toggle(
                    'sat-fullscreen'
                );

                document.body.classList.toggle(
                    'sat-map-lock',
                    shell.classList.contains(
                        'sat-fullscreen'
                    )
                );
            }

            syncFullscreen();
        }
    );

    document.addEventListener(
        'fullscreenchange',
        syncFullscreen
    );

    document.addEventListener(
        'keydown',
        event => {
            if (
                event.key === 'Escape' &&
                shell.classList.contains(
                    'sat-fullscreen'
                )
            ) {
                shell.classList.remove(
                    'sat-fullscreen'
                );

                document.body.classList.remove(
                    'sat-map-lock'
                );

                syncFullscreen();
            }
        }
    );

    // =====================================================
    // REDIMENSIONAMIENTO
    // =====================================================

    if (window.ResizeObserver) {
        new ResizeObserver(
            () => map.resize()
        ).observe(shell);
    }

    // =====================================================
    // INICIO DEL MAPA
    // =====================================================

    map.on('load', () => {
        mapReady = true;

        if (lastData) {
            draw(lastData);
        }
    });

    map.on('error', event => {
        if (
            event &&
            event.error
        ) {
            console.warn(
                '[SAT GPS] Problema al cargar mapa:',
                event.error.message
            );
        }
    });

    destinationButton.disabled = true;

    refresh();

    window.setInterval(
        refresh,
        15000
    );

})();

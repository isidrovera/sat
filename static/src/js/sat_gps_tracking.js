/** Seguimiento público SAT: solo utiliza la API autorizada de Odoo. */
(function () {
    'use strict';
    const root = document.getElementById('sat_gps_tracking');
    if (!root) return;

    const shell = document.getElementById('sat_gps_map_shell');
    const status = document.getElementById('sat_gps_status');
    const statusBox = status.closest('.sat-status');
    const cards = document.getElementById('sat_gps_tecnicos');
    const fitButton = document.getElementById('sat_gps_fit');
    const destinationButton = document.getElementById('sat_gps_destination');
    const fullscreenButton = document.getElementById('sat_gps_fullscreen');
    const sourceUrl = root.dataset.url;
    const tilesUrl = root.dataset.tilesUrl;

    if (!window.maplibregl || !sourceUrl || !tilesUrl) {
        status.textContent = 'No se pudo iniciar el mapa. Revise la configuración GPS.';
        statusBox.classList.add('sat-error');
        return;
    }
    const map = new maplibregl.Map({
        container: 'sat_gps_map',
        style: {
            version: 8,
            sources: {
                osm: {type: 'raster', tiles: [tilesUrl], tileSize: 256,
                    attribution: '© OpenStreetMap contributors'},
            },
            layers: [{id: 'osm', type: 'raster', source: 'osm'}],
        },
        center: [-77.0428, -12.0464],
        zoom: 11,
        maxZoom: 19,
        attributionControl: true,
    });
    map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
    const colors = ['#2563eb', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#db2777'];
    const markers = new Map();
    const sources = new Set();
    let lastData = null;
    let selectedId = null;
    let didFit = false;
    let stopped = false;
    let pending = false;
    let mapReady = false;

    const valid = p => Array.isArray(p) && p.length === 2 &&
        p.every(v => typeof v === 'number' && Number.isFinite(v)) &&
        p[0] >= -180 && p[0] <= 180 && p[1] >= -90 && p[1] <= 90;
    const coordinates = t => ({
        loc: valid(t.ultima_posicion) ? t.ultima_posicion : null,
        path: Array.isArray(t.recorrido) ? t.recorrido.filter(valid) : [],
    });
    function localTime(value) {
        if (!value) return 'Sin señal reciente';
        const date = new Date(value);
        return Number.isNaN(date.getTime())
            ? String(value)
            : date.toLocaleString('es-PE', {timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short'});
    }
    function setStatus(message, error) {
        status.textContent = message;
        statusBox.classList.toggle('sat-error', Boolean(error));
    }
    function cameraBounds(points, maxZoom = 15) {
        const good = points.filter(valid);
        if (!good.length) return false;
        if (good.length === 1) {
            map.easeTo({center: good[0], zoom: Math.min(maxZoom, 15), duration: 600});
            return true;
        }
        const bounds = new maplibregl.LngLatBounds(good[0], good[0]);
        good.forEach(point => bounds.extend(point));
        map.fitBounds(bounds, {padding: {top: 100, bottom: 60, left: 35, right: 35},
            maxZoom, duration: 600});
        return true;
    }
    function focusAll() {
        if (!lastData) return;
        const points = [];
        if (valid(lastData.destino)) points.push(lastData.destino);
        (lastData.tecnicos || []).forEach(t => {
            const data = coordinates(t);
            points.push(...data.path);
            if (data.loc) points.push(data.loc);
        });
        cameraBounds(points);
    }
    function focusTechnician(id) {
        if (!lastData) return;
        const technician = (lastData.tecnicos || []).find(t => String(t.id) === String(id));
        if (!technician) return;
        selectedId = String(id);
        const {loc, path} = coordinates(technician);
        if (!cameraBounds(loc ? [...path, loc] : path, 16)) {
            setStatus('Todavía no se recibieron coordenadas de este técnico.');
        }
        renderCards(lastData.tecnicos || []);
        updateVisibility();
    }
    function updateVisibility() {
        sources.forEach(id => {
            if (!map.getLayer(id)) return;
            const technicianId = id.slice('ruta-'.length);
            map.setLayoutProperty(id, 'visibility',
                !selectedId || selectedId === technicianId ? 'visible' : 'none');
        });
        markers.forEach((marker, id) => {
            if (id === 'destino') return;
            marker.getElement().style.display = !selectedId || selectedId === id ? '' : 'none';
        });
    }
    function drawRoute(t, i) {
        const id = 'ruta-' + t.id;
        const {path, loc} = coordinates(t);
        const line = {type: 'Feature', properties: {},
            geometry: {type: 'LineString', coordinates: path}};
        if (map.getSource(id)) map.getSource(id).setData(line);
        else if (path.length >= 2) {
            map.addSource(id, {type: 'geojson', data: line});
            map.addLayer({id, type: 'line', source: id,
                paint: {'line-color': colors[i % colors.length],
                    'line-width': 5, 'line-opacity': 0.88}});
            sources.add(id);
        }
        const key = String(t.id);
        if (loc) {
            if (markers.has(key)) markers.get(key).setLngLat(loc);
            else {
                const marker = new maplibregl.Marker({color: colors[i % colors.length]})
                    .setLngLat(loc)
                    .setPopup(new maplibregl.Popup().setText(t.nombre || 'Técnico'))
                    .addTo(map);
                markers.set(key, marker);
            }
        } else if (markers.has(key)) {
            markers.get(key).remove();
            markers.delete(key);
        }
    }
    function renderCards(technicians) {
        cards.replaceChildren();
        technicians.forEach((t, i) => {
            const color = colors[i % colors.length];
            const {loc, path} = coordinates(t);
            const card = document.createElement('article');
            card.className = 'sat-tech-card';
            const top = document.createElement('div');
            top.className = 'sat-tech-top';
            const avatar = document.createElement('span');
            avatar.className = 'sat-avatar';
            avatar.style.backgroundColor = color;
            avatar.textContent = (t.nombre || 'T').trim().charAt(0).toUpperCase();
            const info = document.createElement('div');
            const name = document.createElement('div');
            name.className = 'sat-tech-name';
            name.textContent = t.nombre || 'Técnico';
            const state = document.createElement('div');
            state.className = 'sat-tech-state';
            state.textContent = (loc ? '● GPS disponible · ' : '○ Sin GPS reciente · ') +
                String(t.estado || 'Sin estado').replace(/_/g, ' ');
            info.append(name, state);
            top.append(avatar, info);
            const meta = document.createElement('div');
            meta.className = 'sat-tech-meta';
            meta.textContent = 'Última señal: ' + localTime(t.actualizado) +
                ' · ' + path.length + ' puntos registrados';
            const action = document.createElement('button');
            action.type = 'button';
            action.className = 'sat-tech-action';
            const selected = selectedId === String(t.id);
            action.textContent = selected ? '✓ Técnico seleccionado · Ver recorrido' : '⌖ Ubicar y ver recorrido';
            action.disabled = !loc && !path.length;
            action.addEventListener('click', () => focusTechnician(t.id));
            card.append(top, meta, action);
            cards.append(card);
        });
    }
    function draw(data) {
        lastData = data;
        const dest = valid(data.destino) ? data.destino : null;
        if (dest) {
            if (markers.has('destino')) markers.get('destino').setLngLat(dest);
            else markers.set('destino', new maplibregl.Marker({color: '#dc2626'})
                .setLngLat(dest)
                .setPopup(new maplibregl.Popup().setText('Dirección del cliente'))
                .addTo(map));
        }
        const technicians = Array.isArray(data.tecnicos) ? data.tecnicos : [];
        const liveIds = new Set(technicians.map(t => String(t.id)));
        if (selectedId && !liveIds.has(selectedId)) selectedId = null;
        technicians.forEach(drawRoute);
        sources.forEach(id => {
            if (liveIds.has(id.slice('ruta-'.length))) return;
            if (map.getLayer(id)) map.removeLayer(id);
            if (map.getSource(id)) map.removeSource(id);
            sources.delete(id);
        });
        markers.forEach((marker, id) => {
            if (id === 'destino' || liveIds.has(id)) return;
            marker.remove();
            markers.delete(id);
        });
        renderCards(technicians);
        updateVisibility();
        destinationButton.disabled = !dest;
        if (!didFit) {
            focusAll();
            didFit = true;
        }
        setStatus(technicians.length
            ? 'Seguimiento actualizado · ' + technicians.length + ' técnico(s) en esta visita.'
            : 'Aún no hay técnicos en desplazamiento con seguimiento disponible.');
    }
    async function refresh() {
        if (stopped || pending) return;
        pending = true;
        try {
            const response = await fetch(sourceUrl, {credentials: 'same-origin', cache: 'no-store'});
            if (!response.ok) {
                if (response.status === 403 || response.status === 404) {
                    stopped = true;
                    setStatus('Este enlace ha caducado o ya no tiene permiso de seguimiento.', true);
                    return;
                }
                throw new Error('HTTP ' + response.status);
            }
            const data = await response.json();
            if (mapReady) draw(data);
            else lastData = data;
        } catch (error) {
            setStatus('No se pudo actualizar el GPS. Se conserva la última posición disponible.', true);
        } finally {
            pending = false;
        }
    }

    fitButton.addEventListener('click', () => {
        selectedId = null;
        renderCards(lastData ? lastData.tecnicos || [] : []);
        updateVisibility();
        focusAll();
    });
    destinationButton.addEventListener('click', () => {
        if (lastData && valid(lastData.destino))
            cameraBounds([lastData.destino], 16);
    });
    function syncFullscreen() {
        const full = document.fullscreenElement === shell ||
            shell.classList.contains('sat-fullscreen');
        fullscreenButton.textContent = full ? '✕ Salir de pantalla completa' : '⛶ Pantalla completa';
        fullscreenButton.setAttribute('aria-pressed', String(full));
        fullscreenButton.setAttribute('aria-label',
            full ? 'Salir de pantalla completa' : 'Activar pantalla completa');
        window.setTimeout(() => map.resize(), 80);
    }
    fullscreenButton.addEventListener('click', async () => {
        try {
            if (document.fullscreenElement === shell) {
                await document.exitFullscreen();
            } else if (shell.classList.contains('sat-fullscreen')) {
                shell.classList.remove('sat-fullscreen');
                document.body.classList.remove('sat-map-lock');
            } else if (shell.requestFullscreen) {
                await shell.requestFullscreen();
            } else {
                shell.classList.add('sat-fullscreen');
                document.body.classList.add('sat-map-lock');
            }
        } catch (error) {
            shell.classList.toggle('sat-fullscreen');
            document.body.classList.toggle('sat-map-lock',
                shell.classList.contains('sat-fullscreen'));
        }
        syncFullscreen();
    });
    document.addEventListener('fullscreenchange', syncFullscreen);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && shell.classList.contains('sat-fullscreen')) {
            shell.classList.remove('sat-fullscreen');
            document.body.classList.remove('sat-map-lock');
            syncFullscreen();
        }
    });
    if (window.ResizeObserver) new ResizeObserver(() => map.resize()).observe(shell);
    map.on('load', () => {
        mapReady = true;
        if (lastData) draw(lastData);
    });
    map.on('error', event => {
        if (event && event.error) console.warn('[SAT GPS] Problema al cargar mapa:', event.error.message);
    });
    destinationButton.disabled = true;
    refresh();
    window.setInterval(refresh, 15000);
})();

/** Seguimiento GPS de visitas COPIER COMPANY.
 *  No conoce Traccar ni credenciales: consume solo la API protegida de Odoo.
 */
(function () {
    'use strict';
    const root = document.getElementById('sat_gps_tracking');
    if (!root) return;
    const status = document.getElementById('sat_gps_status');
    const cards = document.getElementById('sat_gps_tecnicos');
    const sourceUrl = root.dataset.url;
    const tilesUrl = root.dataset.tilesUrl;
    if (!window.maplibregl) {
        status.textContent = 'No se pudo cargar el motor del mapa.';
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
        center: [-77.0428, -12.0464], zoom: 11,
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    const colors = ['#2563eb', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#db2777'];
    const markers = new Map();
    let fitted = false;
    let stopped = false;

    function valid(p) {
        return Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);
    }
    function localTime(value) {
        if (!value) return 'Sin hora GPS';
        const d = new Date(value);
        return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('es-PE', {timeZone: 'America/Lima'});
    }
    function draw(data) {
        const bounds = new maplibregl.LngLatBounds();
        const dest = valid(data.destino) ? data.destino : null;
        if (dest) bounds.extend(dest);
        if (dest && !markers.has('destino')) {
            markers.set('destino', new maplibregl.Marker({color: '#dc2626'})
                .setLngLat(dest).setPopup(new maplibregl.Popup().setText('Sede del cliente')).addTo(map));
        }
        cards.replaceChildren();
        (data.tecnicos || []).forEach((t, i) => {
            const color = colors[i % colors.length];
            const loc = valid(t.ultima_posicion) ? t.ultima_posicion : null;
            const path = Array.isArray(t.recorrido) ? t.recorrido.filter(valid) : [];
            if (loc) bounds.extend(loc);
            if (path.length) path.forEach(p => bounds.extend(p));
            const id = 'ruta-' + t.id;
            const line = {type: 'Feature', geometry: {type: 'LineString', coordinates: path}, properties: {}};
            if (map.getSource(id)) map.getSource(id).setData(line);
            else if (path.length >= 2) {
                map.addSource(id, {type: 'geojson', data: line});
                map.addLayer({id, type: 'line', source: id,
                    paint: {'line-color': color, 'line-width': 5, 'line-opacity': 0.85}});
            }
            const key = String(t.id);
            if (loc) {
                if (markers.has(key)) markers.get(key).setLngLat(loc);
                else markers.set(key, new maplibregl.Marker({color}).setLngLat(loc)
                    .setPopup(new maplibregl.Popup().setText(t.nombre || 'Técnico')).addTo(map));
            } else if (markers.has(key)) {
                markers.get(key).remove(); markers.delete(key);
            }
            const item = document.createElement('div');
            item.className = 'col-sm-6 col-lg-4';
            const box = document.createElement('div');
            box.className = 'border rounded-3 p-3 h-100';
            const dot = document.createElement('span');
            dot.style.cssText = 'display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px;background:' + color;
            const title = document.createElement('strong'); title.textContent = t.nombre || 'Técnico';
            const state = document.createElement('div'); state.textContent = 'Estado: ' + (t.estado || 'No disponible');
            const time = document.createElement('small'); time.className = 'text-muted';
            time.textContent = 'Última señal: ' + localTime(t.actualizado);
            box.append(dot, title, state, time); item.append(box); cards.append(item);
        });
        if (!fitted && !bounds.isEmpty()) {
            map.fitBounds(bounds, {padding: 55, maxZoom: 15, duration: 0});
            fitted = true;
        }
        status.textContent = (data.tecnicos || []).length
            ? 'Posiciones consultadas: ' + (data.tecnicos || []).length + ' técnico(s).'
            : 'Todavía no hay técnicos en desplazamiento con seguimiento disponible.';
    }
    async function refresh() {
        if (stopped) return;
        try {
            const res = await fetch(sourceUrl, {credentials: 'same-origin', cache: 'no-store'});
            if (!res.ok) {
                if (res.status === 404 || res.status === 403) {
                    stopped = true;
                    status.textContent = 'Este enlace ha caducado o ya no tiene permiso de seguimiento.';
                    return;
                }
                throw new Error('HTTP ' + res.status);
            }
            const data = await res.json();
            if (map.loaded()) draw(data);
            else map.once('load', () => draw(data));
        } catch (err) {
            status.textContent = 'No se pudo actualizar el GPS. Se conserva la última posición disponible.';
        }
    }
    refresh();
    setInterval(refresh, 15000);
})();

(function () {
    'use strict';

    var app = document.getElementById('evidencia-app');

    if (!app) {
        console.warn('[evidencia] No existe #evidencia-app. JS omitido.');
        return;
    }

    var TOKEN = app.dataset.token || '';

    var coords = null;
    var precision = null;
    var momento = 'antes';
    var direccionActual = null;
    var direccionProvider = null;

    var statusEl = document.getElementById('gps-status');
    var btnTomar = document.getElementById('btn-tomar');
    var btnReintentar = document.getElementById('btn-reintentar-gps');
    var inputFoto = document.getElementById('input-foto');
    var btnAntes = document.getElementById('btn-antes');
    var btnDespues = document.getElementById('btn-despues');
    var progressEl = document.getElementById('progress');
    var progressText = document.getElementById('progress-text');
    var toastEl = document.getElementById('toast');
    var galeriaTitulo = document.getElementById('galeria-titulo');
    var gridFotos = document.getElementById('grid-fotos');
    var debugPanel = document.getElementById('debug-panel');
    var previewSection = document.getElementById('preview-section');
    var previewImg = document.getElementById('preview-img');

    function log(msg, tipo) {
        tipo = tipo || 'ok';

        var ts = new Date().toLocaleTimeString('es-PE');
        var line = document.createElement('div');

        line.className = 'log-line log-' + tipo;
        line.textContent = '[' + ts + '] ' + msg;

        if (debugPanel) {
            debugPanel.appendChild(line);
            debugPanel.scrollTop = debugPanel.scrollHeight;
        }

        if (tipo === 'error') {
            console.error('[evidencia]', msg);
        } else if (tipo === 'warn') {
            console.warn('[evidencia]', msg);
        } else {
            console.log('[evidencia]', msg);
        }
    }

    function showToast(msg, tipo) {
        if (!toastEl) {
            return;
        }

        toastEl.textContent = msg;
        toastEl.className = 'toast show ' + (tipo || 'ok');

        setTimeout(function () {
            toastEl.className = 'toast';
        }, 4200);
    }

    function setProgress(texto) {
        if (progressText) {
            progressText.textContent = texto || 'Procesando foto...';
        }
    }

    function showProgress(texto) {
        setProgress(texto);

        if (progressEl) {
            progressEl.classList.add('show');
        }
    }

    function hideProgress() {
        if (progressEl) {
            progressEl.classList.remove('show');
        }
    }

    function validarElementos() {
        var faltantes = [];

        if (!TOKEN) faltantes.push('TOKEN');
        if (!statusEl) faltantes.push('#gps-status');
        if (!btnTomar) faltantes.push('#btn-tomar');
        if (!btnReintentar) faltantes.push('#btn-reintentar-gps');
        if (!inputFoto) faltantes.push('#input-foto');
        if (!btnAntes) faltantes.push('#btn-antes');
        if (!btnDespues) faltantes.push('#btn-despues');
        if (!gridFotos) faltantes.push('#grid-fotos');

        if (faltantes.length) {
            log('Elementos faltantes: ' + faltantes.join(', '), 'error');
            return false;
        }

        return true;
    }

    log('=== Inicializando evidencia pública JS externo ===', 'info');
    log('TOKEN: ' + TOKEN, 'info');
    log('User-Agent: ' + navigator.userAgent.substring(0, 120), 'info');
    log('URL: ' + window.location.href, 'info');
    log('HTTPS / SecureContext: ' + window.isSecureContext, 'info');
    log('En iframe: ' + (window.self !== window.top), 'info');
    log('Geolocation disponible: ' + !!navigator.geolocation, 'info');
    log('FileReader disponible: ' + !!window.FileReader, 'info');
    log('Canvas disponible: ' + !!document.createElement('canvas').getContext, 'info');

    if (!validarElementos()) {
        showToast('Error inicializando la página de evidencia', 'error');
        return;
    }

    function pedirGPS() {
    log('=== Solicitando GPS mejorado ===', 'info');

    coords = null;
    precision = null;
    direccionActual = null;
    direccionProvider = null;

    if (!navigator.geolocation) {
        log('navigator.geolocation no disponible', 'error');
        statusEl.className = 'gps-status error';
        statusEl.textContent = '❌ Tu navegador no soporta GPS. La foto se subirá sin coordenadas.';
        btnReintentar.style.display = 'block';
        return;
    }

    if (!window.isSecureContext) {
        log('Contexto inseguro. HTTPS requerido para GPS.', 'error');
        statusEl.className = 'gps-status error';
        statusEl.textContent = '❌ Se requiere HTTPS para obtener ubicación.';
        btnReintentar.style.display = 'block';
        return;
    }

    var mejorPosicion = null;
    var watchId = null;
    var terminado = false;

    function guardarMejorPosicion(pos, origen) {
        var acc = pos.coords.accuracy || 999999;

        if (!mejorPosicion || acc < mejorPosicion.coords.accuracy) {
            mejorPosicion = pos;

            coords = {
                lat: pos.coords.latitude,
                lng: pos.coords.longitude
            };

            precision = acc;

            log(
                'GPS ' + origen + ' | lat=' + coords.lat +
                ' | lng=' + coords.lng +
                ' | precision=' + precision + 'm',
                precision <= 100 ? 'ok' : 'warn'
            );

            if (precision <= 100) {
                statusEl.className = 'gps-status ok';
                statusEl.textContent = '✅ GPS activo | Precisión: ' + Math.round(precision) + ' m';
            } else {
                statusEl.className = 'gps-status warning';
                statusEl.textContent = '⚠️ GPS aproximado | Precisión: ' + Math.round(precision) + ' m. Esperando mejora...';
            }
        }
    }

    function finalizarGPS(motivo) {
        if (terminado) {
            return;
        }

        terminado = true;

        if (watchId !== null) {
            navigator.geolocation.clearWatch(watchId);
            log('watchPosition detenido | motivo=' + motivo, 'info');
        }

        if (coords) {
            if (precision && precision <= 100) {
                statusEl.className = 'gps-status ok';
                statusEl.textContent = '✅ GPS listo | Precisión: ' + Math.round(precision) + ' m';
            } else {
                statusEl.className = 'gps-status warning';
                statusEl.textContent = '⚠️ GPS aproximado | Precisión: ' + Math.round(precision || 0) + ' m. Puedes tomar foto, pero la ubicación puede variar.';
            }

            btnReintentar.style.display = 'block';
        } else {
            statusEl.className = 'gps-status error';
            statusEl.textContent = '❌ No se pudo obtener ubicación. La foto se subirá sin coordenadas.';
            btnReintentar.style.display = 'block';
        }
    }

    statusEl.className = 'gps-status warning';
    statusEl.textContent = '⏳ Buscando ubicación precisa...';

    navigator.geolocation.getCurrentPosition(
        function (pos) {
            guardarMejorPosicion(pos, 'getCurrentPosition');

            if (pos.coords.accuracy <= 80) {
                finalizarGPS('precision_suficiente_getCurrentPosition');
            }
        },
        function (err) {
            log('GPS getCurrentPosition error | code=' + err.code + ' | message=' + err.message, 'warn');
        },
        {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
        }
    );

    watchId = navigator.geolocation.watchPosition(
        function (pos) {
            guardarMejorPosicion(pos, 'watchPosition');

            if (pos.coords.accuracy <= 80) {
                finalizarGPS('precision_suficiente_watchPosition');
            }
        },
        function (err) {
            log('GPS watchPosition error | code=' + err.code + ' | message=' + err.message, 'error');
            finalizarGPS('error_watchPosition');
        },
        {
            enableHighAccuracy: true,
            timeout: 20000,
            maximumAge: 0
        }
    );

    setTimeout(function () {
        finalizarGPS('timeout_12s');
    }, 12000);
}

    function obtenerDireccionPorGPS() {
        return new Promise(function (resolve) {
            direccionActual = null;
            direccionProvider = null;

            if (!coords) {
                log('No hay coordenadas. No se consultará dirección.', 'warn');
                resolve(null);
                return;
            }

            log(
                'Consultando dirección vía Odoo/Traccar | lat=' + coords.lat + ' | lng=' + coords.lng,
                'info'
            );

            fetch('/evidencia/' + TOKEN + '/geocode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        lat: coords.lat,
                        lng: coords.lng
                    }
                })
            })
                .then(function (r) {
                    log('Respuesta HTTP geocode: ' + r.status, r.ok ? 'ok' : 'error');
                    return r.json();
                })
                .then(function (data) {
                    log('Respuesta geocode JSON: ' + JSON.stringify(data).substring(0, 500), 'info');

                    var result = data.result || {};

                    if (result.success && result.address) {
                        direccionActual = result.address;
                        direccionProvider = result.provider || 'desconocido';

                        log(
                            'Dirección obtenida OK | provider=' + direccionProvider + ' | address=' + direccionActual,
                            'ok'
                        );

                        resolve(direccionActual);
                    } else {
                        log(
                            'No se pudo obtener dirección: ' + (result.error || 'sin detalle'),
                            'warn'
                        );

                        resolve(null);
                    }
                })
                .catch(function (err) {
                    log('Error consultando dirección: ' + err.message, 'warn');
                    resolve(null);
                });
        });
    }

    function setMomento(nuevoMomento) {
        log('Cambio de momento: ' + nuevoMomento, 'info');

        momento = nuevoMomento;

        btnAntes.classList.toggle('active', momento === 'antes');
        btnDespues.classList.toggle('active', momento === 'despues');

        if (galeriaTitulo) {
            galeriaTitulo.textContent = 'Fotos ' + (momento === 'antes' ? 'antes' : 'después');
        }

        var items = gridFotos.querySelectorAll('[data-momento]');

        items.forEach(function (item) {
            item.style.display = item.dataset.momento === momento ? '' : 'none';
        });
    }

    function cargarImagen(src) {
        return new Promise(function (resolve, reject) {
            var img = new Image();

            img.onload = function () {
                log('Imagen cargada | width=' + img.width + ' | height=' + img.height, 'info');
                resolve(img);
            };

            img.onerror = function () {
                reject(new Error('No se pudo cargar la imagen base'));
            };

            img.src = src;
        });
    }

    function cargarImagenExterna(src) {
        return new Promise(function (resolve) {
            var img = new Image();

            img.crossOrigin = 'anonymous';

            img.onload = function () {
                log('Imagen externa cargada correctamente: ' + src.substring(0, 80), 'ok');
                resolve(img);
            };

            img.onerror = function () {
                log('No se pudo cargar imagen externa: ' + src.substring(0, 120), 'warn');
                resolve(null);
            };

            img.src = src;
        });
    }

    function formatearFechaHora() {
        var ahora = new Date();

        var fecha = ahora.toLocaleDateString('es-PE', {
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });

        var hora = ahora.toLocaleTimeString('es-PE', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        return fecha + ' ' + hora;
    }

    function limpiarDireccion(address) {
        if (!address) {
            return '';
        }

        return String(address)
            .replace(/\s+/g, ' ')
            .replace(/,\s*,/g, ',')
            .trim();
    }

    function dividirTextoEnLineas(ctx, texto, maxWidth, maxLines) {
        if (!texto) {
            return [];
        }

        var palabras = texto.split(/\s+/);
        var lineas = [];
        var lineaActual = '';

        for (var i = 0; i < palabras.length; i++) {
            var prueba = lineaActual ? lineaActual + ' ' + palabras[i] : palabras[i];
            var medida = ctx.measureText(prueba).width;

            if (medida <= maxWidth) {
                lineaActual = prueba;
            } else {
                if (lineaActual) {
                    lineas.push(lineaActual);
                }

                lineaActual = palabras[i];

                if (lineas.length >= maxLines) {
                    break;
                }
            }
        }

        if (lineaActual && lineas.length < maxLines) {
            lineas.push(lineaActual);
        }

        return lineas;
    }

    function obtenerTextoUbicacion(ctx, maxWidth) {
        if (!coords) {
            return [
                'Ubicación GPS no disponible',
                'Foto subida sin coordenadas'
            ];
        }

        var lineas = [];

        if (direccionActual) {
            var direccionLimpia = limpiarDireccion(direccionActual);
            var direccionLineas = dividirTextoEnLineas(ctx, direccionLimpia, maxWidth, 3);

            direccionLineas.forEach(function (linea) {
                lineas.push(linea);
            });
        } else {
            lineas.push('Lat: ' + coords.lat.toFixed(6) + ', Lng: ' + coords.lng.toFixed(6));
        }

        lineas.push('Precisión GPS: ' + Math.round(precision || 0) + ' m');

        return lineas;
    }

    function obtenerUrlMapaMini() {
        if (!coords) {
            return null;
        }

        var lat = coords.lat;
        var lng = coords.lng;

        return 'https://staticmap.openstreetmap.de/staticmap.php'
            + '?center=' + encodeURIComponent(lat + ',' + lng)
            + '&zoom=16'
            + '&size=320x220'
            + '&markers=' + encodeURIComponent(lat + ',' + lng + ',red-pushpin');
    }

    function obtenerUrlLogoEmpresa() {
        return '/evidencia/' + TOKEN + '/logo?ts=' + new Date().getTime();
    }

    function dibujarTextoConSombra(ctx, texto, x, y, tamano, align) {
        ctx.font = 'bold ' + tamano + 'px Arial, sans-serif';
        ctx.textAlign = align || 'left';
        ctx.textBaseline = 'top';

        ctx.lineWidth = Math.max(3, Math.floor(tamano / 6));
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.75)';
        ctx.strokeText(texto, x, y);

        ctx.fillStyle = 'white';
        ctx.fillText(texto, x, y);
    }

    function dibujarPanelInferior(ctx, canvas, panelY, panelAlto) {
        var grad = ctx.createLinearGradient(0, panelY, 0, canvas.height);

        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(0.35, 'rgba(0,0,0,0.48)');
        grad.addColorStop(1, 'rgba(0,0,0,0.78)');

        ctx.fillStyle = grad;
        ctx.fillRect(0, panelY, canvas.width, panelAlto);
    }

    function dibujarMiniMapa(ctx, canvas, mapaImg) {
        if (!mapaImg || !coords) {
            log('Mini mapa omitido', 'warn');
            return;
        }

        var margen = Math.round(canvas.width * 0.035);
        var mapaW = Math.round(canvas.width * 0.30);
        var mapaH = Math.round(mapaW * 0.70);
        var mapaX = margen;
        var mapaY = canvas.height - mapaH - margen;

        ctx.fillStyle = 'rgba(255,255,255,0.95)';
        ctx.fillRect(mapaX - 5, mapaY - 5, mapaW + 10, mapaH + 10);

        ctx.drawImage(mapaImg, mapaX, mapaY, mapaW, mapaH);

        ctx.strokeStyle = 'rgba(255,255,255,0.98)';
        ctx.lineWidth = 4;
        ctx.strokeRect(mapaX, mapaY, mapaW, mapaH);

        ctx.beginPath();
        ctx.arc(mapaX + mapaW / 2, mapaY + mapaH / 2, 10, 0, Math.PI * 2);
        ctx.fillStyle = '#e53e3e';
        ctx.fill();

        ctx.beginPath();
        ctx.arc(mapaX + mapaW / 2, mapaY + mapaH / 2, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();

        log('Mini mapa dibujado en canvas', 'ok');
    }

    function dibujarLogoEmpresa(ctx, canvas, logoImg) {
        var margen = Math.round(canvas.width * 0.035);

        if (!logoImg) {
            log('Logo no disponible. Se usará texto como respaldo.', 'warn');

            var fontFallback = Math.max(18, Math.round(canvas.width * 0.026));

            dibujarTextoConSombra(
                ctx,
                'Andes Solution Copiers',
                canvas.width - margen,
                margen,
                fontFallback,
                'right'
            );

            return;
        }

        var maxLogoW = Math.round(canvas.width * 0.30);
        var maxLogoH = Math.round(canvas.height * 0.13);

        var ratio = Math.min(
            maxLogoW / logoImg.width,
            maxLogoH / logoImg.height,
            1
        );

        var logoW = Math.round(logoImg.width * ratio);
        var logoH = Math.round(logoImg.height * ratio);

        var logoX = canvas.width - logoW - margen;
        var logoY = margen;

        ctx.fillStyle = 'rgba(255, 255, 255, 0.88)';
        ctx.fillRect(
            logoX - 10,
            logoY - 10,
            logoW + 20,
            logoH + 20
        );

        ctx.drawImage(logoImg, logoX, logoY, logoW, logoH);

        log(
            'Logo dibujado en canvas | width=' + logoW + ' | height=' + logoH,
            'ok'
        );
    }

    function crearFotoConMarca(base64Original, filename) {
        return new Promise(function (resolve, reject) {
            log('=== Crear foto con marca ===', 'info');
            log('Archivo para marca: ' + filename, 'info');

            cargarImagen(base64Original)
                .then(function (img) {
                    var canvas = document.createElement('canvas');
                    var ctx = canvas.getContext('2d');

                    var maxWidth = 1600;
                    var scale = Math.min(1, maxWidth / img.width);

                    canvas.width = Math.round(img.width * scale);
                    canvas.height = Math.round(img.height * scale);

                    log(
                        'Canvas creado | width=' + canvas.width +
                        ' | height=' + canvas.height +
                        ' | scale=' + scale,
                        'info'
                    );

                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                    var fechaHora = formatearFechaHora();

                    var margen = Math.round(canvas.width * 0.035);
                    var fontGrande = Math.max(28, Math.round(canvas.width * 0.045));
                    var fontMediano = Math.max(22, Math.round(canvas.width * 0.034));
                    var fontPequeno = Math.max(18, Math.round(canvas.width * 0.026));

                    ctx.font = 'bold ' + fontMediano + 'px Arial, sans-serif';

                    var maxTextoWidth = Math.round(canvas.width * 0.62);
                    var lineasUbicacion = obtenerTextoUbicacion(ctx, maxTextoWidth);

                    var panelAlto = Math.round(canvas.height * 0.28);
                    var panelY = canvas.height - panelAlto;

                    dibujarPanelInferior(ctx, canvas, panelY, panelAlto);

                    var xTexto = canvas.width - margen;
                    var yTexto = panelY + Math.round(panelAlto * 0.12);

                    dibujarTextoConSombra(
                        ctx,
                        fechaHora,
                        xTexto,
                        yTexto,
                        fontGrande,
                        'right'
                    );

                    yTexto += fontGrande + 8;

                    for (var i = 0; i < lineasUbicacion.length; i++) {
                        dibujarTextoConSombra(
                            ctx,
                            lineasUbicacion[i],
                            xTexto,
                            yTexto,
                            fontMediano,
                            'right'
                        );

                        yTexto += fontMediano + 6;
                    }

                    dibujarTextoConSombra(
                        ctx,
                        'Evidencia: ' + (momento === 'antes' ? 'ANTES' : 'DESPUÉS'),
                        xTexto,
                        yTexto,
                        fontPequeno,
                        'right'
                    );

                    var urlMapa = obtenerUrlMapaMini();
                    var urlLogo = obtenerUrlLogoEmpresa();

                    if (!urlMapa) {
                        log('No hay coordenadas. Se generará foto sin mapa, pero con logo.', 'warn');

                        cargarImagenExterna(urlLogo).then(function (logoImg) {
                            try {
                                dibujarLogoEmpresa(ctx, canvas, logoImg);
                            } catch (errLogoSinGps) {
                                log('Error dibujando logo sin GPS: ' + errLogoSinGps.message, 'warn');
                            }

                            finalizarCanvas();
                        });

                        return;
                    }

                    log('URL mini mapa: ' + urlMapa, 'info');
                    log('URL logo empresa: ' + urlLogo, 'info');

                    Promise.all([
                        cargarImagenExterna(urlMapa),
                        cargarImagenExterna(urlLogo)
                    ]).then(function (resultados) {
                        var mapaImg = resultados[0];
                        var logoImg = resultados[1];

                        try {
                            dibujarMiniMapa(ctx, canvas, mapaImg);
                        } catch (errMapa) {
                            log('Error dibujando mini mapa: ' + errMapa.message, 'warn');
                        }

                        try {
                            dibujarLogoEmpresa(ctx, canvas, logoImg);
                        } catch (errLogo) {
                            log('Error dibujando logo: ' + errLogo.message, 'warn');
                        }

                        finalizarCanvas();
                    });

                    function finalizarCanvas() {
                        try {
                            var imagenFinal = canvas.toDataURL('image/jpeg', 0.88);

                            log(
                                'Canvas convertido a JPEG | tamaño_base64_kb=' +
                                Math.round(imagenFinal.length / 1024),
                                'ok'
                            );

                            resolve(imagenFinal);
                        } catch (err) {
                            reject(err);
                        }
                    }
                })
                .catch(function (err) {
                    reject(err);
                });
        });
    }

    function subirFoto(base64, filename) {
        log('=== Iniciando subida a Odoo ===', 'info');

        var lat = coords ? coords.lat : 0;
        var lng = coords ? coords.lng : 0;
        var prec = precision || 0;

        log('Endpoint: /evidencia/' + TOKEN + '/upload', 'info');
        log(
            'Payload | momento=' + momento +
            ' | lat=' + lat +
            ' | lng=' + lng +
            ' | precision=' + prec +
            ' | direccion=' + (direccionActual || '') +
            ' | filename=' + filename,
            'info'
        );

        fetch('/evidencia/' + TOKEN + '/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {
                    momento: momento,
                    imagen_base64: base64,
                    latitud: lat,
                    longitud: lng,
                    precision: prec,
                    direccion: direccionActual || '',
                    filename: filename || 'evidencia.jpg'
                }
            })
        })
            .then(function (r) {
                log('Respuesta HTTP upload: ' + r.status, r.ok ? 'ok' : 'error');
                return r.json();
            })
            .then(function (data) {
                log('Respuesta JSON recibida: ' + JSON.stringify(data).substring(0, 300), 'info');

                var result = data.result || {};

                if (result.success) {
                    log('Upload OK | foto_id=' + result.foto_id, 'ok');
                    showToast('✅ Foto subida correctamente', 'ok');

                    setProgress('Foto subida. Actualizando galería...');

                    setTimeout(function () {
                        location.reload();
                    }, 1500);
                } else {
                    hideProgress();

                    log(
                        'Backend rechazó upload: ' + (result.error || 'sin detalle'),
                        'error'
                    );

                    showToast('❌ ' + (result.error || 'Error desconocido'), 'error');
                }
            })
            .catch(function (err) {
                hideProgress();

                log('Error fetch upload: ' + err.message, 'error');
                showToast('❌ Error de conexión con Odoo', 'error');
            })
            .finally(function () {
                inputFoto.value = '';
            });
    }

    btnAntes.addEventListener('click', function () {
        setMomento('antes');
    });

    btnDespues.addEventListener('click', function () {
        setMomento('despues');
    });

    btnTomar.addEventListener('click', function (e) {
        e.preventDefault();

        log('=== Click en botón tomar foto ===', 'info');
        log('Momento actual: ' + momento, 'info');
        log(
            'Coords actuales: ' +
            (coords ? ('lat=' + coords.lat + ' lng=' + coords.lng) : 'null'),
            coords ? 'ok' : 'warn'
        );

        try {
            inputFoto.click();
            log('inputFoto.click() ejecutado', 'ok');
        } catch (err) {
            log('Error abriendo selector/cámara: ' + err.message, 'error');
            showToast('Error abriendo cámara o selector', 'error');
        }
    });

    btnReintentar.addEventListener('click', function () {
        log('=== Reintento GPS solicitado ===', 'info');
        pedirGPS();
    });

    inputFoto.addEventListener('change', function (e) {
        log('=== Input file change ===', 'info');

        var file = e.target.files[0];

        if (!file) {
            log('No hay archivo seleccionado', 'warn');
            showToast('No se seleccionó ningún archivo', 'error');
            return;
        }

        log(
            'Archivo seleccionado | name=' + file.name +
            ' | type=' + file.type +
            ' | size_kb=' + Math.round(file.size / 1024),
            'info'
        );

        if (!file.type || !file.type.startsWith('image/')) {
            log('Archivo rechazado, no es imagen | type=' + file.type, 'error');
            showToast('El archivo seleccionado no es una imagen', 'error');
            inputFoto.value = '';
            return;
        }

        if (!window.FileReader) {
            log('FileReader no disponible', 'error');
            showToast('Tu navegador no puede leer la imagen', 'error');
            inputFoto.value = '';
            return;
        }

        showProgress('Leyendo foto...');

        var reader = new FileReader();

        reader.onload = function (ev) {
            log(
                'FileReader OK | base64_kb=' +
                Math.round(ev.target.result.length / 1024),
                'ok'
            );

            showProgress('Obteniendo dirección desde Traccar...');

            obtenerDireccionPorGPS()
                .then(function () {
                    showProgress('Agregando logo, fecha, dirección y mapa...');
                    return crearFotoConMarca(ev.target.result, file.name);
                })
                .then(function (imagenMarcada) {
                    log('Foto marcada generada correctamente', 'ok');

                    if (previewImg && previewSection) {
                        previewImg.src = imagenMarcada;
                        previewSection.classList.add('show');
                    }

                    showProgress('Subiendo foto a Odoo...');
                    subirFoto(imagenMarcada, file.name);
                })
                .catch(function (err) {
                    log('Error creando marca: ' + err.message, 'error');
                    showToast('No se pudo agregar la marca. Se subirá la foto original.', 'error');

                    showProgress('Subiendo foto original...');
                    subirFoto(ev.target.result, file.name);
                });
        };

        reader.onerror = function () {
            hideProgress();
            log('FileReader error', 'error');
            showToast('Error leyendo la imagen', 'error');
            inputFoto.value = '';
        };

        reader.readAsDataURL(file);
    });

    pedirGPS();
    setMomento('antes');

    log('Inicialización completa. Esperando foto del usuario.', 'ok');

})();
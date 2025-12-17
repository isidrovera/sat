# -*- coding: utf-8 -*-
from odoo import http, _, fields
from odoo.http import request
import re
import logging
import json

_logger = logging.getLogger(__name__)

NUM_CORE_RE = re.compile(r'(\d{2,5})')


def _norm(s):
    """Normaliza strings eliminando espacios extra"""
    return (s or '').strip()


def clean_brand_from_model(model_text, brand_name):
    """
    Elimina el nombre de la marca del inicio del modelo si está presente.
    """
    if not model_text or not brand_name:
        return model_text

    text = model_text.strip()
    brand_upper = brand_name.upper()
    text_upper = text.upper()

    brand_variations = []

    if brand_upper in ['KONICA', 'KONICA MINOLTA', 'MINOLTA']:
        brand_variations = [
            'KONICA MINOLTA ',
            'KONICA-MINOLTA ',
            'KONICAMINOLTA ',
            'KONICA ',
            'MINOLTA ',
        ]
    elif brand_upper == 'CANON':
        brand_variations = ['CANON ']
    elif brand_upper == 'RICOH':
        brand_variations = ['RICOH ']
    elif brand_upper == 'KYOCERA':
        brand_variations = ['KYOCERA ']
    elif brand_upper in ['HP', 'HEWLETT', 'HEWLETT PACKARD']:
        brand_variations = [
            'HEWLETT-PACKARD ',
            'HEWLETT PACKARD ',
            'HP ',
        ]
    elif brand_upper == 'XEROX':
        brand_variations = ['XEROX ']
    elif brand_upper == 'BROTHER':
        brand_variations = ['BROTHER ']
    elif brand_upper == 'SAMSUNG':
        brand_variations = ['SAMSUNG ']
    elif brand_upper == 'SHARP':
        brand_variations = ['SHARP ']
    elif brand_upper == 'LEXMARK':
        brand_variations = ['LEXMARK ']
    else:
        brand_variations = [
            brand_upper + ' ',
            brand_upper + '-',
        ]

    for variation in brand_variations:
        if text_upper.startswith(variation):
            result = text[len(variation):].strip()
            _logger.info(
                "[SNMP Clean] Limpiado '%s' → '%s' (eliminado: %s)",
                model_text, result, variation.strip()
            )
            return result

    _logger.debug("[SNMP Clean] No se encontró marca al inicio: '%s'", model_text)
    return text


def normalize_model_by_brand(model_text, brand):
    """
    Normaliza nombres de modelos según la marca específica para comparación.
    """
    if not model_text:
        return ""

    text = model_text.lower().strip()
    brand_upper = (brand or '').upper()

    # ==================== CANON ====================
    if brand_upper == 'CANON':
        text = re.sub(r'image\s*-?\s*runner', 'ir', text)
        text = text.replace('advance', 'adv')
        text = text.replace('irc', 'ir c')

    # ==================== RICOH ====================
    elif brand_upper == 'RICOH':
        text = text.replace('aficio mp', 'mp')
        text = text.replace('aficio', '')
        text = text.replace('gestetner', '')
        text = text.replace('savin', '')

    # ==================== KONICA MINOLTA ====================
    elif brand_upper in ['KONICA', 'KONICA MINOLTA', 'MINOLTA']:
        pass

    # ==================== KYOCERA ====================
    elif brand_upper == 'KYOCERA':
        text = text.replace('task alfa', 'taskalfa')

    # ==================== HP ====================
    elif brand_upper == 'HP':
        text = text.replace('laserjet pro', 'laserjet pro')

    # ==================== XEROX ====================
    elif brand_upper == 'XEROX':
        text = text.replace('workcentre', 'workcentre')
        text = text.replace('workcenter', 'workcentre')
        text = text.replace('versalink', 'versalink')
        text = text.replace('altalink', 'altalink')

    # ==================== BROTHER / SAMSUNG / SHARP / LEXMARK ====================
    # (por ahora sin reglas especiales)

    # Separar letras pegadas a números
    text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([a-z])', r'\1 \2', text)

    # Eliminar caracteres especiales
    text = re.sub(r'[-/._+,]+', ' ', text)

    # Espacios múltiples
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def extract_version_suffix(model_text):
    """
    Extrae el sufijo de versión (I, II, III, i, etc.)
    Retorna (texto_sin_sufijo, sufijo)
    """
    if not model_text:
        return model_text, None

    text = model_text.strip()

    match = re.search(r'\s+(I{1,3}|IV|V|VI|VII|VIII|IX|X)$', text, re.IGNORECASE)
    if match:
        suffix = match.group(1).upper()
        base = text[:match.start()].strip()
        return base, suffix

    match = re.search(r'(\d)([i])$', text, re.IGNORECASE)
    if match:
        suffix = match.group(2).lower()
        base = text[:-1].strip()
        return base, suffix

    return text, None


def infer_tipo_color(model_text):
    """
    Detecta si es COLOR o MONOCROMÁTICA basándose en la 'C' antes del número.
    """
    if not model_text:
        return 'monocromatica'

    text = model_text.upper().strip()

    pattern = r'\bC[\s-]?\d{3,5}'

    if re.search(pattern, text):
        _logger.debug("[SNMP Color] Detectado como COLOR (patrón C+número): %s", model_text)
        return 'color'

    if 'COLOR' in text or 'COLOUR' in text:
        _logger.debug("[SNMP Color] Detectado como COLOR (palabra explícita): %s", model_text)
        return 'color'

    _logger.debug("[SNMP Color] Detectado como MONOCROMÁTICA: %s", model_text)
    return 'monocromatica'


def calculate_similarity_score(model_snmp, model_db, brand):
    """
    Calcula score de similitud entre dos modelos (0.0 a 1.0)
    """
    norm_snmp = normalize_model_by_brand(model_snmp, brand)
    norm_db = normalize_model_by_brand(model_db, brand)

    base_snmp, version_snmp = extract_version_suffix(norm_snmp)
    base_db, version_db = extract_version_suffix(norm_db)

    _logger.debug("[SNMP Score] SNMP: '%s' (versión: %s)", base_snmp, version_snmp or 'N/A')
    _logger.debug("[SNMP Score] DB: '%s' (versión: %s)", base_db, version_db or 'N/A')

    if base_snmp == base_db:
        if version_snmp == version_db or not version_snmp or not version_db:
            _logger.debug("[SNMP Score] ✅ MATCH PERFECTO (bases idénticas)")
            return 1.0
        else:
            _logger.debug("[SNMP Score] ⚠️ Bases iguales, versiones diferentes")
            return 0.90

    score = 0.0

    # 1) Tokens comunes
    tokens_snmp = set(base_snmp.split())
    tokens_db = set(base_db.split())

    common_tokens = tokens_snmp & tokens_db
    total_tokens = tokens_snmp | tokens_db

    if total_tokens:
        token_score = len(common_tokens) / len(total_tokens)
        score += token_score * 0.5
        _logger.debug("[SNMP Score] Tokens comunes: %s | Score: %.2f", common_tokens, token_score)

    # 2) Números en mismo orden
    nums_snmp = ''.join(re.findall(r'\d+', base_snmp))
    nums_db = ''.join(re.findall(r'\d+', base_db))

    if nums_snmp and nums_db:
        if nums_snmp == nums_db:
            score += 0.40
            _logger.debug("[SNMP Score] ✅ Números idénticos: %s", nums_snmp)
        elif nums_snmp in nums_db or nums_db in nums_snmp:
            score += 0.20
            _logger.debug("[SNMP Score] ⚠️ Números parcialmente coinciden")

    # 3) Longitud parecida
    len_diff = abs(len(base_snmp) - len(base_db))
    max_len = max(len(base_snmp), len(base_db))
    if max_len > 0:
        len_score = 1 - (len_diff / max_len)
        score += len_score * 0.10

    _logger.debug("[SNMP Score] 🎯 TOTAL: %.2f", score)
    return score


def parse_model(text):
    """
    Extrae familia (aprox), núcleo numérico y variante.
    """
    t = _norm(text)
    if not t:
        return (None, None, None)

    m = NUM_CORE_RE.search(t)
    fam = None
    core = None
    var = None

    if m:
        core = m.group(1)
        before = t[:m.start()].strip()
        after = t[m.end():].strip()
        fam = re.sub(r'[^A-Za-z\-]+', ' ', before).strip() or None
        var = after or None
        _logger.debug(
            "[SNMP Parser] '%s' -> Familia: %s, Core: %s, Variante: %s",
            t, fam, core, var
        )
    else:
        _logger.warning("[SNMP Parser] No se encontró núcleo numérico en: %s", t)

    if fam:
        fam = fam.replace('iR', 'IR').replace('iRC', 'IRC')
        fam = re.sub(r'\s+', ' ', fam)
    if var:
        var = var.replace('Series', '').strip()
        var = re.sub(r'\s+', ' ', var)

    return (fam, core, var)


def find_logistics_user(env):
    usr = env['res.users'].search([('groups_id.name', 'ilike', 'logística')], limit=1)
    if not usr:
        usr = env.ref('base.user_admin', raise_if_not_found=False)
    return usr


def ensure_brand(env, brand_name):
    """Asegura (o crea) la marca usando sudo()."""
    if not brand_name:
        return False

    Marca = env['marca.marca'].sudo()
    clean_name = brand_name.strip()

    brand = Marca.search([('name', '=ilike', clean_name)], limit=1)

    if brand:
        _logger.info("[SNMP] Marca existente: %s (ID: %s)", brand.name, brand.id)
        return brand.id

    try:
        brand = Marca.create({'name': clean_name})
        _logger.info("[SNMP] Marca CREADA: %s (ID: %s)", brand.name, brand.id)
        return brand.id
    except Exception as e:
        _logger.error("[SNMP] Error creando marca '%s': %s", clean_name, e)
        return False


def get_default_tipo_maquina(env):
    """Obtiene el tipo de máquina por defecto.

    1) Primero intenta leer el parámetro snmp.default_tipo_maquina_id
    2) Si no existe o no es válido, busca un tipo de máquina cuyo nombre contenga 'Fotocopiadora'
    """
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_tipo_maquina_id')
    try:
        if param:
            tipo_id = int(param)
            if env['tipo.maquina'].sudo().browse(tipo_id).exists():
                return tipo_id
    except Exception:
        pass

    # Fallback: buscar tipo 'Fotocopiadora'
    tipo = env['tipo.maquina'].sudo().search([('name', 'ilike', 'fotocopiadora')], limit=1)
    if tipo:
        return tipo.id

    return None


def get_default_precio(env):
    """
    Obtiene el precio de venta por defecto para modelos creados por SNMP.
    Parámetro: snmp.default_precio_venta
    """
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_precio_venta')
    try:
        return float(param) if param else 0.0
    except Exception:
        return 0.0


def build_canon_commercial_name(model_snmp, current_model_name, tipo_color_snmp, core_snmp):
    """
    Construye el nombre comercial corto para Canon.
    Ejemplos:
      - DX Color: iR-ADV DX C5735
      - No DX Color: iR-ADV C5235
      - DX Mono: iR-ADV DX 4525
      - No DX Mono: iR-ADV 4525
    Solo pone DX si:
      - El SNMP trae DX, o
      - El modelo actual del SAT tiene DX
    """
    if not core_snmp:
        return None

    up_snmp = (model_snmp or '').upper()
    up_cur = (current_model_name or '').upper()

    dx_flag = ('DX' in up_snmp) or ('DX' in up_cur)

    prefix = 'iR-ADV '
    if dx_flag:
        prefix += 'DX '

    if tipo_color_snmp == 'color':
        return f"{prefix}C{core_snmp}"
    else:
        return f"{prefix}{core_snmp}"


def find_and_update_model(env, model_snmp, brand_name, core_snmp, tipo_color_snmp, commercial_name=None):
    """
    Busca modelo con la siguiente lógica:
    1. EXACTO: 
       - Si hay nombre comercial (Canon DX), buscar primero commercial_name
       - Luego buscar el nombre exacto que envía SNMP
    2. SIMILAR: Busca por núcleo + marca + color, si encuentra UNO que coincide 
       con buen score, lo MODIFICA (renombra al nombre comercial o al SNMP)
    3. SIN MODELO CONFIABLE: No crea nada, delega a intervención manual.

    Retorna: (modelo, acción, modificado)
    acción ∈ {'exact', 'updated', 'failed'}
    modificado = True si se renombró el modelo existente
    """
    Mod = env['modelo.maquina'].sudo()

    # ==========================
    # PASO 1: BÚSQUEDA EXACTA
    # ==========================
    # 1.1 Primero intentar con nombre comercial (si existe)
    if commercial_name:
        _logger.info("[SNMP Match] Paso 1A: Búsqueda EXACTA de comercial '%s'", commercial_name)
        exact_commercial = Mod.search([('name', '=ilike', commercial_name)], limit=1)
        if exact_commercial:
            _logger.info(
                "[SNMP Match] ✅ Modelo EXACTO (comercial) encontrado: %s (ID: %s)",
                exact_commercial.name, exact_commercial.id
            )
            return exact_commercial, 'exact', False

    # 1.2 Luego intentar con el nombre crudo que envía SNMP
    _logger.info("[SNMP Match] Paso 1B: Búsqueda EXACTA de '%s'", model_snmp)
    exact = Mod.search([('name', '=ilike', model_snmp)], limit=1)

    if exact:
        _logger.info(
            "[SNMP Match] ✅ Modelo EXACTO encontrado: %s (ID: %s)",
            exact.name, exact.id
        )
        return exact, 'exact', False

    # ==========================
    # PASO 2: BÚSQUEDA SIMILAR
    # ==========================
    _logger.info("[SNMP Match] Paso 2: Búsqueda SIMILAR (para modificar)")

    domain = []

    brand_obj = None
    if brand_name:
        brand_obj = env['marca.marca'].sudo().search([('name', '=ilike', brand_name)], limit=1)
        if brand_obj:
            domain.append(('marca_id', '=', brand_obj.id))
            _logger.info(
                "[SNMP Match] Filtrando por marca: %s (ID: %s)",
                brand_obj.name, brand_obj.id
            )

    domain.append(('tipo_id', '=', tipo_color_snmp))
    _logger.info("[SNMP Match] Filtrando por tipo: %s", tipo_color_snmp)

    candidates = Mod.search(domain)
    _logger.info("[SNMP Match] Evaluando %s modelos candidatos", len(candidates))

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        _, core_candidate, _ = parse_model(candidate.name)

        if not core_candidate or core_candidate != core_snmp:
            continue

        score = calculate_similarity_score(model_snmp, candidate.name, brand_name)
        _logger.debug(
            "[SNMP Match] Evaluando: %s | Score: %.3f",
            candidate.name, score
        )

        if score > best_score:
            best_score = score
            best_match = candidate

    THRESHOLD_UPDATE = 0.85

    if best_match and best_score >= THRESHOLD_UPDATE:
        _logger.info(
            "[SNMP Match] ✅ Modelo SIMILAR encontrado: %s (Score: %.3f)",
            best_match.name, best_score
        )

        # Decidir nombre destino:
        #   - Preferimos nombre comercial si existe
        #   - Si no, usamos el nombre tal cual llega de SNMP
        new_name = commercial_name or model_snmp
        if best_match.name == new_name:
            _logger.info("[SNMP Match] ℹ️ El modelo ya tiene el nombre esperado: %s", new_name)
            return best_match, 'exact', False

        _logger.info(
            "[SNMP Match] 🔄 MODIFICANDO modelo de '%s' a '%s'",
            best_match.name, new_name
        )

        try:
            nombre_anterior = best_match.name
            best_match.sudo().write({'name': new_name})
            _logger.info("[SNMP Match] ✅ Modelo ACTUALIZADO exitosamente")

            # Notificar a equipos sat.sat que usan este modelo
            try:
                Sat = env['sat.sat'].sudo()
                equipos = Sat.search([('name', '=', best_match.id)])
                _logger.info(
                    "[SNMP Match] Notificando a %s equipos sobre el cambio de nombre",
                    len(equipos)
                )

                for equipo in equipos:
                    try:
                        equipo.message_post(
                            body=_(
                                "📝 <b>Modelo actualizado automáticamente por SNMP</b><br/>"
                                "Nombre anterior: <b>%s</b><br/>"
                                "Nombre nuevo: <b>%s</b><br/>"
                                "Razón: Coincidencia de %.1f%% con datos SNMP"
                            ) % (nombre_anterior, new_name, best_score * 100)
                        )
                    except Exception as e_msg:
                        _logger.warning(
                            "[SNMP Match] No se pudo notificar a equipo %s: %s",
                            equipo.id, e_msg
                        )
            except Exception as e_equipos:
                _logger.warning(
                    "[SNMP Match] No se pudo notificar cambios a equipos: %s",
                    e_equipos
                )

            return best_match, 'updated', True

        except Exception as e:
            _logger.error("[SNMP Match] ❌ Error modificando modelo: %s", e)
            _logger.exception("[SNMP Match] Traceback:")
            return best_match, 'exact', False

    elif best_match:
        _logger.warning(
            "[SNMP Match] ⚠️ Match insuficiente: %s (Score: %.3f < %.2f)",
            best_match.name, best_score, THRESHOLD_UPDATE
        )

    # ==========================
    # PASO 3: SIN CREACIÓN AUTOMÁTICA
    # ==========================
    _logger.warning(
        "[SNMP Match] ⚠️ No se encontró modelo exacto ni similar con score suficiente. "
        "Se requiere intervención manual, no se creará modelo automáticamente."
    )

    # No crear modelo; se delega al caller (snmp_intake) para que llame a _suggest_model
    return None, 'failed', False


class SNMPPublicController(http.Controller):

    @http.route('/snmp/intake', type='json', auth='public', methods=['POST'], csrf=False)
    def snmp_intake(self, **kwargs):
        """
        Endpoint público para recibir datos SNMP.
        Espera JSON con: serial, model, brand, total_counter
        """

        # ==========================
        # 0) Parseo del payload
        # ==========================
        try:
            if hasattr(request, 'get_json_data'):
                payload = request.get_json_data()
            elif hasattr(request, 'jsonrequest'):
                payload = request.jsonrequest
            elif kwargs:
                payload = kwargs
            else:
                payload = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception as e:
            _logger.error("[SNMP INTAKE] Error parseando JSON: %s", e)
            payload = {}

        _logger.info("=" * 80)
        _logger.info("[SNMP INTAKE] Nueva solicitud recibida")
        _logger.info("[SNMP INTAKE] Payload: %s", payload)

        serial = _norm(payload.get('serial'))
        model_snmp_raw = _norm(payload.get('model'))
        brand = _norm(payload.get('brand'))
        total_counter = payload.get('total_counter')

        # Limpiar marca del modelo
        model_snmp = clean_brand_from_model(model_snmp_raw, brand)

        _logger.info(
            "[SNMP INTAKE] Serial: %s | Modelo: %s | Marca: %s | Contador: %s",
            serial or 'N/A', model_snmp or 'N/A', brand or 'N/A', total_counter or 'N/A'
        )

        if not serial:
            _logger.error("[SNMP INTAKE] ERROR: Serial requerido")
            return {'ok': False, 'error': 'serial requerido'}

        Sat = request.env['sat.sat'].sudo()

        # ==========================
        # 1) Buscar y BLOQUEAR equipo
        # ==========================
        sat = Sat.search([('serie_id', '=', serial)], limit=1)

        if not sat:
            _logger.warning("[SNMP] Serie '%s' no encontrada", serial)
            return {'ok': True, 'skipped': 'sat no encontrado por serie'}

        # 🔒 BLOQUEO PARA EVITAR CONCURRENCIA
        sat = sat.with_lock()

        _logger.info(
            "[SNMP] Equipo encontrado: %s (ID: %s)",
            sat.display_name, sat.id
        )

        # ==========================
        # 2) Parsear modelo SNMP
        # ==========================
        fam_snmp, core_snmp, var_snmp = parse_model(model_snmp)

        if sat.name:
            fam_cur, core_cur, var_cur = parse_model(sat.name.name)
        else:
            core_cur = None

        # ==========================
        # 3) Detectar tipo de color
        # ==========================
        tipo_color_snmp = infer_tipo_color(model_snmp)

        # ==========================
        # 4) Canon: nombre comercial DX
        # ==========================
        commercial_name = None
        brand_upper = (brand or '').upper()

        if brand_upper == 'CANON' and core_snmp:
            has_dx_current = bool(sat.name and sat.name.name and 'DX' in sat.name.name.upper())
            if has_dx_current:
                if tipo_color_snmp == 'color':
                    commercial_name = f"iR-ADV DX C{core_snmp}"
                else:
                    commercial_name = f"iR-ADV DX {core_snmp}"

        # ==========================
        # 5) Flujo NORMAL de modelo
        # ==========================
        target_model, action, modified = find_and_update_model(
            request.env,
            model_snmp=model_snmp,
            brand_name=brand,
            core_snmp=core_snmp,
            tipo_color_snmp=tipo_color_snmp,
            commercial_name=commercial_name,
        )

        if not target_model:
            _logger.warning("[SNMP] No se pudo determinar modelo, solo se actualiza contador")
            self._safe_update_counters(sat, total_counter)
            self._suggest_model(sat, model_snmp)
            return {
                'ok': True,
                'suggested': model_snmp,
                'note': 'pendiente de creación manual'
            }

        # ==========================
        # 6) Asignar modelo si cambia
        # ==========================
        if not sat.name or sat.name.id != target_model.id:
            modelo_anterior = sat.name.name if sat.name else 'Sin modelo'
            sat.write({'name': target_model.id})

            sat.message_post(
                body=_(
                    "Modelo asignado por SNMP: <b>%s</b> (desde: %s)"
                ) % (target_model.name, modelo_anterior)
            )

        # ==========================
        # 7) ACTUALIZAR CONTADOR (ÚNICA VEZ)
        # ==========================
        self._safe_update_counters(sat, total_counter)

        _logger.info("=" * 80)

        return {
            'ok': True,
            'model': target_model.name,
            'contador': total_counter,
            'action': action,
            'modified': modified,
        }


    def _safe_update_counters(self, sat, total_counter):
        """Actualiza contador SNMP de forma segura (SIN notificar)"""

        if total_counter is None:
            return

        try:
            # Limpiar valores a solo dígitos
            contador_actual_str = str(sat.contometro or '0')
            contador_nuevo_str = str(total_counter)

            contador_actual = int(re.sub(r'[^\d]', '', contador_actual_str) or 0)
            contador_nuevo = int(re.sub(r'[^\d]', '', contador_nuevo_str) or 0)

            _logger.info(
                "[SNMP Contador] Actual: %s | Nuevo: %s",
                contador_actual, contador_nuevo
            )

            # 🛑 DEDUP: si es el mismo valor, no hacer nada
            if contador_actual == contador_nuevo:
                _logger.info("[SNMP] Contador sin cambios, se ignora")
                return

            # ==========================
            # SOLO ESCRIBIR
            # ==========================
            vals = {
                'contometro': contador_nuevo_str,
                'contador_antes_snmp': contador_actual_str,
                'ultima_actualizacion_snmp': fields.Datetime.now(),
                'total_actualizaciones_snmp': (sat.total_actualizaciones_snmp or 0) + 1,
                'ultima_fuente_actualizacion': 'snmp',
            }

            sat.sudo().write(vals)

            _logger.info(
                "[SNMP] ✅ Contador actualizado: %s -> %s",
                contador_actual, contador_nuevo
            )

        except Exception as e:
            _logger.error("[SNMP] ❌ Error actualizando contador: %s", e)
            _logger.exception("[SNMP] Traceback:")


    def _notify_core_mismatch(self, sat, snmp_model, current_model, new_model=None):
        """Notifica diferencia de núcleo/modelo usando método del modelo sat.sat."""
        try:
            # Intento con firma extendida (con modelo nuevo)
            sat.notify_snmp_model_mismatch(
                snmp_model=snmp_model,
                current_model=current_model,
                new_model=new_model,
            )
        except TypeError:
            # Compatibilidad: si el método definido en sat.sat no acepta new_model
            try:
                sat.notify_snmp_model_mismatch(
                    snmp_model=snmp_model,
                    current_model=current_model,
                )
            except Exception as e:
                _logger.error(
                    "[SNMP] Error notificando diferencia de modelo (sin new_model): %s",
                    e
                )
        except Exception as e:
            _logger.error(
                "[SNMP] Error notificando diferencia de modelo: %s",
                e
            )

    def _suggest_model(self, sat, snmp_model):
        """Crea sugerencia de modelo (chatter + correo por plantilla)."""
        try:
            sat.notify_snmp_model_suggestion(snmp_model)
        except Exception as e:
            _logger.error("[SNMP] Error en sugerencia de modelo SNMP: %s", e)
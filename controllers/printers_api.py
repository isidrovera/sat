# -*- coding: utf-8 -*-
from odoo import http, _
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
    
    Ejemplos:
    - "KONICA MINOLTA bizhub 364e" + "KONICA" → "bizhub 364e"
    - "Canon iR-ADV C3330" + "CANON" → "iR-ADV C3330"
    - "RICOH Aficio MP C3004" + "RICOH" → "Aficio MP C3004"
    """
    if not model_text or not brand_name:
        return model_text
    
    text = model_text.strip()
    brand_upper = brand_name.upper()
    text_upper = text.upper()
    
    # Lista de variaciones del nombre de marca a eliminar
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
        # Marca genérica
        brand_variations = [
            brand_upper + ' ',
            brand_upper + '-',
        ]
    
    # Intentar eliminar cada variación
    for variation in brand_variations:
        if text_upper.startswith(variation):
            result = text[len(variation):].strip()
            _logger.info("[SNMP Clean] Limpiado '%s' → '%s' (eliminado: %s)", 
                        model_text, result, variation.strip())
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
    
    # ==================== BROTHER ====================
    elif brand_upper == 'BROTHER':
        pass
    
    # ==================== SAMSUNG ====================
    elif brand_upper == 'SAMSUNG':
        text = text.replace('multixpress', 'multixpress')
        text = text.replace('multi xpress', 'multixpress')
    
    # ==================== SHARP ====================
    elif brand_upper == 'SHARP':
        pass
    
    # ==================== LEXMARK ====================
    elif brand_upper == 'LEXMARK':
        pass
    
    # Separar letras pegadas a números (C3330 → C 3330)
    text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
    
    # Eliminar caracteres especiales
    text = re.sub(r'[-/._+,]+', ' ', text)
    
    # Eliminar espacios múltiples
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
    
    # Buscar sufijos romanos al final
    match = re.search(r'\s+(I{1,3}|IV|V|VI|VII|VIII|IX|X)$', text, re.IGNORECASE)
    if match:
        suffix = match.group(1).upper()
        base = text[:match.start()].strip()
        return base, suffix
    
    # Buscar letra 'i' sola al final
    match = re.search(r'(\d)([i])$', text, re.IGNORECASE)
    if match:
        suffix = match.group(2).lower()
        base = text[:-1].strip()
        return base, suffix
    
    return text, None

def infer_tipo_color(model_text):
    """
    Detecta si es COLOR o MONOCROMÁTICA basándose en la 'C' antes del número.
    
    REGLA: Si tiene 'C' seguido de espacio/guion y número → COLOR
    """
    if not model_text:
        return 'monocromatica'
    
    text = model_text.upper().strip()
    
    # Patrón: busca "C" seguido opcionalmente de espacio/guion y luego números
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
    
    # Si las bases normalizadas son idénticas
    if base_snmp == base_db:
        if version_snmp == version_db or not version_snmp or not version_db:
            _logger.debug("[SNMP Score] ✅ MATCH PERFECTO (bases idénticas)")
            return 1.0
        else:
            _logger.debug("[SNMP Score] ⚠️ Bases iguales, versiones diferentes")
            return 0.90
    
    score = 0.0
    
    # 1. Score por tokens comunes (50%)
    tokens_snmp = set(base_snmp.split())
    tokens_db = set(base_db.split())
    
    common_tokens = tokens_snmp & tokens_db
    total_tokens = tokens_snmp | tokens_db
    
    if total_tokens:
        token_score = len(common_tokens) / len(total_tokens)
        score += token_score * 0.5
        _logger.debug("[SNMP Score] Tokens comunes: %s | Score: %.2f", common_tokens, token_score)
    
    # 2. Score por números en mismo orden (40%)
    nums_snmp = ''.join(re.findall(r'\d+', base_snmp))
    nums_db = ''.join(re.findall(r'\d+', base_db))
    
    if nums_snmp and nums_db:
        if nums_snmp == nums_db:
            score += 0.40
            _logger.debug("[SNMP Score] ✅ Números idénticos: %s", nums_snmp)
        elif nums_snmp in nums_db or nums_db in nums_snmp:
            score += 0.20
            _logger.debug("[SNMP Score] ⚠️ Números parcialmente coinciden")
    
    # 3. Score por similitud de longitud (10%)
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
        _logger.debug("[SNMP Parser] '%s' -> Familia: %s, Core: %s, Variante: %s", 
                     t, fam, core, var)
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
    """Intenta encontrar un usuario de logística."""
    usr = env['res.users'].search([('groups_id.name', 'ilike', 'logística')], limit=1)
    if not usr:
        usr = env.ref('base.user_admin', raise_if_not_found=False)
    return usr

def ensure_brand(env, brand_name):
    """Asegura (o crea) la marca."""
    if not brand_name:
        return False
    
    Marca = env['marca.marca']
    brand = Marca.search([('name', '=ilike', brand_name.strip())], limit=1)
    
    if brand:
        _logger.info("[SNMP] Marca existente: %s (ID: %s)", brand.name, brand.id)
        return brand.id
    
    try:
        brand = Marca.create({'name': brand_name.strip()})
        _logger.info("[SNMP] Marca CREADA: %s (ID: %s)", brand.name, brand.id)
        return brand.id
    except Exception as e:
        _logger.error("[SNMP] Error creando marca '%s': %s", brand_name, e)
        return False

def get_default_tipo_maquina(env):
    """Obtiene el tipo de máquina por defecto."""
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_tipo_maquina_id')
    try:
        return int(param) if param else None
    except Exception:
        return None

def get_default_precio(env):
    """Obtiene el precio por defecto."""
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_precio_venta')
    try:
        return float(param) if param else 0.0
    except Exception:
        return 0.0

def find_and_update_model(env, model_snmp, brand_name, core_snmp, tipo_color_snmp):
    """
    Busca modelo con la siguiente lógica:
    1. EXACTO: Busca el nombre exacto que envía SNMP
    2. SIMILAR: Busca por núcleo + marca + color, si encuentra UNO que coincida, lo MODIFICA
    3. CREAR: Si no encuentra ninguno, crea nuevo
    
    Retorna: (modelo, acción, modificado)
    """
    Mod = env['modelo.maquina'].sudo()
    
    # ============ PASO 1: Búsqueda EXACTA ============
    _logger.info("[SNMP Match] Paso 1: Búsqueda EXACTA de '%s'", model_snmp)
    exact = Mod.search([('name', '=ilike', model_snmp)], limit=1)
    
    if exact:
        _logger.info("[SNMP Match] ✅ Modelo EXACTO encontrado: %s (ID: %s)", exact.name, exact.id)
        return exact, 'exact', False
    
    # ============ PASO 2: Búsqueda SIMILAR para MODIFICAR ============
    _logger.info("[SNMP Match] Paso 2: Búsqueda SIMILAR (para modificar)")
    
    domain = []
    
    brand_obj = None
    if brand_name:
        brand_obj = env['marca.marca'].sudo().search([('name', '=ilike', brand_name)], limit=1)
        if brand_obj:
            domain.append(('marca_id', '=', brand_obj.id))
            _logger.info("[SNMP Match] Filtrando por marca: %s (ID: %s)", brand_obj.name, brand_obj.id)
    
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
        
        _logger.debug("[SNMP Match] Evaluando: %s | Score: %.3f", candidate.name, score)
        
        if score > best_score:
            best_score = score
            best_match = candidate
    
    THRESHOLD_UPDATE = 0.85
    
    if best_match and best_score >= THRESHOLD_UPDATE:
        _logger.info("[SNMP Match] ✅ Modelo SIMILAR encontrado: %s (Score: %.3f)", 
                    best_match.name, best_score)
        _logger.info("[SNMP Match] 🔄 MODIFICANDO modelo de '%s' a '%s'", 
                    best_match.name, model_snmp)
        
        try:
            nombre_anterior = best_match.name
            best_match.sudo().write({'name': model_snmp})
            _logger.info("[SNMP Match] ✅ Modelo ACTUALIZADO exitosamente")
            
            try:
                Sat = env['sat.sat'].sudo()
                equipos = Sat.search([('name', '=', best_match.id)])
                _logger.info("[SNMP Match] Notificando a %s equipos sobre el cambio de nombre", len(equipos))
                
                for equipo in equipos:
                    try:
                        equipo.message_post(
                            body=_("📝 <b>Modelo actualizado automáticamente por SNMP</b><br/>"
                                   "Nombre anterior: <b>%s</b><br/>"
                                   "Nombre nuevo: <b>%s</b><br/>"
                                   "Razón: Coincidencia de %.1f%% con datos SNMP")
                                 % (nombre_anterior, model_snmp, best_score * 100))
                    except Exception as e_msg:
                        _logger.warning("[SNMP Match] No se pudo notificar a equipo %s: %s", equipo.id, e_msg)
            except Exception as e_equipos:
                _logger.warning("[SNMP Match] No se pudo notificar cambios a equipos: %s", e_equipos)
            
            return best_match, 'updated', True
            
        except Exception as e:
            _logger.error("[SNMP Match] ❌ Error modificando modelo: %s", e)
            _logger.exception("[SNMP Match] Traceback:")
            return best_match, 'exact', False
    
    elif best_match:
        _logger.warning("[SNMP Match] ⚠️ Match insuficiente: %s (Score: %.3f < %.2f)", 
                       best_match.name, best_score, THRESHOLD_UPDATE)
    
    # ============ PASO 3: CREAR nuevo modelo ============
    _logger.info("[SNMP Match] Paso 3: Intentando CREAR nuevo modelo")
    
    brand_id = ensure_brand(env, brand_name) if brand_name else False
    tipo_maquina_id = get_default_tipo_maquina(env)
    precio = get_default_precio(env)
    
    if not tipo_maquina_id:
        _logger.error("[SNMP Match] ❌ Falta 'snmp.default_tipo_maquina_id' - no se puede crear")
        return None, 'failed', False
    
    vals = {
        'name': model_snmp,
        'marca_id': brand_id or False,
        'tipo_id': tipo_color_snmp,
        'precio_venta': precio,
        'tipo_maquina_id': tipo_maquina_id,
    }
    
    try:
        created = Mod.create(vals)
        _logger.info("[SNMP Match] ✅ Modelo CREADO: %s (ID: %s)", created.name, created.id)
        return created, 'created', False
    except Exception as e:
        _logger.error("[SNMP Match] ❌ Error creando modelo: %s", e)
        _logger.exception("[SNMP Match] Traceback:")
        return None, 'failed', False

class SNMPPublicController(http.Controller):

    @http.route('/snmp/intake', type='json', auth='public', methods=['POST'], csrf=False)
    def snmp_intake(self, **kwargs):
        """
        Endpoint público para recibir datos SNMP.
        Espera JSON con: serial, model, brand, total_counter
        """
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
        
        _logger.info("="*80)
        _logger.info("[SNMP INTAKE] Nueva solicitud recibida")
        _logger.info("[SNMP INTAKE] Payload: %s", payload)
        
        serial = _norm(payload.get('serial'))
        model_snmp_raw = _norm(payload.get('model'))
        brand = _norm(payload.get('brand'))
        total_counter = payload.get('total_counter')

        # ✅ Limpiar marca del modelo
        model_snmp = clean_brand_from_model(model_snmp_raw, brand)
        
        if model_snmp != model_snmp_raw:
            _logger.info("[SNMP INTAKE] Modelo limpiado: '%s' → '%s'", model_snmp_raw, model_snmp)

        _logger.info("[SNMP INTAKE] Serial: %s | Modelo: %s | Marca: %s | Contador: %s",
                    serial or 'N/A', model_snmp or 'N/A', brand or 'N/A', total_counter or 'N/A')

        if not serial:
            _logger.error("[SNMP INTAKE] ERROR: Serial requerido")
            return {'ok': False, 'error': 'serial requerido'}

        Sat = request.env['sat.sat'].sudo()

        # 1) Buscar equipo por serie
        _logger.info("[SNMP] Buscando equipo con serie: %s", serial)
        sat = Sat.search([('serie_id', '=', serial)], limit=1)
        
        if not sat:
            _logger.warning("[SNMP] ❌ Serie '%s' NO encontrada", serial)
            return {'ok': True, 'skipped': 'sat.sat no encontrado por serie'}
        
        _logger.info("[SNMP] ✅ Equipo encontrado: %s (ID: %s)", sat.display_name, sat.id)
        _logger.info("[SNMP] Modelo actual: %s", sat.name.name if sat.name else 'SIN MODELO')

        # 2) Parsear modelo SNMP
        _logger.info("[SNMP] Parseando modelo SNMP: %s", model_snmp)
        fam_snmp, core_snmp, var_snmp = parse_model(model_snmp)
        
        if sat.name:
            fam_cur, core_cur, var_cur = parse_model(sat.name.name)
        else:
            core_cur = None

        # 3) Validar núcleo
        if not core_snmp:
            _logger.warning("[SNMP] ⚠️ No se pudo extraer núcleo: %s", model_snmp)
            self._safe_update_counters(sat, total_counter)
            sat.message_post(body=_("SNMP recibido sin núcleo identificable. Modelo: %s") % (model_snmp or '—'))
            return {'ok': True, 'updated_counters': True, 'note': 'modelo no parseable'}

        _logger.info("[SNMP] Núcleo SNMP: %s | Núcleo actual: %s", core_snmp, core_cur or 'N/A')

        # 4) Detectar tipo de color
        tipo_color_snmp = infer_tipo_color(model_snmp)
        _logger.info("[SNMP] Tipo detectado: %s", tipo_color_snmp.upper())

        # 5) Verificar mismatch de núcleo
        if sat.name and core_cur and (core_cur != core_snmp):
            _logger.warning("[SNMP] 🚨 MISMATCH DE NÚCLEO!")
            _logger.warning("[SNMP] Actual: %s (%s) | SNMP: %s (%s)", 
                          sat.name.name, core_cur, model_snmp, core_snmp)
            
            self._safe_update_counters(sat, total_counter)
            self._notify_core_mismatch(sat, model_snmp, sat.name.name)
            
            return {
                'ok': True,
                'warning': 'core_mismatch',
                'current_model': sat.name.name,
                'snmp_model': model_snmp
            }

        # 6) Buscar/Actualizar/Crear modelo
        target_model, action, modified = find_and_update_model(
            request.env, model_snmp, brand, core_snmp, tipo_color_snmp
        )

        if not target_model:
            _logger.warning("[SNMP] ⚠️ No se pudo procesar el modelo")
            self._safe_update_counters(sat, total_counter)
            self._suggest_model(sat, model_snmp)
            return {'ok': True, 'suggested': model_snmp, 'note': 'pendiente de creación manual'}

        # 7) Actualizar contador
        self._safe_update_counters(sat, total_counter)

        # 8) Asignar modelo al equipo si es necesario
        if sat.name and sat.name.id == target_model.id:
            _logger.info("[SNMP] ℹ️ Modelo ya asignado: %s", target_model.name)
            return {
                'ok': True,
                'assigned': 'unchanged',
                'model': target_model.name,
                'action': action,
                'modified': modified
            }
        
        modelo_anterior = sat.name.name if sat.name else 'Sin modelo'
        sat.write({'name': target_model.id})
        _logger.info("[SNMP] ✅ Modelo ASIGNADO: %s -> %s", modelo_anterior, target_model.name)
        
        msg_action = {
            'exact': 'encontrado exacto',
            'updated': 'actualizado de nombre anterior',
            'created': 'creado nuevo'
        }
        
        sat.message_post(
            body=_("Modelo %s por SNMP: <b>%s</b> (desde: %s)") %
                 (msg_action.get(action, action), target_model.name, modelo_anterior))
        
        _logger.info("="*80)
        
        return {
            'ok': True,
            'assigned': action,
            'model': target_model.name,
            'previous_model': modelo_anterior,
            'modified': modified
        }

    def _safe_update_counters(self, sat, total_counter):
        """Actualiza contador con registro de historial SNMP"""
        if total_counter is None:
            return
        
        try:
            # Normalizar contadores
            contador_actual_str = str(sat.contometro or '0')
            contador_nuevo_str = str(total_counter)
            
            # Limpiar solo números
            contador_actual = int(re.sub(r'[^\d]', '', contador_actual_str))
            contador_nuevo = int(re.sub(r'[^\d]', '', contador_nuevo_str))
            
            _logger.info("[SNMP Contador] Actual: %s | Nuevo: %s", contador_actual, contador_nuevo)
            
            # Detectar decremento
            if contador_actual > 0 and contador_nuevo < contador_actual:
                diferencia = contador_actual - contador_nuevo
                _logger.warning("[SNMP] ⚠️ CONTADOR DECRECIÓ: %s -> %s (-%s)", 
                              contador_actual, contador_nuevo, diferencia)
                
                sat.message_post(
                    body=_("⚠️ <b>Contador decreció por SNMP</b><br/>"
                           "Anterior: <b>%s</b><br/>"
                           "Nuevo: <b>%s</b><br/>"
                           "Diferencia: <b>-%s</b>")
                         % (f"{contador_actual:,}", f"{contador_nuevo:,}", f"{diferencia:,}"))
                
                usr = find_logistics_user(request.env)
                if usr:
                    try:
                        request.env['mail.activity'].sudo().create({
                            'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                            'res_id': sat.id,
                            'user_id': usr.id,
                            'summary': _("Revisar contador decreciente (SNMP)"),
                            'note': _("Contador disminuyó de %s a %s (-%s copias)") 
                                   % (f"{contador_actual:,}", f"{contador_nuevo:,}", f"{diferencia:,}"),
                            'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                        })
                    except Exception as e:
                        _logger.error("[SNMP] Error creando actividad: %s", e)
            
            # Actualizar campos
            vals = {
                'contometro': contador_nuevo_str,
                'contador_antes_snmp': contador_actual_str,
                'ultima_actualizacion_snmp': request.env['ir.fields'].browse(1)._fields['create_date'].now(),
                'total_actualizaciones_snmp': sat.total_actualizaciones_snmp + 1,
                'ultima_fuente_actualizacion': 'snmp',
            }
            
            sat.sudo().write(vals)
            _logger.info("[SNMP] ✅ Contador actualizado: %s -> %s", contador_actual, contador_nuevo)
            
        except Exception as e:
            _logger.error("[SNMP] ❌ Error actualizando contador: %s", e)
            _logger.exception("[SNMP] Traceback:")

    def _notify_core_mismatch(self, sat, snmp_model, current_model):
        """Notifica diferencia de núcleo"""
        try:
            sat.message_post(
                body=_("⚠️ <b>Diferencia de núcleo detectada</b><br/>"
                       "Detectado: <b>%s</b><br/>"
                       "Actual: <b>%s</b>")
                     % (snmp_model, current_model))
        except Exception as e:
            _logger.error("[SNMP] Error en chatter: %s", e)
        
        usr = find_logistics_user(request.env)
        if usr:
            try:
                request.env['mail.activity'].sudo().create({
                    'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                    'res_id': sat.id,
                    'user_id': usr.id,
                    'summary': _("Revisar cambio de modelo (núcleo distinto)"),
                    'note': _("SNMP detectó: <b>%s</b><br/>Actual: <b>%s</b>") 
                           % (snmp_model, current_model),
                    'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                })
            except Exception as e:
                _logger.error("[SNMP] Error creando actividad: %s", e)

    def _suggest_model(self, sat, snmp_model):
        """Crea sugerencia de modelo"""
        try:
            sat.message_post(
                body=_("💡 <b>Sugerencia de modelo SNMP</b><br/>"
                       "Detectado: <b>%s</b>") % snmp_model)
        except Exception as e:
            _logger.error("[SNMP] Error en sugerencia: %s", e)
        
        usr = find_logistics_user(request.env)
        if usr:
            try:
                request.env['mail.activity'].sudo().create({
                    'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                    'res_id': sat.id,
                    'user_id': usr.id,
                    'summary': _("Crear modelo sugerido por SNMP"),
                    'note': _("SNMP sugiere: <b>%s</b>") % snmp_model,
                    'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                })
            except Exception as e:
                _logger.error("[SNMP] Error creando actividad: %s", e)
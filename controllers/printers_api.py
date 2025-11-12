# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
import re
import logging

_logger = logging.getLogger(__name__)

NUM_CORE_RE = re.compile(r'(\d{2,5})')  # 2 a 5 dígitos: 224, 4525, 4505, 3435, etc.

def _norm(s):
    """Normaliza strings eliminando espacios extra"""
    return (s or '').strip()

def parse_model(text):
    """
    Extrae familia (aprox), núcleo numérico y variante.
    p.ej. "iR-ADV 4535 III" -> ('IR-ADV', '4535', 'III')
    """
    t = _norm(text)
    if not t:
        _logger.debug("[SNMP Parser] Texto vacío recibido")
        return (None, None, None)

    # familia: primeras "palabras" alfabéticas antes del número
    # variante: lo que viene después del número
    m = NUM_CORE_RE.search(t)
    fam = None
    core = None
    var  = None
    
    if m:
        core = m.group(1)
        before = t[:m.start()].strip()
        after  = t[m.end():].strip()
        # Familia = lo alfabético principal (normalize guiones/espacios)
        fam = re.sub(r'[^A-Za-z\-]+', ' ', before).strip() or None
        var = after or None
        _logger.debug("[SNMP Parser] Parseado '%s' -> Familia: %s, Core: %s, Variante: %s", 
                     t, fam, core, var)
    else:
        _logger.warning("[SNMP Parser] No se encontró núcleo numérico en: %s", t)

    # Normalizaciones sencillas
    if fam:
        fam = fam.replace('iR', 'IR').replace('iRC', 'IRC')
        fam = re.sub(r'\s+', ' ', fam)
    if var:
        # Dejar solo marcas roman numerals o cortas
        var = var.replace('Series', '').strip()
        var = re.sub(r'\s+', ' ', var)

    return (fam, core, var)

def infer_tipo_color(model_text):
    """
    Heurística mejorada: si el nombre contiene C/color -> 'color', si no 'monocromatica'
    """
    t = (model_text or '').lower()
    
    # Patrones más específicos para detectar color
    color_patterns = [
        r'\bc\b',                    # Solo 'C' como palabra independiente
        r'color',                    # Palabra color explícita
        r'irc\b',                    # Canon IRC
        r'mp\s*c\b',                 # Ricoh MP C
        r'bizhub\s*c\b',             # Konica Minolta Bizhub C
        r'taskalfa\s*c\b',           # Kyocera TASKalfa C
        r'imagerunner\s*c\b',        # Canon ImageRunner C
        r'imagerunner\s*advance\s*c\b',  # Canon IR-ADV C
        r'mpc\d+',                   # Ricoh compacto MPC
        r'ir-adv\s*c',               # Canon IR-ADV C
    ]
    
    for pattern in color_patterns:
        if re.search(pattern, t):
            _logger.debug("[SNMP] Detectado como COLOR por patrón '%s' en: %s", pattern, model_text)
            return 'color'
    
    _logger.debug("[SNMP] Detectado como MONOCROMÁTICA: %s", model_text)
    return 'monocromatica'

def find_logistics_user(env):
    """
    Intenta encontrar un usuario de logística para asignar actividades.
    """
    _logger.debug("[SNMP] Buscando usuario de logística...")
    usr = env['res.users'].search([('groups_id.name', 'ilike', 'logística')], limit=1)
    if not usr:
        _logger.debug("[SNMP] No se encontró usuario de logística, usando admin")
        usr = env.ref('base.user_admin', raise_if_not_found=False)
    else:
        _logger.debug("[SNMP] Usuario de logística encontrado: %s", usr.name)
    return usr

def ensure_brand(env, brand_name):
    """
    Asegura (o crea) la marca en marca.marca si tu modelo lo permite.
    Si no deseas crear marcas automáticamente, cambia a búsqueda simple.
    """
    if not brand_name:
        _logger.debug("[SNMP] No se proporcionó nombre de marca")
        return False
    
    Marca = env['marca.marca']
    brand = Marca.search([('name', '=ilike', brand_name.strip())], limit=1)
    
    if brand:
        _logger.info("[SNMP] Marca existente encontrada: %s (ID: %s)", brand.name, brand.id)
        return brand.id
    
    # Crear marca simple si no existe
    try:
        brand = Marca.create({'name': brand_name.strip()})
        _logger.info("[SNMP] Marca CREADA: %s (ID: %s)", brand.name, brand.id)
        return brand.id
    except Exception as e:
        _logger.error("[SNMP] Error creando marca '%s': %s", brand_name, e)
        return False

def get_default_tipo_maquina(env):
    """Obtiene el tipo de máquina por defecto desde parámetros del sistema"""
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_tipo_maquina_id')
    try:
        tipo_id = int(param) if param else None
        if tipo_id:
            _logger.debug("[SNMP] Tipo de máquina por defecto: %s", tipo_id)
        else:
            _logger.warning("[SNMP] No hay tipo de máquina por defecto configurado")
        return tipo_id
    except Exception as e:
        _logger.error("[SNMP] Error obteniendo tipo de máquina por defecto: %s", e)
        return None

def get_default_precio(env):
    """Obtiene el precio por defecto desde parámetros del sistema"""
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_precio_venta')
    try:
        precio = float(param) if param else 0.0
        _logger.debug("[SNMP] Precio por defecto: %.2f", precio)
        return precio
    except Exception as e:
        _logger.error("[SNMP] Error obteniendo precio por defecto: %s", e)
        return 0.0

class SNMPPublicController(http.Controller):

    @http.route('/snmp/intake', type='json', auth='public', methods=['POST'], csrf=False)
    def snmp_intake(self, **kwargs):
        """
        Endpoint público para recibir datos SNMP.
        Espera JSON con: serial, model, brand, total_counter
        No crea sat.sat. Solo actualiza si la serie existe.
        """
        payload = request.jsonrequest or {}
        
        _logger.info("="*80)
        _logger.info("[SNMP INTAKE] Nueva solicitud recibida")
        _logger.info("[SNMP INTAKE] Payload completo: %s", payload)
        
        serial = _norm(payload.get('serial'))
        model_snmp = _norm(payload.get('model'))
        brand = _norm(payload.get('brand'))
        total_counter = payload.get('total_counter')

        _logger.info("[SNMP INTAKE] Serial: %s | Modelo: %s | Marca: %s | Contador: %s",
                    serial or 'N/A', model_snmp or 'N/A', brand or 'N/A', total_counter or 'N/A')

        # Validación de serial
        if not serial:
            _logger.error("[SNMP INTAKE] ERROR: Serial requerido pero no proporcionado")
            return {'ok': False, 'error': 'serial requerido'}

        Sat = request.env['sat.sat'].sudo()
        Mod = request.env['modelo.maquina'].sudo()

        # 1) Encontrar equipo por serie
        _logger.info("[SNMP] Buscando equipo con serie: %s", serial)
        sat = Sat.search([('serie_id', '=', serial)], limit=1)
        
        if not sat:
            _logger.warning("[SNMP] ❌ Serie '%s' NO encontrada en sat.sat; ignorando solicitud", serial)
            return {'ok': True, 'skipped': 'sat.sat no encontrado por serie'}
        
        _logger.info("[SNMP] ✅ Equipo encontrado: %s (ID: %s)", sat.display_name, sat.id)
        _logger.info("[SNMP] Modelo actual del equipo: %s", sat.name.name if sat.name else 'SIN MODELO')

        # 2) Resolver modelo por núcleo numérico
        _logger.info("[SNMP] Parseando modelo SNMP: %s", model_snmp)
        fam_snmp, core_snmp, var_snmp = parse_model(model_snmp)
        
        _logger.info("[SNMP] Parseando modelo ACTUAL del equipo: %s", sat.name.name if sat.name else 'N/A')
        fam_cur, core_cur, var_cur = parse_model(sat.name.name if sat.name else None)

        # 3) Si no hay modelo detectado (sin core), solo actualiza contador y sale
        if not core_snmp:
            _logger.warning("[SNMP] ⚠️ No se pudo extraer núcleo del modelo SNMP: %s", model_snmp)
            self._safe_update_counters(sat, total_counter)
            sat.message_post(body=_("SNMP recibido sin núcleo identificable. Modelo bruto: %s") % (model_snmp or '—'))
            _logger.info("[SNMP] Proceso finalizado (sin núcleo identificable)")
            return {'ok': True, 'updated_counters': True, 'note': 'modelo no parseable'}

        _logger.info("[SNMP] Núcleo extraído SNMP: %s | Núcleo actual: %s", core_snmp, core_cur or 'N/A')

        # 4) Buscar EXACTO por nombre (model_snmp normalizado)
        _logger.info("[SNMP] Buscando modelo EXACTO: %s", model_snmp)
        exact = Mod.search([('name', '=ilike', model_snmp)], limit=1)
        
        if exact:
            _logger.info("[SNMP] ✅ Modelo EXACTO encontrado: %s (ID: %s)", exact.name, exact.id)
        else:
            _logger.info("[SNMP] ❌ No se encontró modelo exacto")

        # 5) Si no exacto, buscar mismo núcleo (+marca si se puede)
        candidate = False
        if not exact:
            _logger.info("[SNMP] Buscando candidatos por núcleo: %s", core_snmp)
            dom = []
            
            if brand:
                _logger.info("[SNMP] Filtrando por marca: %s", brand)
                brand_obj = request.env['marca.marca'].sudo().search([('name', '=ilike', brand)], limit=1)
                if brand_obj:
                    dom.append(('marca_id', '=', brand_obj.id))
                    _logger.info("[SNMP] Marca encontrada en sistema: %s (ID: %s)", brand_obj.name, brand_obj.id)
                else:
                    _logger.warning("[SNMP] Marca '%s' no encontrada en sistema", brand)
            
            # Buscar todos y filtrar por núcleo en Python
            mods = Mod.search(dom) if dom else Mod.search([])
            _logger.info("[SNMP] Modelos a evaluar: %s", len(mods))
            
            for m in mods:
                _, core_m, _ = parse_model(m.name)
                if core_m and (core_m == core_snmp):
                    candidate = m
                    _logger.info("[SNMP] Candidato encontrado por núcleo: %s", m.name)
                    # Si además coincide variante, mejor
                    if var_snmp and m.name.lower().endswith(var_snmp.lower()):
                        candidate = m
                        _logger.info("[SNMP] ✅ Mejor candidato (con variante): %s", m.name)
                        break

        target_model = exact or candidate
        
        if target_model:
            _logger.info("[SNMP] 🎯 Modelo objetivo seleccionado: %s (ID: %s)", 
                        target_model.name, target_model.id)
        else:
            _logger.info("[SNMP] ❌ No se encontró modelo objetivo en sistema")

        # 6) Si el equipo ya tiene modelo y el núcleo difiere, NO cambiar; notificar Logística
        if sat.name:
            _, core_current, _ = parse_model(sat.name.name)
            if core_current and (core_current != core_snmp):
                _logger.warning("[SNMP] 🚨 MISMATCH DE NÚCLEO DETECTADO!")
                _logger.warning("[SNMP] Núcleo actual: %s | Núcleo SNMP: %s", core_current, core_snmp)
                _logger.warning("[SNMP] Modelo actual: %s | Modelo SNMP: %s", sat.name.name, model_snmp)
                
                self._safe_update_counters(sat, total_counter)
                self._notify_core_mismatch(sat, model_snmp, sat.name.name)
                
                _logger.info("[SNMP] Actividad creada para logística - revisar cambio de modelo")
                return {
                    'ok': True,
                    'warning': 'core_mismatch',
                    'current_model': sat.name.name,
                    'snmp_model': model_snmp
                }

        # 7) Si encontramos un modelo destino, asignarlo
        if target_model:
            self._safe_update_counters(sat, total_counter)
            
            if sat.name and sat.name.id == target_model.id:
                # Ya está asignado
                _logger.info("[SNMP] ℹ️ Modelo ya estaba asignado correctamente: %s", target_model.name)
                return {'ok': True, 'assigned': 'unchanged', 'model': target_model.name}
            
            modelo_anterior = sat.name.name if sat.name else 'Sin modelo'
            sat.write({'name': target_model.id})
            _logger.info("[SNMP] ✅ Modelo ACTUALIZADO: %s -> %s", modelo_anterior, target_model.name)
            
            sat.message_post(body=_("Modelo actualizado por SNMP a: %s (desde: %s)") %
                                  (target_model.name, modelo_anterior))
            return {'ok': True, 'assigned': 'existing', 'model': target_model.name}

        # 8) No existe modelo compatible -> intentar CREAR en modelo.maquina
        _logger.info("[SNMP] Intentando CREAR nuevo modelo: %s", model_snmp)
        created = self._try_create_model(Mod, model_snmp, brand)
        
        if created:
            _logger.info("[SNMP] ✅ Modelo CREADO exitosamente: %s (ID: %s)", created.name, created.id)
            self._safe_update_counters(sat, total_counter)
            sat.write({'name': created.id})
            sat.message_post(body=_("Modelo creado y asignado por SNMP: %s") % created.name)
            return {'ok': True, 'assigned': 'created', 'model': created.name}

        # 9) No se pudo crear (faltan parámetros requeridos) -> sugerir y notificar
        _logger.warning("[SNMP] ⚠️ No se pudo crear modelo automáticamente: %s", model_snmp)
        _logger.info("[SNMP] Creando sugerencia para creación manual")
        
        self._safe_update_counters(sat, total_counter)
        self._suggest_model(sat, model_snmp)
        
        _logger.info("[SNMP] Proceso finalizado - modelo pendiente de creación manual")
        _logger.info("="*80)
        
        return {'ok': True, 'suggested': model_snmp, 'note': 'pendiente de creación manual'}

    # ---------------- Métodos Internos ----------------

    def _safe_update_counters(self, sat, total_counter):
        """Actualiza el contador del equipo de forma segura"""
        vals = {}
        
        if total_counter is not None:
            try:
                vals['contometro'] = str(total_counter)
                _logger.info("[SNMP] Actualizando contador: %s -> %s", 
                           sat.contometro or 'N/A', total_counter)
            except Exception as e:
                _logger.error("[SNMP] Error convirtiendo contador a string: %s", e)
        
        if vals:
            try:
                sat.sudo().write(vals)
                _logger.info("[SNMP] ✅ Contador actualizado exitosamente")
            except Exception as e:
                _logger.error("[SNMP] ❌ Error actualizando contador: %s", e)

    def _notify_core_mismatch(self, sat, snmp_model, current_model):
        """Notifica diferencia de núcleo entre modelo actual y detectado"""
        _logger.info("[SNMP] Generando notificación de mismatch para equipo ID: %s", sat.id)
        
        # Post en chatter
        try:
            sat.message_post(
                body=_("⚠️ <b>Diferencia de núcleo detectada por SNMP</b><br/>"
                       "Detectado: <b>%s</b><br/>"
                       "Actual: <b>%s</b><br/>"
                       "Revisar posible reclamo o modificación de precio.")
                     % (snmp_model or '—', current_model or '—'))
            _logger.info("[SNMP] Mensaje publicado en chatter")
        except Exception as e:
            _logger.error("[SNMP] Error publicando mensaje en chatter: %s", e)
        
        # Actividad a logística
        usr = find_logistics_user(request.env)
        if usr:
            try:
                request.env['mail.activity'].sudo().create({
                    'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                    'res_id': sat.id,
                    'user_id': usr.id,
                    'summary': _("Revisar cambio de modelo (núcleo distinto)"),
                    'note': _("SNMP detectó modelo: <b>%s</b><br/>Actual: <b>%s</b><br/>"
                             "Verificar si corresponde a cambio legítimo o requiere ajuste de precio.") 
                           % (snmp_model or '—', current_model or '—'),
                    'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                })
                _logger.info("[SNMP] ✅ Actividad creada para usuario: %s", usr.name)
            except Exception as e:
                _logger.error("[SNMP] ❌ Error creando actividad: %s", e)

    def _suggest_model(self, sat, snmp_model):
        """Crea sugerencia de modelo para creación manual"""
        _logger.info("[SNMP] Generando sugerencia de modelo: %s", snmp_model)
        
        # Sugerencia en chatter
        try:
            sat.message_post(
                body=_("💡 <b>Sugerencia de modelo por SNMP</b><br/>"
                       "Modelo detectado: <b>%s</b><br/>"
                       "Este modelo no existe en el sistema. Se requiere creación manual.") 
                     % (snmp_model or '—'))
            _logger.info("[SNMP] Sugerencia publicada en chatter")
        except Exception as e:
            _logger.error("[SNMP] Error publicando sugerencia: %s", e)
        
        # Actividad a logística
        usr = find_logistics_user(request.env)
        if usr:
            try:
                request.env['mail.activity'].sudo().create({
                    'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                    'res_id': sat.id,
                    'user_id': usr.id,
                    'summary': _("Crear/Asignar modelo sugerido por SNMP"),
                    'note': _("SNMP sugiere modelo: <b>%s</b><br/>"
                             "Por favor crear este modelo en el sistema o asignar uno equivalente.") 
                           % (snmp_model or '—'),
                    'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                })
                _logger.info("[SNMP] ✅ Actividad de sugerencia creada para: %s", usr.name)
            except Exception as e:
                _logger.error("[SNMP] ❌ Error creando actividad de sugerencia: %s", e)

    def _try_create_model(self, Mod, model_name, brand):
        """
        Crea modelo.maquina solo si hay parámetros mínimos:
        - marca (crea si no existe)
        - tipo_maquina_id desde parámetro del sistema
        - precio_venta (parámetro o 0.0)
        """
        _logger.info("[SNMP CREATE] Iniciando creación de modelo: %s", model_name)
        
        env = request.env
        if not model_name:
            _logger.error("[SNMP CREATE] ❌ Nombre de modelo vacío")
            return False

        # Resolver marca
        brand_id = ensure_brand(env, brand) if brand else False
        if brand and not brand_id:
            _logger.warning("[SNMP CREATE] No se pudo crear/encontrar marca: %s", brand)
        
        # Obtener parámetros requeridos
        tipo_maquina_id = get_default_tipo_maquina(env)
        precio = get_default_precio(env)
        tipo_color = infer_tipo_color(model_name)

        _logger.info("[SNMP CREATE] Parámetros: Marca ID: %s | Tipo Máquina: %s | Precio: %.2f | Color: %s",
                    brand_id or 'N/A', tipo_maquina_id or 'N/A', precio, tipo_color)

        if not tipo_maquina_id:
            _logger.error("[SNMP CREATE] ❌ Falta parámetro 'snmp.default_tipo_maquina_id' - no se puede crear modelo")
            _logger.error("[SNMP CREATE] Configurar en: Ajustes > Parámetros del Sistema")
            return False

        vals = {
            'name': model_name,
            'marca_id': brand_id or False,
            'tipo_id': tipo_color,
            'precio_venta': precio,
            'tipo_maquina_id': tipo_maquina_id,
        }
        
        _logger.info("[SNMP CREATE] Valores para crear: %s", vals)
        
        try:
            created = Mod.create(vals)
            _logger.info("[SNMP CREATE] ✅ Modelo creado exitosamente: %s (ID: %s)", created.name, created.id)
            return created
        except Exception as e:
            _logger.error("[SNMP CREATE] ❌ Error creando modelo '%s': %s", model_name, str(e))
            _logger.exception("[SNMP CREATE] Traceback completo:")
            return False
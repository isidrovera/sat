# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
import re
import logging

_logger = logging.getLogger(__name__)

NUM_CORE_RE = re.compile(r'(\d{2,5})')  # 2 a 5 dígitos: 224, 4525, 4505, 3435, etc.

def _norm(s):
    return (s or '').strip()

def parse_model(text):
    """
    Extrae familia (aprox), núcleo numérico y variante.
    p.ej. "iR-ADV 4535 III" -> ('IR-ADV', '4535', 'III')
    """
    t = _norm(text)
    if not t:
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
    Heurística: si el nombre contiene C/color -> 'color', si no 'monocromatica'
    """
    t = (model_text or '').lower()
    if re.search(r'\b(c|color|irc|mp c|bizhub c|taskalfa c)\b', t):
        return 'color'
    return 'monocromatica'

def find_logistics_user(env):
    """
    Intenta encontrar un usuario de logística para asignar actividades.
    """
    usr = env['res.users'].search([('groups_id.name', 'ilike', 'logística')], limit=1)
    if not usr:
        usr = env.ref('base.user_admin', raise_if_not_found=False)
    return usr

def ensure_brand(env, brand_name):
    """
    Asegura (o crea) la marca en marca.marca si tu modelo lo permite.
    Si no deseas crear marcas automáticamente, cambia a búsqueda simple.
    """
    if not brand_name:
        return False
    Marca = env['marca.marca']
    brand = Marca.search([('name', '=ilike', brand_name.strip())], limit=1)
    if brand:
        return brand.id
    # Crear marca simple si no existe (ajusta si tu modelo tiene más requisitos)
    brand = Marca.create({'name': brand_name.strip()})
    return brand.id

def get_default_tipo_maquina(env):
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_tipo_maquina_id')
    try:
        return int(param) if param else None
    except Exception:
        return None

def get_default_precio(env):
    param = env['ir.config_parameter'].sudo().get_param('snmp.default_precio_venta')
    try:
        return float(param) if param else 0.0
    except Exception:
        return 0.0

class SNMPPublicController(http.Controller):

    @http.route('/snmp/intake', type='json', auth='public', methods=['POST'], csrf=False)
    def snmp_intake(self, **kwargs):
        """
        Endpoint público de pruebas.
        Espera JSON con: serial, model, brand, total_counter, ip
        No crea sat.sat. Solo actualiza si la serie existe.
        """
        payload = request.jsonrequest or {}
        serial = _norm(payload.get('serial'))
        model_snmp = _norm(payload.get('model'))
        brand = _norm(payload.get('brand'))
        total_counter = payload.get('total_counter')
        ip = _norm(payload.get('ip'))

        if not serial:
            return {'ok': False, 'error': 'serial requerido'}

        Sat = request.env['sat.sat'].sudo()
        Mod = request.env['modelo.maquina'].sudo()

        # 1) Encontrar equipo por serie
        sat = Sat.search([('serie_id', '=', serial)], limit=1)
        if not sat:
            _logger.info("[SNMP] Serie %s no existe en sat.sat; ignorando.", serial)
            return {'ok': True, 'skipped': 'sat.sat no encontrado por serie'}

        # 2) Resolver modelo por núcleo numérico
        fam_snmp, core_snmp, var_snmp = parse_model(model_snmp)
        fam_cur, core_cur, var_cur = parse_model(sat.name.name if sat.name else None)

        # 3) Si no hay modelo detectado (sin core), solo actualiza contador y sale
        if not core_snmp:
            self._safe_update_counters(sat, total_counter, ip)
            sat.message_post(body=_("SNMP recibido sin núcleo identificable. Modelo bruto: %s") % (model_snmp or '—'))
            return {'ok': True, 'updated_counters': True, 'note': 'modelo no parseable'}

        # 4) Buscar EXACTO por nombre (model_snmp normalizado)
        exact = Mod.search([('name', '=ilike', model_snmp)], limit=1)

        # 5) Si no exacto, buscar mismo núcleo (+marca si se puede)
        candidate = False
        if not exact:
            dom = []
            if brand:
                # unir por marca si puedes
                brand_id = request.env['marca.marca'].sudo().search([('name', '=ilike', brand)], limit=1)
                if brand_id:
                    dom.append(('marca_id', '=', brand_id.id))
            # buscar todos y filtrar por núcleo en Python (por rendimiento podrías indexar un campo serie_base)
            mods = Mod.search(dom) if dom else Mod.search([])
            for m in mods:
                _, core_m, _ = parse_model(m.name)
                if core_m and (core_m == core_snmp):
                    candidate = m
                    # si además coincide variante, mejor
                    if var_snmp and m.name.lower().endswith(var_snmp.lower()):
                        candidate = m
                        break

        target_model = exact or candidate

        # 6) Si el equipo ya tiene modelo y el núcleo difiere, NO cambiar; notificar Logística
        if sat.name:
            _, core_current, _ = parse_model(sat.name.name)
            if core_current and (core_current != core_snmp):
                self._safe_update_counters(sat, total_counter, ip)
                self._notify_core_mismatch(sat, model_snmp, sat.name.name)
                return {
                    'ok': True,
                    'warning': 'core_mismatch',
                    'current_model': sat.name.name,
                    'snmp_model': model_snmp
                }

        # 7) Si encontramos un modelo destino, asignarlo
        if target_model:
            self._safe_update_counters(sat, total_counter, ip)
            if sat.name and sat.name.id == target_model.id:
                # Ya está asignado
                return {'ok': True, 'assigned': 'unchanged', 'model': target_model.name}
            sat.write({'name': target_model.id})
            sat.message_post(body=_("Modelo actualizado por SNMP a: %s (desde: %s)") %
                                  (target_model.name, sat.name.name if sat.name else '—'))
            return {'ok': True, 'assigned': 'existing', 'model': target_model.name}

        # 8) No existe modelo compatible -> intentar CREAR en modelo.maquina
        created = self._try_create_model(Mod, model_snmp, brand)
        if created:
            self._safe_update_counters(sat, total_counter, ip)
            sat.write({'name': created.id})
            sat.message_post(body=_("Modelo creado y asignado por SNMP: %s") % created.name)
            return {'ok': True, 'assigned': 'created', 'model': created.name}

        # 9) No se pudo crear (faltan parámetros requeridos) -> sugerir y notificar
        self._safe_update_counters(sat, total_counter, ip)
        self._suggest_model(sat, model_snmp)
        return {'ok': True, 'suggested': model_snmp, 'note': 'pendiente de creación manual'}

    # ---------------- Internos ----------------

    def _safe_update_counters(self, sat, total_counter, ip):
        vals = {}
        # contometro es Char en tu modelo
        if total_counter is not None:
            try:
                vals['contometro'] = str(total_counter)
            except Exception:
                pass
        # Si tienes un campo IP, añade aquí (ejemplo 'ultima_ip'); si no, omite
        if ip and 'ultima_ip' in sat._fields:
            vals['ultima_ip'] = ip
        if vals:
            sat.sudo().write(vals)

    def _notify_core_mismatch(self, sat, snmp_model, current_model):
        # Post en chatter
        sat.message_post(
            body=_("Diferencia de núcleo detectada por SNMP. Detectado: <b>%s</b>; Actual: <b>%s</b>. "
                   "Revisar reclamo/modificación de precio.")
                 % (snmp_model or '—', current_model or '—'))
        # Actividad a logística (si se puede)
        usr = find_logistics_user(request.env)
        if usr:
            request.env['mail.activity'].sudo().create({
                'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                'res_id': sat.id,
                'user_id': usr.id,
                'summary': _("Revisar cambio de modelo (núcleo distinto)"),
                'note': _("SNMP detectó modelo: %s. Actual: %s.") % (snmp_model or '—', current_model or '—'),
                'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
            })

    def _suggest_model(self, sat, snmp_model):
        # Sugerencia en chatter + actividad
        sat.message_post(body=_("Sugerencia de modelo por SNMP: <b>%s</b> (no creado automáticamente).") % (snmp_model or '—'))
        usr = find_logistics_user(request.env)
        if usr:
            request.env['mail.activity'].sudo().create({
                'res_model_id': request.env['ir.model']._get_id('sat.sat'),
                'res_id': sat.id,
                'user_id': usr.id,
                'summary': _("Crear/Asignar modelo sugerido"),
                'note': _("SNMP sugiere: %s") % (snmp_model or '—'),
                'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
            })

    def _try_create_model(self, Mod, model_name, brand):
        """
        Crea modelo.maquina solo si hay parámetros mínimos:
        - marca (crea si no existe)
        - tipo_maquina_id desde parámetro del sistema
        - precio_venta (parámetro o 0.0)
        """
        env = request.env
        if not model_name:
            return False

        brand_id = ensure_brand(env, brand) if brand else False
        tipo_maquina_id = get_default_tipo_maquina(env)
        precio = get_default_precio(env)
        tipo_id = infer_tipo_color(model_name)

        if not tipo_maquina_id:
            # No tenemos cómo cumplir el required -> no crear
            _logger.warning("[SNMP] Falta 'snmp.default_tipo_maquina_id'; no se crea modelo '%s'", model_name)
            return False

        vals = {
            'name': model_name,
            'marca_id': brand_id or False,
            'tipo_id': tipo_id,
            'precio_venta': precio,
            'tipo_maquina_id': tipo_maquina_id,
        }
        try:
            created = Mod.create(vals)
            return created
        except Exception as e:
            _logger.error("[SNMP] Error creando modelo '%s': %s", model_name, e)
            return False

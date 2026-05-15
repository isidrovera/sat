import calendar
import requests
import uuid
from urllib.parse import urlencode
from odoo.exceptions import UserError, ValidationError
import io
import qrcode
import re
import base64
from io import BytesIO
import xlwt
from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
class UnidadAlquiler(models.Model):
    _inherit = 'alquiler'

     # CAMPOS PARA SISTEMA DE BLOQUEO
    estado_bloqueo = fields.Selection([
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido por Mora'),
        ('bloqueado', 'Bloqueado Remotamente'),
        ('no_accesible', 'No Accesible para Bloqueo'),
        ('pendiente_bloqueo', 'Pendiente de Bloqueo'),
        ('pendiente_desbloqueo', 'Pendiente de Desbloqueo')
    ], string='Estado de Servicio', default='activo', tracking=True)

    motivo_bloqueo = fields.Text(string='Motivo del Bloqueo/Suspensión', tracking=True)
    fecha_bloqueo = fields.Datetime(string='Fecha de Bloqueo', readonly=True, tracking=True)
    fecha_desbloqueo = fields.Datetime(string='Fecha de Desbloqueo', readonly=True, tracking=True)
    usuario_bloqueo = fields.Many2one('res.users', string='Usuario que Bloqueó', readonly=True)

    acceso_remoto_disponible = fields.Boolean(
        string='Acceso Remoto Disponible', 
        default=True,
        help="Indica si el equipo puede ser bloqueado/desbloqueado remotamente"
    )

    ip_equipo = fields.Char(string='IP del Equipo', tracking=True)

    notificado_bloqueo = fields.Boolean(string='Notificado Bloqueo', default=False)
    notificado_desbloqueo = fields.Boolean(string='Notificado Desbloqueo', default=False)

    asesor_ventas_id = fields.Many2one('res.users', string='Asesor de Ventas', tracking=True)
    soporte_tecnico_id = fields.Many2one('res.users', string='Soporte Técnico Asignado', tracking=True)

    observaciones_bloqueo = fields.Text(string='Observaciones de Bloqueo')

    def action_suspender_servicio(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo == 'suspendido':
            raise UserError("El servicio ya está suspendido")
        self.write({
            'estado_bloqueo': 'suspendido',
            'motivo_bloqueo': motivo or 'Suspendido por mora de pagos',
            'fecha_bloqueo': fields.Datetime.now(),
            'usuario_bloqueo': usuario_id or self.env.user.id,
            'notificado_bloqueo': False
        })
        self._enviar_notificacion_suspension()
        self.message_post(
            body=f"⚠️ Servicio suspendido: {motivo or 'Mora de pagos'}",
            message_type='notification'
        )
        return True

    def action_bloquear_equipo(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo == 'bloqueado':
            raise UserError("El equipo ya está bloqueado")
        
        # Bloquear directamente sin verificar acceso remoto
        self.write({
            'estado_bloqueo': 'bloqueado',
            'fecha_bloqueo': fields.Datetime.now(),
            'motivo_bloqueo': motivo or 'Bloqueo remoto por suspensión de servicio',
            'usuario_bloqueo': usuario_id or self.env.user.id,
            'notificado_bloqueo': False
        })
        
        # Siempre enviar notificación de bloqueo exitoso
        self._enviar_notificacion_bloqueo_exitoso()
        
        self.message_post(
            body=f"🔒 Equipo bloqueado: {motivo or 'Bloqueo remoto por suspensión de servicio'}",
            message_type='notification'
        )
        
        return {'success': True, 'message': 'Equipo bloqueado exitosamente'}

    def action_desbloquear_equipo(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo not in ['bloqueado', 'suspendido']:
            raise UserError("El equipo no está bloqueado")
        
        # Desbloquear directamente sin verificar acceso remoto
        self.write({
            'estado_bloqueo': 'activo',
            'fecha_desbloqueo': fields.Datetime.now(),
            'motivo_bloqueo': False,
            'observaciones_bloqueo': False,
            'usuario_bloqueo': usuario_id or self.env.user.id,
            'notificado_desbloqueo': False
        })
        
        # Siempre enviar notificación de desbloqueo exitoso
        self._enviar_notificacion_desbloqueo_exitoso()
        
        self.message_post(
            body="🔓 Equipo desbloqueado exitosamente",
            message_type='notification'
        )
        
        return {'success': True, 'message': 'Equipo desbloqueado exitosamente'}

    def _ejecutar_bloqueo_remoto(self):
        try:
            if not self.ip_equipo:
                return {'success': False, 'error': 'IP del equipo no configurada'}
            url = f"http://{self.ip_equipo}/api/block"
            response = requests.post(url, timeout=30, json={
                'action': 'block',
                'reason': self.motivo_bloqueo
            })
            if response.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Error HTTP: {response.status_code}'}
        except Exception as e:
            _logger.error(f"Error al bloquear equipo {self.serie}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _ejecutar_desbloqueo_remoto(self):
        try:
            if not self.ip_equipo:
                return {'success': False, 'error': 'IP del equipo no configurada'}
            url = f"http://{self.ip_equipo}/api/unblock"
            response = requests.post(url, timeout=30, json={'action': 'unblock'})
            if response.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Error HTTP: {response.status_code}'}
        except Exception as e:
            _logger.error(f"Error al desbloquear equipo {self.serie}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _enviar_notificacion_suspension(self):
        """Envía notificación de suspensión a grupos y contactos"""
        mensaje = """⚠️ *SERVICIO SUSPENDIDO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Motivo: {}
    Dirección: {}

    Se ha suspendido el servicio técnico.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo,
            self.direccion
        )
        
        # Usar el método que maneja grupos Y usuarios
        self._enviar_a_contactos_responsables(mensaje)
    def _enviar_notificacion_bloqueo_exitoso(self):
        mensaje = """🔒 *EQUIPO BLOQUEADO EXITOSAMENTE*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Fecha: {}
    IP: {}

    El equipo ha sido bloqueado remotamente.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M'),
            self.ip_equipo or 'No configurada'
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_bloqueo_fallido(self):
        mensaje = """❌ *ERROR AL BLOQUEAR EQUIPO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Error: {}

    Se requiere bloqueo manual del equipo.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_desbloqueo_exitoso(self):
        mensaje = """🔓 *EQUIPO DESBLOQUEADO EXITOSAMENTE*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Fecha: {}

    El equipo ha sido desbloqueado. Se puede usar normal.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_desbloqueo_fallido(self):
        mensaje = """❌ *ERROR AL DESBLOQUEAR EQUIPO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Error: {}

    Se requiere desbloqueo manual del equipo.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_no_accesible(self):
        mensaje = """⚠️ *EQUIPO NO ACCESIBLE PARA BLOQUEO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado: NO ACCESIBLE

    Se requiere intervención manual para suspender el servicio.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_a_contactos_responsables(self, mensaje):
        """Envía mensaje a grupos y contactos responsables con logging detallado"""
        _logger.info(f"========== INICIO ENVÍO NOTIFICACIONES - Equipo: {self.serie} ==========")
        _logger.info(f"Grupo Notificaciones ID: {self.grupo_notificaciones_id}")
        _logger.info(f"Grupo Asesor ID: {self.grupo_asesor_ventas_id}")
        _logger.info(f"Asesor Ventas: {self.asesor_ventas_id.name if self.asesor_ventas_id else 'No asignado'}")
        
        enviados = []
        errores = []
        
        # 1. Enviar a grupo de notificaciones principal
        if self.grupo_notificaciones_id:
            _logger.info(f"Intentando enviar a grupo notificaciones: {self.grupo_notificaciones_id}")
            try:
                resultado = self._send_whatsapp_notification(self.grupo_notificaciones_id, mensaje)
                if resultado:
                    enviados.append(f"Grupo Notificaciones: {self.grupo_notificaciones_id}")
                    _logger.info(f"✅ ÉXITO: Enviado a grupo notificaciones {self.grupo_notificaciones_id}")
                else:
                    errores.append(f"Grupo Notificaciones: {self.grupo_notificaciones_id}")
                    _logger.error(f"❌ ERROR: No se pudo enviar a grupo notificaciones {self.grupo_notificaciones_id}")
            except Exception as e:
                errores.append(f"Grupo Notificaciones: {self.grupo_notificaciones_id} - Error: {str(e)}")
                _logger.error(f"❌ EXCEPCIÓN al enviar a grupo notificaciones: {str(e)}")
        else:
            _logger.warning("⚠️ No hay grupo de notificaciones configurado")
        
        # 2. Enviar a grupo del asesor de ventas
        if self.grupo_asesor_ventas_id:
            _logger.info(f"Intentando enviar a grupo asesor: {self.grupo_asesor_ventas_id}")
            try:
                resultado = self._send_whatsapp_notification(self.grupo_asesor_ventas_id, mensaje)
                if resultado:
                    enviados.append(f"Grupo Asesor: {self.grupo_asesor_ventas_id}")
                    _logger.info(f"✅ ÉXITO: Enviado a grupo asesor {self.grupo_asesor_ventas_id}")
                else:
                    errores.append(f"Grupo Asesor: {self.grupo_asesor_ventas_id}")
                    _logger.error(f"❌ ERROR: No se pudo enviar a grupo asesor {self.grupo_asesor_ventas_id}")
            except Exception as e:
                errores.append(f"Grupo Asesor: {self.grupo_asesor_ventas_id} - Error: {str(e)}")
                _logger.error(f"❌ EXCEPCIÓN al enviar a grupo asesor: {str(e)}")
        else:
            _logger.warning("⚠️ No hay grupo de asesor configurado")
        
        # 3. Enviar al número del asesor (solo si no hay grupos configurados)
        if not self.grupo_notificaciones_id and not self.grupo_asesor_ventas_id:
            _logger.info("No hay grupos configurados, intentando enviar directamente al asesor")
            if self.asesor_ventas_id and self.asesor_ventas_id.mobile_phone:
                phone_asesor = self._clean_phone_number(self.asesor_ventas_id.mobile_phone)
                _logger.info(f"Teléfono asesor limpio: {phone_asesor}")
                try:
                    resultado = self._send_whatsapp_notification(phone_asesor, mensaje)
                    if resultado:
                        enviados.append(f"Asesor directo: {self.asesor_ventas_id.name} ({phone_asesor})")
                        _logger.info(f"✅ ÉXITO: Enviado a asesor {self.asesor_ventas_id.name}")
                    else:
                        errores.append(f"Asesor directo: {self.asesor_ventas_id.name}")
                        _logger.error(f"❌ ERROR: No se pudo enviar a asesor {self.asesor_ventas_id.name}")
                except Exception as e:
                    errores.append(f"Asesor directo: {self.asesor_ventas_id.name} - Error: {str(e)}")
                    _logger.error(f"❌ EXCEPCIÓN al enviar a asesor: {str(e)}")
            else:
                _logger.warning("⚠️ No hay asesor con teléfono configurado")
        else:
            _logger.info("Hay grupos configurados, no se envía al asesor directamente")
        
        # Resumen final
        _logger.info("========== RESUMEN DE ENVÍOS ==========")
        if enviados:
            _logger.info(f"✅ Enviados exitosamente: {len(enviados)}")
            for enviado in enviados:
                _logger.info(f"  - {enviado}")
        else:
            _logger.error("❌ No se enviaron notificaciones exitosamente")
        
        if errores:
            _logger.error(f"❌ Errores en envíos: {len(errores)}")
            for error in errores:
                _logger.error(f"  - {error}")
        
        _logger.info(f"========== FIN ENVÍO NOTIFICACIONES ==========\n")
        
        # Registrar en el chatter del equipo
        if enviados or errores:
            resumen = "📤 <b>Notificaciones enviadas:</b><br/>"
            if enviados:
                resumen += "✅ Exitosos:<br/>" + "<br/>".join([f"• {e}" for e in enviados])
            if errores:
                resumen += "<br/>❌ Fallidos:<br/>" + "<br/>".join([f"• {e}" for e in errores])
            
            self.message_post(body=resumen, message_type='notification')

    def _clean_phone_number(self, phone):
        if not phone:
            return None
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone.startswith('51'):
            phone = '51' + phone
        return phone

    def _send_whatsapp_notification(self, phone, message):
        """Envía notificación a WhatsApp (grupos o números individuales)"""
        if not phone:
            _logger.warning("Teléfono/grupo no especificado")
            return False
            
        try:
            # ✅ Nueva API
            url = 'https://boot.andessolutioncopiers.com/api/send-message'
            data = {
                'to': phone,  # Funciona para ambos: "51999999999" o "51990649502-1484267115@g.us"
                'message': message
            }
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': 'wg_fc215093f007df7ff4a32c04c7d8170d11960583e3a1b43a695037f5a627d3e3'
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                # ✅ Verificar respuesta de la API
                if response_data.get('success'):
                    _logger.info(f"✅ Notificación enviada exitosamente a {phone}")
                    return True
                else:
                    error_msg = response_data.get('error', 'Error desconocido')
                    _logger.error(f"❌ Error en API: {error_msg} para {phone}")
                    return False
            else:
                _logger.error(f"❌ Error HTTP al enviar a {phone}: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            _logger.error(f"❌ Timeout al enviar notificación WhatsApp a {phone}")
            return False
        except requests.exceptions.RequestException as e:
            _logger.error(f"❌ Error de red al enviar notificación WhatsApp: {str(e)}")
            return False
        except Exception as e:
            _logger.error(f"❌ Error inesperado al enviar notificación WhatsApp: {str(e)}")
            return False
     # Reemplazar los campos Char por estos:

    grupo_notificaciones_id = fields.Selection(
        selection='_get_grupos_whatsapp',
        string='Grupo de Notificaciones',
        help="Grupo de WhatsApp para notificaciones de bloqueo/desbloqueo"
    )

    grupo_asesor_ventas_id = fields.Selection(
        selection='_get_grupos_whatsapp', 
        string='Grupo Asesor de Ventas',
        help="Grupo de WhatsApp del asesor de ventas"
    )
    @api.model
    def _get_grupos_whatsapp(self):
        """Obtiene la lista de grupos de WhatsApp desde la API"""
        try:
            url = 'https://boot.andessolutioncopiers.com/api/groups'
            headers = {
                'x-api-key': 'wg_fc215093f007df7ff4a32c04c7d8170d11960583e3a1b43a695037f5a627d3e3'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    grupos = []
                    for grupo in data['data']:
                        grupos.append((
                            grupo['id'], 
                            f"{grupo['name']} ({grupo.get('participants', 0)} miembros)"
                        ))
                    return grupos
            return [('', 'Error al cargar grupos')]
        except Exception as e:
            _logger.exception(f"Error al obtener grupos: {str(e)}")
            return [('', 'Error al cargar grupos')]
    def action_refresh_grupos(self):
        """Refresca la lista de grupos disponibles"""
        # Forzar recálculo del selection
        self._fields['grupo_notificaciones_id'].selection = self._get_grupos_whatsapp()
        self._fields['grupo_asesor_ventas_id'].selection = self._get_grupos_whatsapp()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Grupos actualizados',
                'message': 'Lista de grupos de WhatsApp actualizada',
                'type': 'success',
            }
        }

    # ============================================
    # MÉTODOS PARA AGREGAR AL MODELO EXISTENTE
    # ============================================

    def action_marcar_pendiente_bloqueo(self):
        """Marca el equipo como pendiente de bloqueo"""
        self.ensure_one()
        if self.estado_bloqueo == 'pendiente_bloqueo':
            raise UserError("El equipo ya está marcado como pendiente de bloqueo")
        
        self.write({
            'estado_bloqueo': 'pendiente_bloqueo',
            'motivo_bloqueo': self.motivo_bloqueo or 'Pendiente de bloqueo - Requiere acción',
            'fecha_bloqueo': fields.Datetime.now(),
            'usuario_bloqueo': self.env.user.id,
            'notificado_bloqueo': False
        })
        
        # Llamar notificación
        self._enviar_notificacion_pendiente_bloqueo()
        
        self.message_post(
            body="⏳ Equipo marcado como pendiente de bloqueo",
            message_type='notification'
        )
        return True

    def action_marcar_pendiente_desbloqueo(self):
        """Marca el equipo como pendiente de desbloqueo"""
        self.ensure_one()
        if self.estado_bloqueo != 'bloqueado':
            raise UserError("Solo se puede marcar como pendiente de desbloqueo un equipo bloqueado")
        
        self.write({
            'estado_bloqueo': 'pendiente_desbloqueo',
            'observaciones_bloqueo': self.observaciones_bloqueo or 'Pendiente de desbloqueo - Pago procesándose',
            'usuario_bloqueo': self.env.user.id,
            'notificado_desbloqueo': False
        })
        
        # Llamar notificación
        self._enviar_notificacion_pendiente_desbloqueo()
        
        self.message_post(
            body="⏳ Equipo marcado como pendiente de desbloqueo",
            message_type='notification'
        )
        return True

    def action_marcar_no_accesible(self):
        """Marca el equipo como no accesible para bloqueo remoto"""
        self.ensure_one()
        
        self.write({
            'estado_bloqueo': 'no_accesible',
            'acceso_remoto_disponible': False,
            'motivo_bloqueo': 'Equipo no accesible para bloqueo remoto',
            'fecha_bloqueo': fields.Datetime.now(),
            'usuario_bloqueo': self.env.user.id,
            'notificado_bloqueo': False
        })
        
        # Ya tienes esta notificación
        self._enviar_notificacion_no_accesible()
        
        self.message_post(
            body="❌ Equipo marcado como NO ACCESIBLE para bloqueo remoto",
            message_type='notification'
        )
        return True

    def action_reactivar_servicio(self):
        """Reactiva el servicio desde cualquier estado"""
        self.ensure_one()
        if self.estado_bloqueo == 'activo':
            raise UserError("El servicio ya está activo")
        
        estado_anterior = self.estado_bloqueo
        
        self.write({
            'estado_bloqueo': 'activo',
            'fecha_desbloqueo': fields.Datetime.now(),
            'motivo_bloqueo': False,
            'observaciones_bloqueo': False,
            'acceso_remoto_disponible': True,
            'usuario_bloqueo': self.env.user.id,
            'notificado_bloqueo': False,
            'notificado_desbloqueo': False
        })
        
        # Llamar notificación de reactivación
        self._enviar_notificacion_reactivacion(estado_anterior)
        
        self.message_post(
            body=f"✅ Servicio reactivado (estado anterior: {estado_anterior})",
            message_type='notification'
        )
        return True

    def action_verificar_acceso_remoto(self):
        """Verifica si el equipo tiene acceso remoto disponible"""
        self.ensure_one()
        
        if not self.ip_equipo:
            raise UserError("No hay IP configurada para este equipo")
        
        try:
            # Intentar conexión de prueba
            url = f"http://{self.ip_equipo}/api/status"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                self.write({
                    'acceso_remoto_disponible': True
                })
                mensaje = "✅ Acceso remoto verificado exitosamente"
            else:
                self.write({
                    'acceso_remoto_disponible': False
                })
                mensaje = "❌ No se pudo verificar el acceso remoto"
                
        except:
            self.write({
                'acceso_remoto_disponible': False
            })
            mensaje = "❌ Error al verificar acceso remoto"
        
        self.message_post(body=mensaje, message_type='notification')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Verificación completada',
                'message': mensaje,
                'type': 'success' if self.acceso_remoto_disponible else 'warning',
            }
        }

    # ============================================
    # NOTIFICACIONES FALTANTES
    # ============================================

    def _enviar_notificacion_pendiente_bloqueo(self):
        """Notificación para estado pendiente_bloqueo"""
        mensaje = """⏳ *EQUIPO PENDIENTE DE BLOQUEO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado: PENDIENTE DE BLOQUEO
    Motivo: {}
    Fecha: {}

    ⚠️ Se requiere acción para proceder con el bloqueo remoto.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo or 'Pendiente de bloqueo por mora',
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        
        # Solo enviar usando _enviar_a_contactos_responsables
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_pendiente_desbloqueo(self):
        """Notificación para estado pendiente_desbloqueo"""
        mensaje = """⏳ *EQUIPO PENDIENTE DE DESBLOQUEO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado: PENDIENTE DE DESBLOQUEO
    Observaciones: {}
    Fecha: {}

    💰 Pago en proceso de verificación. Se desbloqueará una vez confirmado.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.observaciones_bloqueo or 'Pago pendiente de confirmación',
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        
        # Solo enviar usando _enviar_a_contactos_responsables
        self._enviar_a_contactos_responsables(mensaje)


    def _enviar_notificacion_reactivacion(self, estado_anterior):
        """Notificación cuando se reactiva el servicio desde cualquier estado"""
        mensaje = """✅ *SERVICIO REACTIVADO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado anterior: {}
    Estado actual: ACTIVO
    Fecha: {}

    ✔️ El servicio ha sido reactivado completamente.
    El equipo está operativo.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            dict(self._fields['estado_bloqueo'].selection).get(estado_anterior, estado_anterior).upper(),
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        
        # Solo enviar usando _enviar_a_contactos_responsables
        self._enviar_a_contactos_responsables(mensaje)
    @api.model
    def get_dashboard_data(self):
        data = {
            'equipos_activos': self.search_count([('estado_bloqueo', '=', 'activo')]),
            'equipos_suspendidos': self.search_count([('estado_bloqueo', '=', 'suspendido')]),
            'equipos_bloqueados': self.search_count([('estado_bloqueo', '=', 'bloqueado')]),
            'equipos_no_accesibles': self.search_count([('estado_bloqueo', '=', 'no_accesible')]),
            'pendientes_bloqueo': self.search_count([('estado_bloqueo', '=', 'pendiente_bloqueo')]),
            'pendientes_desbloqueo': self.search_count([('estado_bloqueo', '=', 'pendiente_desbloqueo')])
        }
        equipos_atencion = self.search([
            ('estado_bloqueo', 'in', ['pendiente_bloqueo', 'pendiente_desbloqueo', 'no_accesible'])
        ], limit=10)
        data['equipos_atencion'] = [{
            'id': eq.id,
            'cliente': eq.cliente_id.name,
            'serie': eq.serie,
            'modelo': eq.name.name,
            'estado': eq.estado_bloqueo,
            'motivo': eq.motivo_bloqueo
        } for eq in equipos_atencion]
        return data
    @api.model
    def buscar_equipos_web(self, busqueda):
        domain = ['|', '|', '|',
                ('serie', 'ilike', busqueda),
                ('cliente_id.name', 'ilike', busqueda),
                ('name.name', 'ilike', busqueda),
                ('marca', 'ilike', busqueda)]
        equipos = self.search(domain, limit=50)
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido']
            })
        return resultado

       

    @api.model
    def get_dashboard_data_alquilados(self):
        """Obtiene datos del dashboard solo para equipos alquilados"""
        base_domain = [('estado_alquiler_id', '=', 'alquilada')]
        
        data = {
            'equipos_activos': self.search_count(base_domain + [('estado_bloqueo', '=', 'activo')]),
            'equipos_suspendidos': self.search_count(base_domain + [('estado_bloqueo', '=', 'suspendido')]),
            'equipos_bloqueados': self.search_count(base_domain + [('estado_bloqueo', '=', 'bloqueado')]),
            'equipos_no_accesibles': self.search_count(base_domain + [('estado_bloqueo', '=', 'no_accesible')]),
            'pendientes_bloqueo': self.search_count(base_domain + [('estado_bloqueo', '=', 'pendiente_bloqueo')]),
            'pendientes_desbloqueo': self.search_count(base_domain + [('estado_bloqueo', '=', 'pendiente_desbloqueo')]),
            'total_alquilados': self.search_count(base_domain)
        }
        
        # Obtener equipos que requieren atención (solo alquilados)
        equipos_atencion = self.search(
            base_domain + [('estado_bloqueo', 'in', ['pendiente_bloqueo', 'pendiente_desbloqueo', 'no_accesible'])],
            limit=10,
            order='fecha_bloqueo desc'
        )
        
        data['equipos_atencion'] = [{
            'id': eq.id,
            'cliente': eq.cliente_id.name,
            'serie': eq.serie,
            'modelo': eq.name.name,
            'estado': eq.estado_bloqueo,
            'estado_label': dict(eq._fields['estado_bloqueo'].selection)[eq.estado_bloqueo],
            'motivo': eq.motivo_bloqueo,
            'fecha_bloqueo': eq.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if eq.fecha_bloqueo else ''
        } for eq in equipos_atencion]
        
        return data

    @api.model
    def get_equipos_alquilados_inicial(self, limit=50):
        """Obtiene lista inicial de equipos alquilados para mostrar al cargar la página"""
        equipos = self.search([
            ('estado_alquiler_id', '=', 'alquilada')
        ], limit=limit, order='serie asc')
        
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'],
                'contacto': equipo.contacto_id,
                'celular': equipo.celular,
                'correo': equipo.correo_
            })
        
        return resultado

    @api.model
    def buscar_equipos_alquilados_web(self, busqueda, estado_filtro=''):
        """Busca equipos solo en estado alquilada"""
        base_domain = [('estado_alquiler_id', '=', 'alquilada')]
        
        # Agregar filtro de búsqueda por texto
        if busqueda:
            search_domain = ['|', '|', '|',
                            ('serie', 'ilike', busqueda),
                            ('cliente_id.name', 'ilike', busqueda),
                            ('name.name', 'ilike', busqueda),
                            ('marca', 'ilike', busqueda)]
            base_domain = base_domain + search_domain
        
        # Agregar filtro por estado de bloqueo
        if estado_filtro:
            base_domain.append(('estado_bloqueo', '=', estado_filtro))
        
        equipos = self.search(base_domain, limit=100, order='serie asc')
        
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'],
                'contacto': equipo.contacto_id,
                'celular': equipo.celular,
                'correo': equipo.correo_
            })
        
        return resultado

    @api.model
    def filtrar_equipos_por_estado_bloqueo(self, estado_bloqueo):
        """Filtra equipos alquilados por estado de bloqueo específico"""
        domain = [
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', estado_bloqueo)
        ]
        
        equipos = self.search(domain, limit=100, order='serie asc')
        
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'],
                'contacto': equipo.contacto_id,
                'celular': equipo.celular,
                'correo': equipo.correo_
            })
        
        return resultado

    def write(self, vals):
        """Sobrescribir write para sincronizar estado de bloqueo entre equipos del mismo cliente"""
        
        # Ejecutar el write original primero
        res = super(UnidadAlquiler, self).write(vals)
        
        # Sincronizar estado de bloqueo entre equipos del mismo cliente
        if 'estado_bloqueo' in vals:
            for record in self:
                if record.cliente_id:
                    # Log para debugging
                    _logger.info(f"SINCRONIZACIÓN INICIADA para equipo {record.serie} del cliente {record.cliente_id.name}")
                    
                    # Buscar otros equipos del mismo cliente (excluyendo el actual)
                    otros_equipos = self.search([
                        ('id', '!=', record.id),
                        ('cliente_id', '=', record.cliente_id.id),
                        ('estado_alquiler_id', '=', 'alquilada')  # Solo equipos alquilados
                    ])
                    
                    _logger.info(f"Equipos encontrados para sincronizar: {len(otros_equipos)} - Series: {otros_equipos.mapped('serie')}")
                    
                    if otros_equipos:
                        # Preparar valores para actualización
                        update_vals = {
                            'estado_bloqueo': vals.get('estado_bloqueo'),
                            'notificado_bloqueo': False,
                            'notificado_desbloqueo': False
                        }
                        
                        # Agregar campos adicionales según el estado
                        if vals.get('estado_bloqueo') in ['suspendido', 'bloqueado']:
                            update_vals.update({
                                'motivo_bloqueo': vals.get('motivo_bloqueo', record.motivo_bloqueo),
                                'fecha_bloqueo': vals.get('fecha_bloqueo', record.fecha_bloqueo),
                                'usuario_bloqueo': vals.get('usuario_bloqueo', record.usuario_bloqueo),
                            })
                        elif vals.get('estado_bloqueo') == 'activo':
                            update_vals.update({
                                'fecha_desbloqueo': vals.get('fecha_desbloqueo', record.fecha_desbloqueo),
                                'motivo_bloqueo': False,
                                'observaciones_bloqueo': False,
                                'acceso_remoto_disponible': True,
                            })
                        
                        # Log de valores que se van a actualizar
                        _logger.info(f"Valores a actualizar: {update_vals}")
                        
                        try:
                            # OPCIÓN 1: Usar write() normal (recomendado para mantener consistencia)
                            # Temporalmente desactivar la sincronización para evitar recursión
                            context_sin_sync = dict(self.env.context, skip_sync=True)
                            otros_equipos.with_context(context_sin_sync).write(update_vals)
                            
                            # Invalidar cache para reflejar cambios
                            otros_equipos.invalidate_cache()
                            
                            _logger.info(f"✅ ÉXITO: Actualización completada para {len(otros_equipos)} equipos")
                            
                            # Log para auditoría en el equipo original
                            estado_nombre = dict(self._fields['estado_bloqueo'].selection).get(vals.get('estado_bloqueo'))
                            record.message_post(
                                body=f"🔄 <b>Sincronización automática:</b><br/>"
                                    f"Estado '{estado_nombre}' aplicado automáticamente a {len(otros_equipos)} equipos adicionales del cliente <b>{record.cliente_id.name}</b><br/>"
                                    f"<small>Series afectadas: {', '.join(otros_equipos.mapped('serie'))}</small>",
                                message_type='notification'
                            )
                            
                            # Log en cada equipo sincronizado
                            for equipo in otros_equipos:
                                equipo.message_post(
                                    body=f"🔄 <b>Estado sincronizado automáticamente</b><br/>"
                                        f"Nuevo estado: <span class='badge badge-info'>{estado_nombre}</span><br/>"
                                        f"Origen: Equipo {record.serie} del mismo cliente<br/>"
                                        f"Usuario: {self.env.user.name}",
                                    message_type='notification'
                                )
                                
                        except Exception as e:
                            _logger.error(f"❌ ERROR en sincronización: {str(e)}")
                            # Continuar con el proceso aunque falle la sincronización
                            record.message_post(
                                body=f"⚠️ <b>Error en sincronización automática:</b><br/>"
                                    f"No se pudo sincronizar con otros equipos del cliente.<br/>"
                                    f"Error: {str(e)}",
                                message_type='notification'
                            )
                    else:
                        _logger.info("No se encontraron otros equipos para sincronizar")
        
        return res
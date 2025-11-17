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
                'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816'
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
                'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816'
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
        estados_permitidos_para_cambio = ['sin_revisar', 'para_revision']
        estados_problema = ['con_problemas', 'de_partes']
        estado_final_no_notificar = 'entregada'

        tipo_revision_modificado = 'tipo_revision' in vals
        prioridad_modificada = 'prioridad' in vals

        isidro_partner_id = self.get_isidro_partner_id()

        # 📌 Snapshot ANTES de escribir, para detectar cambios de modelo/tipo/contómetro
        cambios_previos = {}
        for record in self:
            cambios_previos[record.id] = {
                'modelo_anterior': record.name.name if record.name else '',
                'tipo_anterior': record.tipo_id,
                'contometro_anterior': record.contometro or '0',
            }

        for record in self:
            estado_actual = record.estado_ventas_id
            nuevo_estado = vals.get('estado_ventas_id', estado_actual)

            _logger.debug(
                f"Inicio de write para ID {record.id}. "
                f"Estado actual: {estado_actual}, Nuevo estado: {nuevo_estado}, Valores: {vals}"
            )

            # Primera parte: Manejo de tipo_revision y prioridad
            if estado_actual in estados_permitidos_para_cambio:
                if tipo_revision_modificado or prioridad_modificada:
                    if vals.get('tipo_revision') or vals.get('prioridad'):
                        vals['estado_ventas_id'] = 'para_revision'
                        # Convertir la hora UTC a hora de Perú al guardar
                        utc_now = datetime.utcnow()
                        peru_tz = pytz.timezone('America/Lima')
                        peru_dt = pytz.utc.localize(utc_now).astimezone(peru_tz)
                        vals['fecha_para_revision'] = peru_dt.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')

                        _logger.info(
                            f"Estado cambiado a 'para_revision' para ID {record.id} "
                            f"por modificación en tipo_revision o prioridad."
                        )

                        if isidro_partner_id:
                            user_name = self.env.user.name
                            record_name = record.name.name
                            serie = record.serie_id
                            message = f"""Se ha colocado una nueva máquina para revisión.

Detalles del equipo:
- Nombre: {record_name}
- Serie: {serie}
- Fecha de registro: {peru_dt.strftime('%Y-%m-%d %H:%M:%S')} (hora Lima)

Modificado por: {user_name}"""
                            record.message_post(
                                body=message,
                                partner_ids=[isidro_partner_id],
                                subtype='mail.mt_comment',
                            )
                    else:
                        vals['estado_ventas_id'] = 'sin_revisar'
                        vals['fecha_para_revision'] = None
                        _logger.info(
                            f"Estado regresado a 'sin_revisar' para ID {record.id}."
                        )

            # Segunda parte: Manejo de estados de problema y notificaciones
            if 'estado_ventas_id' in vals:
                nuevo_estado = vals['estado_ventas_id']

                # Si cambia a estado de problema
                if nuevo_estado in estados_problema:
                    _logger.debug(
                        f"Cambiando a estado de problema para ID {record.id}. "
                        f"Ejecutando super().write()."
                    )
                    result = super(SatSat, self).write(vals)

                    try:
                        record.enviar_mensaje_problema_asesora()
                        _logger.info(
                            f"Notificación de problema enviada para ID {record.id}."
                        )
                    except Exception as e:
                        _logger.error(
                            f"Error al enviar notificaciones para ID {record.id}: {e}"
                        )

                    return result

                # Si cambia de un estado problemático a otro no problemático
                elif estado_actual in estados_problema and nuevo_estado not in estados_problema:
                    _logger.debug(
                        f"Saliendo de estado de problema para ID {record.id}. "
                        f"Limpiando descripción."
                    )
                    vals['descripcion'] = False
                    vals['activador'] = 'no'
                    message = _(
                        "Se limpió la descripción al cambiar el estado de '%s' a '%s'"
                    ) % (estado_actual, nuevo_estado)
                    record.message_post(body=message)

                # Nueva lógica: Enviar notificación de disponibilidad si aplica
                if estado_actual in estados_problema and nuevo_estado != estado_final_no_notificar:
                    _logger.debug(
                        f"Enviando notificación de disponibilidad para ID {record.id}."
                    )
                    try:
                        record.enviar_notificacion_disponibilidad()
                        _logger.info(
                            f"Notificación de disponibilidad enviada para ID {record.id}."
                        )
                    except Exception as e:
                        _logger.error(
                            f"Error al enviar notificación de disponibilidad para ID {record.id}: {e}"
                        )

        # Ejecutar la escritura final después de todas las validaciones y notificaciones
        _logger.debug(f"Finalizando write para registros {self.ids} con valores: {vals}")
        result = super(SatSat, self).write(vals)

        # 🔍 Después de escribir, revisar anomalías de modelo y contómetro
        for record in self:
            prev = cambios_previos.get(record.id) or {}
            modelo_anterior = prev.get('modelo_anterior', '')
            tipo_anterior = prev.get('tipo_anterior')
            contometro_anterior = prev.get('contometro_anterior', '0')

            modelo_nuevo = record.name.name if record.name else ''
            tipo_nuevo = record.tipo_id
            contometro_nuevo = record.contometro or '0'

            # 1) Cambios raros de modelo (velocidad / color)
            self._check_model_anomalies(
                record,
                modelo_anterior,
                modelo_nuevo,
                tipo_anterior,
                tipo_nuevo,
            )

            # 2) Saltos raros de contómetro
            self._check_counter_anomalies(
                record,
                contometro_anterior,
                contometro_nuevo,
            )

        return result
    def _check_model_anomalies(self, record, modelo_anterior, modelo_nuevo, tipo_anterior, tipo_nuevo):
        """
        Detecta casos como:
        - Canon 4525  -> 4535 (cambio de velocidad dentro misma familia)
        - bizhub 364e -> bizhub C364e (cambio de mono a color)
        y genera:
        - mensaje en chatter
        - correo usando plantilla: sat.email_template_snmp_model_change
        """
        # Si no cambió el modelo, no hacemos nada
        if not modelo_anterior or not modelo_nuevo or modelo_anterior == modelo_nuevo:
            return

        # Extraer último bloque numérico de cada modelo (núcleo de velocidad)
        def _get_core_digits(text):
            nums = re.findall(r'\d+', text or '')
            return nums[-1] if nums else None

        core_old = _get_core_digits(modelo_anterior)
        core_new = _get_core_digits(modelo_nuevo)

        posible_cambio_velocidad = False
        detalle_velocidad = ""

        if core_old and core_new and core_old != core_new:
            try:
                if len(core_old) == len(core_new):
                    # caso típico 4525 -> 4535
                    if len(core_old) == 4 and core_old[:2] == core_new[:2]:
                        posible_cambio_velocidad = True
                        detalle_velocidad = f"{core_old[-2:]} → {core_new[-2:]}"
                    else:
                        posible_cambio_velocidad = True
                        detalle_velocidad = f"{core_old} → {core_new}"
            except Exception:
                pass

        # Cambio de tipo (color/mono)
        cambio_tipo = False
        if tipo_anterior and tipo_nuevo and tipo_anterior != tipo_nuevo:
            cambio_tipo = True

        # Si no hay nada relevante, salir
        if not posible_cambio_velocidad and not cambio_tipo:
            return

        isidro_partner_id = record.get_isidro_partner_id()
        url = record.generate_record_url(record)

        # 🔹 Mensaje en chatter con todos los detalles
        lineas = [
            "Se detectó una actualización relevante del modelo (posiblemente por SNMP o edición manual):",
            f"• Modelo anterior: <b>{modelo_anterior}</b>",
            f"• Modelo nuevo: <b>{modelo_nuevo}</b>",
        ]

        if posible_cambio_velocidad:
            lineas.append(f"• Posible cambio de velocidad (núcleo): <b>{detalle_velocidad}</b>")

        if cambio_tipo:
            sel_tipo = dict(record._fields['tipo_id'].selection)
            txt_old = sel_tipo.get(tipo_anterior, tipo_anterior)
            txt_new = sel_tipo.get(tipo_nuevo, tipo_nuevo)
            lineas.append(f"• Cambio de tipo: <b>{txt_old}</b> → <b>{txt_new}</b>")

        lineas.append(f"• Equipo: <b>{record.name.name if record.name else ''}</b> / Serie: <b>{record.serie_id}</b>")
        lineas.append(f"• Enlace al equipo: {url}")

        body = "<br/>".join(lineas)

        record.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
            partner_ids=[isidro_partner_id] if isidro_partner_id else None,
        )

        # 🔹 Envío de correo usando plantilla
        template = record.env.ref('sat.email_template_snmp_model_change', raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(record.id, force_send=True)
            except Exception as e:
                _logger.error(f"[SNMP Model Alert] Error al enviar correo de cambio de modelo para ID {record.id}: {e}")
    def _check_counter_anomalies(self, record, contometro_anterior, contometro_nuevo):
        """
        Detecta variaciones sospechosas en el contómetro, por ejemplo:
        - 2,000  → 20,000  (x10)
        - 2,000  → 2,000,000 (muchos más dígitos)
        y NO molesta si es algo normal, como:
        - 40,000 → 42,000
        Luego:
        - registra detalle en chatter
        - envía correo usando plantilla: sat.email_template_snmp_counter_anomaly
        """

        # Limpiar a solo dígitos
        old_digits = re.sub(r'[^\d]', '', contometro_anterior or '') or '0'
        new_digits = re.sub(r'[^\d]', '', contometro_nuevo or '') or '0'

        try:
            old_val = int(old_digits)
            new_val = int(new_digits)
        except Exception:
            return

        # Si alguno es cero o el nuevo es menor, no analizamos aquí
        if old_val <= 0 or new_val <= 0 or new_val <= old_val:
            return

        digit_diff = abs(len(str(old_val)) - len(str(new_val)))
        ratio = new_val / float(old_val) if old_val else 0.0

        # Reglas:
        # - muchos más dígitos (ej: 4 → 7)
        # - o incremento >= x10 del valor anterior
        if digit_diff < 2 and ratio < 10.0:
            # incremento normal, no avisamos
            return

        incremento = new_val - old_val
        isidro_partner_id = record.get_isidro_partner_id()
        url = record.generate_record_url(record)

        # 🔹 Detalle completo en chatter
        lineas = [
            "⚠️ Se detectó una variación inusual en el contómetro:",
            f"• Valor anterior: <b>{old_val:,}</b>",
            f"• Valor nuevo: <b>{new_val:,}</b>",
            f"• Incremento: <b>{incremento:,}</b>",
            f"• Multiplicador aproximado: <b>x{ratio:.1f}</b>",
            f"• Equipo: <b>{record.name.name if record.name else ''}</b> / Serie: <b>{record.serie_id}</b>",
            f"• Enlace al equipo: {url}",
        ]

        body = "<br/>".join(lineas)

        record.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
            partner_ids=[isidro_partner_id] if isidro_partner_id else None,
        )

        # 🔹 Envío de correo usando plantilla
        template = record.env.ref('sat.email_template_snmp_counter_anomaly', raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(record.id, force_send=True)
            except Exception as e:
                _logger.error(f"[SNMP Counter Alert] Error al enviar correo de anomalía de contometro para ID {record.id}: {e}")

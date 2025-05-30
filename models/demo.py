# models/alquiler.py - Agregar estos campos y métodos al modelo existente

from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class UnidadAlquiler(models.Model):
    _name = 'alquiler'

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
        if not self.acceso_remoto_disponible:
            self.write({
                'estado_bloqueo': 'no_accesible',
                'motivo_bloqueo': 'Equipo no accesible para bloqueo remoto',
                'usuario_bloqueo': usuario_id or self.env.user.id
            })
            self._enviar_notificacion_no_accesible()
            raise UserError("Este equipo no puede ser bloqueado remotamente")
        if self.estado_bloqueo == 'bloqueado':
            raise UserError("El equipo ya está bloqueado")
        resultado_bloqueo = self._ejecutar_bloqueo_remoto()
        if resultado_bloqueo['success']:
            self.write({
                'estado_bloqueo': 'bloqueado',
                'fecha_bloqueo': fields.Datetime.now(),
                'motivo_bloqueo': motivo or 'Bloqueo remoto por suspensión de servicio',
                'usuario_bloqueo': usuario_id or self.env.user.id,
                'notificado_bloqueo': False
            })
            self._enviar_notificacion_bloqueo_exitoso()
            return {'success': True, 'message': 'Equipo bloqueado exitosamente'}
        else:
            self.write({
                'estado_bloqueo': 'pendiente_bloqueo',
                'motivo_bloqueo': resultado_bloqueo.get('error', 'Error en bloqueo remoto'),
                'usuario_bloqueo': usuario_id or self.env.user.id
            })
            self._enviar_notificacion_bloqueo_fallido()
            return {'success': False, 'message': resultado_bloqueo.get('error', 'Error en bloqueo remoto')}

    def action_desbloquear_equipo(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo not in ['bloqueado', 'suspendido']:
            raise UserError("El equipo no está bloqueado")
        if not self.acceso_remoto_disponible:
            raise UserError("Este equipo no puede ser desbloqueado remotamente")
        resultado_desbloqueo = self._ejecutar_desbloqueo_remoto()
        if resultado_desbloqueo['success']:
            self.write({
                'estado_bloqueo': 'activo',
                'fecha_desbloqueo': fields.Datetime.now(),
                'motivo_bloqueo': False,
                'observaciones_bloqueo': False,
                'usuario_bloqueo': usuario_id or self.env.user.id,
                'notificado_desbloqueo': False
            })
            self._enviar_notificacion_desbloqueo_exitoso()
            return {'success': True, 'message': 'Equipo desbloqueado exitosamente'}
        else:
            self.write({
                'estado_bloqueo': 'pendiente_desbloqueo',
                'motivo_bloqueo': resultado_desbloqueo.get('error', 'Error en desbloqueo remoto'),
                'usuario_bloqueo': usuario_id or self.env.user.id
            })
            self._enviar_notificacion_desbloqueo_fallido()
            return {'success': False, 'message': resultado_desbloqueo.get('error', 'Error en desbloqueo remoto')}

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
        if self.asesor_ventas_id and self.asesor_ventas_id.mobile_phone:
            mensaje_asesor = f"""
⚠️ *SERVICIO SUSPENDIDO*

Cliente: *{self.cliente_id.name}*
Equipo: {self.name.name} - Serie: {self.serie}
Motivo: {self.motivo_bloqueo}
Dirección: {self.direccion}

Se ha suspendido el servicio técnico.
"""
            phone_asesor = self._clean_phone_number(self.asesor_ventas_id.mobile_phone)
            self._send_whatsapp_notification(phone_asesor, mensaje_asesor)

        soporte_users = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('sat.group_soporte_tecnico').id)
        ])

        mensaje_soporte = f"""
🚫 *NO BRINDAR SOPORTE TÉCNICO*

Cliente: *{self.cliente_id.name}*
Equipo: {self.name.name} - Serie: {self.serie}
Estado: SUSPENDIDO
Motivo: {self.motivo_bloqueo}

No proporcionar soporte técnico hasta nuevo aviso.
"""
        for user in soporte_users:
            if user.mobile_phone:
                phone_soporte = self._clean_phone_number(user.mobile_phone)
                self._send_whatsapp_notification(phone_soporte, mensaje_soporte)

    def _enviar_notificacion_bloqueo_exitoso(self):
        mensaje = f"""
🔒 *EQUIPO BLOQUEADO EXITOSAMENTE*

Cliente: *{self.cliente_id.name}*
Equipo: {self.name.name} - Serie: {self.serie}
Fecha: {fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}
IP: {self.ip_equipo}

El equipo ha sido bloqueado remotamente.
"""
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_bloqueo_fallido(self):
        mensaje = f"""
❌ *ERROR AL BLOQUEAR EQUIPO*

Cliente: *{self.cliente_id.name}*
Equipo: {self.name.name} - Serie: {self.serie}
Error: {self.motivo_bloqueo}

Se requiere bloqueo manual del equipo.
"""
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_desbloqueo_exitoso(self):
        mensaje = f"""
🔓 *EQUIPO DESBLOQUEADO EXITOSAMENTE*

Cliente: *{self.cliente_id.name}*
Equipo: {self.name.name} - Serie: {self.serie}
Fecha: {fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}

El equipo ha sido desbloqueado. Se puede brindar soporte normal.
"""
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_no_accesible(self):
        mensaje = f"""
⚠️ *EQUIPO NO ACCESIBLE PARA BLOQUEO*

Cliente: *{self.cliente_id.name}*
Equipo: {self.name.name} - Serie: {self.serie}
Estado: NO ACCESIBLE

Se requiere intervención manual para suspender el servicio.
"""
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_a_contactos_responsables(self, mensaje):
        contactos = []
        if self.asesor_ventas_id and self.asesor_ventas_id.mobile_phone:
            contactos.append(self.asesor_ventas_id.mobile_phone)
        soporte_users = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('sat.group_soporte_tecnico').id)
        ])
        for user in soporte_users:
            if user.mobile_phone:
                contactos.append(user.mobile_phone)
        for phone in contactos:
            clean_phone = self._clean_phone_number(phone)
            self._send_whatsapp_notification(clean_phone, mensaje)

    def _clean_phone_number(self, phone):
        if not phone:
            return None
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone.startswith('51'):
            phone = '51' + phone
        return phone

    def _send_whatsapp_notification(self, phone, message):
        try:
            url = 'https://whatsapp.andessolutioncopiers.com/api/message'
            data = {
                'phone': phone,
                'message': message
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                _logger.info(f"Notificación enviada exitosamente a {phone}")
                return True
            else:
                _logger.error(f"Error al enviar notificación a {phone}: {response.status_code}")
                return False
        except Exception as e:
            _logger.error(f"Error al enviar notificación WhatsApp: {str(e)}")
            return False

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

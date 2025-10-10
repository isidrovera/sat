from odoo import _, models, fields, api, exceptions, _
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
import qrcode
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)
import requests
import json
from odoo.tools import config
from odoo.exceptions import UserError
import zipfile
import io
from odoo.http import request
import uuid



class ReparacionesMensajes(models.Model):
    _inherit = 'reparaciones.reparaciones'
    _description = 'Mensajes de Reparaciones'

    @api.depends('responsable_id.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            if record.responsable_id.mobile_phone:
                # Remove '+' and all types of spaces
                phone = record.responsable_id.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                # Ensure phone starts with '51'
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_mobile_clean = phone
            else:
                record.responsable_mobile_clean = ''
                record.responsable_mobile_clean = ''


    def send_whatsapp_message(self, phone, message):
        """Envía un mensaje de WhatsApp utilizando la API externa."""
        url = 'https://whatsapp.andessolutioncopiers.com/api/message'
        data = {
            'phone': phone,
            'message': message
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data)

        print("Código de estado:", response.status_code)
        print("Respuesta de la API:", response.text)

        # Verificar si la respuesta contiene un cuerpo JSON válido
        try:
            response_json = response.json()
            print("Respuesta JSON:", response_json)
            return response_json
        except json.JSONDecodeError as e:
            error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
            print(error_msg)
            return {"error": error_msg}  # Devuelve un diccionario con la clave 'error' y el mensaje de error como valor
    def get_selection_labels(self):
        selection_labels = {}
        for field_name, field in self._fields.items():
            if field.type == 'selection' and hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    selection = field.selection
                    if callable(selection):
                        selection = selection(self)
                    for option_value, option_label in selection:
                        if option_value == value:
                            selection_labels[field_name] = option_label
                            break
                else:
                    selection_labels[field_name] = 'NA'
        return selection_labels
    def enviar_mensaje_whatsapp_reparaciones(self):
        selection_labels = self.get_selection_labels()
        # Contexto para las plantillas de correo
        context = dict(self.env.context or {})
        context.update({
            'selection_labels': selection_labels
        })
        # Lógica para enviar correos
        template = self.env.ref('sat.email_template_reparaciones')
        template.with_context(**context).send_mail(self.id, force_send=True)

        #additional_template = self.env.ref('sat.email_template_reparacion_creada')
        #additional_template.with_context(**context).send_mail(self.id, force_send=True)

        # Generar URL del registro y la galería de fotos
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_reparaciones_window').id
        menu_id = self.env.ref('sat.reparaciones').id
        record_url = f"{base_url}/web#id={self.id}&view_type=form&model=reparaciones.reparaciones&action={action_id}&menu_id={menu_id}"
        gallery_url = f"{base_url}/gallery/{self.id}"

        # Construir y enviar el mensaje de WhatsApp
        msg = f"""Hola;\n*{self.responsable_id.name if self.responsable_id.name else 'NA'}*\n
    Se te ha asignado la inspección y elaboración del informe de la máquina que se encuentra en el taller.
    
    *REPARACIÓN N°:* {self.name if self.name else 'NA'}
    *Cliente:* {self.cliente_id.name if self.cliente_id.name else 'NA'}
    *Importación:* {self.importacion if self.importacion else 'NA'}
    *Tipo de equipo:* {self.tipo_machine if self.tipo_machine else 'NA'}
    *Marca:* {self.marca if self.marca else 'NA'}
    *Modelo:* {self.maquina_id.name.name if self.maquina_id.name and self.maquina_id.name.name else 'NA'}
    *Serie:* {self.serie_id if self.serie_id else 'NA'}
    *Estado:* {selection_labels.get('estado_id', 'NA')}
    *Tipo de revisión:* {selection_labels.get('tipo_revision', 'NA')}
    *Prioridad:* {selection_labels.get('prioridad', 'NA')}
    *Ubicación:* {selection_labels.get('ubicacion_id', 'NA')}
    *Asesora:* {self.maquina_id.asesora_id if self.maquina_id.asesora_id else 'NA'}

    *Enlaces:*
    - Acceso al registro: {record_url}
    - Galería de fotos: {gallery_url}"""

        if self.responsable_id and self.responsable_mobile_clean:
            phone_number = self.responsable_mobile_clean
            self.send_whatsapp_message(phone_number, msg)

        # Actualizar estado de la reparación
        self.estado_id = 'en_revision'
        return {
            'type': 'ir.actions.act_window_close'  # Cerrar ventana tras completar la acción
        }
    def enviar_mensaje_finalizacion_asesora(self):
        pdf_url = self.generate_pdf_report_url()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        gallery_url = f'{base_url}/gallery/{self.id}'
        action_id = self.env.ref('sat.action_reparaciones_window').id
        menu_id = self.env.ref('sat.reparaciones').id
        record_url = f"{base_url}/web#id={self.id}&view_type=form&model=reparaciones.reparaciones&action={action_id}&menu_id={menu_id}"
        #Registro: {record_url}
        msg = f"""*Reparación Finalizada*
            *Cliente:* {self.cliente_id.name if self.cliente_id.name else 'NA'}
            *Marca:* {self.marca if self.marca else 'NA'}
            *Modelo:* {self.nombre_maquina if self.nombre_maquina else 'NA'}
            *Serie:* {self.serie_id if self.serie_id else 'NA'}
            *Contómetro:* {self.contometrok_id if self.contometrok_id else 'NA'}
            *Estado:* {self.obtener_estado_legible() if self.obtener_estado_legible() else 'NA'}
            *Técnico:* {self.responsable_id.name if self.responsable_id.name else 'NA'}

            *Enlaces:*
            Reporte: {pdf_url}
            Fotos: {gallery_url}
            """

        if self.asesora_mobile_clean:
            phone_number = self.asesora_mobile_clean
            self.send_whatsapp_message(phone_number, msg)
    
# -*- coding: utf-8 -*-
"""SMS por Traccar SMS Gateway. Importar desde models/__init__.py.

Parametros de sistema:
  sat.sms_enabled: True para habilitar (deshabilitado por defecto).
  sat.sms_gateway_url: https://www.traccar.org/sms/ o URL de la app.
  sat.sms_gateway_authorization: token o API key de la app, sin Bearer.

Este archivo no activa alertas automaticamente ni modifica WhatsApp.
Llamar desde el flujo autorizado: ticket._enviar_sms(numero, texto).
success indica aceptacion HTTP, NO entrega al destinatario.
No reintentar automaticamente un resultado unknown: podria duplicar SMS.
"""

import logging
import re
from urllib.parse import urlsplit

import requests

from odoo import models

_logger = logging.getLogger(__name__)


class TicketNotificacionesSms(models.Model):
    _inherit = "ticket.alquiler"

    def _normalizar_numero_sms(self, phone):
        """Un solo destinatario; celulares peruanos locales o internacional."""
        numero = str(phone or "").strip()
        if not numero or not re.fullmatch(r"\+?[0-9\s().-]+", numero):
            return False
        numero = re.sub(r"[\s().-]", "", numero)
        if numero.startswith("00"):
            numero = "+" + numero[2:]
        elif re.fullmatch(r"9[0-9]{8}", numero):
            numero = "+51" + numero
        elif re.fullmatch(r"519[0-9]{8}", numero):
            numero = "+" + numero
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", numero):
            return False
        return numero

    def _enviar_sms(self, phone, message):
        """Metodo interno: no exponer una ruta publica para enviar SMS.

        Retorna success, status, error y status_code cuando corresponde.
        No cambia estados, no envia correos y no registra entregas ficticias.
        """
        parametros = self.env["ir.config_parameter"].sudo()
        habilitado = str(parametros.get_param("sat.sms_enabled", "False"))
        if habilitado.strip().lower() not in ("true", "1", "yes", "si"):
            return {"success": False, "status": "disabled",
                    "error": "El envio de SMS esta deshabilitado."}

        numero = self._normalizar_numero_sms(phone)
        if not numero:
            return {"success": False, "status": "invalid",
                    "error": "Indique un celular peruano de 9 digitos o un numero internacional con +."}
        if not isinstance(message, str) or not message.strip():
            return {"success": False, "status": "invalid",
                    "error": "El mensaje SMS no puede estar vacio."}

        url = (parametros.get_param("sat.sms_gateway_url") or "").strip()
        authorization = (
            parametros.get_param("sat.sms_gateway_authorization") or ""
        ).strip()
        try:
            parsed = urlsplit(url)
            url_valida = (
                parsed.scheme in ("http", "https") and parsed.hostname
                and not parsed.username and not parsed.password
                and not parsed.fragment
            )
        except ValueError:
            url_valida = False
        if not url_valida or not authorization:
            return {"success": False, "status": "configuration_error",
                    "error": "Configure sat.sms_gateway_url y sat.sms_gateway_authorization."}
        if "\r" in authorization or "\n" in authorization:
            return {"success": False, "status": "configuration_error",
                    "error": "La autorizacion SMS contiene saltos de linea."}

        # No registrar tokens, texto, respuesta completa ni numero completo.
        destino = "***" + numero[-4:]
        try:
            response = requests.post(
                url,
                headers={"Authorization": authorization,
                         "Content-Type": "application/json"},
                json={"to": numero, "message": message.strip()},
                timeout=(10, 30),
                allow_redirects=False,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            _logger.warning("SMS: resultado desconocido para %s", destino)
            return {"success": False, "status": "unknown",
                    "error": "No se obtuvo confirmacion. Compruebe la pasarela antes de reenviar para evitar duplicados."}
        except requests.exceptions.RequestException:
            _logger.warning("SMS: error de solicitud para %s", destino)
            return {"success": False, "status": "error",
                    "error": "No se pudo completar la solicitud SMS. Revise la configuracion."}

        status_code = response.status_code
        if not 200 <= status_code < 300:
            _logger.warning("SMS: HTTP %s para %s", status_code, destino)
            return {"success": False,
                    "status": "unknown" if status_code >= 500 else "rejected",
                    "status_code": status_code,
                    "error": "La pasarela SMS respondio HTTP %s." % status_code}

        # La pasarela puede devolver una respuesta vacia o no JSON.
        # No asumir el contrato success de la API de WhatsApp.
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and (
            data.get("success") is False or data.get("error")
        ):
            return {"success": False, "status": "rejected",
                    "status_code": status_code,
                    "error": "La pasarela informo un error al procesar el SMS."}

        _logger.info("SMS: solicitud aceptada por la pasarela para %s", destino)
        return {"success": True, "status": "accepted",
                "status_code": status_code, "error": False}

# -*- coding: utf-8 -*-

import json
import logging
import time

import requests

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SatAIService(models.AbstractModel):
    _name = "sat.ai.service"
    _description = "Servicio IA SAT"

    @api.model
    def analyze_event(self, event, task_type="extract_event", fail_silently=True):
        config = self.env["sat.automation.config"].get_config()

        if config.ai_mode == "disabled":
            _logger.info(
                "[SAT AI][SKIP] event_id=%s reason=disabled",
                event.id,
            )
            return {
                "ok": False,
                "disabled": True,
                "data": {},
                "error": "IA desactivada",
            }

        try:
            prompt = self.env["sat.ai.prompt"].get_active_prompt(task_type)
        except Exception as exc:
            _logger.warning(
                "[SAT AI][NO_PROMPT] event_id=%s task=%s error=%s",
                event.id, task_type, exc,
            )
            if fail_silently:
                return {
                    "ok": False,
                    "data": {},
                    "error": str(exc),
                }
            raise

        providers = self.env["sat.ai.provider"].search(
            [("active", "=", True)],
            order="sequence, id",
        )

        if not providers:
            msg = _("No existen proveedores IA activos.")
            _logger.warning("[SAT AI][NO_PROVIDER] event_id=%s", event.id)
            return {"ok": False, "data": {}, "error": msg}

        last_error = None

        for provider in providers:
            started = time.time()
            try:
                payload = self._build_prompt_payload(event, prompt)
                result = self._call_provider(provider, payload)
                latency_ms = int((time.time() - started) * 1000)

                input_tokens = int(result.get("input_tokens") or 0)
                output_tokens = int(result.get("output_tokens") or 0)
                cost = provider.calculate_cost(input_tokens, output_tokens)

                self.env["sat.ai.usage"].create({
                    "event_id": event.id,
                    "provider_id": provider.id,
                    "prompt_id": prompt.id,
                    "model_name": provider.model_name,
                    "task_type": task_type,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_cost": cost,
                    "latency_ms": latency_ms,
                    "success": True,
                })

                data = result.get("data") or {}
                confidence = float(
                    data.get("confidence")
                    or result.get("confidence")
                    or 0.0
                )

                event.register_ai_result(
                    provider_name=provider.name,
                    model_name=provider.model_name,
                    result=data,
                    confidence=confidence,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    prompt_version=prompt.version,
                    raw_response=result.get("raw"),
                )

                _logger.info(
                    "[SAT AI][SUCCESS] event_id=%s provider=%s model=%s "
                    "confidence=%s latency_ms=%s cost=%s",
                    event.id, provider.name, provider.model_name,
                    confidence, latency_ms, cost,
                )

                return {
                    "ok": True,
                    "data": data,
                    "provider": provider,
                    "confidence": confidence,
                }

            except Exception as exc:
                last_error = exc
                latency_ms = int((time.time() - started) * 1000)

                self.env["sat.ai.usage"].create({
                    "event_id": event.id,
                    "provider_id": provider.id,
                    "prompt_id": prompt.id,
                    "model_name": provider.model_name,
                    "task_type": task_type,
                    "latency_ms": latency_ms,
                    "success": False,
                    "error_message": str(exc),
                })

                event._audit(
                    "ai_provider_error",
                    level="error",
                    message=str(exc),
                    data={
                        "provider": provider.name,
                        "model": provider.model_name,
                    },
                )

                _logger.exception(
                    "[SAT AI][ERROR] event_id=%s provider=%s",
                    event.id, provider.name,
                )

        result = {
            "ok": False,
            "data": {},
            "error": str(last_error or _("Todos los proveedores IA fallaron.")),
        }

        if fail_silently:
            return result

        raise UserError(result["error"])

    @api.model
    def _build_prompt_payload(self, event, prompt):
        """
        Construye el payload del prompt sin usar str.format().

        IMPORTANTE:
        Los prompts pueden contener ejemplos JSON con llaves { }.
        str.format() interpreta esas llaves como placeholders y puede
        provocar KeyError, por ejemplo con:
            {
                "event_type": "string"
            }

        Por eso reemplazamos únicamente los placeholders permitidos:
            {event_json}
            {body}
            {subject}
            {sender}

        El resto del contenido del prompt permanece intacto.
        """
        context = {
            "source": event.source,
            "event_type": event.event_type,
            "sender": event.sender,
            "sender_domain": event.sender_domain,
            "subject": event.subject,
            "body": event.body_plain,
            "serial_number": event.serial_number,
            "partner": (
                event.partner_id.display_name
                if event.partner_id
                else None
            ),
            "equipment": (
                event.equipment_id.display_name
                if event.equipment_id
                else None
            ),
        }

        user_text = prompt.user_template or ""

        replacements = {
            "{event_json}": json.dumps(
                context,
                ensure_ascii=False,
                default=str,
            ),
            "{body}": event.body_plain or "",
            "{subject}": event.subject or "",
            "{sender}": event.sender or "",
        }

        for placeholder, value in replacements.items():
            user_text = user_text.replace(
                placeholder,
                str(value or ""),
            )

        return {
            "system": prompt.system_prompt or "",
            "user": user_text,
            "schema": prompt.expected_json_schema or "",
        }

    @api.model
    def _call_provider(self, provider, payload):
        if provider.provider_type in ("openai", "openai_compatible"):
            return self._call_openai_compatible(provider, payload)
        if provider.provider_type == "gemini":
            return self._call_gemini(provider, payload)
        if provider.provider_type == "anthropic":
            return self._call_anthropic(provider, payload)
        if provider.provider_type == "custom_http":
            return self._call_custom_http(provider, payload)

        raise UserError(
            _("Proveedor no soportado: %s") % provider.provider_type
        )

    @api.model
    def _call_openai_compatible(self, provider, payload):
        base_url = (provider.base_url or "").rstrip("/")
        if not base_url:
            if provider.provider_type == "openai":
                base_url = "https://api.openai.com/v1"
            else:
                raise UserError(_("Debe configurar URL base."))

        headers = {
            "Authorization": "Bearer %s" % provider.api_key,
            "Content-Type": "application/json",
        }
        headers.update(provider.get_extra_headers())

        body = {
            "model": provider.model_name,
            "messages": [
                {"role": "system", "content": payload["system"]},
                {"role": "user", "content": payload["user"]},
            ],
            "temperature": provider.temperature,
            "max_tokens": provider.max_output_tokens,
        }

        if provider.supports_json:
            body["response_format"] = {"type": "json_object"}

        response = self._request(
            provider, "POST",
            "%s/chat/completions" % base_url,
            headers=headers,
            json=body,
        )

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}

        return {
            "data": self._parse_json(content),
            "input_tokens": usage.get("prompt_tokens") or 0,
            "output_tokens": usage.get("completion_tokens") or 0,
            "raw": data,
        }

    @api.model
    def _call_gemini(self, provider, payload):
        base_url = (
            provider.base_url
            or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")

        url = "%s/models/%s:generateContent?key=%s" % (
            base_url, provider.model_name, provider.api_key
        )

        body = {
            "contents": [{
                "parts": [{
                    "text": "%s\n\n%s" % (
                        payload["system"],
                        payload["user"],
                    )
                }]
            }],
            "generationConfig": {
                "temperature": provider.temperature,
                "maxOutputTokens": provider.max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

        response = self._request(
            provider, "POST", url,
            headers={"Content-Type": "application/json"},
            json=body,
        )

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise UserError(_("Gemini no devolvió candidatos."))

        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        content = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata") or {}

        return {
            "data": self._parse_json(content),
            "input_tokens": usage.get("promptTokenCount") or 0,
            "output_tokens": usage.get("candidatesTokenCount") or 0,
            "raw": data,
        }

    @api.model
    def _call_anthropic(self, provider, payload):
        base_url = (
            provider.base_url or "https://api.anthropic.com/v1"
        ).rstrip("/")

        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        headers.update(provider.get_extra_headers())

        body = {
            "model": provider.model_name,
            "system": payload["system"],
            "messages": [{"role": "user", "content": payload["user"]}],
            "temperature": provider.temperature,
            "max_tokens": provider.max_output_tokens,
        }

        response = self._request(
            provider, "POST",
            "%s/messages" % base_url,
            headers=headers,
            json=body,
        )

        data = response.json()
        blocks = data.get("content") or []
        content = "".join(
            x.get("text", "")
            for x in blocks
            if x.get("type") == "text"
        )
        usage = data.get("usage") or {}

        return {
            "data": self._parse_json(content),
            "input_tokens": usage.get("input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "raw": data,
        }

    @api.model
    def _call_custom_http(self, provider, payload):
        if not provider.base_url:
            raise UserError(_("Debe configurar URL HTTP."))

        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = "Bearer %s" % provider.api_key
        headers.update(provider.get_extra_headers())

        response = self._request(
            provider, "POST", provider.base_url,
            headers=headers,
            json={
                "model": provider.model_name,
                "system": payload["system"],
                "prompt": payload["user"],
                "schema": payload["schema"],
            },
        )

        data = response.json()
        return {
            "data": data.get("data") if isinstance(data.get("data"), dict) else data,
            "input_tokens": data.get("input_tokens") or 0,
            "output_tokens": data.get("output_tokens") or 0,
            "raw": data,
        }

    @api.model
    def _request(self, provider, method, url, **kwargs):
        last_error = None
        attempts = (provider.max_retries or 0) + 1

        for attempt in range(attempts):
            try:
                _logger.info(
                    "[SAT AI][HTTP] provider=%s attempt=%s/%s",
                    provider.name, attempt + 1, attempts,
                )

                response = requests.request(
                    method=method,
                    url=url,
                    timeout=provider.timeout_seconds or 45,
                    **kwargs,
                )

                if response.status_code >= 400:
                    raise UserError(
                        _("HTTP %s: %s")
                        % (response.status_code, response.text[:2000])
                    )

                return response

            except Exception as exc:
                last_error = exc
                _logger.exception(
                    "[SAT AI][HTTP][ERROR] provider=%s attempt=%s",
                    provider.name, attempt + 1,
                )
                if attempt < attempts - 1:
                    time.sleep(
                        min(
                            max(provider.retry_delay_seconds or 0, 0)
                            * (2 ** attempt),
                            10,
                        )
                    )

        raise last_error

    @api.model
    def _parse_json(self, content):
        if isinstance(content, dict):
            return content

        txt = (content or "").strip()

        if txt.startswith("```"):
            txt = txt.strip("`").strip()
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()

        try:
            return json.loads(txt)
        except Exception as exc:
            raise UserError(
                _("La IA no devolvió JSON válido: %s") % str(exc)
            )

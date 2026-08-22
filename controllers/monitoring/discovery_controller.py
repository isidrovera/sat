# -*- coding: utf-8 -*-

import logging

from odoo import http, fields, _
from odoo.http import request

from .common import MonitoringApiMixin, MonitoringApiError


_logger = logging.getLogger(__name__)


class MonitoringDiscoveryController(http.Controller, MonitoringApiMixin):

    def _find_existing_device(self, agent, network, host):
        Device = request.env['sat.monitoring.device'].sudo()

        serial = self._clean_text(host.get('serial'))
        mac = self._clean_text(host.get('mac'))
        ip = self._clean_text(host.get('ip'))

        # 1. Serie: identificador preferido cuando está disponible.
        if serial:
            device = Device.search(
                [
                    ('agent_id', '=', agent.id),
                    ('serial', '=', serial),
                ],
                limit=1,
            )
            if device:
                return device

        # 2. MAC dentro del agente.
        if mac:
            device = Device.search(
                [
                    ('agent_id', '=', agent.id),
                    ('mac_address', '=ilike', mac),
                ],
                limit=1,
            )
            if device:
                return device

        # 3. IP dentro de la red.
        if ip:
            device = Device.search(
                [
                    ('network_id', '=', network.id),
                    ('ip_address', '=', ip),
                ],
                limit=1,
            )
            if device:
                return device

        return Device.browse()

    def _prepare_new_device_values(self, agent, network, host):
        model = self._clean_text(host.get('model'))
        serial = self._clean_text(host.get('serial'))
        ip = self._clean_text(host.get('ip'))

        name_parts = [value for value in (model, serial, ip) if value]

        return {
            'name': ' - '.join(name_parts) or _('Equipo SNMP'),
            'agent_id': agent.id,
            'network_id': network.id,
            'partner_id': network.partner_id.id if network.partner_id else False,
            'branch_name': network.branch_name or '',
            'ip_address': ip or False,
            'mac_address': self._clean_text(host.get('mac')) or False,
            'model': model or False,
            'serial': serial or False,
            'monitoring_enabled': bool(network.polling_enabled),
            'inventory_enabled': True,
            'is_confirmed_printer': bool(host.get('is_printer')),
            'discovery_state': 'new',
            'needs_discovery': True,
        }

    def _process_host(self, agent, network, host):
        if not isinstance(host, dict):
            return {
                'ok': False,
                'reason': 'invalid_host_payload',
            }

        ip = self._clean_text(host.get('ip'))
        if not ip:
            return {
                'ok': False,
                'reason': 'ip_required',
            }

        if not self._ip_allowed_in_network(network, ip):
            return {
                'ok': False,
                'ip': ip,
                'reason': 'ip_out_of_scope',
            }

        is_printer = bool(host.get('is_printer'))
        if network.printers_only and not is_printer:
            return {
                'ok': True,
                'ip': ip,
                'ignored': True,
                'reason': 'not_confirmed_printer',
            }

        device = self._find_existing_device(agent, network, host)
        created = False

        if not device:
            if not network.auto_create_devices:
                return {
                    'ok': True,
                    'ip': ip,
                    'created': False,
                    'reason': 'auto_create_disabled',
                }

            device = request.env['sat.monitoring.device'].sudo().create(
                self._prepare_new_device_values(agent, network, host)
            )
            created = True

        # Si el equipo cambió de red dentro del mismo agente, discovery lo corrige.
        update_vals = {}
        if device.network_id != network:
            update_vals['network_id'] = network.id
            update_vals['agent_id'] = agent.id
            if network.partner_id:
                update_vals['partner_id'] = network.partner_id.id
            if network.branch_name:
                update_vals['branch_name'] = network.branch_name

        if is_printer and not device.is_confirmed_printer:
            update_vals['is_confirmed_printer'] = True

        if update_vals:
            device.sudo().write(update_vals)

        identity = {
            'ip': ip,
            'mac': host.get('mac'),
            'hostname': host.get('hostname'),
            'manufacturer': host.get('manufacturer'),
            'brand_code': host.get('brand_code'),
            'model': host.get('model'),
            'model_raw': host.get('model_raw'),
            'serial': host.get('serial'),
            'firmware': host.get('firmware'),
            'enterprise_id': host.get('enterprise_id'),
            'sysdescr': host.get('sysdescr'),
            'technology': host.get('technology'),
            'system_name': host.get('system_name'),
            'system_location': host.get('system_location'),
            'system_contact': host.get('system_contact'),
            'engine_id': host.get('engine_id'),
            'gateway': host.get('gateway'),
            'subnet_mask': host.get('subnet_mask'),
            'ipv6': host.get('ipv6'),
        }

        device.apply_identity_payload(identity)

        # Si no se encontró perfil y la red no permite desconocidos, mantenemos
        # inventario pero evitamos polling periódico hasta revisión.
        if not device.profile_id and not network.monitor_unknown_devices:
            device.sudo().write({
                'monitoring_enabled': False,
                'needs_discovery': True,
                'discovery_reason': 'profile_not_found',
            })

        return {
            'ok': True,
            'id': device.id,
            'ip': device.ip_address,
            'serial': device.serial or '',
            'model': device.model or device.model_raw or '',
            'created': created,
            'confirmed_printer': device.is_confirmed_printer,
            'profile_id': device.profile_id.id if device.profile_id else False,
            'profile_code': device.profile_code or '',
            'needs_discovery': device.needs_discovery,
            'monitoring_enabled': device.monitoring_enabled,
        }

    @http.route(
        '/api/monitoring/agent/discovery',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def discovery(self, **kwargs):
        """
        Payload:
        {
            "network_id": 12,
            "duration_ms": 1234,
            "hosts": [ ... ]
        }
        """
        try:
            agent = self._authenticate_agent()
            payload = self._read_json(required=True)

            network = self._get_agent_network(agent, payload.get('network_id'))
            if not network.discovery_enabled:
                raise MonitoringApiError(
                    _('El discovery está deshabilitado para esta red.'),
                    status=403,
                    code='discovery_disabled',
                )

            hosts = payload.get('hosts') or []
            if not isinstance(hosts, list):
                raise MonitoringApiError(
                    _('hosts debe ser una lista.'),
                    status=400,
                    code='invalid_hosts',
                )

            if len(hosts) > network.max_hosts_per_cycle:
                raise MonitoringApiError(
                    _('La cantidad de hosts excede el límite configurado.'),
                    status=400,
                    code='host_limit_exceeded',
                    details={
                        'limit': network.max_hosts_per_cycle,
                        'received': len(hosts),
                    },
                )

            results = []
            printer_count = 0
            discovered_count = 0

            for host in hosts:
                item = self._process_host(agent, network, host)
                results.append(item)

                if item.get('ok') and not item.get('ignored'):
                    discovered_count += 1
                if item.get('confirmed_printer'):
                    printer_count += 1

            network.register_discovery_result(
                success=True,
                duration_ms=payload.get('duration_ms'),
                host_count=discovered_count,
                printer_count=printer_count,
            )

            return self._ok({
                'network_id': network.id,
                'processed': len(hosts),
                'discovered': discovered_count,
                'printers': printer_count,
                'results': results,
            })

        except Exception as error:
            # Si conocemos la red podemos intentar registrar el error, pero no
            # debemos ocultar la excepción original si eso también falla.
            try:
                payload = locals().get('payload') or {}
                agent = locals().get('agent')
                if agent and payload.get('network_id'):
                    network = self._get_agent_network(agent, payload.get('network_id'))
                    network.register_discovery_result(
                        success=False,
                        duration_ms=payload.get('duration_ms'),
                        error_message=str(error),
                    )
            except Exception:
                pass

            return self._handle_api_exception(error, endpoint='discovery')

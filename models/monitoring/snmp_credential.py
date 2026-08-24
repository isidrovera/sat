# -*- coding: utf-8 -*-

import base64
import hashlib
import logging
import os
import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)


try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = Exception


# ============================================================
# CONSTANTES
# ============================================================

MASTER_KEY_ENV = 'SAT_SNMP_MASTER_KEY'


# ============================================================
# HELPERS
# ============================================================

def _clean_text(value):
    if value in (None, False):
        return ''

    return str(value).strip()


def _normalize_code(value):
    value = _clean_text(value).lower()

    value = re.sub(
        r'[^a-z0-9]+',
        '_',
        value,
    )

    value = re.sub(
        r'_+',
        '_',
        value,
    )

    return value.strip('_')


def _hash_secret(value):
    """
    Hash auxiliar.

    NO sirve para recuperar el secreto.
    Se utiliza únicamente para:
        - auditoría
        - comparación
        - saber si cambió
    """
    value = _clean_text(value)

    if not value:
        return ''

    return hashlib.sha256(
        value.encode('utf-8')
    ).hexdigest()


def _secret_preview(value):
    """
    Genera una vista parcial segura.

    Ejemplo:
        public123 -> pu*****23
    """
    value = _clean_text(value)

    if not value:
        return ''

    if len(value) <= 4:
        return '****'

    start = value[:2]
    end = value[-2:]

    stars = '*' * max(
        len(value) - 4,
        4,
    )

    return (
        start
        + stars
        + end
    )


# ============================================================
# CREDENCIAL SNMP
# ============================================================

class SatSnmpCredential(models.Model):

    _name = 'sat.snmp.credential'
    _description = 'Credencial SNMP'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
    ]
    _order = (
        'priority desc, '
        'sequence, '
        'name, '
        'id'
    )

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        index=True,
        help=(
            'Nombre administrativo de la credencial.\n'
            'Ejemplo: Cliente Lima - SNMP v2c.'
        ),
    )

    code = fields.Char(
        string='Código técnico',
        required=True,
        copy=False,
        tracking=True,
        index=True,
        help=(
            'Código estable utilizado por API y agentes.\n'
            'Ejemplo: cliente_lima_v2.'
        ),
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
        index=True,
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    priority = fields.Integer(
        string='Prioridad',
        default=100,
        tracking=True,
        index=True,
        help=(
            'Cuando existen varias credenciales posibles, '
            'se intenta primero la de mayor prioridad.'
        ),
    )

    # ========================================================
    # CLIENTE
    # ========================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        ondelete='set null',
        tracking=True,
        index=True,
    )

    global_credential = fields.Boolean(
        string='Credencial global',
        default=False,
        tracking=True,
        help=(
            'Permite utilizar esta credencial en diferentes clientes. '
            'Debe utilizarse únicamente para credenciales realmente '
            'compartidas.'
        ),
    )

    # ========================================================
    # SNMP
    # ========================================================

    snmp_version = fields.Selection(
        [
            ('1', 'SNMP v1'),
            ('2c', 'SNMP v2c'),
            ('3', 'SNMP v3'),
        ],
        string='Versión SNMP',
        required=True,
        default='2c',
        tracking=True,
        index=True,
    )

    port = fields.Integer(
        string='Puerto',
        required=True,
        default=161,
        tracking=True,
    )

    timeout = fields.Float(
        string='Timeout',
        default=2.0,
        required=True,
    )

    retries = fields.Integer(
        string='Reintentos',
        default=1,
        required=True,
    )

    # ========================================================
    # COMMUNITY V1 / V2C
    # ========================================================

    community_encrypted = fields.Text(
        string='Community cifrada',
        readonly=False,
        copy=False,
        groups='base.group_system',
    )

    community_hash = fields.Char(
        string='Hash community',
        readonly=False,
        copy=False,
        groups='base.group_system',
    )

    community_preview = fields.Char(
        string='Community',
        readonly=False,
        copy=False,
    )

    community_set = fields.Boolean(
        string='Community configurada',
        compute='_compute_secret_states',
        store=True,
    )

    community_input = fields.Char(
        string='Nueva community',
        copy=False,
        help=(
            'Escriba aquí la community SNMP v1/v2c. '
            'El valor se cifra antes de guardarse y este campo queda vacío.'
        ),
    )

    # ========================================================
    # SNMP V3
    # ========================================================

    v3_username = fields.Char(
        string='Usuario SNMP v3',
        tracking=True,
        index=True,
    )

    v3_security_level = fields.Selection(
        [
            (
                'noAuthNoPriv',
                'Sin autenticación / Sin privacidad',
            ),
            (
                'authNoPriv',
                'Autenticación / Sin privacidad',
            ),
            (
                'authPriv',
                'Autenticación / Privacidad',
            ),
        ],
        string='Nivel de seguridad',
        default='authPriv',
        tracking=True,
    )

    # ========================================================
    # SNMP V3 AUTH
    # ========================================================

    v3_auth_protocol = fields.Selection(
        [
            ('none', 'Ninguno'),
            ('md5', 'MD5'),
            ('sha', 'SHA-1'),
            ('sha224', 'SHA-224'),
            ('sha256', 'SHA-256'),
            ('sha384', 'SHA-384'),
            ('sha512', 'SHA-512'),
        ],
        string='Protocolo autenticación',
        default='sha',
        tracking=True,
    )

    v3_auth_key_encrypted = fields.Text(
        string='Clave auth cifrada',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )

    v3_auth_key_hash = fields.Char(
        string='Hash clave auth',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )

    v3_auth_key_preview = fields.Char(
        string='Clave autenticación',
        readonly=True,
        copy=False,
    )

    v3_auth_key_set = fields.Boolean(
        string='Clave auth configurada',
        compute='_compute_secret_states',
        store=True,
    )

    v3_auth_key_input = fields.Char(
        string='Nueva clave autenticación',
        copy=False,
        help=(
            'Clave temporal para SNMP v3. '
            'Se cifra antes de guardarse y este campo queda vacío.'
        ),
    )

    # ========================================================
    # SNMP V3 PRIVACY
    # ========================================================

    v3_priv_protocol = fields.Selection(
        [
            ('none', 'Ninguno'),
            ('des', 'DES'),
            ('3des', '3DES'),
            ('aes128', 'AES-128'),
            ('aes192', 'AES-192'),
            ('aes256', 'AES-256'),
        ],
        string='Protocolo privacidad',
        default='aes128',
        tracking=True,
    )

    v3_priv_key_encrypted = fields.Text(
        string='Clave privacidad cifrada',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )

    v3_priv_key_hash = fields.Char(
        string='Hash clave privacidad',
        readonly=True,
        copy=False,
        groups='base.group_system',
    )

    v3_priv_key_preview = fields.Char(
        string='Clave privacidad',
        readonly=True,
        copy=False,
    )

    v3_priv_key_set = fields.Boolean(
        string='Clave privacidad configurada',
        compute='_compute_secret_states',
        store=True,
    )

    v3_priv_key_input = fields.Char(
        string='Nueva clave privacidad',
        copy=False,
        help=(
            'Clave temporal de privacidad SNMP v3. '
            'Se cifra antes de guardarse y este campo queda vacío.'
        ),
    )

    # ========================================================
    # CONTEXTO V3
    # ========================================================

    v3_context_name = fields.Char(
        string='Context Name',
        tracking=True,
    )

    v3_context_engine_id = fields.Char(
        string='Context Engine ID',
        tracking=True,
    )

    # ========================================================
    # USO
    # ========================================================

    allow_discovery = fields.Boolean(
        string='Permitir discovery',
        default=True,
    )

    allow_polling = fields.Boolean(
        string='Permitir polling',
        default=True,
    )

    fallback_enabled = fields.Boolean(
        string='Disponible como fallback',
        default=True,
    )

    # ========================================================
    # ESTADO
    # ========================================================

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('testing', 'En pruebas'),
            ('validated', 'Validada'),
            ('disabled', 'Deshabilitada'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )

    # ========================================================
    # ESTADÍSTICAS DE VALIDACIÓN
    # ========================================================

    tested_count = fields.Integer(
        string='Pruebas',
        default=0,
        readonly=True,
        copy=False,
    )

    success_count = fields.Integer(
        string='Éxitos',
        default=0,
        readonly=True,
        copy=False,
    )

    failure_count = fields.Integer(
        string='Fallos',
        default=0,
        readonly=True,
        copy=False,
    )

    success_rate = fields.Float(
        string='Éxito (%)',
        compute='_compute_success_rate',
        store=True,
        digits=(5, 2),
    )

    last_test_date = fields.Datetime(
        string='Última prueba',
        readonly=True,
        copy=False,
    )

    last_success_date = fields.Datetime(
        string='Último éxito',
        readonly=True,
        copy=False,
    )

    last_failure_date = fields.Datetime(
        string='Último fallo',
        readonly=True,
        copy=False,
    )

    last_failure_message = fields.Text(
        string='Último error',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # AUDITORÍA DE USO
    # ========================================================

    last_used_at = fields.Datetime(
        string='Último uso',
        readonly=True,
        copy=False,
    )

    use_count = fields.Integer(
        string='Usos',
        default=0,
        readonly=True,
        copy=False,
    )

    secret_updated_at = fields.Datetime(
        string='Secretos actualizados',
        readonly=True,
        copy=False,
    )

    secret_updated_by = fields.Many2one(
        'res.users',
        string='Secretos actualizados por',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # ROTACIÓN
    # ========================================================

    secret_revision = fields.Integer(
        string='Revisión secretos',
        default=1,
        required=True,
        readonly=True,
        copy=False,
        help=(
            'Incrementa cada vez que se modifica community, '
            'clave auth o clave privacy.'
        ),
    )

    # ========================================================
    # NOTAS
    # ========================================================

    notes = fields.Text(
        string='Notas',
        tracking=True,
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_snmp_credential_code_unique',
            'unique(code)',
            'El código técnico de la credencial ya está siendo utilizado.',
        ),
        (
            'sat_snmp_credential_port_valid',
            'CHECK(port > 0 AND port <= 65535)',
            'El puerto SNMP debe estar entre 1 y 65535.',
        ),
        (
            'sat_snmp_credential_timeout_positive',
            'CHECK(timeout >= 0)',
            'El timeout no puede ser negativo.',
        ),
        (
            'sat_snmp_credential_retries_positive',
            'CHECK(retries >= 0)',
            'Los reintentos no pueden ser negativos.',
        ),
        (
            'sat_snmp_credential_priority_positive',
            'CHECK(priority >= 0)',
            'La prioridad no puede ser negativa.',
        ),
        (
            'sat_snmp_credential_secret_revision_positive',
            'CHECK(secret_revision > 0)',
            'La revisión de secretos debe ser mayor que cero.',
        ),
    ]

    # ========================================================
    # COMPUTES
    # ========================================================

    @api.depends(
        'community_encrypted',
        'v3_auth_key_encrypted',
        'v3_priv_key_encrypted',
    )
    def _compute_secret_states(self):
        for record in self:
            record.community_set = bool(
                record.community_encrypted
            )

            record.v3_auth_key_set = bool(
                record.v3_auth_key_encrypted
            )

            record.v3_priv_key_set = bool(
                record.v3_priv_key_encrypted
            )

    @api.depends(
        'tested_count',
        'success_count',
    )
    def _compute_success_rate(self):
        for record in self:
            if record.tested_count <= 0:
                record.success_rate = 0.0
                continue

            record.success_rate = (
                record.success_count
                / record.tested_count
            ) * 100.0

    # ========================================================
    # MASTER KEY
    # ========================================================

    @api.model
    def _get_master_key(self):
        """
        Obtiene la clave maestra desde una variable de entorno.

        NUNCA se guarda la clave maestra dentro de esta tabla.

        Variable requerida:

            SAT_SNMP_MASTER_KEY
        """
        if Fernet is None:
            raise UserError(
                _(
                    'No está instalada la librería Python '
                    '"cryptography".\n\n'
                    'Es necesaria para proteger las credenciales SNMP.'
                )
            )

        master_key = os.environ.get(
            MASTER_KEY_ENV
        )

        master_key = _clean_text(
            master_key
        )

        if not master_key:
            raise UserError(
                _(
                    'No está configurada la variable de entorno '
                    '%s.\n\n'
                    'Las credenciales SNMP no pueden cifrarse '
                    'ni descifrarse sin la clave maestra.'
                )
                % MASTER_KEY_ENV
            )

        try:
            key_bytes = master_key.encode(
                'ascii'
            )

            # Fernet valida el formato.
            Fernet(
                key_bytes
            )

            return key_bytes

        except Exception:
            raise UserError(
                _(
                    'La variable %s no contiene una clave '
                    'Fernet válida.'
                )
                % MASTER_KEY_ENV
            )

    @api.model
    def _get_cipher(self):
        return Fernet(
            self._get_master_key()
        )

    # ========================================================
    # CIFRAR
    # ========================================================

    @api.model
    def _encrypt_secret(self, value):
        value = _clean_text(
            value
        )

        if not value:
            return False

        cipher = self._get_cipher()

        encrypted = cipher.encrypt(
            value.encode('utf-8')
        )

        return encrypted.decode(
            'ascii'
        )

    # ========================================================
    # DESCIFRAR
    # ========================================================

    @api.model
    def _decrypt_secret(self, encrypted_value):
        encrypted_value = _clean_text(
            encrypted_value
        )

        if not encrypted_value:
            return ''

        cipher = self._get_cipher()

        try:
            decrypted = cipher.decrypt(
                encrypted_value.encode(
                    'ascii'
                )
            )

            return decrypted.decode(
                'utf-8'
            )

        except InvalidToken:
            _logger.error(
                '[SNMP CREDENTIAL] No se pudo descifrar un secreto. '
                'Posible cambio de SAT_SNMP_MASTER_KEY.'
            )

            raise UserError(
                _(
                    'No se pudo descifrar la credencial SNMP.\n\n'
                    'Compruebe que SAT_SNMP_MASTER_KEY sea la misma '
                    'clave utilizada cuando se guardó el secreto.'
                )
            )

        except Exception as error:
            _logger.exception(
                '[SNMP CREDENTIAL] Error descifrando secreto: %s',
                error,
            )

            raise UserError(
                _(
                    'Ocurrió un error al descifrar '
                    'la credencial SNMP.'
                )
            )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            normalized = _normalize_code(
                record.code
            )

            if not normalized:
                raise ValidationError(
                    _(
                        'El código técnico de la credencial '
                        'no es válido.'
                    )
                )

            if normalized != record.code:
                raise ValidationError(
                    _(
                        'El código técnico debe utilizar únicamente '
                        'letras minúsculas, números y guion bajo.\n\n'
                        'Código sugerido: %s'
                    )
                    % normalized
                )

    @api.constrains(
        'global_credential',
        'partner_id',
    )
    def _check_partner_configuration(self):
        for record in self:
            if (
                not record.global_credential
                and not record.partner_id
            ):
                raise ValidationError(
                    _(
                        'Una credencial que no es global '
                        'debe pertenecer a un cliente.'
                    )
                )

    @api.constrains(
        'snmp_version',
        'v3_username',
        'v3_security_level',
        'v3_auth_protocol',
        'v3_priv_protocol',
        'community_encrypted',
        'v3_auth_key_encrypted',
        'v3_priv_key_encrypted',
    )
    def _check_snmp_configuration(self):
        for record in self:

            # -----------------------------------------------
            # V1 / V2C
            # -----------------------------------------------

            if record.snmp_version in (
                '1',
                '2c',
            ):
                if not record.community_encrypted:
                    raise ValidationError(
                        _(
                            'Las credenciales SNMP v1/v2c '
                            'deben tener una community configurada.'
                        )
                    )

                continue

            # -----------------------------------------------
            # V3
            # -----------------------------------------------

            if not record.v3_username:
                raise ValidationError(
                    _(
                        'SNMP v3 requiere un nombre de usuario.'
                    )
                )

            if (
                record.v3_security_level
                == 'noAuthNoPriv'
            ):
                continue

            if (
                record.v3_auth_protocol
                == 'none'
            ):
                raise ValidationError(
                    _(
                        'El nivel de seguridad seleccionado '
                        'requiere protocolo de autenticación.'
                    )
                )

            if not record.v3_auth_key_encrypted:
                raise ValidationError(
                    _(
                        'El nivel de seguridad seleccionado '
                        'requiere clave de autenticación.'
                    )
                )

            if (
                record.v3_security_level
                == 'authPriv'
            ):
                if (
                    record.v3_priv_protocol
                    == 'none'
                ):
                    raise ValidationError(
                        _(
                            'authPriv requiere un protocolo '
                            'de privacidad.'
                        )
                    )

                if not record.v3_priv_key_encrypted:
                    raise ValidationError(
                        _(
                            'authPriv requiere una clave '
                            'de privacidad.'
                        )
                    )

    # ========================================================
    # CREACIÓN
    # ========================================================

    def _prepare_secret_input_vals(self, vals):
        """
        Convierte los campos editables temporales en valores cifrados.

        Los campos *_input nunca conservan el secreto después de guardar.
        """
        vals = dict(vals or {})
        secret_changed = False

        community = _clean_text(
            vals.pop(
                'community_input',
                False,
            )
        )

        if community:
            vals.update({
                'community_encrypted':
                    self._encrypt_secret(
                        community
                    ),

                'community_hash':
                    _hash_secret(
                        community
                    ),

                'community_preview':
                    _secret_preview(
                        community
                    ),
            })

            secret_changed = True

        auth_key = _clean_text(
            vals.pop(
                'v3_auth_key_input',
                False,
            )
        )

        if auth_key:
            vals.update({
                'v3_auth_key_encrypted':
                    self._encrypt_secret(
                        auth_key
                    ),

                'v3_auth_key_hash':
                    _hash_secret(
                        auth_key
                    ),

                'v3_auth_key_preview':
                    _secret_preview(
                        auth_key
                    ),
            })

            secret_changed = True

        priv_key = _clean_text(
            vals.pop(
                'v3_priv_key_input',
                False,
            )
        )

        if priv_key:
            vals.update({
                'v3_priv_key_encrypted':
                    self._encrypt_secret(
                        priv_key
                    ),

                'v3_priv_key_hash':
                    _hash_secret(
                        priv_key
                    ),

                'v3_priv_key_preview':
                    _secret_preview(
                        priv_key
                    ),
            })

            secret_changed = True

        if secret_changed:
            vals.update({
                'secret_updated_at':
                    fields.Datetime.now(),

                'secret_updated_by':
                    self.env.user.id,
            })

        return vals, secret_changed

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []

        for vals in vals_list:
            vals = dict(vals)

            if (
                vals.get('name')
                and not vals.get('code')
            ):
                vals['code'] = (
                    _normalize_code(
                        vals['name']
                    )
                )

            prepared_vals, secret_changed = (
                self._prepare_secret_input_vals(
                    vals
                )
            )

            prepared_vals_list.append(
                prepared_vals
            )

        return super().create(
            prepared_vals_list
        )

    def write(self, vals):
        """
        Permite escribir Community/Auth/Privacy directamente en el formulario
        sin guardar el secreto en texto plano.
        """
        prepared_vals, secret_changed = (
            self._prepare_secret_input_vals(
                vals
            )
        )

        result = super().write(
            prepared_vals
        )

        if secret_changed:
            self._touch_secret_revision()

        return result

    # ========================================================
    # ACTUALIZAR REVISIONES
    # ========================================================

    def _touch_secret_revision(self):
        now = fields.Datetime.now()

        for record in self:
            record.sudo().write({
                'secret_revision':
                    record.secret_revision + 1,

                'secret_updated_at':
                    now,

                'secret_updated_by':
                    self.env.user.id,
            })

            networks = self.env[
                'sat.monitoring.network'
            ].search(
                [
                    (
                        'credential_id',
                        '=',
                        record.id,
                    ),
                ]
            )

            networks.mapped(
                'agent_id'
            ).bump_config_revision()

            devices = self.env[
                'sat.monitoring.device'
            ].search(
                [
                    (
                        'credential_id',
                        '=',
                        record.id,
                    ),
                ]
            )

            devices.mapped(
                'agent_id'
            ).bump_config_revision()

        return True

    # ========================================================
    # COMMUNITY
    # ========================================================

    def set_community(self, community):
        """
        Configura o reemplaza community SNMP v1/v2c.
        """
        self.ensure_one()

        community = _clean_text(
            community
        )

        if not community:
            raise UserError(
                _(
                    'Debe indicar una community SNMP.'
                )
            )

        encrypted = self._encrypt_secret(
            community
        )

        self.sudo().write({
            'community_encrypted':
                encrypted,

            'community_hash':
                _hash_secret(
                    community
                ),

            'community_preview':
                _secret_preview(
                    community
                ),
        })

        self._touch_secret_revision()

        return True

    def clear_community(self):
        self.sudo().write({
            'community_encrypted':
                False,

            'community_hash':
                False,

            'community_preview':
                False,
        })

        self._touch_secret_revision()

        return True

    # ========================================================
    # AUTH KEY
    # ========================================================

    def set_v3_auth_key(self, key):
        self.ensure_one()

        key = _clean_text(
            key
        )

        if not key:
            raise UserError(
                _(
                    'Debe indicar la clave '
                    'de autenticación SNMP v3.'
                )
            )

        self.sudo().write({
            'v3_auth_key_encrypted':
                self._encrypt_secret(
                    key
                ),

            'v3_auth_key_hash':
                _hash_secret(
                    key
                ),

            'v3_auth_key_preview':
                _secret_preview(
                    key
                ),
        })

        self._touch_secret_revision()

        return True

    def clear_v3_auth_key(self):
        self.sudo().write({
            'v3_auth_key_encrypted':
                False,

            'v3_auth_key_hash':
                False,

            'v3_auth_key_preview':
                False,
        })

        self._touch_secret_revision()

        return True

    # ========================================================
    # PRIV KEY
    # ========================================================

    def set_v3_priv_key(self, key):
        self.ensure_one()

        key = _clean_text(
            key
        )

        if not key:
            raise UserError(
                _(
                    'Debe indicar la clave '
                    'de privacidad SNMP v3.'
                )
            )

        self.sudo().write({
            'v3_priv_key_encrypted':
                self._encrypt_secret(
                    key
                ),

            'v3_priv_key_hash':
                _hash_secret(
                    key
                ),

            'v3_priv_key_preview':
                _secret_preview(
                    key
                ),
        })

        self._touch_secret_revision()

        return True

    def clear_v3_priv_key(self):
        self.sudo().write({
            'v3_priv_key_encrypted':
                False,

            'v3_priv_key_hash':
                False,

            'v3_priv_key_preview':
                False,
        })

        self._touch_secret_revision()

        return True

    # ========================================================
    # LIMPIAR TODOS LOS SECRETOS
    # ========================================================

    def action_clear_secrets(self):
        self.sudo().write({
            'community_encrypted':
                False,

            'community_hash':
                False,

            'community_preview':
                False,

            'v3_auth_key_encrypted':
                False,

            'v3_auth_key_hash':
                False,

            'v3_auth_key_preview':
                False,

            'v3_priv_key_encrypted':
                False,

            'v3_priv_key_hash':
                False,

            'v3_priv_key_preview':
                False,
        })

        self._touch_secret_revision()

        return True

    # ========================================================
    # RECUPERAR SECRETOS
    # ========================================================

    def _get_community_secret(self):
        self.ensure_one()

        return self._decrypt_secret(
            self.community_encrypted
        )

    def _get_v3_auth_secret(self):
        self.ensure_one()

        return self._decrypt_secret(
            self.v3_auth_key_encrypted
        )

    def _get_v3_priv_secret(self):
        self.ensure_one()

        return self._decrypt_secret(
            self.v3_priv_key_encrypted
        )

    # ========================================================
    # COMPATIBILIDAD CLIENTE
    # ========================================================

    def can_be_used_for_partner(self, partner):
        self.ensure_one()

        if self.global_credential:
            return True

        if not partner:
            return False

        return (
            self.partner_id
            == partner
        )

    # ========================================================
    # VERIFICAR AGENTE AUTORIZADO
    # ========================================================

    def can_be_used_by_agent(self, agent):
        """
        Verifica que el agente tenga realmente acceso a una red
        o equipo que utilice esta credencial.

        Evita que un agente autenticado solicite arbitrariamente
        credenciales de otro cliente.
        """
        self.ensure_one()
        agent.ensure_one()

        if not (
            agent.active
            and agent.enabled
        ):
            return False

        # -----------------------------------------------
        # Credencial usada directamente por una red
        # -----------------------------------------------

        network = self.env[
            'sat.monitoring.network'
        ].sudo().search(
            [
                (
                    'agent_id',
                    '=',
                    agent.id,
                ),
                (
                    'credential_id',
                    '=',
                    self.id,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
            ],
            limit=1,
        )

        if network:
            return True

        # -----------------------------------------------
        # Credencial específica de dispositivo
        # -----------------------------------------------

        device = self.env[
            'sat.monitoring.device'
        ].sudo().search(
            [
                (
                    'agent_id',
                    '=',
                    agent.id,
                ),
                (
                    'credential_id',
                    '=',
                    self.id,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
            ],
            limit=1,
        )

        if device:
            return True

        return False

    # ========================================================
    # PAYLOAD SIN SECRETOS
    # ========================================================

    def get_agent_payload(self):
        """
        Información no sensible.

        Puede incluirse en configuraciones generales sin revelar
        community ni passwords.
        """
        self.ensure_one()

        return {
            'id':
                self.id,

            'code':
                self.code,

            'name':
                self.name,

            'secret_revision':
                self.secret_revision,

            'snmp_version':
                self.snmp_version,

            'port':
                self.port,

            'timeout':
                self.timeout,

            'retries':
                self.retries,

            'allow_discovery':
                self.allow_discovery,

            'allow_polling':
                self.allow_polling,

            'fallback_enabled':
                self.fallback_enabled,

            'state':
                self.state,

            'v1_v2': {
                'community_configured':
                    self.community_set,
            },

            'v3': {
                'username':
                    self.v3_username or '',

                'security_level':
                    self.v3_security_level
                    or '',

                'auth_protocol':
                    self.v3_auth_protocol
                    or '',

                'auth_key_configured':
                    self.v3_auth_key_set,

                'priv_protocol':
                    self.v3_priv_protocol
                    or '',

                'priv_key_configured':
                    self.v3_priv_key_set,

                'context_name':
                    self.v3_context_name
                    or '',

                'context_engine_id':
                    self.v3_context_engine_id
                    or '',
            },
        }

    # ========================================================
    # PAYLOAD PRIVADO PARA AGENTE AUTORIZADO
    # ========================================================

    def get_agent_secret_payload(self, agent):
        """
        ESTE es el único método que debe utilizar posteriormente
        la API autenticada para entregar secretos al agente.

        Primero verifica que el agente tenga derecho a utilizar
        esta credencial.
        """
        self.ensure_one()
        agent.ensure_one()

        if not self.active:
            raise AccessError(
                _(
                    'La credencial SNMP está inactiva.'
                )
            )

        if self.state == 'disabled':
            raise AccessError(
                _(
                    'La credencial SNMP está deshabilitada.'
                )
            )

        if not self.can_be_used_by_agent(
            agent
        ):
            _logger.warning(
                '[SNMP SECURITY] Agent %s attempted access '
                'to credential %s',
                agent.code,
                self.code,
            )

            raise AccessError(
                _(
                    'El agente no está autorizado '
                    'para utilizar esta credencial SNMP.'
                )
            )

        payload = {
            'id':
                self.id,

            'code':
                self.code,

            'secret_revision':
                self.secret_revision,

            'snmp_version':
                self.snmp_version,

            'port':
                self.port,

            'timeout':
                self.timeout,

            'retries':
                self.retries,
        }

        # -----------------------------------------------
        # SNMP V1 / V2C
        # -----------------------------------------------

        if self.snmp_version in (
            '1',
            '2c',
        ):
            payload['community'] = (
                self._get_community_secret()
            )

        # -----------------------------------------------
        # SNMP V3
        # -----------------------------------------------

        else:
            payload.update({
                'username':
                    self.v3_username
                    or '',

                'security_level':
                    self.v3_security_level
                    or 'noAuthNoPriv',

                'auth_protocol':
                    self.v3_auth_protocol
                    or 'none',

                'priv_protocol':
                    self.v3_priv_protocol
                    or 'none',

                'context_name':
                    self.v3_context_name
                    or '',

                'context_engine_id':
                    self.v3_context_engine_id
                    or '',
            })

            if (
                self.v3_security_level
                in (
                    'authNoPriv',
                    'authPriv',
                )
            ):
                payload['auth_key'] = (
                    self._get_v3_auth_secret()
                )

            if (
                self.v3_security_level
                == 'authPriv'
            ):
                payload['priv_key'] = (
                    self._get_v3_priv_secret()
                )

        self.register_use()

        return payload

    # ========================================================
    # ESTADOS
    # ========================================================

    def action_set_draft(self):
        self.write({
            'state':
                'draft',
        })

        return True

    def action_set_testing(self):
        self._check_snmp_configuration()

        self.write({
            'state':
                'testing',
        })

        return True

    def action_validate(self):
        self._check_snmp_configuration()

        self.write({
            'state':
                'validated',
        })

        return True

    def action_disable(self):
        self.write({
            'state':
                'disabled',

            'active':
                False,
        })

        return True

    def action_enable(self):
        self.write({
            'active':
                True,

            'state':
                'draft',
        })

        return True

    # ========================================================
    # RESULTADO DE PRUEBA
    # ========================================================

    def register_test_result(
        self,
        success,
        error_message=None,
    ):
        now = fields.Datetime.now()

        for record in self:
            vals = {
                'tested_count':
                    record.tested_count + 1,

                'last_test_date':
                    now,
            }

            if success:
                vals.update({
                    'success_count':
                        record.success_count + 1,

                    'last_success_date':
                        now,

                    'last_failure_message':
                        False,
                })

            else:
                vals.update({
                    'failure_count':
                        record.failure_count + 1,

                    'last_failure_date':
                        now,

                    'last_failure_message':
                        _clean_text(
                            error_message
                        ),
                })

            record.sudo().write(
                vals
            )

        return True

    # ========================================================
    # REGISTRAR USO
    # ========================================================

    def register_use(self):
        now = fields.Datetime.now()

        for record in self:
            record.sudo().write({
                'last_used_at':
                    now,

                'use_count':
                    record.use_count + 1,
            })

        return True

    # ========================================================
    # RESUMEN
    # ========================================================

    def get_credential_summary(self):
        self.ensure_one()

        return {
            'id':
                self.id,

            'code':
                self.code,

            'name':
                self.name,

            'partner_id':
                self.partner_id.id
                if self.partner_id
                else False,

            'global':
                self.global_credential,

            'snmp_version':
                self.snmp_version,

            'state':
                self.state,

            'active':
                self.active,

            'priority':
                self.priority,

            'secret_revision':
                self.secret_revision,

            'community_configured':
                self.community_set,

            'auth_key_configured':
                self.v3_auth_key_set,

            'priv_key_configured':
                self.v3_priv_key_set,

            'tested_count':
                self.tested_count,

            'success_count':
                self.success_count,

            'failure_count':
                self.failure_count,

            'success_rate':
                self.success_rate,
        }
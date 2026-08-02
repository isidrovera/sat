# -*- coding: utf-8 -*-

import base64
import re
import unicodedata

from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ModelosMaquina(models.Model):
    _inherit = 'modelo.maquina'

    # =========================================================
    # IDENTIFICACIÓN TÉCNICA
    # =========================================================

    codigo_tecnico = fields.Char(
        string='Código técnico',
        copy=False,
        index=True,
        help=(
            'Código estable del modelo utilizado para generar el ID externo. '
            'Ejemplo: mp_c4504.'
        ),
    )

    familia_id = fields.Many2one(
        'modelo.maquina.familia',
        string='Familia técnica',
        ondelete='restrict',
        index=True,
        domain="[('marca_id', '=', marca_id)]",
        help=(
            'Familia técnica opcional. Se utilizará principalmente para '
            'compatibilidad de accesorios. La configuración específica '
            'del modelo tendrá prioridad.'
        ),
    )

    external_id_display = fields.Char(
        string='ID externo',
        compute='_compute_external_id_info',
        readonly=True,
    )

    external_id_state = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('generated', 'Generado'),
            ('conflict', 'Conflicto'),
        ],
        string='Estado ID externo',
        compute='_compute_external_id_info',
        readonly=True,
    )

    external_id_generated_date = fields.Datetime(
        string='Fecha de generación',
        readonly=True,
        copy=False,
    )

    external_id_generated_by = fields.Many2one(
        'res.users',
        string='Generado por',
        readonly=True,
        copy=False,
    )

    # =========================================================
    # CONFIGURACIÓN COPIADA DESDE OTRO MODELO
    # =========================================================

    modelo_referencia_id = fields.Many2one(
        'modelo.maquina',
        string='Modelo de referencia',
        help=(
            'Selecciona un modelo existente para copiar automáticamente '
            'sus componentes y accesorios.'
        ),
        domain="[('id', '!=', id)]",
    )

    total_componentes = fields.Integer(
        string='Componentes',
        compute='_compute_totales_config',
    )

    total_accesorios = fields.Integer(
        string='Accesorios',
        compute='_compute_totales_config',
    )

    _sql_constraints = [
        (
            'unique_marca_codigo_tecnico_modelo',
            'unique(marca_id, codigo_tecnico)',
            'Ya existe un modelo con este código técnico para la marca.',
        ),
    ]

    # =========================================================
    # NORMALIZACIÓN
    # =========================================================

    @api.model
    def _normalizar_codigo(self, value):
        value = value or ''

        value = unicodedata.normalize('NFKD', value)
        value = ''.join(
            character
            for character in value
            if not unicodedata.combining(character)
        )

        value = value.lower().strip()
        value = re.sub(r'[^a-z0-9]+', '_', value)
        value = re.sub(r'_+', '_', value)
        value = value.strip('_')

        return value

    @api.onchange('name')
    def _onchange_name_codigo_tecnico(self):
        for record in self:
            if record.name and not record.codigo_tecnico:
                record.codigo_tecnico = record._normalizar_codigo(
                    record.name
                )

    @api.onchange('marca_id')
    def _onchange_marca_familia(self):
        for record in self:
            if (
                record.familia_id
                and record.familia_id.marca_id != record.marca_id
            ):
                record.familia_id = False

    @api.constrains('familia_id', 'marca_id')
    def _check_familia_marca(self):
        for record in self:
            if (
                record.familia_id
                and record.marca_id
                and record.familia_id.marca_id != record.marca_id
            ):
                raise ValidationError(
                    _(
                        'La familia seleccionada pertenece a la marca %s, '
                        'pero el modelo pertenece a la marca %s.'
                    ) % (
                        record.familia_id.marca_id.name,
                        record.marca_id.name,
                    )
                )

    @api.constrains('codigo_tecnico')
    def _check_codigo_tecnico(self):
        for record in self:
            if not record.codigo_tecnico:
                continue

            normalizado = record._normalizar_codigo(
                record.codigo_tecnico
            )

            if not normalizado:
                raise ValidationError(
                    _('El código técnico del modelo no es válido.')
                )

            if record.codigo_tecnico != normalizado:
                raise ValidationError(
                    _(
                        'El código técnico debe utilizar únicamente '
                        'letras minúsculas, números y guion bajo.\n\n'
                        'Código sugerido: %s'
                    ) % normalizado
                )

    # =========================================================
    # ID EXTERNO
    # =========================================================

    def _get_external_id_record(self):
        self.ensure_one()

        if not self.id:
            return self.env['ir.model.data']

        IrModelData = self.env['ir.model.data'].sudo()

        external_record = IrModelData.search(
            [
                ('module', '=', 'sat'),
                ('model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            limit=1,
        )

        if external_record:
            return external_record

        return IrModelData.search(
            [
                ('model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            limit=1,
        )

    def _get_complete_external_id(self):
        self.ensure_one()

        external_record = self._get_external_id_record()

        if not external_record:
            return False

        return f'{external_record.module}.{external_record.name}'

    @api.depends(
        'codigo_tecnico',
        'marca_id',
        'marca_id.codigo_tecnico',
    )
    def _compute_external_id_info(self):
        IrModelData = self.env['ir.model.data'].sudo()

        for record in self:
            record.external_id_display = False
            record.external_id_state = 'pending'

            if not record.id:
                continue

            external_record = record._get_external_id_record()

            if external_record:
                record.external_id_display = (
                    f'{external_record.module}.{external_record.name}'
                )
                record.external_id_state = 'generated'
                continue

            if (
                record.marca_id.codigo_tecnico
                and record.codigo_tecnico
            ):
                proposed_name = (
                    f'modelo_'
                    f'{record.marca_id.codigo_tecnico}_'
                    f'{record.codigo_tecnico}'
                )

                conflict = IrModelData.search(
                    [
                        ('module', '=', 'sat'),
                        ('name', '=', proposed_name),
                    ],
                    limit=1,
                )

                if conflict and not (
                    conflict.model == record._name
                    and conflict.res_id == record.id
                ):
                    record.external_id_state = 'conflict'

    def action_generate_external_id(self):
        """
        Genera IDs externos para uno o varios modelos.

        Ejemplo:
            sat.modelo_ricoh_mp_c4504
        """
        IrModelData = self.env['ir.model.data'].sudo()

        generated = 0
        existing = 0
        conflicts = []

        for record in self:
            if not record.marca_id:
                conflicts.append(
                    _('%s: no tiene una marca asignada.')
                    % (record.name or record.id)
                )
                continue

            if not record.marca_id.codigo_tecnico:
                conflicts.append(
                    _(
                        '%s: la marca %s no tiene código técnico.'
                    ) % (
                        record.name,
                        record.marca_id.name,
                    )
                )
                continue

            if not record.codigo_tecnico:
                record.codigo_tecnico = record._normalizar_codigo(
                    record.name
                )

            if not record.codigo_tecnico:
                conflicts.append(
                    _('%s: no tiene un código técnico válido.')
                    % record.name
                )
                continue

            current_external = record._get_external_id_record()

            if current_external:
                existing += 1
                continue

            external_name = (
                f'modelo_'
                f'{record.marca_id.codigo_tecnico}_'
                f'{record.codigo_tecnico}'
            )

            conflict = IrModelData.search(
                [
                    ('module', '=', 'sat'),
                    ('name', '=', external_name),
                ],
                limit=1,
            )

            if conflict:
                conflicts.append(
                    _(
                        '%s: el ID sat.%s ya pertenece a otro registro.'
                    ) % (
                        record.name,
                        external_name,
                    )
                )
                continue

            IrModelData.create(
                {
                    'module': 'sat',
                    'name': external_name,
                    'model': record._name,
                    'res_id': record.id,
                    'noupdate': False,
                }
            )

            record.write(
                {
                    'external_id_generated_date': fields.Datetime.now(),
                    'external_id_generated_by': self.env.user.id,
                }
            )

            generated += 1

        if conflicts:
            raise UserError(
                _(
                    'No se pudieron generar todos los IDs externos:\n\n%s'
                ) % '\n'.join(conflicts)
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('IDs externos de modelos'),
                'message': _(
                    'Generados: %(generated)s\n'
                    'Ya existentes: %(existing)s'
                ) % {
                    'generated': generated,
                    'existing': existing,
                },
                'type': 'success',
                'sticky': False,
            },
        }

    # =========================================================
    # EXPORTACIÓN XML
    # =========================================================

    def _get_related_external_id(self, record):
        """
        Obtiene el ID externo completo de cualquier registro relacionado.
        """
        if not record:
            return False

        external_ids = record.get_external_id()
        return external_ids.get(record.id)

    def _append_xml_field(
        self,
        parent,
        field_name,
        value=None,
        reference=None,
    ):
        field_node = etree.SubElement(
            parent,
            'field',
            name=field_name,
        )

        if reference:
            field_node.set('ref', reference)
            return field_node

        if value is False or value is None:
            field_node.set('eval', 'False')
            return field_node

        if isinstance(value, bool):
            field_node.set(
                'eval',
                'True' if value else 'False',
            )
            return field_node

        field_node.text = str(value)
        return field_node

    def action_export_models_xml(self):
        """
        Exporta los modelos seleccionados como XML actualizable.

        El XML utiliza los IDs externos existentes, por lo que al cargarlo
        en el módulo actualizará los registros actuales y no creará
        modelos duplicados.
        """
        records = self

        if not records:
            active_ids = self.env.context.get('active_ids', [])
            records = self.browse(active_ids)

        if not records:
            raise UserError(
                _('Debe seleccionar al menos un modelo.')
            )

        records = records.sorted(
            key=lambda item: (
                item.marca_id.name or '',
                item.familia_id.name or '',
                item.name or '',
            )
        )

        missing_external_ids = []

        for record in records:
            if not record._get_external_id_record():
                missing_external_ids.append(
                    record.display_name
                )

        if missing_external_ids:
            raise UserError(
                _(
                    'Los siguientes modelos todavía no tienen '
                    'ID externo:\n\n%s\n\n'
                    'Genere primero sus IDs externos.'
                ) % '\n'.join(missing_external_ids)
            )

        root = etree.Element(
            'odoo',
            noupdate='0',
        )

        data_node = etree.SubElement(root, 'data')

        current_brand = False
        current_family = False

        for record in records:
            external_record = record._get_external_id_record()

            if record.marca_id.name != current_brand:
                current_brand = record.marca_id.name
                current_family = False

                data_node.append(
                    etree.Comment(
                        f' Marca: {current_brand} '
                    )
                )

            family_name = (
                record.familia_id.name
                if record.familia_id
                else 'Sin familia'
            )

            if family_name != current_family:
                current_family = family_name

                data_node.append(
                    etree.Comment(
                        f' Familia: {current_family} '
                    )
                )

            record_node = etree.SubElement(
                data_node,
                'record',
                id=external_record.name,
                model='modelo.maquina',
            )

            self._append_xml_field(
                record_node,
                'name',
                record.name,
            )

            brand_external_id = self._get_related_external_id(
                record.marca_id
            )

            if brand_external_id:
                self._append_xml_field(
                    record_node,
                    'marca_id',
                    reference=brand_external_id,
                )

            family_external_id = self._get_related_external_id(
                record.familia_id
            )

            if family_external_id:
                self._append_xml_field(
                    record_node,
                    'familia_id',
                    reference=family_external_id,
                )

            type_machine_external_id = self._get_related_external_id(
                record.tipo_maquina_id
            )

            if type_machine_external_id:
                self._append_xml_field(
                    record_node,
                    'tipo_maquina_id',
                    reference=type_machine_external_id,
                )

            self._append_xml_field(
                record_node,
                'codigo_tecnico',
                record.codigo_tecnico,
            )

            self._append_xml_field(
                record_node,
                'tipo_id',
                record.tipo_id,
            )

            self._append_xml_field(
                record_node,
                'precio_venta',
                record.precio_venta or 0.0,
            )

            # Configuración actual de tóners
            self._append_xml_field(
                record_node,
                'durabilidad_toner_black',
                record.durabilidad_toner_black or 0,
            )

            self._append_xml_field(
                record_node,
                'durabilidad_toner_cyan',
                record.durabilidad_toner_cyan or 0,
            )

            self._append_xml_field(
                record_node,
                'durabilidad_toner_magenta',
                record.durabilidad_toner_magenta or 0,
            )

            self._append_xml_field(
                record_node,
                'durabilidad_toner_yellow',
                record.durabilidad_toner_yellow or 0,
            )

            self._append_xml_field(
                record_node,
                'stock_minimo_black',
                record.stock_minimo_black or 0,
            )

            self._append_xml_field(
                record_node,
                'stock_minimo_cyan',
                record.stock_minimo_cyan or 0,
            )

            self._append_xml_field(
                record_node,
                'stock_minimo_magenta',
                record.stock_minimo_magenta or 0,
            )

            self._append_xml_field(
                record_node,
                'stock_minimo_yellow',
                record.stock_minimo_yellow or 0,
            )

            self._append_xml_field(
                record_node,
                'tiempo_entrega_dias',
                record.tiempo_entrega_dias or 0,
            )

            self._append_xml_field(
                record_node,
                'margen_seguridad_dias',
                record.margen_seguridad_dias or 0,
            )

            self._append_xml_field(
                record_node,
                'alerta_stock_critico',
                bool(record.alerta_stock_critico),
            )

            self._append_xml_field(
                record_node,
                'alerta_consumo_alto',
                bool(record.alerta_consumo_alto),
            )

            self._append_xml_field(
                record_node,
                'gestionar_toner_automatico',
                bool(record.gestionar_toner_automatico),
            )

        xml_content = etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding='UTF-8',
        )

        filename = (
            'modelos_maquina_exportados_%s.xml'
            % fields.Date.today().strftime('%Y%m%d')
        )

        attachment = self.env['ir.attachment'].create(
            {
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(xml_content),
                'mimetype': 'application/xml',
                'res_model': self._name,
                'res_id': records[0].id if len(records) == 1 else False,
            }
        )

        return {
            'type': 'ir.actions.act_url',
            'url': (
                '/web/content/%s?download=true'
                % attachment.id
            ),
            'target': 'self',
        }

    # =========================================================
    # TOTALES DE CONFIGURACIÓN
    # =========================================================

    def _compute_totales_config(self):
        for record in self:
            record.total_componentes = (
                self.env[
                    'modelo.maquina.componente'
                ].search_count(
                    [('modelo_id', '=', record.id)]
                )
            )

            record.total_accesorios = (
                self.env[
                    'modelo.maquina.accesorio'
                ].search_count(
                    [('modelo_id', '=', record.id)]
                )
            )

    # =========================================================
    # MODELO DE REFERENCIA
    # =========================================================

    @api.onchange('modelo_referencia_id')
    def _onchange_modelo_referencia(self):
        if not self.modelo_referencia_id:
            return

        if not self.id or isinstance(self.id, models.NewId):
            comp_count = self.env[
                'modelo.maquina.componente'
            ].search_count(
                [
                    (
                        'modelo_id',
                        '=',
                        self.modelo_referencia_id.id,
                    )
                ]
            )

            acc_count = self.env[
                'modelo.maquina.accesorio'
            ].search_count(
                [
                    (
                        'modelo_id',
                        '=',
                        self.modelo_referencia_id.id,
                    )
                ]
            )

            return {
                'warning': {
                    'title': _(
                        'Configuración se copiará al guardar'
                    ),
                    'message': _(
                        'Al guardar este modelo se copiarán '
                        '%(components)s componentes y '
                        '%(accessories)s accesorios desde "%(model)s".'
                    ) % {
                        'components': comp_count,
                        'accessories': acc_count,
                        'model': self.modelo_referencia_id.name,
                    },
                }
            }

        return {
            'warning': {
                'title': _('Información'),
                'message': _(
                    'Para copiar la configuración en un modelo existente, '
                    'utilice el botón "Copiar configuración".'
                ),
            }
        }

    def _copiar_configuracion_desde_modelo(
        self,
        modelo_origen,
    ):
        self.ensure_one()

        if not modelo_origen:
            return {
                'componentes': 0,
                'accesorios': 0,
            }

        if not self.id or isinstance(self.id, models.NewId):
            return {
                'componentes': 0,
                'accesorios': 0,
            }

        ComponenteModel = self.env[
            'modelo.maquina.componente'
        ]

        SubparteModel = self.env[
            'modelo.maquina.componente.subparte'
        ]

        AccesorioModel = self.env[
            'modelo.maquina.accesorio'
        ]

        es_destino_monocromo = (
            self.tipo_id == 'monocromatica'
        )

        componentes_origen = ComponenteModel.search(
            [('modelo_id', '=', modelo_origen.id)]
        )

        componentes_copiados = 0

        for comp_origen in componentes_origen:
            is_color_sensitive = bool(
                getattr(
                    comp_origen.tipo_id,
                    'is_color_sensitive',
                    False,
                )
            )

            if (
                is_color_sensitive
                and es_destino_monocromo
                and comp_origen.color != 'k'
            ):
                continue

            existe = ComponenteModel.search(
                [
                    ('modelo_id', '=', self.id),
                    ('tipo_id', '=', comp_origen.tipo_id.id),
                    ('color', '=', comp_origen.color),
                ],
                limit=1,
            )

            if existe:
                continue

            vals_comp = {
                'modelo_id': self.id,
                'tipo_id': comp_origen.tipo_id.id,
                'color': comp_origen.color,
                'prioridad': comp_origen.prioridad,
                'vida_util_paginas': (
                    comp_origen.vida_util_paginas
                ),
                'vida_util_meses': (
                    comp_origen.vida_util_meses
                ),
                'frase_desgaste': (
                    comp_origen.frase_desgaste
                ),
                'frase_cambio': (
                    comp_origen.frase_cambio
                ),
            }

            if comp_origen.estado_sugerido_id:
                vals_comp['estado_sugerido_id'] = (
                    comp_origen.estado_sugerido_id.id
                )

            comp_nuevo = ComponenteModel.create(
                vals_comp
            )

            componentes_copiados += 1

            for subparte_origen in comp_origen.detalle_ids:
                SubparteModel.create(
                    {
                        'componente_id': comp_nuevo.id,
                        'subparte_id': (
                            subparte_origen.subparte_id.id
                        ),
                        'cantidad': subparte_origen.cantidad,
                        'nota': subparte_origen.nota,
                    }
                )

        accesorios_origen = AccesorioModel.search(
            [('modelo_id', '=', modelo_origen.id)]
        )

        accesorios_copiados = 0

        for acc_origen in accesorios_origen:
            existe_acc = AccesorioModel.search(
                [
                    ('modelo_id', '=', self.id),
                    ('tipo_id', '=', acc_origen.tipo_id.id),
                ],
                limit=1,
            )

            if existe_acc:
                continue

            vals_acc = {
                'modelo_id': self.id,
                'tipo_id': acc_origen.tipo_id.id,
                'obligatorio': acc_origen.obligatorio,
                'nota': acc_origen.nota,
            }

            if acc_origen.estado_predeterminado_id:
                vals_acc['estado_predeterminado_id'] = (
                    acc_origen.estado_predeterminado_id.id
                )

            if (
                hasattr(acc_origen, 'subparte_ids')
                and acc_origen.subparte_ids
            ):
                vals_acc['subparte_ids'] = [
                    (
                        6,
                        0,
                        acc_origen.subparte_ids.ids,
                    )
                ]

            AccesorioModel.create(vals_acc)
            accesorios_copiados += 1

        return {
            'componentes': componentes_copiados,
            'accesorios': accesorios_copiados,
        }

    # =========================================================
    # CREATE
    # =========================================================

    @api.model_create_multi
    def create(self, vals_list):
        modelos_referencia = []

        for vals in vals_list:
            if vals.get('name') and not vals.get('codigo_tecnico'):
                vals['codigo_tecnico'] = self._normalizar_codigo(
                    vals['name']
                )

            modelos_referencia.append(
                vals.get('modelo_referencia_id')
            )

        records = super().create(vals_list)

        for record, modelo_ref_id in zip(
            records,
            modelos_referencia,
        ):
            if not modelo_ref_id:
                continue

            modelo_referencia = self.env[
                'modelo.maquina'
            ].browse(modelo_ref_id)

            if modelo_referencia.exists():
                record._copiar_configuracion_desde_modelo(
                    modelo_referencia
                )

        return records

    # =========================================================
    # ACCIONES EXISTENTES
    # =========================================================

    def action_copiar_desde_modelo(self):
        self.ensure_one()

        if not self.modelo_referencia_id:
            raise UserError(
                _(
                    'Debe seleccionar un modelo de referencia.'
                )
            )

        comp_count = self.env[
            'modelo.maquina.componente'
        ].search_count(
            [
                (
                    'modelo_id',
                    '=',
                    self.modelo_referencia_id.id,
                )
            ]
        )

        acc_count = self.env[
            'modelo.maquina.accesorio'
        ].search_count(
            [
                (
                    'modelo_id',
                    '=',
                    self.modelo_referencia_id.id,
                )
            ]
        )

        resultado = self._copiar_configuracion_desde_modelo(
            self.modelo_referencia_id
        )

        self._compute_totales_config()

        comp_copiados = resultado.get(
            'componentes',
            0,
        )

        acc_copiados = resultado.get(
            'accesorios',
            0,
        )

        if comp_copiados == 0 and acc_copiados == 0:
            message = _(
                'No se copió ningún elemento. '
                'Los registros pueden existir previamente.'
            )
            notification_type = 'info'
        else:
            message = _(
                'Se copiaron %(components)s de %(total_components)s '
                'componentes y %(accessories)s de %(total_accessories)s '
                'accesorios desde "%(model)s".'
            ) % {
                'components': comp_copiados,
                'total_components': comp_count,
                'accessories': acc_copiados,
                'total_accessories': acc_count,
                'model': self.modelo_referencia_id.name,
            }
            notification_type = 'success'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración copiada'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            },
        }

    def action_ver_componentes(self):
        self.ensure_one()

        return {
            'name': _('Componentes - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina.componente',
            'view_mode': 'list,form',
            'domain': [('modelo_id', '=', self.id)],
            'context': {
                'default_modelo_id': self.id,
                'search_default_modelo_id': self.id,
            },
        }

    def action_ver_accesorios(self):
        self.ensure_one()

        return {
            'name': _('Accesorios - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina.accesorio',
            'view_mode': 'list,form',
            'domain': [('modelo_id', '=', self.id)],
            'context': {
                'default_modelo_id': self.id,
                'search_default_modelo_id': self.id,
            },
        }
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SolicitudPartesAprobarWizard(models.TransientModel):
    """Wizard para aprobar solicitud y seleccionar quien retira"""
    _name = 'solicitud.partes.aprobar.wizard'
    _description = 'Wizard Aprobar y Autorizar Retiro'
    
    solicitud_id = fields.Many2one(
        'solicitud.partes', 
        string='Solicitud', 
        required=True,
        readonly=True
    )
    
    # Información de la solicitud (para mostrar)
    maquina_origen = fields.Char(
        related='solicitud_id.maquina_origen_id.name.name',
        string='Máquina Origen',
        readonly=True
    )
    serie_origen = fields.Char(
        related='solicitud_id.maquina_origen_id.serie',
        string='Serie Origen',
        readonly=True
    )
    solicitante = fields.Char(
        related='solicitud_id.solicitante_id.name',
        string='Solicitante',
        readonly=True
    )
    
    # Campo principal
    autorizado_retirar_id = fields.Many2one(
        'res.users',
        string='Autorizado para Retirar',
        required=True,
        domain="[('share', '=', False)]",
        help="Seleccione el usuario autorizado para retirar las partes"
    )
    
    # Mostrar si tiene teléfono
    tiene_telefono = fields.Boolean(
        string='Tiene Teléfono',
        compute='_compute_tiene_telefono'
    )
    telefono_display = fields.Char(
        string='Teléfono',
        compute='_compute_tiene_telefono'
    )
    
    @api.depends('autorizado_retirar_id')
    def _compute_tiene_telefono(self):
        for record in self:
            if record.autorizado_retirar_id and record.autorizado_retirar_id.mobile_phone:
                record.tiene_telefono = True
                record.telefono_display = record.autorizado_retirar_id.mobile_phone
            else:
                record.tiene_telefono = False
                record.telefono_display = 'Sin teléfono registrado'
    
    @api.constrains('autorizado_retirar_id')
    def _check_telefono(self):
        """Advertencia si no tiene teléfono"""
        for record in self:
            if record.autorizado_retirar_id and not record.autorizado_retirar_id.mobile_phone:
                _logger.warning(
                    f"Usuario {record.autorizado_retirar_id.name} sin teléfono. "
                    f"No recibirá notificación WhatsApp."
                )
    
    def action_aprobar(self):
        """Aprobar y notificar"""
        self.ensure_one()
        
        if not self.autorizado_retirar_id:
            raise UserError(_('Debe seleccionar un usuario autorizado'))
        
        # Actualizar solicitud
        self.solicitud_id.write({
            'autorizado_retirar_id': self.autorizado_retirar_id.id
        })
        
        # Aprobar y notificar
        self.solicitud_id._aprobar_y_notificar()
        
        return {'type': 'ir.actions.act_window_close'}


class SolicitudPartesRetiroWizard(models.TransientModel):
    """Wizard para confirmar retiro de parte"""
    _name = 'solicitud.partes.retiro.wizard'
    _description = 'Wizard Confirmar Retiro'
    
    solicitud_id = fields.Many2one(
        'solicitud.partes', 
        string='Solicitud',
        readonly=True
    )
    parte_linea_id = fields.Many2one(
        'solicitud.partes.linea', 
        string='Parte', 
        required=True,
        readonly=True
    )
    
    # Información de la parte (mostrar)
    parte_nombre = fields.Char(
        related='parte_linea_id.parte',
        string='Parte',
        readonly=True
    )
    parte_descripcion = fields.Text(
        related='parte_linea_id.descripcion',
        string='Descripción',
        readonly=True
    )
    maquina_origen = fields.Char(
        related='solicitud_id.maquina_origen_id.name.name',
        readonly=True
    )
    
    # Campo principal: quien instala
    opcion_instalacion = fields.Selection([
        ('yo_mismo', 'Yo mismo lo instalaré'),
        ('otra_persona', 'Otra persona lo instalará')
    ], string='¿Quién instalará esta parte?', required=True, default='yo_mismo')
    
    instalado_por_id = fields.Many2one(
        'res.users',
        string='Será instalado por',
        domain="[('share', '=', False)]"
    )
    
    # Info del instalador
    tiene_telefono_instalador = fields.Boolean(
        string='Tiene Teléfono',
        compute='_compute_info_instalador'
    )
    telefono_instalador = fields.Char(
        string='Teléfono',
        compute='_compute_info_instalador'
    )
    
    @api.depends('instalado_por_id')
    def _compute_info_instalador(self):
        for record in self:
            if record.instalado_por_id and record.instalado_por_id.mobile_phone:
                record.tiene_telefono_instalador = True
                record.telefono_instalador = record.instalado_por_id.mobile_phone
            else:
                record.tiene_telefono_instalador = False
                record.telefono_instalador = 'Sin teléfono'
    
    @api.onchange('opcion_instalacion')
    def _onchange_opcion(self):
        """Al cambiar opción, prellenar campos"""
        if self.opcion_instalacion == 'yo_mismo':
            self.instalado_por_id = self.env.user
        else:
            self.instalado_por_id = False
    
    @api.constrains('opcion_instalacion', 'instalado_por_id')
    def _check_instalado_por(self):
        """Validar que se seleccione instalador"""
        for record in self:
            if record.opcion_instalacion == 'otra_persona' and not record.instalado_por_id:
                raise ValidationError(_('Debe seleccionar quién instalará la parte'))
    
    def action_confirmar_retiro(self):
        """Confirmar retiro"""
        self.ensure_one()
        
        if self.opcion_instalacion == 'otra_persona' and not self.instalado_por_id:
            raise UserError(_('Debe seleccionar quién instalará'))
        
        instalado_por = (
            self.instalado_por_id 
            if self.opcion_instalacion == 'otra_persona' 
            else self.env.user
        )
        yo_mismo = (self.opcion_instalacion == 'yo_mismo')
        
        # Confirmar retiro
        self.parte_linea_id._confirmar_retiro(instalado_por.id, yo_mismo)
        
        return {'type': 'ir.actions.act_window_close'}


class SolicitudPartesReposicionWizard(models.TransientModel):
    """Wizard para confirmar reposición con foto"""
    _name = 'solicitud.partes.reposicion.wizard'
    _description = 'Wizard Confirmar Reposición'
    
    parte_linea_id = fields.Many2one(
        'solicitud.partes.linea', 
        string='Parte', 
        required=True,
        readonly=True
    )
    
    # Información de la parte
    parte_nombre = fields.Char(
        related='parte_linea_id.parte',
        readonly=True
    )
    parte_descripcion = fields.Text(
        related='parte_linea_id.descripcion',
        readonly=True
    )
    solicitud_nombre = fields.Char(
        related='parte_linea_id.solicitud_id.name',
        string='Solicitud',
        readonly=True
    )
    fecha_retiro = fields.Datetime(
        related='parte_linea_id.fecha_retiro_real',
        string='Retirada el',
        readonly=True
    )
    
    # Campos principales
    condicion = fields.Selection([
        ('bueno', 'Buen Estado'),
        ('defectuoso', 'Defectuoso')
    ], string='Condición de la Parte Repuesta', required=True, default='bueno')
    
    foto_reposicion = fields.Binary(
        string='Foto de Reposición',
        required=True,
        help="Adjunte foto clara de la parte repuesta e instalada"
    )
    foto_reposicion_filename = fields.Char(
        string='Nombre Archivo',
        default='reposicion.jpg'
    )
    
    observaciones = fields.Text(
        string='Observaciones',
        help="Comentarios adicionales sobre la reposición"
    )
    
    # Ayuda visual
    mostrar_ayuda = fields.Boolean(
        string='Mostrar instrucciones',
        default=True
    )
    
    @api.constrains('foto_reposicion')
    def _check_foto(self):
        """Validar que se adjunte foto"""
        for record in self:
            if not record.foto_reposicion:
                raise ValidationError(_('La foto de reposición es obligatoria'))
    
    def action_confirmar_reposicion(self):
        """Confirmar reposición"""
        self.ensure_one()
        
        if not self.foto_reposicion:
            raise UserError(_('Debe adjuntar una foto de la reposición'))
        
        # Confirmar reposición
        self.parte_linea_id._confirmar_reposicion(
            self.condicion,
            self.foto_reposicion,
            self.foto_reposicion_filename,
            self.observaciones
        )
        
        return {'type': 'ir.actions.act_window_close'}


class SolicitudPartesAutorizarRetiroWizard(models.TransientModel):
    """Wizard para autorizar retiro y asignar responsables"""
    _name = 'solicitud.partes.autorizar.retiro.wizard'
    _description = 'Wizard Autorizar Retiro'
    
    solicitud_id = fields.Many2one('solicitud.partes', required=True, readonly=True)
    
    autorizado_retirar_id = fields.Many2one(
        'res.users',
        string='Quien Retirará',
        required=True,
        domain="[('share', '=', False)]"
    )
    
    responsable_reposicion_id = fields.Many2one(
        'res.users',
        string='Quien Recibirá/Repondrá',
        required=True,
        domain="[('share', '=', False)]"
    )
    
    def action_autorizar(self):
        self.ensure_one()
        
        self.solicitud_id._autorizar_retiro_confirmar(
            self.autorizado_retirar_id.id,
            self.responsable_reposicion_id.id
        )
        
        return {'type': 'ir.actions.act_window_close'}
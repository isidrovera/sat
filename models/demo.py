    @api.model
    def accion_bloqueo_rapida(self, equipo_id, accion, motivo=None):
        """
        Método para ejecutar acciones de bloqueo rápidas desde el dashboard
        
        Args:
            equipo_id (int): ID del equipo
            accion (str): 'suspender', 'bloquear', 'desbloquear'
            motivo (str): Motivo de la acción
        
        Returns:
            dict: Resultado de la operación
        """
        try:
            equipo = self.env['alquiler'].browse(equipo_id)
            if not equipo.exists():
                return {'success': False, 'error': 'Equipo no encontrado'}

            usuario_id = self.env.user.id
            
            if accion == 'suspender':
                result = equipo.action_suspender_servicio(motivo, usuario_id)
            elif accion == 'bloquear':
                result = equipo.action_bloquear_equipo(motivo, usuario_id)
            elif accion == 'desbloquear':
                result = equipo.action_desbloquear_equipo(motivo, usuario_id)
            else:
                return {'success': False, 'error': 'Acción no válida'}

            if result:
                _logger.info(f"Acción {accion} ejecutada en equipo {equipo.serie} por usuario {self.env.user.name}")
                return {
                    'success': True, 
                    'message': f'Acción {accion} ejecutada exitosamente',
                    'nuevo_estado': equipo.estado_bloqueo
                }
            else:
                return {'success': False, 'error': 'Error al ejecutar la acción'}

        except Exception as e:
            _logger.error(f"Error en accion_bloqueo_rapida: {str(e)}")
            return {'success': False, 'error': str(e)}
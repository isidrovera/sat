odoo.define('equipment_blocking_dashboard', function (require) {
    'use strict';

    var core = require('web.core');
    var publicWidget = require('web.public.widget');
    var ajax = require('web.ajax');

    var EquipmentBlockingDashboard = publicWidget.Widget.extend({
        selector: '#wrap',
        events: {
            'click .dashboard-card': '_onDashboardCardClick',
            'keypress #search-input': '_onSearchKeypress',
            'click #confirmActionBtn': '_executeAction',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.currentAction = null;
            this.currentEquipmentId = null;
            this.actionModal = null;
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                // Inicializar modal de Bootstrap
                var modalEl = document.getElementById('actionModal');
                if (modalEl && typeof bootstrap !== 'undefined') {
                    self.actionModal = new bootstrap.Modal(modalEl);
                }
                
                // Configurar event listeners
                self._setupEventListeners();
            });
        },

        _setupEventListeners: function () {
            var self = this;
            
            // Shortcuts de teclado
            document.addEventListener('keydown', function(e) {
                // Ctrl/Cmd + K para buscar
                if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                    e.preventDefault();
                    document.getElementById('search-input').focus();
                }
                
                // Escape para cerrar modal
                if (e.key === 'Escape' && self.actionModal) {
                    self.actionModal.hide();
                }
            });
        },

        _onSearchKeypress: function (ev) {
            if (ev.which === 13) { // Enter key
                this.searchEquipments();
            }
        },

        _onDashboardCardClick: function (ev) {
            // Implementar filtro por tipo de estado si es necesario
        },

        getCsrfToken: function () {
            return odoo.csrf_token || $('meta[name="csrf-token"]').attr('content') || '';
        },

        refreshDashboard: function () {
            var self = this;
            return ajax.jsonRpc('/equipment/blocking/dashboard_data', 'call', {})
                .then(function (result) {
                    if (result.status === 'success') {
                        var data = result.data;
                        $('#equipos-activos').text(data.equipos_activos);
                        $('#equipos-suspendidos').text(data.equipos_suspendidos);
                        $('#equipos-bloqueados').text(data.equipos_bloqueados);
                        $('#equipos-no-accesibles').text(data.equipos_no_accesibles);
                        $('#pendientes-bloqueo').text(data.pendientes_bloqueo);
                        $('#pendientes-desbloqueo').text(data.pendientes_desbloqueo);
                        
                        self.showAlert('success', 'Dashboard actualizado correctamente');
                    }
                })
                .fail(function (error) {
                    console.error('Error al actualizar dashboard:', error);
                    self.showAlert('danger', 'Error al actualizar el dashboard');
                });
        },

        searchEquipments: function () {
            var self = this;
            var searchTerm = $('#search-input').val();
            var resultsContainer = $('#equipment-results');
            
            resultsContainer.html(
                '<div class="text-center py-5">' +
                    '<div class="spinner-border text-primary mb-3" role="status"></div>' +
                    '<p class="text-muted">Buscando equipos...</p>' +
                '</div>'
            );

            return ajax.jsonRpc('/equipment/blocking/search', 'call', {
                search_term: searchTerm
            }).then(function (result) {
                if (result.status === 'success') {
                    self.displayEquipments(result.equipos);
                } else {
                    self.showAlert('danger', 'Error al buscar equipos: ' + result.message);
                }
            }).fail(function (error) {
                self.showAlert('danger', 'Error de conexión');
                console.error('Error:', error);
            });
        },

        loadPendingEquipments: function () {
            var self = this;
            $('#search-input').val('');
            
            var resultsContainer = $('#equipment-results');
            resultsContainer.html(
                '<div class="text-center py-5">' +
                    '<div class="spinner-border text-warning mb-3" role="status"></div>' +
                    '<p class="text-muted">Cargando equipos pendientes...</p>' +
                '</div>'
            );

            return ajax.jsonRpc('/equipment/blocking/search', 'call', {
                search_term: '',
                only_pending: true
            }).then(function (result) {
                if (result.status === 'success') {
                    var pendingEquipments = result.equipos.filter(function(eq) {
                        return ['suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'].includes(eq.estado_bloqueo);
                    });
                    self.displayEquipments(pendingEquipments);
                } else {
                    self.showAlert('danger', 'Error al cargar equipos: ' + result.message);
                }
            }).fail(function (error) {
                self.showAlert('danger', 'Error de conexión');
                console.error('Error:', error);
            });
        },

        displayEquipments: function (equipos) {
            var self = this;
            var resultsContainer = $('#equipment-results');
            
            if (equipos.length === 0) {
                resultsContainer.html(
                    '<div class="text-center py-5">' +
                        '<i class="fas fa-inbox fa-3x text-muted mb-3"></i>' +
                        '<p class="text-muted">No se encontraron equipos con los criterios especificados.</p>' +
                    '</div>'
                );
                return;
            }

            var equipmentCards = equipos.map(function(equipo) {
                var motivoSection = equipo.motivo_bloqueo ? 
                    '<div class="alert alert-info py-2 mb-3">' +
                        '<strong>Motivo:</strong> ' + self._escapeHtml(equipo.motivo_bloqueo) +
                    '</div>' : '';
                
                var fechaSection = equipo.fecha_bloqueo ? 
                    '<div class="text-muted small mb-3">' +
                        '<i class="fas fa-clock"></i> ' + self._escapeHtml(equipo.fecha_bloqueo) +
                    '</div>' : '';

                var buttons = [];
                if (equipo.puede_suspender) {
                    buttons.push(
                        '<button class="btn btn-warning btn-sm" onclick="equipmentDashboard.openActionModal(\'suspend\', ' + 
                        equipo.id + ', \'' + self._escapeHtml(equipo.serie) + '\', ' + 
                        JSON.stringify(equipo).replace(/"/g, '&quot;') + ')">' +
                            '<i class="fas fa-pause me-1"></i> Suspender' +
                        '</button>'
                    );
                }
                if (equipo.puede_bloquear) {
                    buttons.push(
                        '<button class="btn btn-danger btn-sm" onclick="equipmentDashboard.openActionModal(\'block\', ' + 
                        equipo.id + ', \'' + self._escapeHtml(equipo.serie) + '\', ' + 
                        JSON.stringify(equipo).replace(/"/g, '&quot;') + ')">' +
                            '<i class="fas fa-lock me-1"></i> Bloquear' +
                        '</button>'
                    );
                }
                if (equipo.puede_desbloquear) {
                    buttons.push(
                        '<button class="btn btn-success btn-sm" onclick="equipmentDashboard.openActionModal(\'unblock\', ' + 
                        equipo.id + ', \'' + self._escapeHtml(equipo.serie) + '\', ' + 
                        JSON.stringify(equipo).replace(/"/g, '&quot;') + ')">' +
                            '<i class="fas fa-unlock me-1"></i> Desbloquear' +
                        '</button>'
                    );
                }

                return (
                    '<div class="equipment-card">' +
                        '<div class="d-flex justify-content-between align-items-start mb-3">' +
                            '<div>' +
                                '<h5 class="mb-1 fw-bold">Serie: ' + self._escapeHtml(equipo.serie) + '</h5>' +
                                '<p class="text-muted mb-0">' + self._escapeHtml(equipo.cliente) + ' - ' + self._escapeHtml(equipo.modelo) + '</p>' +
                            '</div>' +
                            '<span class="status-badge status-' + equipo.estado_bloqueo + '">' +
                                self._escapeHtml(equipo.estado_label) +
                            '</span>' +
                        '</div>' +
                        
                        '<div class="detail-grid">' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-industry"></i>' +
                                '<span>Marca: ' + self._escapeHtml(equipo.marca) + '</span>' +
                            '</div>' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-map-marker-alt"></i>' +
                                '<span>Dirección: ' + self._escapeHtml(equipo.direccion) + '</span>' +
                            '</div>' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-network-wired"></i>' +
                                '<span>IP: ' + self._escapeHtml(equipo.ip_equipo || 'No configurada') + '</span>' +
                            '</div>' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-wifi"></i>' +
                                '<span>Acceso remoto: ' + (equipo.acceso_remoto ? 'Disponible' : 'No disponible') + '</span>' +
                            '</div>' +
                        '</div>' +
                        
                        motivoSection +
                        fechaSection +
                        
                        '<div class="d-flex gap-2 justify-content-end flex-wrap">' +
                            buttons.join('') +
                        '</div>' +
                    '</div>'
                );
            }).join('');

            resultsContainer.html(equipmentCards);
        },

        openActionModal: function (action, equipmentId, serie, equipmentData) {
            var self = this;
            this.currentAction = action;
            this.currentEquipmentId = equipmentId;
            
            var equipment = typeof equipmentData === 'string' ? JSON.parse(equipmentData) : equipmentData;
            
            var modalTitle = $('#modalTitle');
            var motivoInput = $('#motivoInput');
            var confirmBtn = $('#confirmActionBtn');
            var equipmentDetails = $('#equipmentDetails');
            
            // Mostrar detalles del equipo
            $('#detailCliente').text(equipment.cliente);
            $('#detailModelo').text(equipment.modelo);
            $('#detailIP').text(equipment.ip_equipo || 'No configurada');
            $('#detailEstado').html('<span class="status-badge status-' + equipment.estado_bloqueo + '">' + equipment.estado_label + '</span>');
            equipmentDetails.show();
            
            // Configurar según la acción
            switch(action) {
                case 'suspend':
                    modalTitle.text('Suspender Servicio - Serie: ' + serie);
                    motivoInput.attr('placeholder', 'Motivo de la suspensión (ej: Mora de pagos, incumplimiento contractual...)');
                    confirmBtn.removeClass().addClass('btn btn-warning');
                    break;
                case 'block':
                    modalTitle.text('Bloquear Equipo - Serie: ' + serie);
                    motivoInput.attr('placeholder', 'Motivo del bloqueo remoto...');
                    confirmBtn.removeClass().addClass('btn btn-danger');
                    break;
                case 'unblock':
                    modalTitle.text('Desbloquear Equipo - Serie: ' + serie);
                    motivoInput.attr('placeholder', 'Observaciones del desbloqueo...');
                    confirmBtn.removeClass().addClass('btn btn-success');
                    break;
            }
            
            // Limpiar modal y mostrar
            motivoInput.val('');
            $('#modalAlert').html('');
            
            if (this.actionModal) {
                this.actionModal.show();
            }
        },

        _executeAction: function () {
            var self = this;
            var motivo = $('#motivoInput').val();
            var btnLoading = $('#btnLoading');
            var btnText = $('#btnText');
            var confirmBtn = $('#confirmActionBtn');
            
            // Mostrar loading
            btnLoading.removeClass('d-none');
            btnText.addClass('d-none');
            confirmBtn.prop('disabled', true);

            var endpoints = {
                'suspend': '/equipment/blocking/suspend',
                'block': '/equipment/blocking/block',
                'unblock': '/equipment/blocking/unblock'
            };

            return ajax.jsonRpc(endpoints[this.currentAction], 'call', {
                equipment_id: this.currentEquipmentId,
                motivo: motivo
            }).then(function (result) {
                if (result.status === 'success') {
                    self.showModalAlert('success', result.message);
                    
                    // Cerrar modal después de 2 segundos y actualizar
                    setTimeout(function() {
                        if (self.actionModal) {
                            self.actionModal.hide();
                        }
                        self.refreshDashboard();
                        self.searchEquipments();
                    }, 2000);
                } else {
                    self.showModalAlert('danger', result.message);
                }
            }).fail(function (error) {
                self.showModalAlert('danger', 'Error de conexión');
                console.error('Error:', error);
            }).always(function () {
                // Ocultar loading
                btnLoading.addClass('d-none');
                btnText.removeClass('d-none');
                confirmBtn.prop('disabled', false);
            });
        },

        showModalAlert: function (type, message) {
            var alertContainer = $('#modalAlert');
            var alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
            var icon = type === 'success' ? 'check-circle' : 'exclamation-triangle';
            
            alertContainer.html(
                '<div class="alert ' + alertClass + ' d-flex align-items-center" role="alert">' +
                    '<i class="fas fa-' + icon + ' me-2"></i>' +
                    '<div>' + this._escapeHtml(message) + '</div>' +
                '</div>'
            );
        },

        showAlert: function (type, message) {
            var self = this;
            // Crear contenedor de alertas si no existe
            var alertContainer = $('#general-alerts');
            if (alertContainer.length === 0) {
                alertContainer = $('<div id="general-alerts" class="position-fixed top-0 end-0 p-3" style="z-index: 1055;"></div>');
                $('body').append(alertContainer);
            }
            
            var alertId = 'alert-' + Date.now();
            var alertClass = type === 'success' ? 'alert-success' : 
                           type === 'warning' ? 'alert-warning' : 'alert-danger';
            var icon = type === 'success' ? 'check-circle' : 
                      type === 'warning' ? 'exclamation-triangle' : 'times-circle';
            
            var alertHtml = (
                '<div id="' + alertId + '" class="alert ' + alertClass + ' alert-dismissible fade show" role="alert">' +
                    '<i class="fas fa-' + icon + ' me-2"></i>' +
                    this._escapeHtml(message) +
                    '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' +
                '</div>'
            );
            
            alertContainer.append(alertHtml);
            
            // Auto-dismiss después de 5 segundos
            setTimeout(function() {
                var alert = $('#' + alertId);
                if (alert.length && typeof bootstrap !== 'undefined') {
                    var bsAlert = new bootstrap.Alert(alert[0]);
                    bsAlert.close();
                }
            }, 5000);
        },

        _escapeHtml: function (text) {
            if (!text) return '';
            var map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return String(text).replace(/[&<>"']/g, function(m) { return map[m]; });
        },

        filterByStatus: function (status) {
            $('#search-input').val('');
            this.loadPendingEquipments();
        },

        getEquipmentDetails: function (equipmentId) {
            return ajax.jsonRpc('/equipment/blocking/get_equipment_details', 'call', {
                equipment_id: equipmentId
            }).then(function (result) {
                return result.status === 'success' ? result.equipment : null;
            }).fail(function (error) {
                console.error('Error al obtener detalles:', error);
                return null;
            });
        }
    });

    // Instanciar y exponer globalmente para compatibilidad
    var equipmentDashboard = new EquipmentBlockingDashboard();
    
    // Funciones globales para compatibilidad con onclick
    window.searchEquipments = function() {
        equipmentDashboard.searchEquipments();
    };
    
    window.loadPendingEquipments = function() {
        equipmentDashboard.loadPendingEquipments();
    };
    
    window.refreshDashboard = function() {
        equipmentDashboard.refreshDashboard();
    };
    
    window.equipmentDashboard = equipmentDashboard;

    // Inicializar cuando el DOM esté listo
    $(document).ready(function() {
        equipmentDashboard.attachTo($('body'));
    });

    return EquipmentBlockingDashboard;
});
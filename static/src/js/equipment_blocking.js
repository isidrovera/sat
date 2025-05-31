// equipment_blocking.js - Versión corregida para Odoo 18

// Definir el namespace global para evitar conflictos
window.EquipmentBlocking = window.EquipmentBlocking || {};

(function() {
    'use strict';

    // Variables del módulo
    let currentAction = null;
    let currentEquipmentId = null;
    let actionModal = null;

    // Objeto principal del módulo
    const EquipmentBlockingModule = {
        // Inicialización
        init: function() {
            this.initializeModal();
            this.setupEventListeners();
            console.log('Equipment Blocking Dashboard initialized');
        },

        initializeModal: function() {
            const modalEl = document.getElementById('actionModal');
            if (modalEl && typeof bootstrap !== 'undefined') {
                actionModal = new bootstrap.Modal(modalEl);
            }
        },

        setupEventListeners: function() {
            // Enter en búsqueda
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                searchInput.addEventListener('keypress', (e) => {
                    if (e.which === 13) {
                        this.searchEquipments();
                    }
                });
            }

            // Botón de confirmación del modal
            const confirmBtn = document.getElementById('confirmActionBtn');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', () => this.executeAction());
            }
            
            // Shortcuts de teclado
            document.addEventListener('keydown', (e) => {
                // Ctrl/Cmd + K para buscar
                if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                    e.preventDefault();
                    if (searchInput) searchInput.focus();
                }
                
                // Escape para cerrar modal
                if (e.key === 'Escape' && actionModal) {
                    actionModal.hide();
                }
            });
        },

        getCsrfToken: function() {
            const metaToken = document.querySelector('meta[name="csrf-token"]');
            return metaToken ? metaToken.getAttribute('content') : '';
        },

        makeJsonRpcCall: function(url, params) {
            return fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: params
                })
            })
            .then(response => response.json())
            .then(data => data.result)
            .catch(error => {
                console.error('JSON-RPC Error:', error);
                throw error;
            });
        },

        refreshDashboard: function() {
            return this.makeJsonRpcCall('/equipment/blocking/dashboard_data', {})
                .then(result => {
                    if (result.status === 'success') {
                        const data = result.data;
                        this.updateElement('equipos-activos', data.equipos_activos);
                        this.updateElement('equipos-suspendidos', data.equipos_suspendidos);
                        this.updateElement('equipos-bloqueados', data.equipos_bloqueados);
                        this.updateElement('equipos-no-accesibles', data.equipos_no_accesibles);
                        this.updateElement('pendientes-bloqueo', data.pendientes_bloqueo);
                        this.updateElement('pendientes-desbloqueo', data.pendientes_desbloqueo);
                        
                        this.showAlert('success', 'Dashboard actualizado correctamente');
                    }
                })
                .catch(error => {
                    console.error('Error al actualizar dashboard:', error);
                    this.showAlert('danger', 'Error al actualizar el dashboard');
                });
        },

        updateElement: function(id, value) {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        },

        searchEquipments: function() {
            const searchInput = document.getElementById('search-input');
            const searchTerm = searchInput ? searchInput.value : '';
            const resultsContainer = document.getElementById('equipment-results');
            
            if (resultsContainer) {
                resultsContainer.innerHTML = 
                    '<div class="text-center py-5">' +
                        '<div class="spinner-border text-primary mb-3" role="status"></div>' +
                        '<p class="text-muted">Buscando equipos...</p>' +
                    '</div>';
            }

            return this.makeJsonRpcCall('/equipment/blocking/search', {
                search_term: searchTerm
            })
            .then(result => {
                if (result.status === 'success') {
                    this.displayEquipments(result.equipos);
                } else {
                    this.showAlert('danger', 'Error al buscar equipos: ' + result.message);
                }
            })
            .catch(error => {
                this.showAlert('danger', 'Error de conexión');
                console.error('Error:', error);
            });
        },

        loadPendingEquipments: function() {
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                searchInput.value = '';
            }
            
            const resultsContainer = document.getElementById('equipment-results');
            if (resultsContainer) {
                resultsContainer.innerHTML = 
                    '<div class="text-center py-5">' +
                        '<div class="spinner-border text-warning mb-3" role="status"></div>' +
                        '<p class="text-muted">Cargando equipos pendientes...</p>' +
                    '</div>';
            }

            return this.makeJsonRpcCall('/equipment/blocking/search', {
                search_term: '',
                only_pending: true
            })
            .then(result => {
                if (result.status === 'success') {
                    const pendingEquipments = result.equipos.filter(eq => 
                        ['suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'].includes(eq.estado_bloqueo)
                    );
                    this.displayEquipments(pendingEquipments);
                } else {
                    this.showAlert('danger', 'Error al cargar equipos: ' + result.message);
                }
            })
            .catch(error => {
                this.showAlert('danger', 'Error de conexión');
                console.error('Error:', error);
            });
        },

        displayEquipments: function(equipos) {
            const resultsContainer = document.getElementById('equipment-results');
            if (!resultsContainer) return;
            
            if (equipos.length === 0) {
                resultsContainer.innerHTML = 
                    '<div class="text-center py-5">' +
                        '<i class="fas fa-inbox fa-3x text-muted mb-3"></i>' +
                        '<p class="text-muted">No se encontraron equipos con los criterios especificados.</p>' +
                    '</div>';
                return;
            }

            const equipmentCards = equipos.map(equipo => {
                const motivoSection = equipo.motivo_bloqueo ? 
                    '<div class="alert alert-info py-2 mb-3">' +
                        '<strong>Motivo:</strong> ' + this.escapeHtml(equipo.motivo_bloqueo) +
                    '</div>' : '';
                
                const fechaSection = equipo.fecha_bloqueo ? 
                    '<div class="text-muted small mb-3">' +
                        '<i class="fas fa-clock"></i> ' + this.escapeHtml(equipo.fecha_bloqueo) +
                    '</div>' : '';

                const buttons = [];
                if (equipo.puede_suspender) {
                    buttons.push(
                        `<button class="btn btn-warning btn-sm" onclick="EquipmentBlocking.openActionModal('suspend', ${equipo.id}, '${this.escapeHtml(equipo.serie)}', ${JSON.stringify(equipo).replace(/"/g, '&quot;')})">` +
                            '<i class="fas fa-pause me-1"></i> Suspender' +
                        '</button>'
                    );
                }
                if (equipo.puede_bloquear) {
                    buttons.push(
                        `<button class="btn btn-danger btn-sm" onclick="EquipmentBlocking.openActionModal('block', ${equipo.id}, '${this.escapeHtml(equipo.serie)}', ${JSON.stringify(equipo).replace(/"/g, '&quot;')})">` +
                            '<i class="fas fa-lock me-1"></i> Bloquear' +
                        '</button>'
                    );
                }
                if (equipo.puede_desbloquear) {
                    buttons.push(
                        `<button class="btn btn-success btn-sm" onclick="EquipmentBlocking.openActionModal('unblock', ${equipo.id}, '${this.escapeHtml(equipo.serie)}', ${JSON.stringify(equipo).replace(/"/g, '&quot;')})">` +
                            '<i class="fas fa-unlock me-1"></i> Desbloquear' +
                        '</button>'
                    );
                }

                return (
                    '<div class="equipment-card">' +
                        '<div class="d-flex justify-content-between align-items-start mb-3">' +
                            '<div>' +
                                '<h5 class="mb-1 fw-bold">Serie: ' + this.escapeHtml(equipo.serie) + '</h5>' +
                                '<p class="text-muted mb-0">' + this.escapeHtml(equipo.cliente) + ' - ' + this.escapeHtml(equipo.modelo) + '</p>' +
                            '</div>' +
                            '<span class="status-badge status-' + equipo.estado_bloqueo + '">' +
                                this.escapeHtml(equipo.estado_label) +
                            '</span>' +
                        '</div>' +
                        
                        '<div class="detail-grid">' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-industry"></i>' +
                                '<span>Marca: ' + this.escapeHtml(equipo.marca) + '</span>' +
                            '</div>' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-map-marker-alt"></i>' +
                                '<span>Dirección: ' + this.escapeHtml(equipo.direccion) + '</span>' +
                            '</div>' +
                            '<div class="detail-item">' +
                                '<i class="fas fa-network-wired"></i>' +
                                '<span>IP: ' + this.escapeHtml(equipo.ip_equipo || 'No configurada') + '</span>' +
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

            resultsContainer.innerHTML = equipmentCards;
        },

        function openActionModal(action, equipmentId, serie, equipmentIdRef) {
    console.log('Opening action modal:', action, equipmentId);
    currentAction = action;
    currentEquipmentId = equipmentId;
    
    // Obtener datos del equipo desde el DOM
    let equipment = {};
    
    // Buscar la tarjeta del equipo en el DOM usando la serie
    const equipmentCards = document.querySelectorAll('.equipment-card');
    let equipmentCard = null;
    
    for (let card of equipmentCards) {
        const serieElement = card.querySelector('h5');
        if (serieElement && serieElement.textContent.includes(serie)) {
            equipmentCard = card;
            break;
        }
    }
    
    if (equipmentCard) {
        // Extraer información del DOM
        const serieText = equipmentCard.querySelector('h5')?.textContent || '';
        const clienteModeloText = equipmentCard.querySelector('p.text-muted')?.textContent || '';
        const [cliente, modelo] = clienteModeloText.split(' - ');
        
        // Extraer marca de los detail-items
        const detailItems = equipmentCard.querySelectorAll('.detail-item span');
        let marca = '';
        let direccion = '';
        let ip = '';
        let accesoRemoto = false;
        
        detailItems.forEach(item => {
            const text = item.textContent;
            if (text.startsWith('Marca:')) {
                marca = text.replace('Marca:', '').trim();
            } else if (text.startsWith('Dirección:')) {
                direccion = text.replace('Dirección:', '').trim();
            } else if (text.startsWith('IP:')) {
                ip = text.replace('IP:', '').trim();
            } else if (text.startsWith('Acceso remoto:')) {
                accesoRemoto = text.includes('Disponible');
            }
        });
        
        // Extraer estado actual
        const statusBadge = equipmentCard.querySelector('.status-badge');
        const estadoClasses = statusBadge?.className || '';
        let estadoBloqueo = '';
        let estadoLabel = statusBadge?.textContent?.trim() || '';
        
        if (estadoClasses.includes('status-activo')) estadoBloqueo = 'activo';
        else if (estadoClasses.includes('status-suspendido')) estadoBloqueo = 'suspendido';
        else if (estadoClasses.includes('status-bloqueado')) estadoBloqueo = 'bloqueado';
        else if (estadoClasses.includes('status-no_accesible')) estadoBloqueo = 'no_accesible';
        else if (estadoClasses.includes('status-pendiente_bloqueo')) estadoBloqueo = 'pendiente_bloqueo';
        else if (estadoClasses.includes('status-pendiente_desbloqueo')) estadoBloqueo = 'pendiente_desbloqueo';
        
        // Construir objeto equipment
        equipment = {
            id: equipmentId,
            serie: serie,
            cliente: cliente?.trim() || '',
            modelo: modelo?.trim() || '',
            marca: marca,
            direccion: direccion,
            ip_equipo: ip === 'No configurada' ? '' : ip,
            acceso_remoto: accesoRemoto,
            estado_bloqueo: estadoBloqueo,
            estado_label: estadoLabel
        };
    } else {
        // Datos básicos si no se encuentra la tarjeta
        equipment = {
            id: equipmentId,
            serie: serie,
            cliente: '',
            modelo: '',
            marca: '',
            direccion: '',
            ip_equipo: '',
            acceso_remoto: false,
            estado_bloqueo: '',
            estado_label: ''
        };
    }
    
    // Configurar elementos del modal
    const modalTitle = document.getElementById('modalTitle');
    const motivoInput = document.getElementById('motivoInput');
    const confirmBtn = document.getElementById('confirmActionBtn');
    const equipmentDetails = document.getElementById('equipmentDetails');
    
    // Mostrar detalles del equipo
    updateElement('detailCliente', equipment.cliente || 'No especificado');
    updateElement('detailModelo', equipment.modelo || 'No especificado');
    updateElement('detailIP', equipment.ip_equipo || 'No configurada');
    
    const estadoElement = document.getElementById('detailEstado');
    if (estadoElement && equipment.estado_bloqueo) {
        estadoElement.innerHTML = '<span class="status-badge status-' + equipment.estado_bloqueo + '">' + 
                                 escapeHtml(equipment.estado_label || equipment.estado_bloqueo) + '</span>';
    } else if (estadoElement) {
        estadoElement.textContent = 'No determinado';
    }
    
    // Mostrar sección de detalles
    if (equipmentDetails) {
        equipmentDetails.style.display = 'block';
    }
    
    // Configurar modal según la acción
    switch(action) {
        case 'suspend':
            if (modalTitle) modalTitle.textContent = 'Suspender Servicio - Serie: ' + serie;
            if (motivoInput) {
                motivoInput.setAttribute('placeholder', 'Motivo de la suspensión (ej: Mora de pagos, incumplimiento contractual...)');
                motivoInput.focus();
            }
            if (confirmBtn) {
                confirmBtn.className = 'btn btn-warning';
                confirmBtn.innerHTML = 
                    '<span id="btnLoading" class="d-none">' +
                        '<span class="spinner-border spinner-border-sm me-2" role="status"></span>' +
                        'Procesando...' +
                    '</span>' +
                    '<span id="btnText">' +
                        '<i class="fas fa-pause me-2"></i>Suspender Servicio' +
                    '</span>';
            }
            break;
            
        case 'block':
            if (modalTitle) modalTitle.textContent = 'Bloquear Equipo - Serie: ' + serie;
            if (motivoInput) {
                motivoInput.setAttribute('placeholder', 'Motivo del bloqueo remoto (ej: Mantenimiento, violación de términos...)');
                motivoInput.focus();
            }
            if (confirmBtn) {
                confirmBtn.className = 'btn btn-danger';
                confirmBtn.innerHTML = 
                    '<span id="btnLoading" class="d-none">' +
                        '<span class="spinner-border spinner-border-sm me-2" role="status"></span>' +
                        'Procesando...' +
                    '</span>' +
                    '<span id="btnText">' +
                        '<i class="fas fa-lock me-2"></i>Bloquear Equipo' +
                    '</span>';
            }
            break;
            
        case 'unblock':
            if (modalTitle) modalTitle.textContent = 'Desbloquear Equipo - Serie: ' + serie;
            if (motivoInput) {
                motivoInput.setAttribute('placeholder', 'Observaciones del desbloqueo (ej: Pago realizado, problema resuelto...)');
                motivoInput.focus();
            }
            if (confirmBtn) {
                confirmBtn.className = 'btn btn-success';
                confirmBtn.innerHTML = 
                    '<span id="btnLoading" class="d-none">' +
                        '<span class="spinner-border spinner-border-sm me-2" role="status"></span>' +
                        'Procesando...' +
                    '</span>' +
                    '<span id="btnText">' +
                        '<i class="fas fa-unlock me-2"></i>Desbloquear Equipo' +
                    '</span>';
            }
            break;
            
        default:
            console.error('Acción no reconocida:', action);
            return;
    }
    
    // Limpiar campos del modal
    if (motivoInput) {
        motivoInput.value = '';
    }
    
    // Limpiar alertas previas del modal
    const modalAlert = document.getElementById('modalAlert');
    if (modalAlert) {
        modalAlert.innerHTML = '';
    }
    
    // Habilitar botón de confirmación
    if (confirmBtn) {
        confirmBtn.disabled = false;
    }
    
    // Mostrar modal
    if (actionModal) {
        actionModal.show();
    } else {
        console.error('Modal no inicializado');
        // Intentar inicializar el modal si no existe
        const modalElement = document.getElementById('actionModal');
        if (modalElement && typeof bootstrap !== 'undefined') {
            actionModal = new bootstrap.Modal(modalElement, {
                backdrop: 'static',
                keyboard: false
            });
            actionModal.show();
        } else {
            showAlert('danger', 'Error: No se pudo abrir el modal de acciones');
        }
    }
    
    console.log('Modal configurado para:', action, 'con equipo:', equipment);
},
        executeAction: function() {
            const motivoInput = document.getElementById('motivoInput');
            const motivo = motivoInput ? motivoInput.value : '';
            const btnLoading = document.getElementById('btnLoading');
            const btnText = document.getElementById('btnText');
            const confirmBtn = document.getElementById('confirmActionBtn');
            
            // Mostrar loading
            if (btnLoading) btnLoading.classList.remove('d-none');
            if (btnText) btnText.classList.add('d-none');
            if (confirmBtn) confirmBtn.disabled = true;

            const endpoints = {
                'suspend': '/equipment/blocking/suspend',
                'block': '/equipment/blocking/block',
                'unblock': '/equipment/blocking/unblock'
            };

            return this.makeJsonRpcCall(endpoints[currentAction], {
                equipment_id: currentEquipmentId,
                motivo: motivo
            })
            .then(result => {
                if (result.status === 'success') {
                    this.showModalAlert('success', result.message);
                    
                    // Cerrar modal después de 2 segundos y actualizar
                    setTimeout(() => {
                        if (actionModal) {
                            actionModal.hide();
                        }
                        this.refreshDashboard();
                        this.searchEquipments();
                    }, 2000);
                } else {
                    this.showModalAlert('danger', result.message);
                }
            })
            .catch(error => {
                this.showModalAlert('danger', 'Error de conexión');
                console.error('Error:', error);
            })
            .finally(() => {
                // Ocultar loading
                if (btnLoading) btnLoading.classList.add('d-none');
                if (btnText) btnText.classList.remove('d-none');
                if (confirmBtn) confirmBtn.disabled = false;
            });
        },

        showModalAlert: function(type, message) {
            const alertContainer = document.getElementById('modalAlert');
            if (!alertContainer) return;
            
            const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
            const icon = type === 'success' ? 'check-circle' : 'exclamation-triangle';
            
            alertContainer.innerHTML = 
                '<div class="alert ' + alertClass + ' d-flex align-items-center" role="alert">' +
                    '<i class="fas fa-' + icon + ' me-2"></i>' +
                    '<div>' + this.escapeHtml(message) + '</div>' +
                '</div>';
        },

        showAlert: function(type, message) {
            // Crear contenedor de alertas si no existe
            let alertContainer = document.getElementById('general-alerts');
            if (!alertContainer) {
                alertContainer = document.createElement('div');
                alertContainer.id = 'general-alerts';
                alertContainer.className = 'position-fixed top-0 end-0 p-3';
                alertContainer.style.zIndex = '1055';
                document.body.appendChild(alertContainer);
            }
            
            const alertId = 'alert-' + Date.now();
            const alertClass = type === 'success' ? 'alert-success' : 
                           type === 'warning' ? 'alert-warning' : 'alert-danger';
            const icon = type === 'success' ? 'check-circle' : 
                      type === 'warning' ? 'exclamation-triangle' : 'times-circle';
            
            const alertHtml = 
                '<div id="' + alertId + '" class="alert ' + alertClass + ' alert-dismissible fade show" role="alert">' +
                    '<i class="fas fa-' + icon + ' me-2"></i>' +
                    this.escapeHtml(message) +
                    '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' +
                '</div>';
            
            alertContainer.insertAdjacentHTML('beforeend', alertHtml);
            
            // Auto-dismiss después de 5 segundos
            setTimeout(() => {
                const alert = document.getElementById(alertId);
                if (alert && typeof bootstrap !== 'undefined') {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                }
            }, 5000);
        },

        escapeHtml: function(text) {
            if (!text) return '';
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return String(text).replace(/[&<>"']/g, m => map[m]);
        }
    };

    // Exponer las funciones necesarias globalmente
    window.EquipmentBlocking = {
        searchEquipments: () => EquipmentBlockingModule.searchEquipments(),
        loadPendingEquipments: () => EquipmentBlockingModule.loadPendingEquipments(),
        refreshDashboard: () => EquipmentBlockingModule.refreshDashboard(),
        openActionModal: (action, equipmentId, serie, equipmentData) => 
            EquipmentBlockingModule.openActionModal(action, equipmentId, serie, equipmentData)
    };

    // Funciones globales para compatibilidad con onclick (fallback)
    window.searchEquipments = () => EquipmentBlockingModule.searchEquipments();
    window.loadPendingEquipments = () => EquipmentBlockingModule.loadPendingEquipments();
    window.refreshDashboard = () => EquipmentBlockingModule.refreshDashboard();
    window.openActionModal = (action, equipmentId, serie, equipmentData) => 
        EquipmentBlockingModule.openActionModal(action, equipmentId, serie, equipmentData);

    // Inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => EquipmentBlockingModule.init());
    } else {
        EquipmentBlockingModule.init();
    }

})();
(function() {
    'use strict';

    // Variables globales
    var currentAction = null;
    var currentEquipmentId = null;
    var actionModal = null;

    // Inicializar cuando el DOM esté listo
    document.addEventListener('DOMContentLoaded', function() {
        initializeDashboard();
        // Cargar equipos automáticamente al inicio
        loadAllEquipments();
    });

    function initializeDashboard() {
        // Inicializar modal de Bootstrap
        var modalEl = document.getElementById('actionModal');
        if (modalEl && typeof bootstrap !== 'undefined') {
            actionModal = new bootstrap.Modal(modalEl);
        }
        
        setupEventListeners();
    }

    function setupEventListeners() {
        // Enter en búsqueda
        var searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('keypress', function(e) {
                if (e.which === 13) {
                    searchEquipments();
                }
            });
        }

        // Botón de acción del modal
        var confirmBtn = document.getElementById('confirmActionBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', executeAction);
        }
        
        // Shortcuts de teclado
        document.addEventListener('keydown', function(e) {
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
    }

    function getCsrfToken() {
        var metaToken = document.querySelector('meta[name="csrf-token"]');
        return metaToken ? metaToken.getAttribute('content') : '';
    }

    function makeJsonRpcCall(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: params
            })
        }).then(function(response) {
            return response.json();
        }).then(function(data) {
            return data.result;
        });
    }

    function refreshDashboard() {
        return makeJsonRpcCall('/equipment/blocking/dashboard_data', {})
            .then(function(result) {
                if (result.status === 'success') {
                    var data = result.data;
                    updateElement('equipos-activos', data.equipos_activos);
                    updateElement('equipos-suspendidos', data.equipos_suspendidos);
                    updateElement('equipos-bloqueados', data.equipos_bloqueados);
                    updateElement('equipos-no-accesibles', data.equipos_no_accesibles);
                    updateElement('pendientes-bloqueo', data.pendientes_bloqueo);
                    updateElement('pendientes-desbloqueo', data.pendientes_desbloqueo);
                    
                    showAlert('success', 'Dashboard actualizado correctamente');
                }
            })
            .catch(function(error) {
                console.error('Error al actualizar dashboard:', error);
                showAlert('danger', 'Error al actualizar el dashboard');
            });
    }

    function updateElement(id, value) {
        var element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    function searchEquipments() {
        var searchInput = document.getElementById('search-input');
        var searchTerm = searchInput ? searchInput.value : '';
        var resultsContainer = document.getElementById('equipment-results');
        
        if (resultsContainer) {
            resultsContainer.innerHTML = 
                '<div class="text-center py-5">' +
                    '<div class="spinner-border text-primary mb-3" role="status"></div>' +
                    '<p class="text-muted">Buscando equipos...</p>' +
                '</div>';
        }

        return makeJsonRpcCall('/equipment/blocking/search', {
            search_term: searchTerm
        }).then(function(result) {
            if (result.status === 'success') {
                displayEquipments(result.equipos);
            } else {
                showAlert('danger', 'Error al buscar equipos: ' + result.message);
            }
        }).catch(function(error) {
            showAlert('danger', 'Error de conexión');
            console.error('Error:', error);
        });
    }

    function loadPendingEquipments() {
        var searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.value = '';
        }
        
        var resultsContainer = document.getElementById('equipment-results');
        if (resultsContainer) {
            resultsContainer.innerHTML = 
                '<div class="text-center py-5">' +
                    '<div class="spinner-border text-warning mb-3" role="status"></div>' +
                    '<p class="text-muted">Cargando equipos pendientes...</p>' +
                '</div>';
        }

        return makeJsonRpcCall('/equipment/blocking/search', {
            search_term: '',
            only_pending: true
        }).then(function(result) {
            if (result.status === 'success') {
                var pendingEquipments = result.equipos.filter(function(eq) {
                    return ['suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'].includes(eq.estado_bloqueo);
                });
                displayEquipments(pendingEquipments);
            } else {
                showAlert('danger', 'Error al cargar equipos: ' + result.message);
            }
        }).catch(function(error) {
            showAlert('danger', 'Error de conexión');
            console.error('Error:', error);
        });
    }

    function loadAllEquipments() {
        var resultsContainer = document.getElementById('equipment-results');
        if (resultsContainer) {
            resultsContainer.innerHTML = 
                '<div class="text-center py-5">' +
                    '<div class="spinner-border text-primary mb-3" role="status"></div>' +
                    '<p class="text-muted">Cargando todos los equipos...</p>' +
                '</div>';
        }

        return makeJsonRpcCall('/equipment/blocking/search', {
            search_term: ''
        }).then(function(result) {
            if (result.status === 'success') {
                displayEquipments(result.equipos);
            } else {
                showAlert('danger', 'Error al cargar equipos: ' + result.message);
            }
        }).catch(function(error) {
            showAlert('danger', 'Error de conexión');
            console.error('Error:', error);
        });
    }

    function displayEquipments(equipos) {
        var resultsContainer = document.getElementById('equipment-results');
        if (!resultsContainer) return;
        
        if (equipos.length === 0) {
            resultsContainer.innerHTML = 
                '<div class="text-center py-5">' +
                    '<i class="fas fa-inbox fa-3x text-muted mb-3"></i>' +
                    '<p class="text-muted">No se encontraron equipos con los criterios especificados.</p>' +
                '</div>';
            return;
        }

        var equipmentCards = equipos.map(function(equipo) {
            var motivoSection = equipo.motivo_bloqueo ? 
                '<div class="alert alert-info py-2 mb-3">' +
                    '<strong>Motivo:</strong> ' + escapeHtml(equipo.motivo_bloqueo) +
                '</div>' : '';
            
            var fechaSection = equipo.fecha_bloqueo ? 
                '<div class="text-muted small mb-3">' +
                    '<i class="fas fa-clock"></i> ' + escapeHtml(equipo.fecha_bloqueo) +
                '</div>' : '';

            var buttons = [];
            if (equipo.puede_suspender) {
                buttons.push(
                    '<button class="btn btn-warning btn-sm" onclick="openActionModal(\'suspend\', ' + 
                    equipo.id + ', \'' + escapeHtml(equipo.serie) + '\', ' + 
                    JSON.stringify(equipo).replace(/"/g, '&quot;') + ')">' +
                        '<i class="fas fa-pause me-1"></i> Suspender' +
                    '</button>'
                );
            }
            if (equipo.puede_bloquear) {
                buttons.push(
                    '<button class="btn btn-danger btn-sm" onclick="openActionModal(\'block\', ' + 
                    equipo.id + ', \'' + escapeHtml(equipo.serie) + '\', ' + 
                    JSON.stringify(equipo).replace(/"/g, '&quot;') + ')">' +
                        '<i class="fas fa-lock me-1"></i> Bloquear' +
                    '</button>'
                );
            }
            if (equipo.puede_desbloquear) {
                buttons.push(
                    '<button class="btn btn-success btn-sm" onclick="openActionModal(\'unblock\', ' + 
                    equipo.id + ', \'' + escapeHtml(equipo.serie) + '\', ' + 
                    JSON.stringify(equipo).replace(/"/g, '&quot;') + ')">' +
                        '<i class="fas fa-unlock me-1"></i> Desbloquear' +
                    '</button>'
                );
            }

            return (
                '<div class="equipment-card">' +
                    '<div class="d-flex justify-content-between align-items-start mb-3">' +
                        '<div>' +
                            '<h5 class="mb-1 fw-bold">Serie: ' + escapeHtml(equipo.serie) + '</h5>' +
                            '<p class="text-muted mb-0">' + escapeHtml(equipo.cliente) + ' - ' + escapeHtml(equipo.modelo) + '</p>' +
                        '</div>' +
                        '<span class="status-badge status-' + equipo.estado_bloqueo + '">' +
                            escapeHtml(equipo.estado_label) +
                        '</span>' +
                    '</div>' +
                    
                    '<div class="detail-grid">' +
                        '<div class="detail-item">' +
                            '<i class="fas fa-industry"></i>' +
                            '<span>Marca: ' + escapeHtml(equipo.marca) + '</span>' +
                        '</div>' +
                        '<div class="detail-item">' +
                            '<i class="fas fa-map-marker-alt"></i>' +
                            '<span>Dirección: ' + escapeHtml(equipo.direccion) + '</span>' +
                        '</div>' +
                        '<div class="detail-item">' +
                            '<i class="fas fa-network-wired"></i>' +
                            '<span>IP: ' + escapeHtml(equipo.ip_equipo || 'No configurada') + '</span>' +
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
    }

    function openActionModal(action, equipmentId, serie, equipmentData) {
        currentAction = action;
        currentEquipmentId = equipmentId;
        
        var equipment = typeof equipmentData === 'string' ? JSON.parse(equipmentData) : equipmentData;
        
        var modalTitle = document.getElementById('modalTitle');
        var motivoInput = document.getElementById('motivoInput');
        var confirmBtn = document.getElementById('confirmActionBtn');
        var equipmentDetails = document.getElementById('equipmentDetails');
        
        // Mostrar detalles del equipo
        updateElement('detailCliente', equipment.cliente);
        updateElement('detailModelo', equipment.modelo);
        updateElement('detailIP', equipment.ip_equipo || 'No configurada');
        
        var estadoElement = document.getElementById('detailEstado');
        if (estadoElement) {
            estadoElement.innerHTML = '<span class="status-badge status-' + equipment.estado_bloqueo + '">' + equipment.estado_label + '</span>';
        }
        
        if (equipmentDetails) {
            equipmentDetails.style.display = 'block';
        }
        
        // Configurar según la acción
        switch(action) {
            case 'suspend':
                if (modalTitle) modalTitle.textContent = 'Suspender Servicio - Serie: ' + serie;
                if (motivoInput) motivoInput.setAttribute('placeholder', 'Motivo de la suspensión (ej: Mora de pagos, incumplimiento contractual...)');
                if (confirmBtn) confirmBtn.className = 'btn btn-warning';
                break;
            case 'block':
                if (modalTitle) modalTitle.textContent = 'Bloquear Equipo - Serie: ' + serie;
                if (motivoInput) motivoInput.setAttribute('placeholder', 'Motivo del bloqueo remoto...');
                if (confirmBtn) confirmBtn.className = 'btn btn-danger';
                break;
            case 'unblock':
                if (modalTitle) modalTitle.textContent = 'Desbloquear Equipo - Serie: ' + serie;
                if (motivoInput) motivoInput.setAttribute('placeholder', 'Observaciones del desbloqueo...');
                if (confirmBtn) confirmBtn.className = 'btn btn-success';
                break;
        }
        
        // Limpiar modal y mostrar
        if (motivoInput) motivoInput.value = '';
        
        var modalAlert = document.getElementById('modalAlert');
        if (modalAlert) modalAlert.innerHTML = '';
        
        if (actionModal) {
            actionModal.show();
        }
    }

    function executeAction() {
        var motivoInput = document.getElementById('motivoInput');
        var motivo = motivoInput ? motivoInput.value : '';
        var btnLoading = document.getElementById('btnLoading');
        var btnText = document.getElementById('btnText');
        var confirmBtn = document.getElementById('confirmActionBtn');
        
        // Mostrar loading
        if (btnLoading) btnLoading.classList.remove('d-none');
        if (btnText) btnText.classList.add('d-none');
        if (confirmBtn) confirmBtn.disabled = true;

        var endpoints = {
            'suspend': '/equipment/blocking/suspend',
            'block': '/equipment/blocking/block',
            'unblock': '/equipment/blocking/unblock'
        };

        return makeJsonRpcCall(endpoints[currentAction], {
            equipment_id: currentEquipmentId,
            motivo: motivo
        }).then(function(result) {
            if (result.status === 'success') {
                showModalAlert('success', result.message);
                
                // Cerrar modal después de 2 segundos y actualizar
                setTimeout(function() {
                    if (actionModal) {
                        actionModal.hide();
                    }
                    refreshDashboard();
                    searchEquipments();
                }, 2000);
            } else {
                showModalAlert('danger', result.message);
            }
        }).catch(function(error) {
            showModalAlert('danger', 'Error de conexión');
            console.error('Error:', error);
        }).finally(function() {
            // Ocultar loading
            if (btnLoading) btnLoading.classList.add('d-none');
            if (btnText) btnText.classList.remove('d-none');
            if (confirmBtn) confirmBtn.disabled = false;
        });
    }

    function showModalAlert(type, message) {
        var alertContainer = document.getElementById('modalAlert');
        if (!alertContainer) return;
        
        var alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
        var icon = type === 'success' ? 'check-circle' : 'exclamation-triangle';
        
        alertContainer.innerHTML = 
            '<div class="alert ' + alertClass + ' d-flex align-items-center" role="alert">' +
                '<i class="fas fa-' + icon + ' me-2"></i>' +
                '<div>' + escapeHtml(message) + '</div>' +
            '</div>';
    }

    function showAlert(type, message) {
        // Crear contenedor de alertas si no existe
        var alertContainer = document.getElementById('general-alerts');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.id = 'general-alerts';
            alertContainer.className = 'position-fixed top-0 end-0 p-3';
            alertContainer.style.zIndex = '1055';
            document.body.appendChild(alertContainer);
        }
        
        var alertId = 'alert-' + Date.now();
        var alertClass = type === 'success' ? 'alert-success' : 
                       type === 'warning' ? 'alert-warning' : 'alert-danger';
        var icon = type === 'success' ? 'check-circle' : 
                  type === 'warning' ? 'exclamation-triangle' : 'times-circle';
        
        var alertHtml = 
            '<div id="' + alertId + '" class="alert ' + alertClass + ' alert-dismissible fade show" role="alert">' +
                '<i class="fas fa-' + icon + ' me-2"></i>' +
                escapeHtml(message) +
                '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>' +
            '</div>';
        
        alertContainer.insertAdjacentHTML('beforeend', alertHtml);
        
        // Auto-dismiss después de 5 segundos
        setTimeout(function() {
            var alert = document.getElementById(alertId);
            if (alert && typeof bootstrap !== 'undefined') {
                var bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, 5000);
    }

    function escapeHtml(text) {
        if (!text) return '';
        var map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return String(text).replace(/[&<>"']/g, function(m) { return map[m]; });
    }

    // Funciones globales para compatibilidad con onclick
    window.searchEquipments = searchEquipments;
    window.loadPendingEquipments = loadPendingEquipments;
    window.loadAllEquipments = loadAllEquipments;
    window.refreshDashboard = refreshDashboard;
    window.openActionModal = openActionModal;

})();
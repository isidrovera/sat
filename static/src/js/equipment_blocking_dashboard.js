/** @odoo-module **/

import { AbstractAction } from "@web/webclient/actions/abstract_action";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState, xml } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class EquipmentBlockingDashboard extends AbstractAction {
    static template = xml`
        <div class="o_dashboard_view">
            <!-- Header del Dashboard -->
            <div class="o_dashboard_header mb-4">
                <div class="d-flex align-items-center">
                    <i class="fa fa-shield-alt fa-2x text-primary me-3"></i>
                    <div>
                        <h2 class="mb-1">Sistema de Bloqueo de Equipos</h2>
                        <p class="text-muted mb-0">Gestión centralizada de estados de servicio y bloqueos remotos</p>
                    </div>
                </div>
            </div>

            <!-- Cards de estadísticas -->
            <div class="o_dashboard_stats row g-3 mb-4">
                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('activo')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Equipos Activos</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_activos"/>
                                    <small class="text-success">
                                        <i class="fa fa-arrow-up"></i> Funcionando normal
                                    </small>
                                </div>
                                <div class="bg-success rounded-circle p-3">
                                    <i class="fa fa-check-circle text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-success" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('suspendido')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Suspendidos</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_suspendidos"/>
                                    <small class="text-warning">
                                        <i class="fa fa-exclamation-triangle"></i> Por mora
                                    </small>
                                </div>
                                <div class="bg-warning rounded-circle p-3">
                                    <i class="fa fa-pause-circle text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-warning" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('bloqueado')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Bloqueados</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_bloqueados"/>
                                    <small class="text-danger">
                                        <i class="fa fa-ban"></i> Acceso denegado
                                    </small>
                                </div>
                                <div class="bg-danger rounded-circle p-3">
                                    <i class="fa fa-lock text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-danger" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('no_accesible')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">No Accesibles</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.equipos_no_accesibles"/>
                                    <small class="text-muted">
                                        <i class="fa fa-tools"></i> Requiere manual
                                    </small>
                                </div>
                                <div class="bg-secondary rounded-circle p-3">
                                    <i class="fa fa-wifi-slash text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-secondary" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('pendiente_bloqueo')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Pend. Bloqueo</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.pendientes_bloqueo"/>
                                    <small class="text-info">
                                        <i class="fa fa-hourglass-half"></i> En proceso
                                    </small>
                                </div>
                                <div class="bg-info rounded-circle p-3">
                                    <i class="fa fa-clock text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-info" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>

                <div class="col-xl-2 col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm h-100 dashboard-card" t-on-click="() => this.filterByStatus('pendiente_desbloqueo')">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="text-muted text-uppercase fw-bold small mb-2">Pend. Desbloqueo</h6>
                                    <h2 class="h1 fw-bold mb-0" t-esc="state.dashboardData.pendientes_desbloqueo"/>
                                    <small class="text-primary">
                                        <i class="fa fa-sync-alt"></i> Restaurando
                                    </small>
                                </div>
                                <div class="bg-primary rounded-circle p-3">
                                    <i class="fa fa-unlock-alt text-white fa-lg"></i>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer bg-primary" style="height: 4px; padding: 0;"></div>
                    </div>
                </div>
            </div>

            <!-- Panel de búsqueda -->
            <div class="o_dashboard_search card mb-4">
                <div class="card-body">
                    <div class="row g-3 align-items-end">
                        <div class="col-lg-6">
                            <label for="search-input" class="form-label fw-bold">
                                <i class="fa fa-search me-2"></i>Buscar Equipos Alquilados
                            </label>
                            <input type="text" class="form-control" 
                                   placeholder="Buscar por serie, cliente, modelo o marca..."
                                   t-model="state.searchTerm"
                                   t-on-keydown="onSearchKeydown" />
                        </div>
                        <div class="col-lg-6">
                            <div class="d-flex gap-2 flex-wrap">
                                <button type="button" class="btn btn-primary" t-on-click="searchEquipments">
                                    <i class="fa fa-search me-2"></i>Buscar
                                </button>
                                <button type="button" class="btn btn-warning" t-on-click="loadPendingEquipments">
                                    <i class="fa fa-exclamation-circle me-2"></i>Ver Pendientes
                                </button>
                                <button type="button" class="btn btn-success" t-on-click="loadAllEquipments">
                                    <i class="fa fa-list me-2"></i>Ver Todos
                                </button>
                                <button type="button" class="btn btn-info" t-on-click="refreshDashboard" t-att-disabled="state.loading">
                                    <i class="fa fa-sync-alt me-2"></i>Actualizar
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Resultados -->
            <div class="o_dashboard_results card">
                <div class="card-header bg-light">
                    <div class="d-flex justify-content-between align-items-center">
                        <h4 class="mb-0">
                            <i class="fa fa-list me-2"></i>Equipos Alquilados
                        </h4>
                        <span class="badge bg-primary" t-esc="state.equipments.length"/>
                    </div>
                </div>
                <div class="card-body">
                    <div t-if="state.loading" class="text-center py-5">
                        <div class="spinner-border text-primary mb-3"></div>
                        <p class="text-muted">Cargando equipos...</p>
                    </div>
                    <div t-elif="state.equipments.length === 0" class="text-center py-5">
                        <i class="fa fa-inbox fa-3x text-muted mb-3"></i>
                        <p class="text-muted">No se encontraron equipos.</p>
                        <button type="button" class="btn btn-primary" t-on-click="loadAllEquipments">
                            <i class="fa fa-list me-2"></i>Ver Todos los Equipos
                        </button>
                    </div>
                    <div t-else="">
                        <div t-foreach="state.equipments" t-as="equipment" t-key="equipment.id" class="equipment-card">
                            <div class="d-flex justify-content-between align-items-start mb-3">
                                <div>
                                    <h5 class="mb-1 fw-bold">Serie: <t t-esc="equipment.serie"/></h5>
                                    <p class="text-muted mb-0"><t t-esc="equipment.cliente"/> - <t t-esc="equipment.modelo"/></p>
                                </div>
                                <span t-attf-class="status-badge status-#{equipment.estado_bloqueo}">
                                    <t t-esc="equipment.estado_label"/>
                                </span>
                            </div>
                            
                            <div class="detail-grid">
                                <div class="detail-item">
                                    <i class="fa fa-industry"></i>
                                    <span>Marca: <t t-esc="equipment.marca"/></span>
                                </div>
                                <div class="detail-item">
                                    <i class="fa fa-map-marker-alt"></i>
                                    <span>Dirección: <t t-esc="equipment.direccion"/></span>
                                </div>
                                <div class="detail-item">
                                    <i class="fa fa-network-wired"></i>
                                    <span>IP: <t t-esc="equipment.ip_equipo or 'No configurada'"/></span>
                                </div>
                                <div class="detail-item">
                                    <i class="fa fa-wifi"></i>
                                    <span>Acceso remoto: <t t-if="equipment.acceso_remoto">Disponible</t><t t-else="">No disponible</t></span>
                                </div>
                            </div>
                            
                            <div t-if="equipment.motivo_bloqueo" class="alert alert-info py-2 mb-3">
                                <strong>Motivo:</strong> <t t-esc="equipment.motivo_bloqueo"/>
                            </div>
                            
                            <div t-if="equipment.fecha_bloqueo" class="text-muted small mb-3">
                                <i class="fa fa-clock"></i> <t t-esc="equipment.fecha_bloqueo"/>
                            </div>
                            
                            <div class="d-flex gap-2 justify-content-end flex-wrap">
                                <button t-if="equipment.puede_suspender" 
                                        class="btn btn-warning btn-sm" 
                                        t-on-click="() => this.openActionModal('suspend', equipment.id, equipment.serie)">
                                    <i class="fa fa-pause me-1"></i> Suspender
                                </button>
                                <button t-if="equipment.puede_bloquear" 
                                        class="btn btn-danger btn-sm" 
                                        t-on-click="() => this.openActionModal('block', equipment.id, equipment.serie)">
                                    <i class="fa fa-lock me-1"></i> Bloquear
                                </button>
                                <button t-if="equipment.puede_desbloquear" 
                                        class="btn btn-success btn-sm" 
                                        t-on-click="() => this.openActionModal('unblock', equipment.id, equipment.serie)">
                                    <i class="fa fa-unlock me-1"></i> Desbloquear
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    setup() {
        super.setup();
        
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        
        this.state = useState({
            dashboardData: {
                equipos_activos: 0,
                equipos_suspendidos: 0,
                equipos_bloqueados: 0,
                equipos_no_accesibles: 0,
                pendientes_bloqueo: 0,
                pendientes_desbloqueo: 0
            },
            equipments: [],
            loading: false,
            currentFilter: 'todos',
            searchTerm: ''
        });

        onWillStart(async () => {
            await this.loadDashboardData();
            await this.loadAllEquipments();
        });
    }

    // Event handlers
    onSearchKeydown(ev) {
        if (ev.key === 'Enter') {
            this.searchEquipments();
        }
    }
    // Métodos de carga de datos
    async loadDashboardData() {
        try {
            const result = await this.orm.call("alquiler", "get_dashboard_data", []);
            this.state.dashboardData = result;
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.notification.add(_t("Error al cargar datos del dashboard"), { type: "danger" });
        }
    }

    async loadAllEquipments() {
        this.state.loading = true;
        this.state.currentFilter = 'todos';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [["estado_alquiler_id", "=", "alquilada"]],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
        } catch (error) {
            console.error("Error loading equipments:", error);
            this.notification.add(_t("Error al cargar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async searchEquipments() {
        const searchTerm = this.state.searchTerm.trim();
        this.state.loading = true;
        this.state.currentFilter = 'busqueda';
        
        try {
            let domain = [["estado_alquiler_id", "=", "alquilada"]];
            
            if (searchTerm) {
                domain.push([
                    "|", "|", "|",
                    ["serie", "ilike", searchTerm],
                    ["cliente_id", "ilike", searchTerm],
                    ["name", "ilike", searchTerm],
                    ["marca", "ilike", searchTerm]
                ]);
            }
            
            const equipments = await this.orm.searchRead(
                "alquiler",
                domain,
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
            const message = searchTerm 
                ? _t(`Encontrados ${equipments.length} equipos para "${searchTerm}"`)
                : _t(`Mostrando ${equipments.length} equipos alquilados`);
            this.notification.add(message, { type: "success" });
            
        } catch (error) {
            console.error("Error searching equipments:", error);
            this.notification.add(_t("Error al buscar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async filterByStatus(estado) {
        this.state.loading = true;
        this.state.currentFilter = estado;
        this.state.searchTerm = '';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [
                    ["estado_alquiler_id", "=", "alquilada"],
                    ["estado_bloqueo", "=", estado]
                ],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
            const estadoLabels = {
                'activo': 'equipos activos',
                'suspendido': 'equipos suspendidos',
                'bloqueado': 'equipos bloqueados',
                'no_accesible': 'equipos no accesibles',
                'pendiente_bloqueo': 'equipos pendientes de bloqueo',
                'pendiente_desbloqueo': 'equipos pendientes de desbloqueo'
            };
            
            const estadoLabel = estadoLabels[estado] || 'equipos';
            this.notification.add(_t(`Mostrando ${equipments.length} ${estadoLabel}`), { type: "success" });
            
        } catch (error) {
            console.error("Error filtering equipments:", error);
            this.notification.add(_t("Error al filtrar equipos"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async loadPendingEquipments() {
        this.state.loading = true;
        this.state.currentFilter = 'pendientes';
        this.state.searchTerm = '';
        
        try {
            const equipments = await this.orm.searchRead(
                "alquiler",
                [
                    ["estado_alquiler_id", "=", "alquilada"],
                    ["estado_bloqueo", "in", ["suspendido", "bloqueado", "no_accesible", "pendiente_bloqueo", "pendiente_desbloqueo"]]
                ],
                [
                    "id", "serie", "cliente_id", "name", "marca", "direccion",
                    "ip_equipo", "estado_bloqueo", "acceso_remoto_disponible",
                    "motivo_bloqueo", "fecha_bloqueo"
                ]
            );
            
            this.state.equipments = this.processEquipments(equipments);
            
            this.notification.add(_t(`${equipments.length} equipos requieren atención`), { type: "warning" });
            
        } catch (error) {
            console.error("Error loading pending equipments:", error);
            this.notification.add(_t("Error al cargar equipos pendientes"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async refreshDashboard() {
        this.state.loading = true;
        
        try {
            await this.loadDashboardData();
            
            // Recargar vista actual según el filtro
            switch(this.state.currentFilter) {
                case 'todos':
                    await this.loadAllEquipments();
                    break;
                case 'pendientes':
                    await this.loadPendingEquipments();
                    break;
                case 'busqueda':
                    await this.searchEquipments();
                    break;
                default:
                    if (['activo', 'suspendido', 'bloqueado', 'no_accesible', 'pendiente_bloqueo', 'pendiente_desbloqueo'].includes(this.state.currentFilter)) {
                        await this.filterByStatus(this.state.currentFilter);
                    } else {
                        await this.loadAllEquipments();
                    }
            }
            
            this.notification.add(_t('Dashboard actualizado correctamente'), { type: "success" });
            
        } catch (error) {
            console.error("Error refreshing dashboard:", error);
            this.notification.add(_t('Error al actualizar el dashboard'), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    // Métodos de procesamiento de datos
    processEquipments(equipments) {
        return equipments.map(equipment => {
            const estadoLabels = {
                'activo': 'Activo',
                'suspendido': 'Suspendido',
                'bloqueado': 'Bloqueado',
                'no_accesible': 'No Accesible',
                'pendiente_bloqueo': 'Pend. Bloqueo',
                'pendiente_desbloqueo': 'Pend. Desbloqueo'
            };
            
            return {
                ...equipment,
                cliente: equipment.cliente_id ? equipment.cliente_id[1] : '',
                modelo: equipment.name ? equipment.name[1] : '',
                estado_label: estadoLabels[equipment.estado_bloqueo] || equipment.estado_bloqueo,
                acceso_remoto: equipment.acceso_remoto_disponible || false,
                puede_suspender: equipment.estado_bloqueo === 'activo',
                puede_bloquear: ['activo', 'suspendido'].includes(equipment.estado_bloqueo) && equipment.acceso_remoto_disponible,
                puede_desbloquear: ['bloqueado', 'suspendido'].includes(equipment.estado_bloqueo)
            };
        });
    }
    // Métodos de acciones
    async openActionModal(action, equipmentId, serie) {
        // Encontrar el equipo en el estado actual
        const equipment = this.state.equipments.find(eq => eq.id === equipmentId);
        
        if (!equipment) {
            this.notification.add(_t("Error: No se encontró el equipo"), { type: "danger" });
            return;
        }

        const actionLabels = {
            'suspend': 'Suspender Servicio',
            'block': 'Bloquear Equipo',
            'unblock': 'Desbloquear Equipo'
        };

        const actionMessages = {
            'suspend': 'Ingrese el motivo de la suspensión:',
            'block': 'Ingrese el motivo del bloqueo:',
            'unblock': 'Ingrese observaciones del desbloqueo (opcional):'
        };

        const motivo = prompt(`${actionLabels[action]} - Serie: ${serie}\n\n${actionMessages[action]}`);
        
        if (motivo !== null) {
            await this.executeAction(action, equipmentId, motivo);
        }
    }

    async executeAction(action, equipmentId, motivo) {
        try {
            const methodMap = {
                'suspend': 'action_suspender_servicio',
                'block': 'action_bloquear_equipo',
                'unblock': 'action_desbloquear_equipo'
            };
            
            const method = methodMap[action];
            if (!method) {
                this.notification.add(_t('Acción no válida'), { type: "danger" });
                return;
            }
            
            const result = await this.orm.call("alquiler", method, [equipmentId], { motivo: motivo });
            
            if (result && result.success !== false) {
                const actionMessages = {
                    'suspend': 'Servicio suspendido correctamente',
                    'block': 'Equipo bloqueado correctamente',
                    'unblock': 'Equipo desbloqueado correctamente'
                };
                
                this.notification.add(_t(actionMessages[action] || 'Acción ejecutada correctamente'), { type: "success" });
                await this.refreshDashboard();
            } else {
                const errorMessage = result && result.error ? result.error : 'Error al ejecutar la acción';
                this.notification.add(_t(errorMessage), { type: "danger" });
            }
            
        } catch (error) {
            console.error("Error executing action:", error);
            
            let errorMessage = 'Error al ejecutar la acción';
            if (error.message) {
                errorMessage += ': ' + error.message;
            }
            
            this.notification.add(_t(errorMessage), { type: "danger" });
        }
    }

    // Métodos de utilidad
    escapeHtml(text) {
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

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    formatDate(dateString) {
        if (!dateString) return '';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('es-ES', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            return dateString;
        }
    }

    // Métodos de validación
    validateEquipmentAction(equipment, action) {
        if (!equipment) {
            return { valid: false, message: 'Equipo no encontrado' };
        }

        const validations = {
            'suspend': {
                condition: equipment.estado_bloqueo === 'activo',
                message: 'Solo se pueden suspender equipos activos'
            },
            'block': {
                condition: ['activo', 'suspendido'].includes(equipment.estado_bloqueo) && equipment.acceso_remoto,
                message: 'Solo se pueden bloquear equipos activos o suspendidos con acceso remoto'
            },
            'unblock': {
                condition: ['bloqueado', 'suspendido'].includes(equipment.estado_bloqueo),
                message: 'Solo se pueden desbloquear equipos bloqueados o suspendidos'
            }
        };

        const validation = validations[action];
        if (!validation) {
            return { valid: false, message: 'Acción no válida' };
        }

        return {
            valid: validation.condition,
            message: validation.condition ? '' : validation.message
        };
    }

    // Métodos de estado
    getStatusClass(estado) {
        const statusClasses = {
            'activo': 'status-success',
            'suspendido': 'status-warning',
            'bloqueado': 'status-danger',
            'no_accesible': 'status-secondary',
            'pendiente_bloqueo': 'status-info',
            'pendiente_desbloqueo': 'status-primary'
        };
        return statusClasses[estado] || 'status-default';
    }

    getStatusIcon(estado) {
        const statusIcons = {
            'activo': 'fa-check-circle',
            'suspendido': 'fa-pause-circle',
            'bloqueado': 'fa-lock',
            'no_accesible': 'fa-wifi-slash',
            'pendiente_bloqueo': 'fa-clock',
            'pendiente_desbloqueo': 'fa-unlock-alt'
        };
        return statusIcons[estado] || 'fa-question-circle';
    }

    // Métodos de estadísticas
    calculateDashboardPercentages() {
        const total = Object.values(this.state.dashboardData).reduce((sum, count) => sum + count, 0);
        
        if (total === 0) return {};
        
        return {
            activos_percent: Math.round((this.state.dashboardData.equipos_activos / total) * 100),
            suspendidos_percent: Math.round((this.state.dashboardData.equipos_suspendidos / total) * 100),
            bloqueados_percent: Math.round((this.state.dashboardData.equipos_bloqueados / total) * 100),
            no_accesibles_percent: Math.round((this.state.dashboardData.equipos_no_accesibles / total) * 100),
            pendientes_bloqueo_percent: Math.round((this.state.dashboardData.pendientes_bloqueo / total) * 100),
            pendientes_desbloqueo_percent: Math.round((this.state.dashboardData.pendientes_desbloqueo / total) * 100)
        };
    }

    // Método de limpieza al destruir el componente
    willUnmount() {
        // Limpiar cualquier timeout o interval si los hubiera
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Registrar el componente en el registro de acciones de Odoo
registry.category("actions").add("equipment_blocking_dashboard", EquipmentBlockingDashboard);
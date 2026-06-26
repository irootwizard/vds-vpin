/**
 * 安全中心页面模块
 * 处理系统安全状态监控和配置
 */

class SecurityCenter {
    constructor() {
        this.securityStatus = {
            keyProtection: true,
            encryptionEnabled: true,
            teeAvailable: false,
            verificationReady: true,
            overallSecurity: 'secure'
        };
        this.securityEvents = [];
        this.securitySettings = {
            level: 'standard',
            keyRotation: 'never',
            auditLogEnabled: true
        };
    }

    async init() {
        console.log('SecurityCenter initializing...');

        // 加载组件
        await this.loadComponents();

        // 设置事件监听器
        this.setupEventListeners();

        // 加载安全状态
        await this.loadSecurityStatus();
        await this.loadSecurityEvents();
    }

    async loadComponents() {
        // 加载header组件
        const headerPlaceholder = document.getElementById('header-container');
        if (headerPlaceholder && !headerPlaceholder.innerHTML) {
            headerPlaceholder.innerHTML = this.getHeaderHTML();
        }

        // 加载sidebar组件
        const sidebarPlaceholder = document.getElementById('sidebar-container');
        if (sidebarPlaceholder && !sidebarPlaceholder.innerHTML) {
            sidebarPlaceholder.innerHTML = this.getSidebarHTML();
        }
    }

    getHeaderHTML() {
        return `
            <div class="header">
                <div class="header-left">
                    <div class="logo">
                        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                            <circle cx="16" cy="16" r="14" fill="#1890ff" opacity="0.1"/>
                            <path d="M16 6L16 26M16 6L10 12M16 6L22 12" stroke="#1890ff" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                        <span class="logo-text">VDS-VPIN</span>
                    </div>
                </div>
                <div class="header-right">
                    <div class="connection-status">
                        <span class="status-dot"></span>
                        <span class="status-text" id="connectionStatus">连接中...</span>
                    </div>
                    <div class="user-info">
                        <span class="user-name">管理员</span>
                    </div>
                </div>
            </div>
        `;
    }

    getSidebarHTML() {
        const sidebarItems = [
            { id: 'dashboard', icon: 'dashboard.svg', text: '工作台', page: 'index.html' },
            { id: 'tasks', icon: 'activity.svg', text: '任务监控', page: 'task-dashboard.html' },
            { id: 'models', icon: 'folder.svg', text: '模型中心', page: 'model-center.html' },
            { id: 'data', icon: 'database.svg', text: '数据配置', page: 'data-config.html' },
            { id: 'privacy', icon: 'dp.svg', text: '隐私预算', page: 'privacy-budget.html' },
            { id: 'security', icon: 'shield-check.svg', text: '安全中心', page: 'security-center.html' },
            { id: 'verification', icon: 'audit.svg', text: '验证报告', page: 'verification-report.html' }
        ];

        const items = sidebarItems.map(item => `
            <a href="${item.page}" class="sidebar-item ${item.page === 'security-center.html' ? 'active' : ''}" data-page="${item.page}">
                <img src="assets/icons/${item.icon}" alt="${item.text}">
                <span>${item.text}</span>
            </a>
        `).join('');

        return `
            <div class="sidebar">
                <nav class="sidebar-nav">
                    ${items}
                </nav>
                <div class="sidebar-footer">
                    <div class="system-info">
                        <div class="info-item">
                            <span class="info-label">版本</span>
                            <span class="info-value">v1.0.0</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">服务器</span>
                            <span class="info-value" id="serverUrl">连接中...</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    setupEventListeners() {
        // Tauri action按钮
        document.querySelectorAll('.tauri-action').forEach(button => {
            button.addEventListener('click', (e) => {
                const action = e.currentTarget.dataset.action;
                this.handleAction(action);
            });
        });
    }

    async handleAction(action) {
        console.log('Handling action:', action);

        switch(action) {
            case 'run-security-check':
                await this.runSecurityCheck();
                break;
            case 'export-security-log':
                await this.exportSecurityLog();
                break;
            case 'save-security-settings':
                await this.saveSecuritySettings();
                break;
            case 'reset-security-settings':
                this.resetSecuritySettings();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }

    async loadSecurityStatus() {
        try {
            // 调用Tauri API获取安全状态
            const result = await window.api.getSecurityStatus();

            if (result.success && result.data) {
                this.securityStatus = { ...this.securityStatus, ...result.data };
            }
        } catch (error) {
            console.error('Failed to load security status:', error);
        }

        this.updateSecurityUI();
    }

    updateSecurityUI() {
        // 更新安全状态显示
        const keyStatus = document.getElementById('keyStatus');
        const encryptionStatus = document.getElementById('encryptionStatus');
        const teeStatus = document.getElementById('teeStatus');
        const verificationStatus = document.getElementById('verificationStatus');

        if (keyStatus) {
            keyStatus.textContent = this.securityStatus.key_protection ? '安全' : '风险';
            keyStatus.style.color = this.securityStatus.key_protection ? '#52c41a' : '#ff4d4f';
        }

        if (encryptionStatus) {
            encryptionStatus.textContent = this.securityStatus.tls_enabled ? '启用' : '未启用';
            encryptionStatus.style.color = this.securityStatus.tls_enabled ? '#52c41a' : '#ff4d4f';
        }

        if (teeStatus) {
            teeStatus.textContent = this.securityStatus.tee_available ? '已启用' : '未启用';
            teeStatus.style.color = this.securityStatus.tee_available ? '#52c41a' : '#faad14';
        }

        if (verificationStatus) {
            verificationStatus.textContent = this.securityStatus.verification_module === 'ready' ? '就绪' : '未就绪';
            verificationStatus.style.color = this.securityStatus.verification_module === 'ready' ? '#52c41a' : '#ff4d4f';
        }

        // 更新设置输入框
        const levelSelect = document.getElementById('securityLevelSelect');
        const rotationSelect = document.getElementById('keyRotationSelect');
        const auditCheckbox = document.getElementById('auditLogEnabled');

        if (levelSelect) levelSelect.value = this.securitySettings.level;
        if (rotationSelect) rotationSelect.value = this.securitySettings.keyRotation;
        if (auditCheckbox) auditCheckbox.checked = this.securitySettings.auditLogEnabled;
    }

    async loadSecurityEvents() {
        try {
            // 调用Tauri API获取安全事件
            const result = await window.api.invoke('get_security_events');

            if (result.success && result.data) {
                this.securityEvents = result.data;
            }
        } catch (error) {
            console.error('Failed to load security events:', error);
            // 使用空数据
            this.securityEvents = [];
        }

        this.renderSecurityEvents();
    }

    renderSecurityEvents() {
        const eventLog = document.getElementById('securityEventLog');
        if (!eventLog) return;

        if (this.securityEvents.length === 0) {
            eventLog.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; color: #8c8c8c;">
                    <img src="assets/icons/history.svg" alt="无事件" style="width: 48px; height: 48px; opacity: 0.3; margin-bottom: 16px;">
                    <p>暂无安全事件</p>
                </div>
            `;
            return;
        }

        eventLog.innerHTML = this.securityEvents.map(event => this.renderEventItem(event)).join('');
    }

    renderEventItem(event) {
        const time = new Date(event.timestamp).toLocaleString();
        const typeColors = {
            'info': '#1890ff',
            'warning': '#faad14',
            'error': '#ff4d4f',
            'success': '#52c41a'
        };
        const typeColor = typeColors[event.type] || '#595959';

        return `
            <div class="log-item">
                <div class="log-time">${time}</div>
                <div class="log-content">
                    <div class="log-type" style="color: ${typeColor};">${event.type.toUpperCase()}</div>
                    <div class="log-description">${event.description}</div>
                </div>
            </div>
        `;
    }

    async runSecurityCheck() {
        console.log('Running security check...');

        try {
            const result = await window.api.invoke('run_security_check');

            if (result.success) {
                this.showNotification('安全检查完成', 'success');
                await this.loadSecurityStatus();
            } else {
                throw new Error(result.error || '检查失败');
            }
        } catch (error) {
            console.error('Security check failed:', error);
            this.showNotification('安全检查失败: ' + error.message, 'error');
        }
    }

    async exportSecurityLog() {
        console.log('Exporting security log...');

        try {
            const result = await window.api.invoke('export_security_log');

            if (result.success) {
                this.showNotification('安全日志导出成功', 'success');
            } else {
                throw new Error(result.error || '导出失败');
            }
        } catch (error) {
            console.error('Export failed:', error);
            this.showNotification('导出失败: ' + error.message, 'error');
        }
    }

    async saveSecuritySettings() {
        const levelSelect = document.getElementById('securityLevelSelect');
        const rotationSelect = document.getElementById('keyRotationSelect');
        const auditCheckbox = document.getElementById('auditLogEnabled');

        if (!levelSelect || !rotationSelect || !auditCheckbox) return;

        this.securitySettings = {
            level: levelSelect.value,
            keyRotation: rotationSelect.value,
            auditLogEnabled: auditCheckbox.checked
        };

        try {
            const result = await window.api.invoke('save_security_settings', this.securitySettings);

            if (result.success) {
                this.showNotification('安全设置保存成功', 'success');
            } else {
                throw new Error(result.error || '保存失败');
            }
        } catch (error) {
            console.error('Save settings failed:', error);
            this.showNotification('保存失败: ' + error.message, 'error');
        }
    }

    resetSecuritySettings() {
        const defaultSettings = {
            level: 'standard',
            keyRotation: 'never',
            auditLogEnabled: true
        };

        const levelSelect = document.getElementById('securityLevelSelect');
        const rotationSelect = document.getElementById('keyRotationSelect');
        const auditCheckbox = document.getElementById('auditLogEnabled');

        if (levelSelect) levelSelect.value = defaultSettings.level;
        if (rotationSelect) rotationSelect.value = defaultSettings.keyRotation;
        if (auditCheckbox) auditCheckbox.checked = defaultSettings.auditLogEnabled;

        this.securitySettings = defaultSettings;
        this.showNotification('已重置为默认设置', 'info');
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;

        notification.style.cssText = `
            position: fixed;
            top: 24px;
            right: 24px;
            padding: 16px 24px;
            border-radius: 8px;
            color: white;
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;

        if (type === 'success') {
            notification.style.background = '#52c41a';
        } else if (type === 'error') {
            notification.style.background = '#ff4d4f';
        } else {
            notification.style.background = '#1890ff';
        }

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
}

// 页面加载完成后初始化安全中心
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.securityCenter = new SecurityCenter();
        window.securityCenter.init();
    });
} else {
    window.securityCenter = new SecurityCenter();
    window.securityCenter.init();
}
/**
 * 隐私预算页面模块
 * 处理差分隐私预算的管理和监控
 */

class PrivacyBudget {
    constructor() {
        this.budgetData = {
            total: 10.0,
            used: 5.8,
            remaining: 4.2,
            usagePercentage: 58
        };
        this.usageHistory = [];
        this.settings = {
            weeklyBudget: 10.0,
            alertThreshold: 80,
            resetPeriod: 'weekly'
        };
    }

    async init() {
        console.log('PrivacyBudget initializing...');

        // 加载组件
        await this.loadComponents();

        // 设置事件监听器
        this.setupEventListeners();

        // 加载数据
        await this.loadBudgetData();
        await this.loadUsageHistory();
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
            <a href="${item.page}" class="sidebar-item ${item.page === 'privacy-budget.html' ? 'active' : ''}" data-page="${item.page}">
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
            case 'refresh-budget':
                await this.refreshBudget();
                break;
            case 'export-report':
                await this.exportReport();
                break;
            case 'save-settings':
                await this.saveSettings();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }

    async loadBudgetData() {
        try {
            // 调用Tauri API获取预算数据
            const result = await window.api.invoke('get_privacy_budget');

            if (result.success && result.data) {
                this.budgetData = result.data;
            }
        } catch (error) {
            console.error('Failed to load budget data:', error);
        }

        this.updateBudgetUI();
    }

    updateBudgetUI() {
        // 更新预算显示
        const totalBudget = document.getElementById('totalBudget');
        const usedBudget = document.getElementById('usedBudget');
        const remainingBudget = document.getElementById('remainingBudget');
        const progressBar = document.getElementById('budgetProgressBar');

        if (totalBudget) totalBudget.textContent = `ε = ${this.budgetData.total.toFixed(1)}`;
        if (usedBudget) usedBudget.textContent = `ε = ${this.budgetData.used.toFixed(1)}`;
        if (remainingBudget) remainingBudget.textContent = `ε = ${this.budgetData.remaining.toFixed(1)}`;

        if (progressBar) {
            const percentage = Math.round((this.budgetData.used / this.budgetData.total) * 100);
            progressBar.style.width = `${percentage}%`;

            // 根据使用比例设置颜色
            if (percentage >= 90) {
                progressBar.style.background = '#ff4d4f'; // 红色警告
            } else if (percentage >= 70) {
                progressBar.style.background = '#faad14'; // 黄色警告
            } else {
                progressBar.style.background = 'linear-gradient(90deg, #52c41a, #1890ff)'; // 正常
            }
        }

        // 更新设置输入框
        const weeklyInput = document.getElementById('weeklyBudgetInput');
        const alertInput = document.getElementById('alertThresholdInput');
        const resetSelect = document.getElementById('resetPeriodSelect');

        if (weeklyInput) weeklyInput.value = this.settings.weeklyBudget;
        if (alertInput) alertInput.value = this.settings.alertThreshold;
        if (resetSelect) resetSelect.value = this.settings.resetPeriod;
    }

    async loadUsageHistory() {
        try {
            // 调用Tauri API获取使用历史
            const result = await window.api.invoke('get_usage_history');

            if (result.success && result.data) {
                this.usageHistory = result.data;
            }
        } catch (error) {
            console.error('Failed to load usage history:', error);
            // 使用空数据
            this.usageHistory = [];
        }

        this.renderUsageHistory();
    }

    renderUsageHistory() {
        const historyList = document.getElementById('usageHistoryList');
        if (!historyList) return;

        if (this.usageHistory.length === 0) {
            historyList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; color: #8c8c8c;">
                    <img src="assets/icons/history.svg" alt="无记录" style="width: 48px; height: 48px; opacity: 0.3; margin-bottom: 16px;">
                    <p>暂无使用记录</p>
                </div>
            `;
            return;
        }

        historyList.innerHTML = `
            <div style="display: flex; flex-direction: column;">
                ${this.usageHistory.map(item => this.renderHistoryItem(item)).join('')}
            </div>
        `;
    }

    renderHistoryItem(item) {
        const date = new Date(item.timestamp).toLocaleString();
        const statusColor = item.status === 'completed' ? '#52c41a' : '#faad14';

        return `
            <div class="history-item">
                <div>
                    <div style="color: #262626; font-weight: 500;">${item.task_name}</div>
                    <div style="color: #8c8c8c; font-size: 12px;">${date}</div>
                </div>
                <div style="text-align: right;">
                    <div style="color: #096dd9; font-weight: 600;">ε = ${item.epsilon_used.toFixed(3)}</div>
                    <div style="color: ${statusColor}; font-size: 12px;">${item.status === 'completed' ? '已完成' : '进行中'}</div>
                </div>
            </div>
        `;
    }

    async refreshBudget() {
        console.log('Refreshing budget data...');
        await this.loadBudgetData();
        await this.loadUsageHistory();
        this.showNotification('预算数据已刷新', 'success');
    }

    async exportReport() {
        console.log('Exporting budget report...');

        try {
            const result = await window.api.invoke('export_budget_report');

            if (result.success) {
                this.showNotification('报告导出成功', 'success');
            } else {
                throw new Error(result.error || '导出失败');
            }
        } catch (error) {
            console.error('Export failed:', error);
            this.showNotification('导出失败: ' + error.message, 'error');
        }
    }

    async saveSettings() {
        const weeklyInput = document.getElementById('weeklyBudgetInput');
        const alertInput = document.getElementById('alertThresholdInput');
        const resetSelect = document.getElementById('resetPeriodSelect');

        if (!weeklyInput || !alertInput || !resetSelect) return;

        this.settings = {
            weeklyBudget: parseFloat(weeklyInput.value),
            alertThreshold: parseInt(alertInput.value),
            resetPeriod: resetSelect.value
        };

        try {
            const result = await window.api.invoke('save_budget_settings', this.settings);

            if (result.success) {
                this.showNotification('设置保存成功', 'success');
                await this.loadBudgetData();
            } else {
                throw new Error(result.error || '保存失败');
            }
        } catch (error) {
            console.error('Save settings failed:', error);
            this.showNotification('保存失败: ' + error.message, 'error');
        }
    }

    resetToDefault() {
        const defaultSettings = {
            weeklyBudget: 10.0,
            alertThreshold: 80,
            resetPeriod: 'weekly'
        };

        const weeklyInput = document.getElementById('weeklyBudgetInput');
        const alertInput = document.getElementById('alertThresholdInput');
        const resetSelect = document.getElementById('resetPeriodSelect');

        if (weeklyInput) weeklyInput.value = defaultSettings.weeklyBudget;
        if (alertInput) alertInput.value = defaultSettings.alertThreshold;
        if (resetSelect) resetSelect.value = defaultSettings.resetPeriod;

        this.settings = defaultSettings;
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

// 页面加载完成后初始化隐私预算页面
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.privacyBudget = new PrivacyBudget();
        window.privacyBudget.init();
    });
} else {
    window.privacyBudget = new PrivacyBudget();
    window.privacyBudget.init();
}
/**
 * 验证报告页面模块
 * 处理CP-SNARK计算量证明验证报告的查看和管理
 */

class VerificationReport {
    constructor() {
        this.reports = [];
        this.currentReport = null;
        this.filters = {
            status: 'all',
            model: 'all',
            time: 'month',
            search: ''
        };
    }

    async init() {
        console.log('VerificationReport initializing...');

        // 加载组件
        await this.loadComponents();

        // 设置事件监听器
        this.setupEventListeners();

        // 加载报告数据
        await this.loadReports();
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
            <a href="${item.page}" class="sidebar-item ${item.page === 'verification-report.html' ? 'active' : ''}" data-page="${item.page}">
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

        // 搜索输入框
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filters.search = e.target.value;
                this.filterReports();
            });
        }

        // 筛选下拉框
        const filters = ['statusFilter', 'modelFilter', 'timeFilter'];
        filters.forEach(filterId => {
            const filterElement = document.getElementById(filterId);
            if (filterElement) {
                filterElement.addEventListener('change', (e) => {
                    this.updateFilters();
                });
            }
        });
    }

    updateFilters() {
        const statusFilter = document.getElementById('statusFilter');
        const modelFilter = document.getElementById('modelFilter');
        const timeFilter = document.getElementById('timeFilter');

        if (statusFilter) this.filters.status = statusFilter.value;
        if (modelFilter) this.filters.model = modelFilter.value;
        if (timeFilter) this.filters.time = timeFilter.value;

        this.filterReports();
    }

    async handleAction(action) {
        console.log('Handling action:', action);

        switch(action) {
            case 'refresh-reports':
                await this.refreshReports();
                break;
            case 'export-all-reports':
                await this.exportAllReports();
                break;
            case 'filter-reports':
                this.updateFilters();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }

    async loadReports() {
        try {
            // 调用Tauri API获取验证报告
            const result = await window.api.invoke('get_verification_reports');

            if (result.success && result.data) {
                this.reports = result.data;
            }
        } catch (error) {
            console.error('Failed to load reports:', error);
            // 使用空数据
            this.reports = [];
        }

        this.renderReports();
    }

    renderReports() {
        const reportList = document.getElementById('reportList');
        if (!reportList) return;

        const filteredReports = this.getFilteredReports();

        if (filteredReports.length === 0) {
            reportList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; color: #8c8c8c;">
                    <img src="assets/icons/audit.svg" alt="无报告" style="width: 48px; height: 48px; opacity: 0.3; margin-bottom: 16px;">
                    <p>暂无验证报告</p>
                    <p style="font-size: 12px; margin-top: 8px;">完成任务后将会生成相应的验证报告</p>
                </div>
            `;
            return;
        }

        reportList.innerHTML = filteredReports.map(report => this.renderReportCard(report)).join('');
    }

    getFilteredReports() {
        let filtered = [...this.reports];

        // 状态筛选
        if (this.filters.status !== 'all') {
            filtered = filtered.filter(report => report.status === this.filters.status);
        }

        // 模型筛选
        if (this.filters.model !== 'all') {
            filtered = filtered.filter(report => report.model_type === this.filters.model);
        }

        // 搜索筛选
        if (this.filters.search) {
            const search = this.filters.search.toLowerCase();
            filtered = filtered.filter(report =>
                report.id.toLowerCase().includes(search) ||
                report.task_name.toLowerCase().includes(search)
            );
        }

        return filtered;
    }

    filterReports() {
        this.renderReports();
    }

    renderReportCard(report) {
        const statusClass = report.status === 'passed' ? 'passed' :
                           report.status === 'failed' ? 'failed' : 'pending';

        const statusText = {
            'passed': '通过验证',
            'failed': '验证失败',
            'pending': '验证中'
        }[report.status] || report.status;

        const createdTime = new Date(report.created_at).toLocaleString();

        return `
            <div class="report-card" onclick="window.verificationReport.showReportDetails('${report.id}')">
                <div class="report-header">
                    <div class="report-id">${report.id}</div>
                    <div class="report-status ${statusClass}">${statusText}</div>
                </div>

                <div class="report-meta">
                    <div class="meta-item">
                        <div class="meta-label">任务名称</div>
                        <div class="meta-value">${report.task_name}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">模型</div>
                        <div class="meta-value">${report.model_name}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">验证时间</div>
                        <div class="meta-value">${createdTime}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">验证耗时</div>
                        <div class="meta-value">${report.verification_time}ms</div>
                    </div>
                </div>

                <div class="report-summary">
                    <div class="summary-grid">
                        <div class="summary-item">
                            <div class="summary-label">计算层数</div>
                            <div class="summary-value">${report.layer_count || 0}</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">点加运算</div>
                            <div class="summary-value">${report.pt_add_count || 0}</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">点乘运算</div>
                            <div class="summary-value">${report.pt_mult_count || 0}</div>
                        </div>
                        <div class="summary-item">
                            <div class="summary-label">证明大小</div>
                            <div class="summary-value">${report.proof_size || 0}KB</div>
                        </div>
                    </div>
                </div>

                <div class="report-actions">
                    <button class="btn-secondary" onclick="event.stopPropagation(); window.verificationReport.showReportDetails('${report.id}')" style="flex: 1;">
                        查看详情
                    </button>
                    <button class="btn-secondary" onclick="event.stopPropagation(); window.verificationReport.exportReport('${report.id}')" style="flex: 1;">
                        导出报告
                    </button>
                </div>
            </div>
        `;
    }

    async showReportDetails(reportId) {
        try {
            // 调用Tauri API获取报告详情
            const result = await window.api.invoke('get_verification_report_details', { report_id: reportId });

            if (result.success && result.data) {
                this.currentReport = result.data;
                this.renderReportDetails();
            } else {
                throw new Error(result.error || '获取详情失败');
            }
        } catch (error) {
            console.error('Failed to get report details:', error);
            this.showNotification('获取报告详情失败: ' + error.message, 'error');
        }
    }

    renderReportDetails() {
        const detailsPanel = document.getElementById('reportDetailsPanel');
        const detailsContent = document.getElementById('reportDetailsContent');

        if (!detailsPanel || !detailsContent || !this.currentReport) return;

        const report = this.currentReport;

        detailsContent.innerHTML = `
            <div class="detail-section">
                <h4>基本信息</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">报告ID</div>
                        <div style="color: #262626; font-weight: 500;">${report.id}</div>
                    </div>
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">任务名称</div>
                        <div style="color: #262626; font-weight: 500;">${report.task_name}</div>
                    </div>
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">验证状态</div>
                        <div style="color: ${report.status === 'passed' ? '#52c41a' : '#ff4d4f'}; font-weight: 500;">
                            ${report.status === 'passed' ? '通过验证' : '验证失败'}
                        </div>
                    </div>
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">验证时间</div>
                        <div style="color: #262626; font-weight: 500;">${new Date(report.verified_at).toLocaleString()}</div>
                    </div>
                </div>
            </div>

            <div class="detail-section">
                <h4>计算量证明链</h4>
                <div class="proof-chain">
                    ${this.renderProofChain(report)}
                </div>
            </div>

            <div class="detail-section">
                <h4>挑战参数</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px;">
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">γ (Gamma)</div>
                        <div style="color: #096dd9; font-weight: 600; font-family: monospace;">${report.challenge?.gamma || 'N/A'}</div>
                    </div>
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">γ_add</div>
                        <div style="color: #096dd9; font-weight: 600;">${report.challenge?.gamma_add || 0}</div>
                    </div>
                    <div>
                        <div style="color: #8c8c8c; font-size: 12px; margin-bottom: 4px;">γ_mult</div>
                        <div style="color: #096dd9; font-weight: 600;">${report.challenge?.gamma_mult || 0}</div>
                    </div>
                </div>
            </div>

            <div class="detail-section">
                <h4>验证结果</h4>
                <div style="background: #fafafa; border-radius: 8px; padding: 16px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 12px;">
                        <span style="color: #595959;">证明验证</span>
                        <span style="color: ${report.verification_result?.proof_valid ? '#52c41a' : '#ff4d4f'}; font-weight: 500;">
                            ${report.verification_result?.proof_valid ? '通过' : '失败'}
                        </span>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 12px;">
                        <span style="color: #595959;">模型完整性</span>
                        <span style="color: ${report.verification_result?.model_integrity ? '#52c41a' : '#ff4d4f'}; font-weight: 500;">
                            ${report.verification_result?.model_integrity ? '通过' : '失败'}
                        </span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #595959;">计算量正确性</span>
                        <span style="color: ${report.verification_result?.computation_correct ? '#52c41a' : '#ff4d4f'}; font-weight: 500;">
                            ${report.verification_result?.computation_correct ? '通过' : '失败'}
                        </span>
                    </div>
                </div>
            </div>
        `;

        detailsPanel.classList.add('active');
    }

    renderProofChain(report) {
        const steps = [
            { number: 1, title: '模型承诺 (P1)', description: `cm_W: ${report.proof_chain?.cm_w?.substring(0, 16)}...` },
            { number: 2, title: '输入承诺 (P2)', description: `cm_x: ${report.proof_chain?.cm_x?.substring(0, 16)}...` },
            { number: 3, title: '同态计算 (P3)', description: `witness 生成完成，包含 ${report.layer_count} 层计算` },
            { number: 4, title: '客户端挑战 (P4)', description: `随机生成挑战参数 γ, γ_add, γ_mult` },
            { number: 5, title: '证明生成 (P5)', description: `服务端生成计算量证明 π` },
            { number: 6, title: '本地验证 (P6)', description: `客户端验证证明和计算正确性` }
        ];

        return steps.map(step => `
            <div class="chain-step">
                <div class="step-number">${step.number}</div>
                <div class="step-content">
                    <div class="step-title">${step.title}</div>
                    <div class="step-description">${step.description}</div>
                </div>
            </div>
        `).join('');
    }

    closeDetails() {
        const detailsPanel = document.getElementById('reportDetailsPanel');
        if (detailsPanel) {
            detailsPanel.classList.remove('active');
        }
        this.currentReport = null;
    }

    async refreshReports() {
        console.log('Refreshing verification reports...');
        await this.loadReports();
        this.showNotification('报告列表已刷新', 'success');
    }

    async exportReport(reportId) {
        console.log('Exporting report:', reportId);

        try {
            const result = await window.api.invoke('export_verification_report', { report_id: reportId });

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

    async exportAllReports() {
        console.log('Exporting all reports...');

        try {
            const result = await window.api.invoke('export_all_verification_reports');

            if (result.success) {
                this.showNotification('全部报告导出成功', 'success');
            } else {
                throw new Error(result.error || '导出失败');
            }
        } catch (error) {
            console.error('Export all failed:', error);
            this.showNotification('导出失败: ' + error.message, 'error');
        }
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

// 页面加载完成后初始化验证报告页面
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.verificationReport = new VerificationReport();
        window.verificationReport.init();
    });
} else {
    window.verificationReport = new VerificationReport();
    window.verificationReport.init();
}
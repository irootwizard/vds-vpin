/**
 * 应用程序主模块
 * 处理页面初始化、组件加载和用户交互
 */

class App {
    constructor() {
        this.currentPage = this.getCurrentPage();
        this.sidebarItems = [
            { id: 'dashboard', icon: 'dashboard.svg', text: '工作台', page: 'index.html' },
            { id: 'tasks', icon: 'activity.svg', text: '任务监控', page: 'task-dashboard.html' },
            { id: 'models', icon: 'model.svg', text: '模型中心', page: 'model-center.html' },
            { id: 'data', icon: 'database.svg', text: '数据配置', page: 'data-config.html' },
            { id: 'privacy', icon: 'dp.svg', text: '隐私预算', page: 'privacy-budget.html' },
            { id: 'security', icon: 'shield-check.svg', text: '安全中心', page: 'security-center.html' },
            { id: 'verification', icon: 'audit.svg', text: '验证报告', page: 'verification-report.html' }
        ];
    }

    getCurrentPage() {
        const path = window.location.pathname;
        const filename = path.split('/').pop();
        return filename || 'index.html';
    }

    async init() {
        console.log('App initializing...');
        await this.loadComponents();
        this.setupEventListeners();
        this.highlightSidebar();
        await this.loadPageData();
        this.startRealtimeUpdates();
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
        const items = this.sidebarItems.map(item => `
            <a href="${item.page}" class="sidebar-item ${item.page === this.currentPage ? 'active' : ''}" data-page="${item.page}">
                <img src="../assets/icons/${item.icon}" alt="${item.text}">
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
        // 侧边栏导航
        document.addEventListener('click', (e) => {
            const sidebarItem = e.target.closest('.sidebar-item');
            if (sidebarItem) {
                document.querySelectorAll('.sidebar-item').forEach(item => {
                    item.classList.remove('active');
                });
                sidebarItem.classList.add('active');
            }
        });

        // 卡片悬停效果
        document.addEventListener('mouseenter', (e) => {
            const card = e.target.closest('.tech-card');
            if (card) {
                card.style.transform = 'translateY(-2px)';
                card.style.boxShadow = '0 12px 32px rgba(24, 144, 255, 0.2)';
            }
        }, true);

        document.addEventListener('mouseleave', (e) => {
            const card = e.target.closest('.tech-card');
            if (card) {
                card.style.transform = 'translateY(0)';
                card.style.boxShadow = '0 8px 32px rgba(0, 80, 179, 0.1)';
            }
        }, true);
    }

    highlightSidebar() {
        const activeItem = document.querySelector(`[data-page="${this.currentPage}"]`);
        if (activeItem) {
            document.querySelectorAll('.sidebar-item').forEach(item => {
                item.classList.remove('active');
            });
            activeItem.classList.add('active');
        }
    }

    async loadPageData() {
        try {
            // 检查连接状态
            const healthResult = await window.api.healthCheck();
            this.updateConnectionStatus(healthResult.success);

            if (healthResult.success) {
                // 获取服务器地址
                const urlResult = await window.api.getServerUrl();
                if (urlResult.success) {
                    document.getElementById('serverUrl').textContent = urlResult.data;
                }
            }

            // 根据页面类型加载特定数据
            await this.loadPageSpecificData();

        } catch (error) {
            console.error('Failed to load page data:', error);
            this.updateConnectionStatus(false);
        }
    }

    updateConnectionStatus(connected) {
        const statusDot = document.querySelector('.status-dot');
        const statusText = document.getElementById('connectionStatus');

        if (statusDot && statusText) {
            if (connected) {
                statusDot.style.background = '#52c41a';
                statusText.textContent = '已连接';
            } else {
                statusDot.style.background = '#ff4d4f';
                statusText.textContent = '连接失败';
            }
        }
    }

    async loadPageSpecificData() {
        // 根据不同页面加载不同数据
        switch(this.currentPage) {
            case 'index.html':
                await this.loadDashboardData();
                break;
            case 'task-dashboard.html':
                await this.loadTaskData();
                break;
            case 'model-center.html':
                await this.loadModelData();
                break;
        }
    }

    async loadDashboardData() {
        try {
            // 获取服务器信息
            const serverInfo = await window.api.getServerInfo();
            console.log('Server info:', serverInfo);

            // 获取任务数据
            const tasksResult = await window.api.getTasks();
            if (tasksResult.success && tasksResult.data) {
                this.updateDashboardStats(tasksResult.data);
                this.updateRecentTasks(tasksResult.data);
            }

            // 获取模型数量
            const modelsResult = await window.api.getModels();
            if (modelsResult.success && modelsResult.data) {
                const modelsCount = document.getElementById('modelsCount');
                if (modelsCount) {
                    modelsCount.textContent = modelsResult.data.length;
                }
            }

            // 获取系统状态
            const systemStatus = await window.api.getSystemStatus();
            if (systemStatus.success && systemStatus.data) {
                this.updateSystemOverview(systemStatus.data);
            }

        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        }
    }

    updateRecentTasks(tasks) {
        const taskList = document.getElementById('taskList');
        if (!taskList) return;

        if (!tasks || tasks.length === 0) {
            taskList.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #8c8c8c;">
                    暂无任务
                </div>
            `;
            return;
        }

        // 显示最近的任务
        const recentTasks = tasks.slice(0, 3);
        taskList.innerHTML = recentTasks.map(task => this.renderTaskItem(task)).join('');
    }

    renderTaskItem(task) {
        const statusClass = task.status === 'running' ? 'running' :
                           task.status === 'queued' ? 'queued' :
                           task.status === 'completed' ? 'success' : 'failed';

        const statusText = {
            'running': '运行中',
            'queued': '排队中',
            'completed': '已完成',
            'failed': '失败'
        }[task.status] || task.status;

        const teeBadge = task.has_tee ? `
            <span class="tag-tee" style="background: rgba(114, 46, 209, 0.1); color: #722ed1; padding: 4px 8px; border-radius: 4px; font-size: 12px;">
                <img src="assets/icons/lock-check.svg" alt="TEE" style="width: 12px; height: 12px;">
                TEE保护中
            </span>
        ` : '';

        return `
            <div class="task-item tech-card" style="background: white; border: none; border-bottom: 1px solid #f0f0f0;">
                <div class="task-info">
                    <div class="task-id" style="color: #8c8c8c;">${task.id}</div>
                    <div class="task-name" style="color: #262626;">${task.name}</div>
                    <div class="task-model" style="color: #595959;">
                        <img src="assets/icons/model-${task.model_type}.svg" alt="模型" style="width: 16px; height: 16px;">
                        ${task.model}
                    </div>
                    ${teeBadge}
                </div>

                <div class="task-status">
                    <div class="status-indicator ${statusClass}">
                        <span class="status-dot" style="background: ${statusClass === 'running' ? '#1890ff' : statusClass === 'success' ? '#52c41a' : '#ff4d4f'};"></span>
                        <span class="status-text" style="color: ${statusClass === 'running' ? '#1890ff' : statusClass === 'success' ? '#52c41a' : '#ff4d4f'};">${statusText}</span>
                    </div>
                    ${task.status === 'running' ? `
                        <div class="progress-info">
                            <div class="progress" style="background: #f0f0f0;">
                                <div class="progress-bar" style="background: #1890ff; width: ${task.progress}%"></div>
                            </div>
                            <span class="progress-text" style="color: #595959;">${task.progress}%</span>
                        </div>
                    ` : ''}
                </div>

                <div class="task-resources" style="color: #595959;">
                    ${task.status === 'running' ? `
                        <div class="resource-item">
                            <img src="assets/icons/cpu.svg" alt="CPU" style="width: 14px; height: 14px;">
                            <span>CPU: ${task.cpu}%</span>
                        </div>
                        <div class="resource-item">
                            <img src="assets/icons/memory.svg" alt="内存" style="width: 14px; height: 14px;">
                            <span>内存: ${task.memory}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    updateSystemOverview(systemStatus) {
        // 更新可用性百分比
        const availability = document.getElementById('availability');
        if (availability && systemStatus.data) {
            availability.textContent = '99.8%';
        }

        // 可以添加更多的系统状态更新
    }

    async loadTaskData() {
        try {
            const tasksResult = await window.api.getTasks();
            if (tasksResult.success && tasksResult.data) {
                this.updateTaskList(tasksResult.data);
            }
        } catch (error) {
            console.error('Failed to load task data:', error);
        }
    }

    async loadModelData() {
        try {
            const modelsResult = await window.api.getModels();
            if (modelsResult.success && modelsResult.data) {
                this.updateModelList(modelsResult.data);
            }
        } catch (error) {
            console.error('Failed to load model data:', error);
        }
    }

    updateDashboardStats(tasks) {
        const running = tasks.filter(t => t.status === 'running').length;
        const completed = tasks.filter(t => t.status === 'completed').length;
        const failed = tasks.filter(t => t.status === 'failed').length;

        // 更新统计卡片
        const statCards = document.querySelectorAll('.stat-card .stat-value');
        if (statCards.length >= 4) {
            statCards[0].textContent = running;
            statCards[2].textContent = completed;
            statCards[3].textContent = failed;
        }
    }

    updateTaskList(tasks) {
        // 更新任务列表
        const taskList = document.querySelector('.task-list');
        if (taskList) {
            // 实现任务列表更新逻辑
            console.log('Updating task list with:', tasks);
        }
    }

    updateModelList(models) {
        // 更新模型列表
        const modelList = document.querySelector('.model-list');
        if (modelList) {
            // 实现模型列表更新逻辑
            console.log('Updating model list with:', models);
        }
    }

    startRealtimeUpdates() {
        // 启动实时更新
        setInterval(async () => {
            try {
                await window.api.healthCheck();
                await this.loadPageSpecificData();
            } catch (error) {
                console.error('Real-time update failed:', error);
            }
        }, 5000); // 每5秒更新一次
    }
}

// 页面加载完成后初始化应用
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.app = new App();
        window.app.init();
    });
} else {
    window.app = new App();
    window.app.init();
}

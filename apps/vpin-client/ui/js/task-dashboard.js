/**
 * 任务监控页面模块
 * 处理任务监控页面的特定逻辑
 */

class TaskDashboard {
    constructor() {
        this.tasks = [];
        this.refreshInterval = 5000; // 5秒刷新一次
        this.refreshTimer = null;
    }

    async init() {
        console.log('TaskDashboard initializing...');

        // 加载组件
        await this.loadComponents();

        // 设置事件监听器
        this.setupEventListeners();

        // 加载初始数据
        await this.loadTasksData();
        await this.loadResourcesData();

        // 启动自动刷新
        this.startAutoRefresh();

        // 监听页面卸载
        window.addEventListener('beforeunload', () => {
            this.stopAutoRefresh();
        });
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
            { id: 'data', icon: 'database.svg', text: '数据配置', page: 'data-config.html' }
        ];

        const items = sidebarItems.map(item => `
            <a href="${item.page}" class="sidebar-item ${item.page === 'task-dashboard.html' ? 'active' : ''}" data-page="${item.page}">
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
                this.handleTauriAction(action);
            });
        });
    }

    async handleTauriAction(action) {
        console.log('Handling Tauri action:', action);

        switch(action) {
            case 'create-task':
                await this.createNewTask();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }

    async createNewTask() {
        try {
            // 这里将调用Tauri命令创建新任务
            const result = await window.api.invoke('create_task_wizard');
            console.log('Create task result:', result);

            if (result.success) {
                // 刷新任务列表
                await this.loadTasksData();
            }
        } catch (error) {
            console.error('Failed to create task:', error);
            alert('创建任务失败: ' + error.message);
        }
    }

    async loadTasksData() {
        try {
            // 调用Tauri API获取任务数据
            const result = await window.api.getTasks();

            if (result.success && result.data) {
                this.tasks = result.data;
                this.updateTasksUI();
                this.updateStats();
            }
        } catch (error) {
            console.error('Failed to load tasks:', error);
            // 使用模拟数据
            this.loadMockTasks();
        }
    }

    loadMockTasks() {
        // 不再提供静态样例数据，实际使用中应从真实API获取
        this.tasks = [];
        this.updateTasksUI();
        this.updateStats();
    }

    updateTasksUI() {
        const taskList = document.getElementById('realTimeTaskList');
        if (!taskList) return;

        if (this.tasks.length === 0) {
            taskList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; color: #8c8c8c;">
                    <img src="assets/icons/folder.svg" alt="无任务" style="width: 48px; height: 48px; opacity: 0.3; margin-bottom: 16px;">
                    <p>暂无任务</p>
                    <button class="btn-primary" onclick="window.app.handleTauriAction('create-task')" style="margin-top: 16px;">
                        创建新任务
                    </button>
                </div>
            `;
            return;
        }

        taskList.innerHTML = this.tasks.map(task => this.renderTaskItem(task)).join('');
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

        const teeBadge = task.hasTEE ? `
            <span class="tag-tee">
                <img src="assets/icons/lock-check.svg" alt="TEE">
                TEE保护中
            </span>
        ` : '';

        return `
            <div class="task-item ${statusClass}">
                <div class="task-info">
                    <div class="task-id">${task.id}</div>
                    <div class="task-name">${task.name}</div>
                    <div class="task-model">
                        <img src="assets/icons/model-${task.modelType}.svg" alt="模型">
                        ${task.model}
                    </div>
                    ${teeBadge}
                </div>

                <div class="task-status">
                    <div class="status-indicator ${statusClass === 'running' ? 'running' : statusClass}">
                        <span class="status-dot"></span>
                        <span class="status-text">${statusText}</span>
                    </div>
                    ${task.status === 'running' ? `
                        <div class="progress-info">
                            <div class="progress">
                                <div class="progress-bar" style="width: ${task.progress}%"></div>
                            </div>
                            <span class="progress-text">${task.progress}%</span>
                        </div>
                    ` : ''}
                </div>

                <div class="task-resources">
                    ${task.status === 'running' ? `
                        <div class="resource-item">
                            <img src="assets/icons/cpu.svg" alt="CPU">
                            <span>CPU: ${task.cpu}%</span>
                        </div>
                        <div class="resource-item">
                            <img src="assets/icons/memory.svg" alt="内存">
                            <span>内存: ${task.memory}</span>
                        </div>
                        <div class="resource-item">
                            <img src="assets/icons/clock.svg" alt="时间">
                            <span>已运行: ${task.time}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    updateStats() {
        const running = this.tasks.filter(t => t.status === 'running').length;
        const queued = this.tasks.filter(t => t.status === 'queued').length;
        const completed = this.tasks.filter(t => t.status === 'completed').length;
        const failed = this.tasks.filter(t => t.status === 'failed').length;

        // 更新统计数字
        this.updateElement('runningTasks', running);
        this.updateElement('queuedTasks', queued);
        this.updateElement('completedTasks', completed);
        this.updateElement('failedTasks', failed);
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    async loadResourcesData() {
        try {
            // 调用Tauri API获取系统资源数据
            const result = await window.api.getSystemStatus();

            if (result.success && result.data) {
                this.updateResourcesUI(result.data);
            }
        } catch (error) {
            console.error('Failed to load resources:', error);
            // 使用模拟数据
            this.loadMockResources();
        }
    }

    loadMockResources() {
        // 模拟资源数据
        const mockResources = {
            cpu: 45,
            memory: { used: 4.2, total: 8 },
            network: 125
        };

        this.updateResourcesUI(mockResources);
    }

    updateResourcesUI(resources) {
        // 更新CPU使用率
        const cpuUsage = document.getElementById('cpuUsage');
        const cpuBar = document.getElementById('cpuBar');
        if (cpuUsage && cpuBar) {
            cpuUsage.textContent = `${resources.cpu}%`;
            cpuBar.style.width = `${resources.cpu}%`;

            // 根据使用率设置颜色
            if (resources.cpu > 80) {
                cpuBar.style.background = '#ff4d4f';
            } else if (resources.cpu > 60) {
                cpuBar.style.background = '#faad14';
            } else {
                cpuBar.style.background = '#52c41a';
            }
        }

        // 更新内存使用
        const memoryUsage = document.getElementById('memoryUsage');
        const memoryBar = document.getElementById('memoryBar');
        if (memoryUsage && memoryBar && resources.memory) {
            const memoryPercent = Math.round((resources.memory.used / resources.memory.total) * 100);
            memoryUsage.textContent = `${resources.memory.used}/${resources.memory.total} GB`;
            memoryBar.style.width = `${memoryPercent}%`;

            if (memoryPercent > 80) {
                memoryBar.style.background = '#ff4d4f';
            } else if (memoryPercent > 60) {
                memoryBar.style.background = '#faad14';
            } else {
                memoryBar.style.background = '#52c41a';
            }
        }

        // 更新网络I/O
        const networkIO = document.getElementById('networkIO');
        const networkBar = document.getElementById('networkBar');
        if (networkIO && networkBar && resources.network) {
            networkIO.textContent = `${resources.network} MB/s`;
            const networkPercent = Math.min(resources.network / 2, 100); // 假设200MB/s为满载
            networkBar.style.width = `${networkPercent}%`;
        }
    }

    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        this.refreshTimer = setInterval(async () => {
            await this.loadTasksData();
            await this.loadResourcesData();
        }, this.refreshInterval);
    }

    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    // 公共方法
    filterTasks() {
        console.log('Filter tasks clicked');
        // 实现任务筛选逻辑
    }

    exportReport() {
        console.log('Export report clicked');
        // 实现报告导出逻辑
    }

    viewVerificationLog() {
        console.log('View verification log clicked');
        // 实现查看验证日志逻辑
    }

    viewProtocolDetails() {
        console.log('View protocol details clicked');
        // 实现查看协议详情逻辑
    }
}

// 页面加载完成后初始化任务监控面板
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.taskDashboard = new TaskDashboard();
        window.taskDashboard.init();
    });
} else {
    window.taskDashboard = new TaskDashboard();
    window.taskDashboard.init();
}

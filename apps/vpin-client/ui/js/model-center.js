/**
 * 模型中心页面模块
 * 处理模型管理、选择和上传
 */

class ModelCenter {
    constructor() {
        this.models = [];
        this.selectedModel = null;
    }

    async init() {
        console.log('ModelCenter initializing...');

        // 加载组件
        await this.loadComponents();

        // 设置事件监听器
        this.setupEventListeners();

        // 加载模型数据
        await this.loadModels();
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
            <a href="${item.page}" class="sidebar-item ${item.page === 'model-center.html' ? 'active' : ''}" data-page="${item.page}">
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
            case 'refresh-models':
                await this.refreshModels();
                break;
            case 'upload-model':
                await this.uploadModel();
                break;
            case 'select-model':
                await this.selectCurrentModel();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }

    async loadModels() {
        try {
            const result = await window.api.getModels();

            if (result.success && result.data) {
                this.models = result.data;
                this.renderModels();
            }
        } catch (error) {
            console.error('Failed to load models:', error);
            // 使用模拟数据
            this.loadMockModels();
        }
    }

    loadMockModels() {
        // 不再提供静态样例数据，实际使用中应从真实API获取
        this.models = [];
        this.renderModels();
    }

    renderModels() {
        const modelGrid = document.getElementById('modelGrid');
        if (!modelGrid) return;

        if (this.models.length === 0) {
            modelGrid.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 60px; color: #8c8c8c;">
                    <img src="assets/icons/folder.svg" alt="无模型" style="width: 64px; height: 64px; opacity: 0.3; margin-bottom: 20px;">
                    <p>暂无可用模型</p>
                    <button class="btn-primary tauri-action" data-action="upload-model" style="margin-top: 20px;">
                        上传模型
                    </button>
                </div>
            `;
            return;
        }

        modelGrid.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px;">
                ${this.models.map(model => this.renderModelCard(model)).join('')}
            </div>
        `;

        // 重新绑定事件监听器
        this.setupEventListeners();
    }

    renderModelCard(model) {
        const statusClass = model.status === 'ready' ? 'success' : 'failed';
        const statusText = model.status === 'ready' ? '就绪' : '不可用';

        return `
            <div class="model-card tech-card" style="border-radius: 12px; padding: 24px; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;"
                 onclick="window.modelCenter.showModelDetail(${model.id})">

                <div style="display: flex; align-items: center; margin-bottom: 16px;">
                    <div class="model-icon" style="width: 48px; height: 48px; border-radius: 8px; background: rgba(24, 144, 255, 0.1); display: flex; align-items: center; justify-content: center; margin-right: 16px;">
                        <img src="assets/icons/model-${model.model_type.toLowerCase()}.svg" alt="${model.model_type}" style="width: 32px; height: 32px;">
                    </div>
                    <div style="flex: 1;">
                        <h3 style="color: #262626; margin-bottom: 4px;">${model.name}</h3>
                        <div class="model-status">
                            <span class="status-indicator ${statusClass}">
                                <span class="status-dot" style="background: ${statusClass === 'success' ? '#52c41a' : '#ff4d4f'};"></span>
                                <span class="status-text" style="color: ${statusClass === 'success' ? '#52c41a' : '#ff4d4f'};">${statusText}</span>
                            </span>
                        </div>
                    </div>
                </div>

                <p style="color: #595959; margin-bottom: 16px; line-height: 1.5;">${model.description || '暂无描述'}</p>

                <div style="display: flex; gap: 16px; margin-bottom: 16px;">
                    <div class="model-stat">
                        <span style="color: #8c8c8c; font-size: 12px;">类型</span>
                        <span style="color: #262626; font-weight: 500;">${model.model_type}</span>
                    </div>
                    <div class="model-stat">
                        <span style="color: #8c8c8c; font-size: 12px;">大小</span>
                        <span style="color: #262626; font-weight: 500;">${model.file_size || '未知'}</span>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <button class="btn-secondary" style="padding: 8px 16px; font-size: 14px;" onclick="event.stopPropagation(); window.modelCenter.showModelDetail(${model.id})">
                        查看详情
                    </button>
                    <button class="btn-primary" style="padding: 8px 16px; font-size: 14px;" onclick="event.stopPropagation(); window.modelCenter.selectModel(${model.id})">
                        选择模型
                    </button>
                </div>
            </div>
        `;
    }

    async refreshModels() {
        console.log('Refreshing models...');

        try {
            const result = await window.api.refreshModels();

            if (result.success && result.data) {
                this.models = result.data;
                this.renderModels();

                // 显示成功提示
                this.showNotification('模型列表已更新', 'success');
            }
        } catch (error) {
            console.error('Failed to refresh models:', error);
            this.showNotification('刷新失败: ' + error.message, 'error');
        }
    }

    async uploadModel() {
        console.log('Uploading model...');

        try {
            // 这里将调用文件上传对话框和上传逻辑
            const result = await window.api.invoke('show_file_dialog', {
                filters: [{
                    name: 'Model Files',
                    extensions: ['pkl', 'h5', 'pt', 'onnx']
                }]
            });

            if (result.success && result.data) {
                // 上传选中的文件
                const uploadResult = await window.api.uploadData(result.data);

                if (uploadResult.success) {
                    this.showNotification('模型上传成功', 'success');
                    await this.refreshModels();
                }
            }
        } catch (error) {
            console.error('Failed to upload model:', error);
            this.showNotification('上传失败: ' + error.message, 'error');
        }
    }

    showModelDetail(modelId) {
        const model = this.models.find(m => m.id === modelId);
        if (!model) return;

        this.selectedModel = model;

        const detailPanel = document.getElementById('modelDetailPanel');
        const detailName = document.getElementById('detailModelName');
        const detailContent = document.getElementById('detailContent');

        if (detailPanel && detailName && detailContent) {
            detailName.textContent = model.name;

            detailContent.innerHTML = `
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; margin-bottom: 24px;">
                    <div>
                        <h4 style="color: #595959; margin-bottom: 8px;">模型类型</h4>
                        <p style="color: #262626;">${model.model_type}</p>
                    </div>
                    <div>
                        <h4 style="color: #595959; margin-bottom: 8px;">状态</h4>
                        <p style="color: #262626;">${model.status === 'ready' ? '就绪' : '不可用'}</p>
                    </div>
                    <div>
                        <h4 style="color: #595959; margin-bottom: 8px;">输入形状</h4>
                        <p style="color: #262626;">${model.input_shape || '未知'}</p>
                    </div>
                    <div>
                        <h4 style="color: #595959; margin-bottom: 8px;">输出类别</h4>
                        <p style="color: #262626;">${model.output_classes || '未知'}</p>
                    </div>
                    <div>
                        <h4 style="color: #595959; margin-bottom: 8px;">文件大小</h4>
                        <p style="color: #262626;">${model.file_size || '未知'}</p>
                    </div>
                    <div>
                        <h4 style="color: #595959; margin-bottom: 8px;">准确率</h4>
                        <p style="color: #262626;">${model.accuracy || '未知'}</p>
                    </div>
                </div>

                <div style="background: #f5f5f5; padding: 16px; border-radius: 8px;">
                    <h4 style="color: #595959; margin-bottom: 8px;">描述</h4>
                    <p style="color: #262626; line-height: 1.6;">${model.description || '暂无描述'}</p>
                </div>
            `;

            detailPanel.style.display = 'block';
        }
    }

    closeDetail() {
        const detailPanel = document.getElementById('modelDetailPanel');
        if (detailPanel) {
            detailPanel.style.display = 'none';
        }
        this.selectedModel = null;
    }

    async selectModel(modelId) {
        const model = this.models.find(m => m.id === modelId);
        if (!model) return;

        try {
            // 这里将调用选择模型的逻辑
            const result = await window.api.invoke('select_model', { model_id: model.id });

            if (result.success) {
                this.showNotification(`已选择模型: ${model.name}`, 'success');

                // 返回到工作台或创建任务
                setTimeout(() => {
                    window.location.href = 'index.html';
                }, 1500);
            }
        } catch (error) {
            console.error('Failed to select model:', error);
            this.showNotification('选择模型失败: ' + error.message, 'error');
        }
    }

    selectCurrentModel() {
        if (this.selectedModel) {
            this.selectModel(this.selectedModel.id);
        }
    }

    showNotification(message, type = 'info') {
        // 创建通知元素
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

// 页面加载完成后初始化模型中心
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.modelCenter = new ModelCenter();
        window.modelCenter.init();
    });
} else {
    window.modelCenter = new ModelCenter();
    window.modelCenter.init();
}
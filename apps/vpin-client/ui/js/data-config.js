/**
 * 数据配置页面模块
 * 处理数据上传和管理
 */

class DataConfig {
    constructor() {
        this.uploadedFiles = [];
        this.currentUpload = null;
    }

    async init() {
        console.log('DataConfig initializing...');

        // 加载组件
        await this.loadComponents();

        // 设置事件监听器
        this.setupEventListeners();

        // 加载已上传数据列表
        await this.loadUploadedData();
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
            <a href="${item.page}" class="sidebar-item ${item.page === 'data-config.html' ? 'active' : ''}" data-page="${item.page}">
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

        // 文件上传区域
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');

        if (uploadArea && fileInput) {
            uploadArea.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => this.handleFileSelect(e.target.files));

            // 拖拽上传
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.style.borderColor = '#1890ff';
                uploadArea.style.background = '#f0f8ff';
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.style.borderColor = '#d9d9d9';
                uploadArea.style.background = '#fafafa';
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.style.borderColor = '#d9d9d9';
                uploadArea.style.background = '#fafafa';

                if (e.dataTransfer.files.length > 0) {
                    this.handleFileSelect(e.dataTransfer.files);
                }
            });
        }
    }

    async handleAction(action) {
        console.log('Handling action:', action);

        switch(action) {
            case 'select-file':
                document.getElementById('fileInput').click();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }

    handleFileSelect(files) {
        if (!files || files.length === 0) return;

        const file = files[0];
        console.log('Selected file:', file.name, file.size, file.type);

        // 开始上传
        this.uploadFile(file);
    }

    async uploadFile(file) {
        try {
            // 显示上传进度
            const uploadProgress = document.getElementById('uploadProgress');
            const uploadFileName = document.getElementById('uploadFileName');
            const uploadPercent = document.getElementById('uploadPercent');
            const uploadProgressBar = document.getElementById('uploadProgressBar');

            if (uploadProgress) {
                uploadProgress.style.display = 'block';
                uploadFileName.textContent = file.name;
            }

            // 调用Tauri上传文件
            const result = await window.api.uploadData(file.path || file.name);

            if (result.success) {
                // 上传成功
                if (uploadProgressBar) {
                    uploadProgressBar.style.width = '100%';
                }
                if (uploadPercent) {
                    uploadPercent.textContent = '100%';
                }

                this.showNotification('文件上传成功', 'success');

                // 刷新数据列表
                setTimeout(async () => {
                    await this.loadUploadedData();

                    // 隐藏上传进度
                    if (uploadProgress) {
                        uploadProgress.style.display = 'none';
                    }
                }, 1000);
            } else {
                throw new Error(result.error || '上传失败');
            }
        } catch (error) {
            console.error('Upload failed:', error);
            this.showNotification('上传失败: ' + error.message, 'error');

            // 隐藏上传进度
            const uploadProgress = document.getElementById('uploadProgress');
            if (uploadProgress) {
                uploadProgress.style.display = 'none';
            }
        }
    }

    async loadUploadedData() {
        try {
            // 这里应该调用真实的数据列表API
            // 目前使用空列表
            this.uploadedFiles = [];

            this.renderDataList();
        } catch (error) {
            console.error('Failed to load uploaded data:', error);
        }
    }

    renderDataList() {
        const dataList = document.getElementById('uploadedDataList');
        if (!dataList) return;

        if (this.uploadedFiles.length === 0) {
            dataList.innerHTML = `
                <div class="empty-state" style="text-align: center; padding: 40px; color: #8c8c8c;">
                    <img src="assets/icons/database.svg" alt="无数据" style="width: 48px; height: 48px; opacity: 0.3; margin-bottom: 16px;">
                    <p>暂无已上传的数据</p>
                    <button class="btn-secondary" onclick="document.getElementById('fileInput').click()" style="margin-top: 16px;">
                        上传数据
                    </button>
                </div>
            `;
            return;
        }

        dataList.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 12px;">
                ${this.uploadedFiles.map(file => this.renderDataItem(file)).join('')}
            </div>
        `;
    }

    renderDataItem(file) {
        const fileIcon = this.getFileIcon(file.type);
        const fileSize = this.formatFileSize(file.size);
        const uploadDate = new Date(file.uploadTime).toLocaleString();

        return `
            <div class="data-item tech-card" style="background: white; border: 1px solid #e8e8e8; border-radius: 8px; padding: 16px;">
                <div style="display: flex; align-items: center; gap: 16px;">
                    <div class="file-icon" style="width: 40px; height: 40px; border-radius: 8px; background: rgba(24, 144, 255, 0.1); display: flex; align-items: center; justify-content: center;">
                        <img src="assets/icons/${fileIcon}" alt="文件" style="width: 24px; height: 24px;">
                    </div>

                    <div style="flex: 1;">
                        <div style="color: #262626; font-weight: 500; margin-bottom: 4px;">${file.name}</div>
                        <div style="color: #8c8c8c; font-size: 12px;">${fileSize} • ${uploadDate}</div>
                    </div>

                    <div style="display: flex; gap: 8px;">
                        <button class="btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="window.dataConfig.useFile('${file.id}')">
                            使用此数据
                        </button>
                        <button class="btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="window.dataConfig.deleteFile('${file.id}')">
                            删除
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    getFileIcon(fileType) {
        const iconMap = {
            'image/png': 'file-image.svg',
            'image/jpeg': 'file-image.svg',
            'image/jpg': 'file-image.svg',
            'text/csv': 'file-csv.svg',
            'application/x-npy': 'file-binary.svg',
            'default': 'file.svg'
        };

        return iconMap[fileType] || iconMap['default'];
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';

        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    useFile(fileId) {
        const file = this.uploadedFiles.find(f => f.id === fileId);
        if (file) {
            // 跳转到创建任务页面
            this.showNotification('已选择数据: ' + file.name, 'success');

            // 这里可以导航到任务创建页面
            setTimeout(() => {
                window.location.href = 'index.html';
            }, 1000);
        }
    }

    async deleteFile(fileId) {
        try {
            // 调用删除API
            const result = await window.api.invoke('delete_data', { file_id: fileId });

            if (result.success) {
                this.showNotification('文件删除成功', 'success');
                await this.loadUploadedData();
            }
        } catch (error) {
            console.error('Failed to delete file:', error);
            this.showNotification('删除失败: ' + error.message, 'error');
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

// 页面加载完成后初始化数据配置
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.dataConfig = new DataConfig();
        window.dataConfig.init();
    });
} else {
    window.dataConfig = new DataConfig();
    window.dataConfig.init();
}
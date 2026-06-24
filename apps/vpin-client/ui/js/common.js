/**
 * 统一的组件加载和配置
 * 确保所有页面都有完整的7个菜单项和正确的组件加载
 */

// 统一的侧边栏菜单项配置
const SIDEBAR_ITEMS = [
    { id: 'dashboard', icon: 'dashboard.svg', text: '工作台', page: 'index.html' },
    { id: 'tasks', icon: 'activity.svg', text: '任务监控', page: 'task-dashboard.html' },
    { id: 'models', icon: 'folder.svg', text: '模型中心', page: 'model-center.html' },
    { id: 'data', icon: 'database.svg', text: '数据配置', page: 'data-config.html' },
    { id: 'privacy', icon: 'dp.svg', text: '隐私预算', page: 'privacy-budget.html' },
    { id: 'security', icon: 'shield-check.svg', text: '安全中心', page: 'security-center.html' },
    { id: 'verification', icon: 'audit.svg', text: '验证报告', page: 'verification-report.html' }
];

// 统一的Header HTML生成函数
function getUnifiedHeaderHTML() {
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

// 统一的侧边栏HTML生成函数
function getUnifiedSidebarHTML(currentPage) {
    const items = SIDEBAR_ITEMS.map(item => `
        <a href="${item.page}" class="sidebar-item ${item.page === currentPage ? 'active' : ''}" data-page="${item.page}">
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

// 统一的组件加载函数
function loadUnifiedComponents() {
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';

    // 加载header组件
    const headerPlaceholder = document.getElementById('header-container');
    if (headerPlaceholder && !headerPlaceholder.innerHTML.trim()) {
        headerPlaceholder.innerHTML = getUnifiedHeaderHTML();
    }

    // 加载sidebar组件
    const sidebarPlaceholder = document.getElementById('sidebar-container');
    if (sidebarPlaceholder && !sidebarPlaceholder.innerHTML.trim()) {
        sidebarPlaceholder.innerHTML = getUnifiedSidebarHTML(currentPage);
    }
}

// 统一的连接状态更新函数
async function updateConnectionStatus() {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('connectionStatus');
    const serverUrlElement = document.getElementById('serverUrl');

    try {
        const healthResult = await window.api.healthCheck();
        const isConnected = healthResult.success && healthResult.data;

        if (statusDot && statusText) {
            if (isConnected) {
                statusDot.style.background = '#52c41a';
                statusDot.classList.remove('disconnected', 'connecting');
                statusDot.classList.add('connected');
                statusText.textContent = '已连接';
                statusText.style.color = '#52c41a';
            } else {
                statusDot.style.background = '#ff4d4f';
                statusDot.classList.remove('connected', 'connecting');
                statusDot.classList.add('disconnected');
                statusText.textContent = '连接失败';
                statusText.style.color = '#ff4d4f';
            }
        }

        if (serverUrlElement && isConnected) {
            const urlResult = await window.api.getServerUrl();
            if (urlResult.success) {
                serverUrlElement.textContent = urlResult.data;
            }
        }
    } catch (error) {
        console.error('Failed to update connection status:', error);
        if (statusDot && statusText) {
            statusDot.style.background = '#ff4d4f';
            statusText.textContent = '连接失败';
            statusText.style.color = '#ff4d4f';
        }
    }
}

// 统一的页面初始化函数
async function initializePage() {
    // 首先加载组件（如果还没有加载）
    loadUnifiedComponents();

    // 设置当前页面激活状态
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    document.querySelectorAll('.sidebar-item').forEach(item => {
        const itemPage = item.getAttribute('data-page');
        if (itemPage === currentPage) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // 更新连接状态
    await updateConnectionStatus();
}

// 在页面加载完成后执行初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    initializePage();
}
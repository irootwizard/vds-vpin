/**
 * Tauri API 模块
 * 统一处理与Rust后端的通信
 */

// Tauri API 命令包装
class TauriAPI {
    constructor() {
        this.isTauri = this.detectTauri();
        this.mockMode = !this.isTauri;
        console.log('Tauri API initialized. Tauri:', this.isTauri, 'Mock mode:', this.mockMode);
    }

    detectTauri() {
        try {
            return window.__TAURI__ !== undefined;
        } catch (e) {
            return false;
        }
    }

    async invoke(cmd, args = {}) {
        if (this.isTauri) {
            try {
                const result = await window.__TAURI__.core.invoke(cmd, args);
                return { success: true, data: result };
            } catch (error) {
                console.error(`Tauri command ${cmd} failed:`, error);
                return { success: false, error: error.message || error };
            }
        } else {
            // 开发模式下的模拟
            console.log(`Mock Tauri command: ${cmd}`, args);
            return this.mockResponse(cmd, args);
        }
    }

    // 模拟响应（开发模式下使用）
    mockResponse(cmd, args) {
        // 空数据响应，实际使用中应从真实API获取
        const mockData = {
            'health_check': { status: 'healthy', timestamp: new Date().toISOString() },
            'get_server_url': 'http://127.0.0.1:8000',
            'get_models': [],
            'get_tasks': [],
            'get_system_status': {
                cpu: 0,
                memory: { used: 0, total: 8.0 },
                network: 0
            },
            'get_security_status': {
                key_protection: true,
                tls_enabled: true,
                tee_available: false,
                protocol_version: 'v1.0',
                verification_module: 'ready'
            },
            'check_python_backend': true,
            'create_task': null,
            'refresh_models': [],
            'upload_data': null
        };

        return { success: true, data: mockData[cmd] || null };
    }

    // 基础命令
    async healthCheck() {
        return this.invoke('health_check');
    }

    async getServerUrl() {
        return this.invoke('get_server_url');
    }

    async setServerUrl(url) {
        return this.invoke('set_server_url', { url });
    }

    // 模型和任务管理
    async getModels() {
        return this.invoke('get_models');
    }

    async refreshModels() {
        return this.invoke('refresh_models');
    }

    async getTasks() {
        return this.invoke('get_tasks');
    }

    async createTask(taskData) {
        return this.invoke('create_task', taskData);
    }

    // 系统状态
    async getSystemStatus() {
        return this.invoke('get_system_status');
    }

    async getSecurityStatus() {
        return this.invoke('get_security_status');
    }

    // Python后端集成
    async checkPythonBackend() {
        return this.invoke('check_python_backend');
    }

    async pythonInference(modelId, dataPath) {
        return this.invoke('python_inference', {
            model_id: modelId,
            data_path: dataPath
        });
    }

    async checkModelAvailable(modelId) {
        return this.invoke('check_model_available', { model_id: modelId });
    }

    async getPythonModels() {
        return this.invoke('get_python_models');
    }

    // 数据上传
    async uploadData(filePath) {
        return this.invoke('upload_data', { file_path: filePath });
    }

    // 工具方法：检查连接状态
    async isHealthy() {
        const result = await this.healthCheck();
        return result.success && result.data && result.data.status === 'healthy';
    }

    // 工具方法：获取服务器信息
    async getServerInfo() {
        const [urlResult, healthResult] = await Promise.all([
            this.getServerUrl(),
            this.healthCheck()
        ]);

        return {
            url: urlResult.success ? urlResult.data : '未知',
            status: healthResult.success && healthResult.data ? healthResult.data.status : 'disconnected',
            isHealthy: healthResult.success && healthResult.data && healthResult.data.status === 'healthy'
        };
    }
}

// 导出全局API实例
window.api = new TauriAPI();

// 向后兼容：保持原有的调用方式
window.TauriAPI = TauriAPI;

/**
 * Netflix Checker 管理面板前端脚本
 */

// 全局变量
let socket = null;
let statusCheckInterval = null;

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查认证
    if (!checkAuth()) {
        return;
    }

    // 初始化WebSocket
    initWebSocket();

    // 加载初始数据
    loadConfig();
    updateStatus();
    loadResults();

    // 启动状态检查
    statusCheckInterval = setInterval(updateStatus, 5000);
});

// 认证相关
function checkAuth() {
    const token = localStorage.getItem('auth_token');
    if (!token) {
        console.log('没有找到token，跳转到登录页');
        window.location.href = '/';
        return false;
    }

    // 设置默认请求头
    window.authHeaders = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };

    console.log('认证token已加载');
    return true;
}

function logout() {
    localStorage.removeItem('auth_token');
    window.location.href = '/';
}

// 统一的API请求函数
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                ...window.authHeaders,
                ...(options.headers || {})
            }
        });

        // 如果是401，自动跳转到登录页
        if (response.status === 401) {
            console.log('认证失败，跳转到登录页');
            localStorage.removeItem('auth_token');
            window.location.href = '/';
            return null;
        }

        return response;
    } catch (error) {
        console.error('API请求错误:', error);
        throw error;
    }
}

// WebSocket连接
function initWebSocket() {
    const token = localStorage.getItem('auth_token');

    socket = io({
        transports: ['websocket'],
        auth: {
            token: token
        }
    });

    socket.on('connect', function() {
        console.log('WebSocket已连接');
        socket.emit('join_logs');
    });

    socket.on('logs_history', function(data) {
        displayLogs(data.logs);
    });

    socket.on('new_logs', function(data) {
        appendLogs(data.logs);
    });

    socket.on('disconnect', function() {
        console.log('WebSocket已断开');
    });

    socket.on('connect_error', function(error) {
        console.error('WebSocket连接错误:', error);
    });
}

// 日志显示
function displayLogs(logs) {
    const logContent = document.getElementById('logContent');
    logContent.innerHTML = '';

    logs.forEach(log => {
        appendLogLine(log);
    });

    // 滚动到底部
    const logContainer = document.getElementById('logContainer');
    logContainer.scrollTop = logContainer.scrollHeight;
}

function appendLogs(logs) {
    logs.forEach(log => {
        appendLogLine(log);
    });

    // 滚动到底部
    const logContainer = document.getElementById('logContainer');
    logContainer.scrollTop = logContainer.scrollHeight;
}

function appendLogLine(log) {
    const logContent = document.getElementById('logContent');
    const logLine = document.createElement('div');

    // 根据日志级别设置样式
    const levelClass = `log-${log.level.toLowerCase()}`;
    logLine.className = levelClass;

    // 格式化时间戳
    const timestamp = new Date(log.timestamp).toLocaleString('zh-CN');

    logLine.textContent = `[${timestamp}] [${log.level}] ${log.message}`;
    logContent.appendChild(logLine);

    // 限制日志行数
    const maxLines = 1000;
    while (logContent.children.length > maxLines) {
        logContent.removeChild(logContent.firstChild);
    }
}

// 配置管理
async function loadConfig() {
    try {
        const response = await apiRequest('/api/config');

        if (response && response.ok) {
            const data = await response.json();
            const configEditor = document.getElementById('configEditor');
            configEditor.value = jsyaml.dump(data.config);
        } else if (response) {
            showAlert('加载配置失败', 'danger');
        }
    } catch (error) {
        console.error('加载配置错误:', error);
        showAlert('加载配置出错', 'danger');
    }
}

async function saveConfig() {
    try {
        const configEditor = document.getElementById('configEditor');
        const configText = configEditor.value;

        // 解析YAML
        let config;
        try {
            config = jsyaml.load(configText);
        } catch (e) {
            showAlert('配置格式错误: ' + e.message, 'danger');
            return;
        }

        const response = await apiRequest('/api/config', {
            method: 'POST',
            body: JSON.stringify(config)
        });

        if (response && response.ok) {
            showAlert('配置已保存', 'success');
        } else if (response) {
            const data = await response.json();
            showAlert(data.error || '保存失败', 'danger');
        }
    } catch (error) {
        console.error('保存配置错误:', error);
        showAlert('保存配置出错', 'danger');
    }
}

// 调度器控制
async function startScheduler() {
    try {
        const response = await apiRequest('/api/scheduler/start', {
            method: 'POST'
        });

        if (response && response.ok) {
            showAlert('调度器已启动', 'success');
            updateStatus();
        } else if (response) {
            const data = await response.json();
            showAlert(data.error || '启动失败', 'danger');
        }
    } catch (error) {
        console.error('启动调度器错误:', error);
        showAlert('启动失败', 'danger');
    }
}

async function stopScheduler() {
    try {
        const response = await apiRequest('/api/scheduler/stop', {
            method: 'POST'
        });

        if (response && response.ok) {
            showAlert('调度器已停止', 'success');
            updateStatus();
        } else if (response) {
            const data = await response.json();
            showAlert(data.error || '停止失败', 'danger');
        }
    } catch (error) {
        console.error('停止调度器错误:', error);
        showAlert('停止失败', 'danger');
    }
}

async function runNow() {
    if (!confirm('确定要立即执行检测任务吗？')) {
        return;
    }

    try {
        const response = await apiRequest('/api/scheduler/run-now', {
            method: 'POST'
        });

        if (response && response.ok) {
            showAlert('任务已开始执行，请查看日志', 'info');
            // 切换到日志标签
            document.getElementById('logs-tab').click();
        } else if (response) {
            const data = await response.json();
            showAlert(data.error || '执行失败', 'danger');
        }
    } catch (error) {
        console.error('执行任务错误:', error);
        showAlert('执行失败', 'danger');
    }
}

// 状态更新
async function updateStatus() {
    try {
        const response = await apiRequest('/api/scheduler/status');

        if (response && response.ok) {
            const data = await response.json();
            const status = data.status;

            // 更新调度器状态
            const schedulerStatus = document.getElementById('schedulerStatus');
            if (status.running) {
                schedulerStatus.textContent = '运行中';
                schedulerStatus.className = 'badge bg-success';
            } else {
                schedulerStatus.textContent = '已停止';
                schedulerStatus.className = 'badge bg-secondary';
            }

            // 更新任务状态
            const taskStatus = document.getElementById('taskStatus');
            if (status.task_running) {
                taskStatus.textContent = '执行中';
                taskStatus.className = 'badge bg-warning';
            } else {
                taskStatus.textContent = '空闲';
                taskStatus.className = 'badge bg-info';
            }
        }
    } catch (error) {
        console.error('更新状态错误:', error);
    }
}

// 结果管理
async function loadResults() {
    try {
        const response = await apiRequest('/api/results');

        if (response && response.ok) {
            const data = await response.json();
            displayResults(data.results);
        } else if (response) {
            showAlert('加载结果失败', 'danger');
        }
    } catch (error) {
        console.error('加载结果错误:', error);
        showAlert('加载结果出错', 'danger');
    }
}

function displayResults(results) {
    const container = document.getElementById('resultsContainer');

    if (!results || !results.results) {
        container.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="fas fa-inbox fa-3x mb-3"></i>
                <p>暂无检测结果</p>
            </div>
        `;
        return;
    }

    const summary = results.summary;
    const items = results.results;

    // 构建HTML
    let html = `
        <div class="mb-3">
            <h5>检测概况</h5>
            <div class="row g-3">
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h3 class="text-primary">${summary.total}</h3>
                            <small class="text-muted">总计</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h3 class="text-success">${summary.full}</h3>
                            <small class="text-muted">完全解锁</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h3 class="text-warning">${summary.partial}</h3>
                            <small class="text-muted">部分解锁</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h3 class="text-danger">${summary.blocked + summary.failed}</h3>
                            <small class="text-muted">不可用</small>
                        </div>
                    </div>
                </div>
            </div>
            <p class="text-muted mt-2">
                <i class="fas fa-clock"></i> 
                检测时间: ${new Date(summary.check_time).toLocaleString('zh-CN')}
            </p>
        </div>
        
        <div class="table-responsive">
            <table class="table table-sm table-hover results-table">
                <thead>
                    <tr>
                        <th>代理名称</th>
                        <th>类型</th>
                        <th>服务器</th>
                        <th>状态</th>
                        <th>地区</th>
                        <th>详情</th>
                    </tr>
                </thead>
                <tbody>
    `;

    // 添加结果行
    items.forEach(item => {
        const statusClass = item.status;
        const statusText = {
            'full': '完全解锁',
            'partial': '部分解锁',
            'blocked': '被封锁',
            'failed': '失败'
        }[item.status] || '未知';

        html += `
            <tr>
                <td>${escapeHtml(item.name)}</td>
                <td>${item.type || '-'}</td>
                <td>${item.server || '-'}</td>
                <td><span class="proxy-status ${statusClass}">${statusText}</span></td>
                <td>${item.region || '-'}</td>
                <td>${escapeHtml(item.details)}</td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;
}

async function showResults() {
    await loadResults();
    document.getElementById('results-tab').click();
}

async function downloadResults() {
    try {
        const response = await apiRequest('/api/results/download');

        if (response && response.ok) {
            // 获取文件内容
            const blob = await response.blob();

            // 从响应头获取文件名，或使用默认名称
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'netflix_check_results.json';
            if (contentDisposition) {
                const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
                if (matches != null && matches[1]) {
                    filename = matches[1].replace(/['"]/g, '');
                }
            }

            // 创建下载链接
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();

            // 清理
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showAlert('下载成功', 'success');
        } else if (response) {
            showAlert('下载失败', 'danger');
        }
    } catch (error) {
        console.error('下载结果错误:', error);
        showAlert('下载出错', 'danger');
    }
}

async function loadVersionInfo() {
    try {
        const response = await apiRequest('/api/version');

        if (response && response.ok) {
            const data = await response.json();
            const versionDiv = document.getElementById('versionInfo');

            let html = '<p class="mb-1"><strong>应用版本:</strong> ' + data.version.app_version + '</p>';

            if (data.version.mihomo_info) {
                const lines = data.version.mihomo_info.split('\n');
                html += '<p class="mb-0"><strong>Mihomo信息:</strong></p>';
                html += '<pre class="mb-0 small" style="background: #f8f9fa; padding: 5px;">';
                lines.forEach(line => {
                    html += line + '\n';
                });
                html += '</pre>';
            }

            versionDiv.innerHTML = html;
        }
    } catch (error) {
        console.error('加载版本信息错误:', error);
    }
}

// 辅助函数
function showAlert(message, type = 'info') {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3" 
             style="z-index: 9999;">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', alertHtml);

    // 3秒后自动关闭
    setTimeout(() => {
        const alert = document.querySelector('.alert');
        if (alert) {
            alert.remove();
        }
    }, 3000);
}

function clearLogs() {
    if (confirm('确定要清空日志吗？')) {
        document.getElementById('logContent').innerHTML = '';
        showAlert('日志已清空', 'success');
    }
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// 添加js-yaml库的引用
if (!window.jsyaml) {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js';
    document.head.appendChild(script);
}
# Netflix Unblock Checker
一个用于检测代理服务器Netflix解锁状态的Web管理面板，提供友好的用户界面和完整的管理功能。

---

## ✨ 功能特性

- 🌐 **Web管理面板**：友好的用户界面，支持实时日志查看
- 🔐 **安全认证**：基于密钥的登录系统，JWT令牌认证
- ⏰ **定时任务**：支持Cron表达式配置的自动检测
- 📊 **结果展示**：直观的检测结果展示和统计
- 🔧 **在线配置**：支持在线编辑和保存配置文件

---

## 🚀 快速开始

### 1. 下载配置文件

```bash
wget https://raw.githubusercontent.com/chinazi/netflix-check/refs/heads/main/config/config.yaml
```

### 2. 修改配置文件

根据您的需求编辑 config.yaml 文件，配置代理服务器信息和检测参数。

### 3. Docker 部署
 桥接模式
```bash
docker run -d \
  --name netflix-checker \
  -p 8080:8080 \
  -v $(pwd)/config.yaml:/app/config/config.yaml \
  tomcatvip/netflix-checker:latest
```
 host模式
```bash
docker run -d \
  --name netflix-checker \
  --network host \
  -v $(pwd)/config.yaml:/app/config/config.yaml \
  tomcatvip/netflix-checker:latest
```

## 📋 使用说明

- **访问面板**：部署成功后，访问 `http://your-server-ip或域名:8080`
- **订阅链接**：`http://你的ip或域名/api/subscription?key=配置文件中配置的subscription key`







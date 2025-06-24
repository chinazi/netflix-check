# Netflix Unblock Checker

一个用于检测代理服务器Netflix解锁状态的Web管理面板。

## 功能特性

- 🌐 **Web管理面板** - 友好的用户界面，支持实时日志查看
- 🔐 **安全认证** - 基于密钥的登录系统，JWT令牌认证
- ⏰ **定时任务** - 支持Cron表达式配置的自动检测
- 📊 **结果展示** - 直观的检测结果展示和统计
- 🔧 **在线配置** - 支持在线编辑和保存配置文件
- 📝 **实时日志** - WebSocket推送的实时日志输出
- 🐳 **Docker支持** - 提供完整的Docker部署方案

  docker run -d \
  --name netflix-checker \
  -p 8080:8080 \
  -v ./config:/app/config \
  -v ./logs:/app/logs \
  -v ./results:/app/results \
  tomcatvip/netflix-checker:latest


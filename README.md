# 带宽测试器 (Bandwidth Tester)

高性能多线程带宽测试工具 - 支持Docker多架构部署和生产级安全配置

[![Docker Hub](https://img.shields.io/docker/pulls/goushuai888/bandwidth-tester)](https://hub.docker.com/r/goushuai888/bandwidth-tester)
[![GitHub](https://img.shields.io/github/stars/goushuai888/bandwidth-tester)](https://github.com/goushuai888/bandwidth-tester)

## ⚡ 超快速启动（一行命令）

```bash
# 拉取镜像
docker pull goushuai888/bandwidth-tester:latest

# 启动容器
docker run -d --name bandwidth-tester --restart always goushuai888/bandwidth-tester:latest

# 查看日志
docker logs -f bandwidth-tester
```

## 📦 镜像地址

- **Docker Hub** (推荐): `goushuai888/bandwidth-tester:latest`
- **GitHub Container Registry**: `ghcr.io/goushuai888/bandwidth-tester:latest`

支持架构: `linux/amd64`, `linux/arm64`

## 🎯 功能特性

- ✅ 多线程并发下载（线程安全）
- ✅ 自定义流量目标
- ✅ Docker 多架构支持
- ✅ 生产级安全配置（CIS 合规）
- ✅ 资源限制和健康检查
- ✅ 优雅退出机制

## 📖 详细使用

### 直接使用已发布的镜像 (最快)

```bash
# 从Docker Hub拉取并运行
docker run -d \
  --name bandwidth-tester \
  -e THREAD_COUNT=5 \
  -e GOAL_GB=0 \
  goushuai888/bandwidth-tester:latest

# 查看日志
docker logs -f bandwidth-tester
```

### 使用Docker Compose (推荐)

1. 克隆或下载项目到本地
2. 修改配置(可选):
   编辑 `docker-compose.yml` 文件中的环境变量
3. 启动服务:
   ```bash
   docker-compose up -d
   ```
4. 查看日志:
   ```bash
   docker-compose logs -f
   ```
5. 停止服务:
   ```bash
   docker-compose down
   ```

### 使用Docker命令

1. 构建镜像:
   ```bash
   docker build -t bandwidth-tester:latest .
   ```

2. 运行容器:
   ```bash
   docker run -d \
     --name bandwidth-tester \
     -e THREAD_COUNT=5 \
     -e GOAL_GB=0 \
     -e URL_LIST="https://example.com/file1.gif,https://example.com/file2.gif" \
     bandwidth-tester:latest
   ```

3. 查看日志:
   ```bash
   docker logs -f bandwidth-tester
   ```

4. 停止容器:
   ```bash
   docker stop bandwidth-tester
   ```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| `THREAD_COUNT` | 并发下载线程数 | 5 | 10 |
| `GOAL_GB` | 目标流量(GB),0表示无限制 | 0 | 10 |
| `URL_LIST` | 下载URL列表,用逗号分隔 | 默认URL | url1,url2,url3 |

### docker-compose.yml示例

```yaml
version: '3.8'

services:
  bandwidth-tester:
    build: .
    image: bandwidth-tester:latest
    container_name: bandwidth-tester
    restart: unless-stopped
    environment:
      - THREAD_COUNT=10
      - GOAL_GB=5
      - URL_LIST=https://example.com/file1.gif,https://example.com/file2.gif
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 512M
```

## 直接运行(不使用Docker)

1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   ```

2. 运行脚本:
   ```bash
   # 使用默认配置
   python bandwidth_tester.py

   # 使用环境变量配置
   export THREAD_COUNT=10
   export GOAL_GB=5
   export URL_LIST="url1,url2"
   python bandwidth_tester.py
   ```

## 注意事项

1. 请确保下载的URL是合法且有权访问的资源
2. 建议根据网络带宽和服务器性能调整线程数
3. 容器资源限制可根据实际需求调整
4. 使用Ctrl+C或docker stop可以优雅退出程序

## 系统要求

- Docker 20.10+
- Docker Compose 1.29+ (可选)
- Python 3.11+ (非Docker环境)

## 许可证

本项目仅供学习和测试使用,请遵守相关法律法规。

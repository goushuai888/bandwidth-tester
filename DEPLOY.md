# 带宽测试器 - 快速部署

## 拉取镜像

```bash
docker pull goushuai888/bandwidth-tester:latest
```

## 启动命令

### 基础启动
```bash
docker run -d \
  --name bandwidth-tester \
  --restart always \
  goushuai888/bandwidth-tester:latest
```

### 自定义配置
```bash
docker run -d \
  --name bandwidth-tester \
  --restart always \
  -e THREAD_COUNT=10 \
  -e GOAL_GB=0 \
  goushuai888/bandwidth-tester:latest
```

## 配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| THREAD_COUNT | 线程数 | 5 |
| GOAL_GB | 目标流量(GB),0=无限制 | 0 |

## 管理命令

```bash
# 查看日志
docker logs -f bandwidth-tester

# 停止容器
docker stop bandwidth-tester

# 启动容器
docker start bandwidth-tester

# 删除容器
docker rm -f bandwidth-tester

# 更新到最新版本
docker rm -f bandwidth-tester && \
docker pull goushuai888/bandwidth-tester:latest && \
docker run -d --name bandwidth-tester --restart always goushuai888/bandwidth-tester:latest
```

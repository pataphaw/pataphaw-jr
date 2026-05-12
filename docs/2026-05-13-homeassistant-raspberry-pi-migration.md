# Home Assistant 树莓派迁移记录

- 日期：2026-05-13
- 目标主机：Raspberry Pi，固定局域网 IP
- 部署方式：Home Assistant Container on Docker
- 目标配置目录：`<remote-ha-root>/config`
- 目标访问地址：`http://<raspberry-pi-ip>:8123`

## 背景

迁移前，Home Assistant 运行在本机 Docker 中：

- 容器名：`homeassistant`
- 镜像：`ghcr.io/home-assistant/home-assistant:stable`
- Home Assistant 版本：以源环境实际版本为准
- 本机配置目录：`<local-ha-config-dir>`
- 本机端口：`localhost:8123`
- 配置体积：以实际环境为准；迁移时可排除 `home-assistant.log*`

迁移目标是把 Home Assistant 从本机 Docker 移到局域网内固定 IP 的树莓派，同时保留原配置、账号、设备、集成、实体和现有 API token。

## 迁移过程

### 1. 建立 SSH 密钥登录

将本机 SSH 公钥写入树莓派用户的 `authorized_keys`，之后通过密钥登录：

```bash
ssh <ssh-user>@<raspberry-pi-ip>
```

树莓派环境确认：

- OS：Debian / Raspberry Pi OS，按实际环境确认
- 架构：`aarch64`
- 主要网络接口：按实际环境确认，例如 `wlan0` 或 `eth0`
- 固定 IP：`<raspberry-pi-ip>`

### 2. 安装 Docker

树莓派初始未安装 Docker，使用 Debian 仓库安装：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker <ssh-user>
sudo systemctl enable --now docker
```

安装后确认版本：

- Docker：以实际安装版本为准
- Docker Compose：以实际安装版本为准

### 3. 准备目标目录和 Compose 配置

目标目录：

```bash
sudo mkdir -p <remote-ha-root>/config
sudo chown -R <ssh-user>:<ssh-user> <remote-ha-root>
```

Compose 文件：`<remote-ha-root>/docker-compose.yml`

```yaml
services:
  homeassistant:
    container_name: homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    restart: unless-stopped
    network_mode: host
    privileged: true
    environment:
      TZ: Asia/Shanghai
    volumes:
      - <remote-ha-root>/config:/config
      - /etc/localtime:/etc/localtime:ro
      - /run/dbus:/run/dbus:ro
```

使用 `network_mode: host` 是为了更接近 Home Assistant 官方容器部署建议，并让局域网设备发现、广播、多播类能力尽量保留。

### 4. 同步配置

先在本机 Home Assistant 仍运行时做预同步：

```bash
rsync -a --delete \
  --exclude '.ha_run.lock' \
  --exclude 'home-assistant.log*' \
  <local-ha-config-dir>/ \
  <ssh-user>@<raspberry-pi-ip>:<remote-ha-root>/config/
```

随后先在树莓派拉取镜像，减少最终停机时间：

```bash
cd <remote-ha-root>
docker-compose pull homeassistant
```

镜像大小以实际拉取结果为准，树莓派磁盘需要预留足够空间。

进入切换窗口后，停止本机容器，再做最终同步：

```bash
docker stop homeassistant

rsync -a --delete \
  --exclude '.ha_run.lock' \
  --exclude 'home-assistant.log*' \
  <local-ha-config-dir>/ \
  <ssh-user>@<raspberry-pi-ip>:<remote-ha-root>/config/
```

迁移时排除了运行锁和日志文件。`home-assistant_v2.db`、`.storage`、`secrets.yaml`、`custom_components` 等配置和状态数据已保留。

### 5. 启动树莓派 Home Assistant

```bash
cd <remote-ha-root>
docker-compose up -d
```

启动后修改 `<remote-ha-root>/config/configuration.yaml` 中的 URL：

```yaml
homeassistant:
  external_url: http://<raspberry-pi-ip>:8123
  internal_url: http://<raspberry-pi-ip>:8123
```

修改前的配置备份为：

```text
<remote-ha-root>/config/configuration.yaml.before-pi-url
```

修改后重启远端容器：

```bash
cd <remote-ha-root>
docker-compose restart homeassistant
```

### 6. 切换 pataphaw-jr 配置

项目内 `config.yaml` 的 Home Assistant 地址从本机切到树莓派：

```yaml
homeassistant:
  base_url: "http://<raspberry-pi-ip>:8123"
  trust_env: true
```

同时调整了项目中 Home Assistant HTTP client 的网络行为：默认不信任环境代理，避免局域网 Home Assistant 请求被外部代理接管；但允许通过 `homeassistant.trust_env` 显式开启环境网络设置。当前部署需要开启该选项，否则 Python/httpx 直连树莓派地址会失败。

涉及代码：

- `src/router/ha_router.py`
- `src/services/homeassistant.py`
- `src/services/ac_controller.py`

## 验证结果

### Home Assistant API

远端 API 正常：

```text
{"message":"API running."}
```

关键实体查询正常：

```text
<entity_id> <state>
```

`pataphaw-jr` 的 `HomeAssistantClient` 使用新配置后也能查询该实体。

### 容器状态

树莓派上 Home Assistant 容器状态：

```bash
cd <remote-ha-root>
docker-compose ps
```

关键参数：

- `Restart=unless-stopped`
- `Network=host`
- 镜像：`ghcr.io/home-assistant/home-assistant:stable`

本机原容器已停止，但没有删除：

```bash
docker ps -a --filter name=homeassistant
```

### 登录账号

迁移后保留了原 Home Assistant 用户。后续若忘记密码，可在树莓派上使用 Home Assistant 官方 auth 脚本重置：

```bash
docker exec homeassistant \
  python -m homeassistant --script auth -c /config list

docker exec homeassistant \
  python -m homeassistant --script auth -c /config change_password <username> <new_password>

docker exec homeassistant \
  python -m homeassistant --script auth -c /config validate <username> <new_password>
```

本文档不记录任何可登录密码。

## 迁移中遇到的问题

### SSH / rsync 间歇超时

最终同步阶段出现过 SSH 连接超时：

```text
ssh: connect to host <raspberry-pi-ip> port 22: Operation timed out
rsync: error: unexpected end of file
```

后续确认树莓派未重启，系统负载和磁盘正常。由于远端配置体积与本机排除日志后的体积一致，且 Home Assistant 成功启动，判断同步内容已足够完整。

### Python/httpx 直连失败

迁移后，`curl` 和 `nc` 能访问 `http://<raspberry-pi-ip>:8123`，但 Python socket/httpx 在禁用系统网络设置时出现：

```text
No route to host
```

处理方式是把 Home Assistant client 的网络行为做成配置项：

- 默认值：`trust_env: false`，保护常规局域网部署不走外部代理。
- 当前部署：`trust_env: true`，让 Python/httpx 使用当前机器可达树莓派所需的环境网络设置。

处理后 `pataphaw-jr` 可正常访问树莓派 Home Assistant。

### 部分设备不可达

远端 Home Assistant 日志中出现部分局域网设备发现失败：

```text
Unable to discover the device <device-ip>
```

树莓派本身也无法 ping 通对应设备 IP。关键实体已能正常更新，因此该问题更像是设备 IP、局域网可达性或设备当前在线状态问题，不是 Home Assistant 容器启动失败。

## 当前状态

当前 Home Assistant 入口：

```text
http://<raspberry-pi-ip>:8123
```

树莓派运维入口：

```bash
ssh <ssh-user>@<raspberry-pi-ip>
cd <remote-ha-root>
docker-compose ps
docker-compose logs -f homeassistant
```

本机原配置仍在：

```text
<local-ha-config-dir>
```

## 回滚方式

如果需要临时切回本机 Home Assistant：

```bash
# 停止树莓派 Home Assistant
ssh <ssh-user>@<raspberry-pi-ip>
cd <remote-ha-root>
docker-compose stop

# 回到本机启动原容器
docker start homeassistant
```

如果 `pataphaw-jr` 也要同步切回本机，需要将 `config.yaml` 的 `homeassistant.base_url` 改回：

```yaml
homeassistant:
  base_url: "http://localhost:8123"
```

# 01 · 部署工作日志

## 今天这件事，从哪里开始

今天的目标很直白：把电脑里的项目放到云上，让别人也能打开，自己关机休息之后网站还能继续运行。

真正操作起来，难点不只在代码。第一次看到黑色登录窗口，不知道该输入什么；安装刷出一大段英文，也很难判断它是在工作、已经完成，还是出了问题。后面网站终于能打开，上传却又报错——这次过程也提醒我们，“页面出来了”和“功能能用了”之间，还有几步需要亲手验证。

这份日志把这些容易卡住的地方也留下来。以后自己回来接着做，或者队友第一次接手，都不用再对着同样的输出猜一遍。

## 一、目标与环境

将 GitHub 上的前后端项目部署到云服务器，让浏览器可以访问，保存的检查不依赖个人电脑持续开机。

| 项目 | 本次环境或结果 |
| --- | --- |
| 云资源 | Flexus L，2 vCPU、2 GiB 内存、40 GiB 系统盘 |
| 系统 | Ubuntu 24.04，x86-64 |
| 操作入口 | 华为云控制台 VNC |
| 后端 | Python 3.12、FastAPI、Uvicorn、SQLite |
| 前端 | Node.js 22、pnpm 10、Vite 构建 |
| 对外入口 | Nginx，HTTP 80 |
| 进程管理 | systemd，专用用户运行后端 |
| 数据目录 | `/var/lib/ai-oralscan`，与源码分开 |

版本是当天观察值，不是永久要求：Git 2.43.0、Nginx 1.24.0、Python 3.12.3、Node 22.23.5、npm 10.9.9、pnpm 10.34.9。后续应以项目锁文件和兼容性要求为准。

## 二、登录与基础环境

实例创建后显示“运行中”。首次登录前设置系统密码；当时经过重置及恢复运行后，通过远程登录进入 VNC。VNC 黑色窗口显示 `login:` 是正常的 Linux 文本登录界面。输入系统用户名后，再输入密码；密码输入通常不显示字符。

控制台中的 CloudShell 入口曾提示 TCP 22 未放通，因此本次使用 VNC。VNC 通过云控制台访问控制台界面，不能据此认定公网 SSH 已可用。

安装了 Git、Nginx、Python 虚拟环境和开发支持等依赖。以下是对应的新机复现示例，并非原始命令逐字录屏：

```bash
apt update
apt install -y git nginx python3-venv python3-dev curl ca-certificates
git --version
nginx -v
python3 --version
```

管理员安装命令在 root 会话执行；普通管理员账号需按权限加 `sudo`。不要把终端提示符 `root@主机:~#` 一起复制进去。

安装日志中的 `Setting up`、`Processing triggers` 是正常进度；`Service restarts being deferred` 表示部分服务重启被延后，不直接表示安装失败。一次版本检查曾因重复粘贴，变成 `python3 --versiongit`；单独执行 `python3 --version` 后正常。

## 三、下载源码

实际使用浅克隆，仅下载 main 分支近期快照：

```bash
git clone --depth 1 --branch main YOUR_GITHUB_REPOSITORY_URL /opt/ai-oralscan
ls -la /opt/ai-oralscan
```

把占位符替换为项目 HTTPS 克隆地址。目标目录已存在时，先检查内容，不要为了重新克隆直接删除。

`Receiving objects: 100%`、`Resolving deltas: 100%` 和 `done` 表示这一步传输完成。随后列目录确认存在 backend、frontend 和模型文件。下载代码不会自动启动网站。

## 四、安装并验证后端

对应复现命令：

```bash
cd /opt/ai-oralscan/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

虚拟环境把项目依赖与系统 Python 分开。安装输出出现 `Successfully installed` 后，临时启动：

```bash
cd /opt/ai-oralscan/backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

观察到 `Application startup complete` 和 `Uvicorn running`。此时命令占据终端是正常现象；这是前台服务，不能作为长期托管方式。验证后按 Ctrl+C 正常停止，再交给 systemd。

## 五、配置后台常驻与数据目录

建立专用系统用户，避免应用长期用 root 运行：

```bash
id oralscan >/dev/null 2>&1 || useradd --system --home /var/lib/ai-oralscan --shell /usr/sbin/nologin oralscan
```

将 [systemd 模板](templates/ai-oralscan.service) 写入 `/etc/systemd/system/ai-oralscan.service`。其中：

- `WorkingDirectory` 指向后端源码。
- `ExecStart` 使用该项目虚拟环境的 Python。
- `StateDirectory` 由 systemd 管理应用状态目录。
- 三个 `Environment` 配置让数据库、上传文件和模型目录离开 Git 源码目录。
- `Restart=on-failure` 让异常退出后重试；不表示所有业务故障都能自动修好。

然后执行：

```bash
systemctl daemon-reload
systemctl enable --now ai-oralscan
systemctl status ai-oralscan --no-pager -l
```

当时观察到 `enabled` 和 `active (running)`，后端空闲内存约 104 MiB。前者表示开机启动，后者表示进程当时正在运行；仍需请求接口验证业务入口。

## 六、安装 Node.js 与构建前端

先从 NodeSource 下载 Node 22 软件源配置脚本：

```bash
curl -fSL --connect-timeout 15 --max-time 120 https://deb.nodesource.com/setup_22.x -o /tmp/oralscan-node22.sh
```

下载完成后检查脚本来源与内容，再单独运行；不要在新行以 `&& bash` 开头：

```bash
less /tmp/oralscan-node22.sh
bash /tmp/oralscan-node22.sh
apt install -y nodejs
node -v
npm -v
npm install -g pnpm@10
pnpm -C /opt/ai-oralscan/frontend install --frozen-lockfile
pnpm -C /opt/ai-oralscan/frontend build
```

`Repository configured successfully` 只表示软件源配置完成，随后还需安装 nodejs。`--frozen-lockfile` 用锁文件约束依赖；锁文件不匹配时应核查仓库，不直接删锁文件绕过。

前端构建成功，生成 `frontend/dist`。黄色的“部分文件超过 500 kB”是体积优化提示；当天显示 `built`，不属于构建失败。Node.js 在这里主要用于构建，发布后的静态文件由 Nginx 提供。

## 七、Nginx 连接前后端

将 [Nginx 模板](templates/ai-oralscan.nginx.conf) 的 `YOUR_SERVER_IP` 替换为自己的地址，保存到 `/etc/nginx/sites-available/ai-oralscan`。

```bash
ln -s /etc/nginx/sites-available/ai-oralscan /etc/nginx/sites-enabled/ai-oralscan
nginx -t
systemctl reload nginx
```

创建链接是首次配置步骤；如果提示文件已存在，先检查现有链接，不要盲目重复创建。必须等语法检查成功再重载。

配置作用：`/` 返回前端文件，`/api/` 代理到本机后端。`proxy_pass` 的地址末尾不加 `/`，保留 API 请求路径。`try_files` 支持单页应用子页面刷新。上传请求体上限设为 26m，给应用 25 MiB 文件限制留出 multipart 包装空间；应用仍进行自己的校验。

在服务器内进行验证，先替换占位符：

```bash
curl -I -H 'Host: YOUR_SERVER_IP' http://127.0.0.1/
curl -i --max-time 10 -H 'Host: YOUR_SERVER_IP' http://127.0.0.1/api/health
```

两个请求均返回 200，健康接口返回 `status: ok`。这是服务器本机验证，尚不能单独证明外网可达。

## 八、安全组与公网访问

在云控制台给实例所绑定的安全组添加入方向规则：

| 设置 | 值 |
| --- | --- |
| 策略 / 类型 | 允许 / IPv4 |
| 协议 / 端口 | TCP / 80 |
| 源地址 | `0.0.0.0/0` |

用户明确选择允许任何来源访问演示网页。这只放通 TCP 80，不代表放通所有端口。之后浏览器成功通过 `http://YOUR_SERVER_IP/` 打开工作台。

## 九、HTTP 上传问题与修复记录

上传时出现 `crypto.randomUUID is not a function`。该浏览器 API 需要安全上下文；公网普通 HTTP 不满足要求。此错误出现在前端，不能据此推断数据库损坏。[MDN 说明](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)

当天在服务器上备份并修改 `frontend/src/features/acquisition/Acquisition.tsx`：把 UUID 生成替换为使用 `crypto.getRandomValues` 的兼容实现，再重新构建前端并强制刷新浏览器。备份文件为 `/opt/ai-oralscan/Acquisition.tsx.before-http-fix`。

修复思路：生成 16 字节随机数，设置 UUID v4 的版本位和变体位，再格式化字符串。不要使用简单时间戳或 `Math.random()` 代替这段实现。该补丁解决当时的 ID 生成问题，不会让 HTTP 自动获得摄像头等安全上下文能力。

用户随后确认上传保存和历史记录测试正常。当天服务器临时补丁是否已经合入 GitHub，仍需通过提交及差异核对；本日志提交不代替功能补丁同步。未来更新前必须检查服务器工作区，不能用强制覆盖丢弃修改。

## 十、验收边界与待办

| 项目 | 当天证据与结论 |
| --- | --- |
| 后端常驻 | systemd 显示 active、enabled |
| 前端构建 | TypeScript 与 Vite 构建完成 |
| Nginx 转发 | 首页与健康接口本机请求均为 200 |
| 外网网页 | 用户浏览器打开公网 HTTP 地址 |
| 上传与历史 | 用户手动验证保存及查看成功 |
| 独立网络访问 | 建议手机关闭 Wi-Fi 测试；未收录已完成证据 |
| HTTPS / 摄像头 | HTTPS 尚未配置，摄像头不算验收通过 |
| YOLO / AI 助理 | 不因页面上线就认定实际模型服务已部署 |
| 备份恢复 / 多用户隔离 | 未完成独立验收 |

次日优先事项：核对并提交服务器临时修复、配置 HTTPS、评估登录与权限、建立备份并演练恢复、逐项验证模型功能。

## 收工前，留给明天的自己

今天最实在的进展，是项目从 GitHub 的源码变成了浏览器里能打开的网页，上传的演示记录也能在历史页面找到。这些都有操作结果支撑，值得记下来。

也有几条很朴素的经验：终端不动，不一定是卡住；黄色文字，不一定是失败；网站打不开，也不一定是数据库坏了。这次分别遇到了命令已完成、构建体积提示和 HTTP/HTTPS 访问问题。先看最后几行，再分层检查，比着急重装更容易找出原因。

明天不用从头再来。代码、服务配置和数据已经有各自的位置。先处理服务器临时修复与仓库同步，再继续补 HTTPS 和功能验证，把今天跑通的东西稳稳接住。

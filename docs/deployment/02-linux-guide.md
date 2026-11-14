# 02 · Linux 命令教程

## 1. 先分清在哪台机器执行

云控制台 VNC 黑色终端里的命令在云服务器执行；Windows PowerShell 默认操作自己的电脑。本文代码块均为 Ubuntu Bash 命令，不要直接当成 PowerShell 命令运行。

提示符示例：`root@server:/opt/ai-oralscan/backend#`。它依次表示用户、主机、当前目录。`#` 通常代表 root；提示符不属于命令。密码输入不回显是正常行为。

VNC 无法直接 Ctrl+V 时，用顶部“复制粘贴”或“复制命令输入”。一次粘贴一次命令；看到新提示符再输入下一条。中英文全角符号不同，使用英文半角 `-`、空格、引号。

## 2. 看目录、读文件

| 命令 | 用途 | 本项目例子 |
| --- | --- | --- |
| `pwd` | 显示当前所在目录 | 确认当前是在 backend 还是 frontend |
| `ls -la` | 列文件，包括隐藏文件和权限 | `ls -la /opt/ai-oralscan` |
| `cd 路径` | 切换工作目录 | `cd /opt/ai-oralscan/backend` |
| `cd ..` | 回到上一级 | backend 回到项目目录 |
| `cat 文件` | 打印整个文本文件 | `cat /etc/systemd/system/ai-oralscan.service` |
| `less 文件` | 分页阅读，按 q 退出 | `less /var/log/nginx/error.log` |
| `tail -n 50 文件` | 看最后 50 行 | `tail -n 50 /var/log/nginx/error.log` |
| `mkdir -p 目录` | 创建目录，含缺失的父目录 | 创建应用专用备份目录 |
| `cp 源 目标` | 复制文件 | 修改配置前复制一份备份 |

`/opt/...` 是从根目录开始的绝对路径；`.venv/...` 是从当前目录开始的相对路径。`.git` 保存 Git 信息；`.venv` 保存 Python 环境，均不应当作垃圾目录随意删除。

## 3. 常见符号与快捷键

| 写法 | 含义 |
| --- | --- |
| `命令A && 命令B` | A 成功后才执行 B |
| `命令A || 命令B` | A 失败后执行 B |
| `>` | 将输出写入文件；会覆盖已有内容 |
| `>>` | 追加到文件尾部 |
| `2>&1` | 把错误输出合并到标准输出 |
| `/dev/null` | 丢弃输出的特殊设备 |
| `Ctrl+C` | 中断当前前台程序 |
| `Ctrl+Shift+R` | 浏览器强制刷新，不是 Linux 终端命令 |
| `exit` | 退出当前终端登录，不是关闭云服务器 |

不要在新提示符后单独输入 `&& 命令`。不要在软件包安装途中反复按 Ctrl+C；先观察是否仍有进度。前台运行 Uvicorn 时没有新提示符是正常现象。

写多行配置时可用 heredoc，下面只是写入临时练习文件：

```bash
cat > /tmp/oralscan-learning-example.txt <<'EOF'
这是第一行
$uri 会被原样保留
EOF
cat /tmp/oralscan-learning-example.txt
```

结束标记 `EOF` 必须单独一行。`<<'EOF'` 中的引号防止 `$uri` 这样的 Nginx 变量被 Bash 提前替换。中间出现 `>` 提示符，通常是在等待剩余内容。

## 4. 安装、环境与构建

| 命令 | 实际作用 |
| --- | --- |
| `apt update` | 刷新可安装软件清单，不等于升级所有软件 |
| `apt install 软件名` | 安装指定系统软件 |
| `python3 -m venv .venv` | 在当前目录创建 Python 虚拟环境 |
| `.venv/bin/python -m pip install -r requirements.txt` | 给该虚拟环境安装后端依赖 |
| `pnpm install --frozen-lockfile` | 按锁文件安装前端依赖 |
| `pnpm build` | 把前端源码编译为发布文件 |

在 frontend 目录外操作可用 `pnpm -C /opt/ai-oralscan/frontend build`。安装依赖、编译、启动服务是三个不同步骤；Git clone 只完成源码下载。

## 5. 管理服务

```bash
systemctl is-active ai-oralscan
systemctl is-enabled ai-oralscan
systemctl status ai-oralscan --no-pager -l
journalctl -u ai-oralscan -n 80 --no-pager
```

以上用于检查；下面会改变服务状态，应在对应场景使用：

| 命令 | 使用场景 |
| --- | --- |
| `systemctl daemon-reload` | 修改 `.service` 文件后重新读取定义 |
| `systemctl start ai-oralscan` | 启动已经停止的服务 |
| `systemctl restart ai-oralscan` | 后端代码或环境变化后重启，有短暂中断 |
| `systemctl stop ai-oralscan` | 有意暂停后端，如一致性备份 |
| `systemctl enable ai-oralscan` | 设置开机启动，不等于立即启动 |
| `systemctl enable --now ai-oralscan` | 同时设置开机启动并立即启动 |
| `nginx -t` | 检查 Nginx 配置语法 |
| `systemctl reload nginx` | 让 Nginx 加载配置 |

`active` 只证明进程状态；接口是否可用还需请求验证。定义解释参见 [systemd 官方文档](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)。

## 6. 资源、端口与请求检查

```bash
df -h
free -h
ss -lntp
curl -i --max-time 10 http://127.0.0.1:8000/api/health
```

依次查看磁盘容量、内存使用、TCP 监听端口、后端接口响应。`curl -I` 只请求响应头；`curl -i` 同时显示响应头和正文；`--max-time` 防止一直等待。

## 7. 权限与操作边界

`root` 能修改系统；`oralscan` 是运行应用的专用账号。文件的读、写、执行权限分别用 r、w、x 表示。目录的 x 权限表示能进入/穿过该目录。服务账号必须能读取源码和虚拟环境，并写入其数据目录。

遇到 Permission denied，应先用 `ls -ld` 检查涉及目录及所有者。不要用 `chmod -R 777` 作为通用修复，这会把不必要的写权限开放给其他用户。

`rm`、覆盖重定向 `>`、`git reset --hard`、`git clean` 都可能丢弃数据。修改前确认路径和备份；本教程不把强制删除作为部署步骤。

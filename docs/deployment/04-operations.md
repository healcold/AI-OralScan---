# 04 · 日常运维与次日继续开发

## 一、结束当天工作

1. 等待上传、保存、构建或安装完成；确认需要的记录已保存。
2. 保存本地编辑器中未保存的文件。若有源码修改，查看差异并按团队流程提交；不要把环境密钥或数据文件一并提交。
3. 在云服务器终端提示符后输入 `exit`，回到登录界面后关闭 VNC 页。
4. 退出云控制台账号，关闭浏览器和本地软件。
5. 正常关闭个人电脑。

云端后端由 systemd 管理，网页由 Nginx 提供。个人电脑关机不会关闭云服务器。不要为休息而执行云实例“关机/删除”或 `systemctl stop`；这些会改变网站可用性。

## 二、次日继续

先打开自己的 HTTP 网址，检查页面和历史记录。需要开发时打开本地仓库；需要部署时再登录服务器。无须每天安装依赖或重新 clone。

服务器快速检查：

```bash
systemctl is-active ai-oralscan nginx
curl -i --max-time 10 http://127.0.0.1:8000/api/health
git -C /opt/ai-oralscan status --short
```

已有修改时先确认来源。特别是当天的 HTTP UUID 兼容补丁，曾仅在服务器修改；不能直接覆盖。

## 三、手动部署更新流程

本节是后续操作教程，未在本次日志中记作实际完成。任何一步失败都应停下查错，不要继续执行后面的发布步骤。

### 1. 合并修改与备份

先把服务器临时修复转成团队可审查的源码提交，并确认 main 已包含需要的变更。不要把服务器上整个目录打包推送，因为其中可能包含环境文件或数据。

```bash
cd /opt/ai-oralscan
git status --short
git diff
git rev-parse HEAD
```

记录当前提交号用于回溯；工作区不干净时先处理差异，不使用 `reset --hard` 绕过。差异可能包含配置，公开分享前需脱敏。

### 2. 一致性备份示例

以下方法会短暂停止后端，适合低流量演示环境。备份覆盖数据库、上传文件和模型状态目录；假定该服务是唯一写入者。若还有其他写入程序，需一并协调暂停。

先记录备份路径，再逐条操作：

```bash
install -d -m 700 /var/backups/ai-oralscan
backup_file="/var/backups/ai-oralscan/state-$(date +%Y%m%d-%H%M%S).tar.gz"
systemctl stop ai-oralscan
systemctl is-active ai-oralscan
```

确认显示 `inactive` 再备份，若状态不符先排查：

```bash
(umask 077; tar -czf "$backup_file" -C /var/lib ai-oralscan)
```

无论打包是否成功，都要恢复服务并检查；打包失败时本次备份无效，不能继续更新：

```bash
systemctl start ai-oralscan
systemctl is-active ai-oralscan
tar -tzf "$backup_file" | head
```

列表检查不等于恢复演练。备份文件含业务数据，不要上传公开 GitHub。保留私有的异地备份；仅存同一块云盘不能应对整盘丢失。Nginx、systemd 和私有环境配置也应独立备份到受控位置。

### 3. 拉取与构建

工作区已干净、备份成功且 main 已审核后：

```bash
cd /opt/ai-oralscan
git pull --ff-only origin main
backend/.venv/bin/python -m pip install -r backend/requirements.txt
pnpm -C frontend install --frozen-lockfile
pnpm -C frontend build
```

`--ff-only` 避免在服务器上意外生成合并提交。如果提示分叉或冲突，应回到团队代码流程处理。依赖或数据库结构变化还需遵守该版本的升级说明；本流程不自动执行数据库迁移。

直接在现有目录构建适合当前演示环境，构建期间可能影响静态文件访问，也不提供无缝回滚。需要稳定发布时改为独立发布目录、构建验证后切换，再进行恢复演练。

### 4. 启用与验收

```bash
systemctl restart ai-oralscan
systemctl is-active ai-oralscan
curl -i --max-time 10 http://127.0.0.1:8000/api/health
```

如果修改了 Nginx 配置，先 `nginx -t`，成功后 `systemctl reload nginx`。仅替换静态文件通常不需要重启 Nginx。

最后用浏览器检查首页、一次演示上传、历史记录读取。健康接口通过不代表所有功能都正常。发生问题时保留日志，依据记录的旧提交与备份制定恢复动作；数据库结构有变化时，不能只退代码就保证兼容。

## 四、故障排查速查

先确认访问地址协议，再检查云实例状态。之后在服务器执行：

```bash
systemctl status nginx ai-oralscan --no-pager -l
ss -lntp
nginx -t
journalctl -u ai-oralscan -n 80 --no-pager
tail -n 50 /var/log/nginx/error.log
```

| 检查结果 | 下一步 |
| --- | --- |
| 本机后端接口失败 | 看后端日志、配置、磁盘、权限 |
| 后端成功但 Nginx API 失败 | 查代理路径、启用的站点配置 |
| 本机 Nginx 成功但外网失败 | 查安全组 TCP80、协议、系统防火墙、客户端网络 |
| 页面成功但旧功能仍报错 | 强制刷新，查实际构建版本与浏览器请求 |
| systemd 反复重启 | 日志定位错误；不要只反复重启 |

日志可能包含客户端地址、上传文件名或异常中的输入数据；分享前脱敏。

## 五、下一阶段任务清单

- [ ] 核对服务器 UUID 兼容修改并合入源码。
- [ ] 手机移动网络测试外网访问与上传。
- [ ] 配置 HTTPS 并验证摄像头授权流程。
- [ ] 明确公共演示范围与访问权限。
- [ ] 为数据库和文件建立私有备份，做一次恢复演练。
- [ ] 逐项部署并验证实际模型与 AI 助理服务。
- [ ] 如需自动部署，再建立审核、凭据管理、失败恢复机制。

## 六、参考资料

- [华为云 Flexus L 安全组设置](https://support.huaweicloud.com/usermanual-flexusl/security_admin_0004.html)
- [NodeSource 安装说明](https://github.com/nodesource/distributions/blob/master/DEV_README.md)
- [Nginx 官方入门](https://nginx.org/en/docs/beginners_guide.html)
- [systemd 服务定义](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
- [MDN randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)
- [MDN getRandomValues](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/getRandomValues)
- [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)

这些链接用于进一步学习；安装源、浏览器限制和云控制台界面应在实际操作时再次核对。

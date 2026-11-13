# gh-fast-download

通过社区镜像下载公开 GitHub 仓库快照、单个文件和 Release 附件。需要 Python 3.8+，无第三方依赖。Agent 和命令行共用 `ghdl.py`，使用相同的公开状态验证、文件保护与响应检查。

## 让 Agent 下载

将整个文件夹安装到 Agent 的技能目录，保留 `SKILL.md` 与 `ghdl.py` 的相对位置。支持 Claude Code、OpenClaw、Codex 等支持本地技能的 Agent。随后直接描述需要的结果，例如：

> 下载这个公开项目到下载目录：https://github.com/owner/repo

Agent 处理链接、Python 检查和文件保存。脚本先向官方 GitHub API 发送**不带凭据**的请求，明确确认仓库公开后，才把文件 URL 交给镜像。URL 看起来正常不代表仓库公开；私有、无法确认、API 限流或网络失败时安全停止，改用官方 GitHub CLI 的认证直连。

需要 Git 历史的克隆应使用官方 `gh repo clone`；本脚本下载仓库快照 ZIP，不提供镜像 Git 克隆。维护仓库或审查技能内容时，不应启动下载流程。

## 命令行使用

```console
python ghdl.py https://github.com/owner/repo ./downloads
python ghdl.py https://github.com/owner/repo/releases/download/v1.0/app.exe ./downloads
python ghdl.py https://github.com/owner/repo/blob/main/README.md ./downloads
python ghdl.py https://raw.githubusercontent.com/owner/repo/main/index.html ./downloads
```

仓库根链接依次尝试 `main`、`master` 快照。其他分支或标签请使用准确的 `/archive/refs/heads/BRANCH.zip`、`/archive/refs/tags/TAG.zip` 链接；也支持 `/archive/COMMIT.zip`。`blob` 链接会转换为 raw 链接。`http://` 和省略协议的 GitHub 链接会规范为 HTTPS。

仅接受精确的 `github.com`、`raw.githubusercontent.com` 主机和上述路径。拒绝 URL 用户名/密码、查询参数、片段、自定义端口、其他协议、相似域名和路径歧义。请勿把带 token 的下载链接交给镜像。仓库或文件名出现在普通 URL 中，无法单独证明其公开性。

## 保存和失败恢复

默认保留已有文件。目的文件存在时会停止；可换一个目录，或在确实需要替换时显式使用：

```console
python ghdl.py https://github.com/owner/repo/blob/main/README.md ./downloads --overwrite
```

下载先写入目标目录中的临时文件。只有完整读取且检查通过后，才原子落盘。普通保存不会覆盖传输期间由其他程序新建的同名文件；`--overwrite` 在成功后使用原子替换。连接中断、校验失败、所有镜像失败时清理临时文件，并保留原文件。失败后可重新运行，当前不支持断点续传。

响应必须为 HTTP 200、内容非空，且与服务端提供的 `Content-Length` 一致。非 HTML 目标会拒绝明显 HTML 页面，避免把常见镜像报错页保存成安装包；明确请求的 `.html`、`.htm` 原文件允许 HTML。明确以 `.zip` 结尾的目标还会检查 ZIP 目录结构，不解压，也不逐项验证 CRC。文件名需适用于 Windows、macOS 和 Linux；不支持的名称会安全停止。

HTML 检查是基于响应类型和前 1024 字节的启发式判断，会跳过前置空白和完整 HTML 注释，无法穷尽所有伪装。这些检查不能证明镜像返回了正确或可信的内容；HTML 目标也无法仅靠响应外观区分正常页面与错误页面。重要文件应核对项目官方公布的校验值或签名。脚本不会解压、安装或执行下载内容。

Windows 使用不覆盖同名文件的重命名；POSIX 使用同目录硬链接原子安装新文件。文件系统不支持所需操作时会报错，保留原文件，不降级为可能覆盖文件的写法。

## 镜像与边界

镜像名单仅在 `ghdl.py` 的 `PROXIES` 中维护，按顺序尝试。它们是第三方社区服务，可用性、隐私与内容可信度没有保证。本轮测试没有访问镜像，也没有验证其当前速度或可用性。

官方 API 不可达、403、404、响应异常或没有明确确认公开时，脚本不联系镜像。不要通过手动拼接镜像 URL 绕过该检查。需要认证、私有仓库或镜像全部失败时，使用官方 GitHub CLI 的直连下载，并保留相同的文件保护原则。

## 开发验证

在仓库根目录执行：

```console
python -m unittest discover -s tests -v
```

测试使用标准库模拟 HTTP 响应，不访问 GitHub API、公共镜像或真实下载地址。覆盖 URL 边界、公开确认、旧文件保护、并发同名文件、原子替换、失败清理、镜像重试、空内容、长度不符、HTML 错误页、合法 HTML 文件和 ZIP 结构。GitHub Actions 配置 Windows/Linux 与 Python 3.8/3.13 的同一离线测试；实际云端结果以 Actions 记录为准。

实现参考了 Python 官方的 [临时文件](https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp)、[原子替换](https://docs.python.org/3/library/os.html#os.replace)与 [HTTPResponse](https://docs.python.org/3/library/http.client.html#http.client.HTTPResponse) API。本项目使用标准库独立实现，沿用 [MIT 许可证](LICENSE)。变更见 [CHANGELOG](CHANGELOG.md)。

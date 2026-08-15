# gh-fast-download

给国内用户用的 GitHub 高速下载 skill：把 GitHub 链接一键转成代理加速链接再下载，告别龟速。

## 这是什么

| 文件 | 作用 |
|------|------|
| `SKILL.md` | 给 AI Agent（Claude Code / OpenClaw / Codex 等）用的技能文件 |
| `ghdl.py` | 给「不想用 Agent、想在命令行自己下载」的人用的独立脚本，零第三方依赖 |
| `README.md` | 本说明 |
| `LICENSE` | MIT 授权 |

## 原理

GitHub 服务器在国外，直连又慢又容易被干扰。gh-proxy 这类镜像是一台「两条腿都快」的中转服务器：它去 GitHub 取文件快，把文件传给你也快，还带缓存。用法就是在原链接前面加一个代理域名：

```
https://gh-proxy.org/https://github.com/OWNER/REPO
```

## 安装到 Agent

根据你用的 Agent，把整个文件夹复制到对应目录：

- **Claude Code**：`.claude/skills/gh-fast-download/`
- **OpenClaw**：`~/.openclaw/plugin-skills/gh-fast-download/`
- **Codex**：`~/.codex/skills/gh-fast-download/`

装好后重启 Agent（或新开会话），然后直接说：

> 下载 https://github.com/xxx/yyy

## 命令行直接下载（不用 Agent）

需要 Python 3.8+（Windows / macOS / Linux 通用）：

```bash
python ghdl.py https://github.com/owner/repo                                    # 下整仓库 zip
python ghdl.py https://github.com/owner/repo/releases/download/v1.0/app.exe     # 下 release 附件
python ghdl.py https://github.com/owner/repo/blob/main/README.md                # 下单个文件
python ghdl.py https://github.com/owner/repo ./downloads                        # 指定保存目录
```

## 代理镜像列表

skill 和脚本里都内置了，按顺序尝试，直到成功：

1. `https://gh-proxy.org/`
2. `https://gh-proxy.com/`
3. `https://ghfast.top/`
4. `https://ghproxy.net/`
5. `https://mirror.ghproxy.com/`

这些是社区自建镜像，会随时间和维护者变化。如果全挂了，搜「gh proxy 加速」换最新的域名即可（改 `ghdl.py` 里的 `PROXIES` 列表，或改 `SKILL.md` 里的列表）。

## 免责声明

- 只对**公开**仓库使用；私有仓库 / 带 token 的链接请勿走公共代理。
- 代理是第三方服务，不保证可用性，也不对内容负责。

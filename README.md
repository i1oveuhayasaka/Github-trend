# Media Digest

一个免费的、安全优先的信息收集与推送工作流。默认信息源只使用 RSS 和官方公开 API，不抓取 X，不使用账号 Cookie。

## 能做什么

- 从高质量免费信息源收集内容：BBC、Guardian、NPR、Hacker News、GitHub Trending、GitHub Search、arXiv，可选 GDELT。
- 用 SQLite 做去重，避免每天重复推送。
- 按来源质量、时间新鲜度、GitHub stars/forks 等排序。
- 输出 Markdown 日报。
- 推送到钉钉、Bark、Server 酱，或自定义 Webhook。
- 生成小红书风格草稿，但不自动登录发帖。

## 快速开始

```bash
cp config.example.toml config.toml
python3 -m media_digest --config config.toml --sample-only --dry-run --include-seen --no-store
```

输出会写到 `outputs/`：

- `digest_YYYY-MM-DD.md`
- `xiaohongshu_YYYY-MM-DD.md`

## 配置钉钉推送

在钉钉群里添加「自定义机器人」，安全设置建议使用「加签」。然后设置环境变量：

```bash
export DINGTALK_WEBHOOK='https://oapi.dingtalk.com/robot/send?access_token=xxxx'
export DINGTALK_SECRET='SECxxxx'
```

编辑 `config.toml`：

```toml
[push.dingtalk]
enabled = true
webhook_env = "DINGTALK_WEBHOOK"
secret_env = "DINGTALK_SECRET"
```

测试：

```bash
python3 -m media_digest --config config.toml --sample-only --include-seen --no-store
```

## 配置 Bark / Server 酱

Bark：

```bash
export BARK_KEY='你的 Bark key'
```

```toml
[push.bark]
enabled = true
key_env = "BARK_KEY"
server = "https://api.day.app"
```

Server 酱：

```bash
cp .env.example .env
```

然后编辑 `.env`，填入：

```bash
SERVERCHAN_SENDKEY='你的 sendkey'
```

```toml
[push.serverchan]
enabled = true
sendkey_env = "SERVERCHAN_SENDKEY"
```

## 配置信息源

每个 `[[sources]]` 都可以独立开关：

```toml
[[sources]]
id = "hacker_news"
name = "Hacker News"
type = "rss"
enabled = true
url = "https://hnrss.org/frontpage?points=80"
quality = 1.15
max_items = 25
tags = ["tech", "hn"]
```

支持的类型：

- `rss`：任何 RSS/Atom 源。
- `github_trending`：解析 GitHub Trending 公开页面，用于 daily/weekly/monthly 趋势榜。
- `github_search`：GitHub 官方 Search API，无需 token 也能小规模使用，适合发现新仓库或特定主题仓库。
- `arxiv`：arXiv 官方 API。
- `gdelt`：GDELT 免费新闻数据库，覆盖广但噪音更高，默认关闭。
- `sample`：本地示例数据，便于测试推送链路。

支持日期占位符：

- `{today}`
- `{date_7d}`
- `{date_30d}`

只运行某几个源：

```bash
python3 -m media_digest --config config.toml --source github_trending_daily --source github_ai_recent
```

## 每日去重

正式运行时不要加 `--include-seen`、`--no-store` 或 `--dry-run`。程序会用 `data/digest.db` 记录已经成功推送进日报的条目，下次运行会自动过滤掉这些 URL。

GitHub Trending 默认抓取前 25 个项目，再从未推送过的项目里挑选进入日报。这样即使榜单前几名连续几天重复，也能尽量给你推送新的项目。

## 翻译

默认 `provider = "none"`，不调用任何外部模型。如果你需要中文翻译/整理，有两个安全选项：

1. 自建 LibreTranslate：

```toml
[translation]
provider = "libretranslate"
libretranslate_url = "http://127.0.0.1:5000"
target_language = "zh"
```

2. OpenAI-compatible API：

```bash
export OPENAI_API_KEY='你的 key'
```

```toml
[translation]
provider = "openai_compatible"
openai_base_url = "https://api.openai.com/v1"
openai_model = "gpt-4.1-mini"
```

GitHub 项目在启用 OpenAI-compatible 翻译后，会生成 2-3 句中文整理：项目是什么、适合什么场景、为什么值得关注。日报里会同时保留原始英文描述，方便核对。

DeepSeek 也可以直接作为 OpenAI-compatible 翻译模型：

```bash
DEEPSEEK_API_KEY='你的 DeepSeek API Key'
```

```toml
[translation]
provider = "openai_compatible"
openai_base_url = "https://api.deepseek.com"
openai_api_key_env = "DEEPSEEK_API_KEY"
openai_model = "deepseek-v4-flash"
```

如果你更看重质量而不是速度/成本，也可以把模型改成 `deepseek-v4-pro`。

第三方 OpenAI-compatible 中转站也可以使用，例如：

```bash
BYTECAT_API_KEY='你的中转站 key'
```

```toml
[translation]
provider = "openai_compatible"
openai_base_url = "https://codecdn.bytecatcode.org/v1"
openai_api_key_env = "BYTECAT_API_KEY"
openai_model = "deepseek-v4-flash"
```

## 每天定时运行

macOS 推荐用 launchd。项目里已经提供了一个每日 GitHub Trending 任务模板，每天 08:30 运行：

```bash
chmod +x scripts/run_daily_github_trending.sh
cp templates/com.local.media-digest.github-trending.plist ~/Library/LaunchAgents/com.local.media-digest.github-trending.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.local.media-digest.github-trending.plist
```

手动跑一次正式任务：

```bash
scripts/run_daily_github_trending.sh
```

查看日志：

```bash
tail -n 80 logs/daily-github-trending.out.log
tail -n 80 logs/daily-github-trending.err.log
```

## 部署到 Linux 云服务器

可以直接部署到腾讯云、阿里云、海外 VPS 等 Linux 服务器。推荐 Python 3.11+。

假设项目放在 `/opt/media-digest`：

```bash
cd /opt
git clone <你的仓库地址> media-digest
cd /opt/media-digest
cp config.example.toml config.toml
cp .env.example .env
chmod +x scripts/run_daily_github_trending_linux.sh
```

编辑 `.env`，填入：

```bash
SERVERCHAN_SENDKEY='你的 Server 酱 SendKey'
BYTECAT_API_KEY='你的中转站 key'
```

编辑 `config.toml`，确认：

```toml
[translation]
provider = "openai_compatible"
openai_base_url = "https://codecdn.bytecatcode.org/v1"
openai_api_key_env = "BYTECAT_API_KEY"
openai_model = "deepseek-v4-flash"

[push.serverchan]
enabled = true
sendkey_env = "SERVERCHAN_SENDKEY"
```

手动测试：

```bash
scripts/check_server_env.sh
scripts/run_daily_github_trending_linux.sh
```

cron 定时，每天北京时间 08:30：

```cron
TZ=Asia/Shanghai
30 8 * * * cd /opt/media-digest && /opt/media-digest/scripts/run_daily_github_trending_linux.sh >> /opt/media-digest/logs/cron.out.log 2>> /opt/media-digest/logs/cron.err.log
```

systemd timer 定时：

```bash
sudo cp templates/media-digest-github-trending.service /etc/systemd/system/
sudo cp templates/media-digest-github-trending.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now media-digest-github-trending.timer
systemctl list-timers | grep media-digest
```

如果你不是部署在 `/opt/media-digest`，需要同步修改 `templates/media-digest-github-trending.service` 里的路径。

服务器需要能访问：

- `github.com`
- `codecdn.bytecatcode.org`
- `sctapi.ftqq.com`

## 小红书草稿

项目只生成 `outputs/xiaohongshu_YYYY-MM-DD.md` 长文草稿，供人工检查和发布。程序不会登录小红书、保存登录态或自动点击发布。

```toml
[social.xiaohongshu]
enabled = true
max_items = 8
```

# 政策法规日报

## 监管情报方法

系统以法规、标准和政策文件为核心实体，不以新闻热度作为收录依据。

信息分为两层：

- `data/intelligence/official/`：已经核验正文、日期、相关性和证据等级的正式情报。
- `data/intelligence/leads/`：行业媒体、企业或间接相关内容形成的待核实线索，不直接进入日报。

每条正式情报记录法域、文件编号、文件类型、法规生命周期、重卡影响等级、适用车型、
动力范围、证据等级和正文证据。媒体报道只有在能够回查权威原文时才升级为正式情报。

来源在 `config/sources.yaml` 中按监管频道声明，而不是只保存网站首页。每个声明包括采集方式、
来源权威、证据等级、允许的文件类型、链接规则和正文规则。结构化 API 优先于网页抓取；
官方列表页适配器只接受能够核验发布日期和正文的详情页。

当前第一批重点覆盖中国、UNECE/WP.29、欧盟、美国联邦和加州。美国 Federal Register
使用结构化 API；其余来源逐步从通用列表页升级为专用适配器。

### 分层筛选

1. 验证正文、发布日期和原始链接。
2. 判断汽车行业相关性。
3. 将重卡影响标记为 `direct`、`probable`、`indirect` 或 `none`。
4. 识别征求意见、草案、发布、修订、生效、延期、执法和废止等阶段。
5. 根据来源权威、证据等级、重卡直接性和法律阶段计算重要性。
6. `direct` 和高可信 `probable` 进入正式库；间接或低证据内容进入线索池。

重要性由确定性规则计算，AI负责从正文提取结构化特征，不单独决定是否为重点。

面向全球重卡、纯电重卡、动力电池、充换电、排放、碳排放、智能驾驶和市场准入的自动化政策监测网站。系统只收录正文、来源与实际发布时间均可核验的信息，生成日报、周报、月报并发布至 GitHub Pages。

## 安全边界

欧盟法规使用欧盟出版局 Cellar 的机器可读 SPARQL 接口发现，再回取 EUR-Lex
正式文本。对于按云机房 IP 返回 403 的来源，不伪装浏览器或绕过限制；改用该机构
公开的法规登记、文件分发或官方镜像链路。替代入口尚未核验前，失败会被明确记录，
不会用搜索片段或二手报道补齐。

- 默认 `dry-run`，不会向真实收件人发送邮件。
- 只有有内容的日报允许发送；周报、月报以及空日报始终拒绝发送。
- API Key、QQ 邮箱授权码和私有仓库令牌仅从环境变量或 GitHub Secrets 读取。
- 不绕过登录、验证码、访问控制或网站规则；单个来源失败不会阻断其他来源。
- 微信公众号没有稳定的公开接口，可能漏采、延迟或因页面变化失效。首期仅保留独立适配层，不部署 WeRSS，不接入收费 API。

## 本地运行

需要 Python 3.11：

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m policy_daily.main --report-type daily --dry-run
```

无 `DEEPSEEK_API_KEY` 时使用确定性的模拟处理器，便于测试管线；模拟结果不得作为正式日报内容发布。安全的站点构建命令：

```bash
python -m policy_daily.main --report-type daily --skip-collect --force --dry-run
python -m http.server 8000 --directory site-dist
```

命令行参数：

- `--report-type daily|weekly|monthly`
- `--start YYYY-MM-DD`、`--end YYYY-MM-DD`
- `--force` 强制重建同一期报告
- `--send-email --no-dry-run` 请求真实发送，仅对有内容日报有效
- `--skip-collect` 仅从现有处理后数据生成报告
- `--data-dir`、`--output-dir`、`--base-path`

## 配置与数据

- `config/settings.yaml`：时区、24 小时窗口、重点阈值、网络和 DeepSeek 参数。
- `config/sources.yaml`：来源入口、适配器、类型、地区与权威等级。
- `config/categories.yaml`、`config/tags.yaml`：固定分类、地区、核心标签与同义词。
- `data/raw`、`processed`、`daily`、`weekly`、`monthly`：版本化数据。
- `data/sources.json`：来源健康状态；`manifest.json` 和 `search-index.json` 供静态网站使用。

修改网站发布路径时应同时传入 `--base-path`。默认值 `/qesbr-heavy-truck-policy-daily/` 已适配实际项目型 GitHub Pages。

## GitHub 部署

1. 创建公开仓库 `qesbr/qesbr-heavy-truck-policy-daily`，把本目录作为仓库根目录推送到 `main`。
2. 创建私有仓库 `qesbr/qesbr-heavy-truck-policy-daily-config`，复制 `private-config-template` 中的两个文件，并在 `recipients.yaml` 填写真实收件人。
3. 在公开仓库 Settings → Pages → Build and deployment 中选择 **GitHub Actions**。
4. 在 Settings → Secrets and variables → Actions 配置下列 Secrets：

| Secret | 用途 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek 正式处理 |
| `SMTP_USERNAME` | QQ 发件邮箱 |
| `SMTP_AUTH_CODE` | QQ SMTP 授权码 |
| `PRIVATE_CONFIG_TOKEN` | 仅可读取私有配置仓库 Contents 的细粒度令牌 |
| `PRIVATE_CONFIG_REPO` | `qesbr/qesbr-heavy-truck-policy-daily-config` |

5. 首次在 Actions 中运行 **Manual report**，选择 `daily` 并保持 `dry_run=true`、`send_email=false`。核验数据和 Pages 后，再单独确认是否启用真实邮件。

定时任务均按 UTC 配置，对应北京时间 08:30：日报每天、周报每周一、月报每月 1 日。Actions 的 `contents: write` 仅用于提交公开数据；Pages 工作流使用 `contents: read`、`pages: write` 和 `id-token: write`。

## 测试

```bash
pytest
```

测试覆盖配置与模型、时间窗口、URL 规范化、权威来源合并、AI 模拟/非法 JSON 重试、幂等报告、空日报、周月报拒发和 GitHub Pages 子路径构建。邮件测试只生成预览或验证拒绝路径。

## 故障排查

- **来源显示 error**：检查入口是否改版、是否允许自动访问及网络是否可用；不要以搜索片段替代正文。
- **DeepSeek 失败**：检查 Key、额度、接口状态和严格 JSON 日志；失败记录会跳过，不会凭标题补写摘要。
- **Pages 空白**：确认 Pages 来源为 GitHub Actions，且 `site-dist/data/manifest.json` 已由构建生成。
- **邮件未发送**：确认是有内容日报、明确选择 `send_email=true` 与 `dry_run=false`，并检查五项 Secrets。发送失败不会阻止网站更新。
- **重复运行**：同一类型和结束日期默认复用；使用 `--force` 才重建。

## 已知限制

通用 HTML 列表采集器采取保守策略，仅跟进同时具备可验证日期和可访问正文的链接。复杂 JavaScript 页面、PDF 日期语义、地区网络限制和反爬策略可能造成漏采。每个正式来源应持续维护专用选择器；自动发现的候选来源在人工或规则核验前不会进入日报。

采集架构借鉴 RSSHub 的站点路由隔离、Trafilatura 的正文与元数据提取，以及 changedetection.io 的可配置 CSS 过滤思想；项目保留自身实现，不复制这些项目的代码或品牌资源。

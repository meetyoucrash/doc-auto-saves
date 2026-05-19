# KDocs 115 增量转存

从金山文档多维表格自动提取 115 网盘分享链接并增量转存到 115 网盘。

## 架构

```
KDocs 多维表格 → Playwright 提取 → p115client API → 115 网盘
```

- **提取器** (`kdocs_115_scraper.py`): 使用 Playwright 从 KDocs 多维表格提取记录
- **注入器** (`kdocs_115_injector.py`): 调用 p115client API 获取文件列表，文件级增量检测
- **定时包装器** (`kdocs_115_cron.py`): 顺序执行提取器和注入器

## 增量逻辑

1. 从 KDocs 提取记录（名称、链、提取码）
2. 解析 URL 获取 share_code 和 password
3. 调用 `p115client.share_snap()` API 获取文件列表（自动分页）
4. 以 **文件名 + 文件大小** 为唯一标识，对比已转存记录
5. 新文件或文件列表变化时，生成转存任务

## 配置

### 1. 安装依赖

```bash
pip3 install p115client --break-system-packages
playwright install chromium  # 如果首次运行需要
```

### 2. 配置 115 Cookie

在 `quark_config.json` 中配置：

```json
{
  "p115_cookie": [
    "你的 115 Cookie (UID=...; CID=...; KID=...; SEID=...)"
  ]
}
```

或在环境变量中设置：

```bash
export P115_COOKIE="UID=...; CID=...; KID=...; SEID=..."
```

### 3. KDocs 表格配置

**重要**: 需要在 KDocs 表格的"提取码"字段填入真实提取码，或在 URL 中包含提取码。

| 字段 | 说明 |
|------|------|
| 名称 | 剧集名称，用于分类 |
| 规格信息 | 可选，如 1080p、4K |
| 链 | 115 分享链接，如 `https://115cdn.com/s/xxx` |
| 提取码 | **必须填入真实提取码**，或 URL 中包含 `?password=xxx` |

## 用法

### 完整流程

```bash
cd /path/to/doc-auto-saves
python3 kdocs_115_cron.py
```

### 只提取，不转存

```bash
python3 kdocs_115_cron.py --scrape-only
```

### 只预览，不执行

```bash
python3 kdocs_115_cron.py --dry-run
```

### 只生成 TASKLIST JSON

```bash
export TASKLIST=$(python3 kdocs_115_cron.py --gen-tasks)
python3 quark_auto_save.py
```

### 全量模式（忽略已追踪）

```bash
python3 kdocs_115_injector.py --full
```

## 定时任务

```bash
crontab -e
```

添加：

```
# 每 6 小时运行一次
0 */6 * * * cd /path/to/doc-auto-saves && P115_COOKIE='你的 115cookie' python3 kdocs_115_cron.py >> cron_kdocs.log 2>&1
```

## 数据目录

```
data/kdocs_115/
├── records.json    # 提取的记录（临时）
├── tracked.json    # 增量追踪状态
└── tasks.json      # 生成的任务（如果 quark_auto_save.py 未找到）
```

## 故障排除

### 115 账号验证失败

- 检查 `P115_COOKIE` 是否有效
- Cookie 格式：`UID=...; CID=...; KID=...; SEID=...`

### 获取分享列表失败：请输入访问码

- 检查提取码是否正确
- KDocs 中的 URL 被脱敏为 `?password=***`，需要填入真实提取码

### p115client 未安装

```bash
pip3 install p115client --break-system-packages
```

### 提取器失败

- 检查 Playwright 是否安装：`playwright install chromium`
- 检查 KDocs 链接是否可访问

## 部署

```bash
bash kdocs_115_deploy.sh /path/to/doc-auto-saves
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `kdocs_115_scraper.py` | Playwright 提取器，从 KDocs 提取记录 |
| `kdocs_115_injector.py` | 增量注入器，调用 p115client API |
| `kdocs_115_cron.py` | 定时任务包装器 |
| `quark_auto_save.py` | 115 转存脚本（原有） |
| `quark_config.json` | 配置文件 |

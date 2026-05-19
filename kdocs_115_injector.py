#!/usr/bin/env python3
"""
KDocs 115 增量注入器
读取 records.json 与 tracked.json 对比，
生成新/更新的 115 转存任务，注入 quark_auto_save.py 流程。

用法 (独立运行):
  python3 kdocs_115_inject.py              # 提取+转存一步完成
  python3 kdocs_115_inject.py --dry-run    # 只看新增，不转存

用法 (与 quark_auto_save.py 配合):
  export TASKLIST=$(python3 kdocs_115_inject.py --gen-tasks)
  python3 quark_auto_save.py

增量追踪: /tmp/kdocs_115_data/tracked.json
"""
import json, os, sys, re, hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE_DIR, "data/kdocs_115")
TRACKED_FILE = os.path.join(OUTDIR, "tracked.json")
RECORDS_FILE = os.path.join(OUTDIR, "records.json")
SCRAPER = os.path.join(BASE_DIR, "kdocs_115_scraper.py")

# 转存路径配置 - 根据规格信息自动判断目录
SAVE_PATH_MAP = {
    '动漫': '/115追番/动漫',
    '华语': '/115追番/华语',
    '日本': '/115追番/动漫',  # 日漫也归到动漫
    '日韩': '/115追番/日韩',
    '欧美': '/115追番/欧美',
    '综艺': '/115追番/综艺',
    '短剧': '/115追番/短剧',
}

def load_tracked():
    """加载已追踪记录"""
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_tracked(tracked):
    """保存追踪记录"""
    os.makedirs(OUTDIR, exist_ok=True)
    with open(TRACKED_FILE, 'w', encoding='utf-8') as f:
        json.dump(tracked, f, ensure_ascii=False, indent=2)

def classify_savepath(name):
    """根据名称判断保存目录"""
    # 从名称中提取分类: 【剧集/分类/子类】
    match = re.search(r'【[^/]*/([^/】]*)', name)
    if match:
        sub = match.group(1)
        for keyword, path in SAVE_PATH_MAP.items():
            if keyword in sub:
                return path
    return '/115追番'

def build_task(record):
    """从记录构建 115 转存任务"""
    name = record.get('名称', '')
    clean_name = re.sub(r'[🔥🔚📆]', '', name).strip()
    url = record.get('链', '')
    savepath = classify_savepath(name)
    specs = record.get('规格信息', '')
    
    taskname = clean_name
    if specs:
        taskname = f"{clean_name} {specs}"
    
    return {
        "taskname": taskname,
        "shareurl": url,
        "savepath": savepath,
        "pattern": "",
        "replace": "",
        "platform": "115",
    }

def detect_changes(records, tracked, include_updated=True):
    """检测新增和更新的记录"""
    new_tasks = []
    
    for rec in records:
        url = rec.get('链', '')
        name = rec.get('名称', '')
        update_time = rec.get('更新时间', '')
        
        if not url:
            continue
        
        # 以 URL 为唯一标识
        key = url
        
        if key not in tracked:
            # 全新记录
            task = build_task(rec)
            new_tasks.append(task)
            tracked[key] = {
                'name': name,
                'url': url,
                'first_seen': update_time,
                'last_updated': update_time,
            }
        elif include_updated:
            # 检查更新时间是否变了
            prev = tracked[key]
            if prev.get('last_updated') != update_time:
                # 记录有更新
                task = build_task(rec)
                new_tasks.append(task)
                prev['last_updated'] = update_time
                prev['name'] = name
    
    return new_tasks, tracked

def gen_tasks_json(records=None, tracked=None):
    """生成 TASKLIST JSON 字符串"""
    if records is None:
        with open(RECORDS_FILE, 'r', encoding='utf-8') as f:
            records = json.load(f)
    if tracked is None:
        tracked = load_tracked()
    
    new_tasks, updated_tracked = detect_changes(records, tracked)
    save_tracked(updated_tracked)
    
    return json.dumps(new_tasks, ensure_ascii=False)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='KDocs 115 增量注入器')
    parser.add_argument('--dry-run', action='store_true', help='只显示新增，不执行')
    parser.add_argument('--gen-tasks', action='store_true', help='直接输出 TASKLIST JSON')
    parser.add_argument('--full', action='store_true', help='全量（忽略已追踪，重新转存所有）')
    args = parser.parse_args()
    
    # 1. 提取最新数据
    print("=== KDocs 115 增量转存 ===")
    print(f"[1/3] 提取金山文档数据...")
    
    if os.path.exists(RECORDS_FILE):
        # 已有缓存，读取
        with open(RECORDS_FILE, 'r', encoding='utf-8') as f:
            records = json.load(f)
        print(f"  读取缓存: {len(records)} 条")
    else:
        print("  缓存不存在，需要先运行提取器")
        return
    
    # 2. 检测变化
    print(f"[2/3] 增量检测...")
    tracked = {} if args.full else load_tracked()
    
    new_tasks, updated_tracked = detect_changes(records, tracked)
    
    if args.full:
        print(f"  全量模式: {len(records)} 条待处理")
        new_tasks = [build_task(r) for r in records if r.get('链')]
    
    if args.gen_tasks:
        # 只输出 JSON 供环境变量使用
        print(json.dumps(new_tasks, ensure_ascii=False))
        return
    
    print(f"  新增: {len(new_tasks)} 条")
    
    if args.dry_run:
        print(f"\n  [DRY RUN] 模拟结果:")
        for t in new_tasks:
            print(f"    {t['taskname']} → {t['savepath']}")
        return
    
    if not new_tasks:
        print("  无需转存")
        save_tracked(updated_tracked)
        return
    
    # 3. 执行转存
    print(f"[3/3] 执行 115 转存...")
    
    tasks_json = json.dumps(new_tasks, ensure_ascii=False)
    
    # 检查 quark_auto_save.py 是否存在
    script_paths = [
        "./quark_auto_save.py",
        "/app/quark_auto_save.py",
        os.path.expanduser("~/quark_auto_save.py"),
    ]
    
    qas_path = None
    for p in script_paths:
        if os.path.exists(p):
            qas_path = p
            break
    
    if not qas_path:
        print("  保存任务到 tasks.json（quark_auto_save.py 未找到）")
        with open(os.path.join(OUTDIR, "tasks.json"), 'w', encoding='utf-8') as f:
            json.dump(new_tasks, f, ensure_ascii=False, indent=2)
        print(f"  任务文件: {OUTDIR}/tasks.json")
    else:
        import subprocess
        env = os.environ.copy()
        env['TASKLIST'] = tasks_json
        result = subprocess.run(
            ['python3', qas_path],
            env=env,
            capture_output=True, text=True, timeout=600
        )
        print(result.stdout)
        if result.stderr:
            print(f"  STDERR: {result.stderr[:500]}")
    
    # 保存追踪记录
    save_tracked(updated_tracked)
    print(f"\n  追踪记录已更新: {len(updated_tracked)} 条")
    print("  完成")

if __name__ == "__main__":
    main()
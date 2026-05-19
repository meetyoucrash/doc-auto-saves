#!/usr/bin/env python3
"""
KDocs 115 增量注入器 v2
读取 records.json 与 tracked.json 对比，
调用 p115client API 获取文件列表（含多页），
以 文件名+文件时间 为唯一标识，生成新/更新的 115 转存任务。

用法 (独立运行):
  python3 kdocs_115_injector.py              # 提取+转存一步完成
  python3 kdocs_115_injector.py --dry-run    # 只看新增，不转存

用法 (与 quark_auto_save.py 配合):
  export TASKLIST=$(python3 kdocs_115_injector.py --gen-tasks)
  python3 quark_auto_save.py

增量追踪: data/kdocs_115/tracked.json
"""
import json, os, sys, re, hashlib
from datetime import datetime

# BASE_DIR: 脚本所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE_DIR, "data/kdocs_115")
TRACKED_FILE = os.path.join(OUTDIR, "tracked.json")
RECORDS_FILE = os.path.join(OUTDIR, "records.json")

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

def extract_url(url):
    """解析 115 分享链接，返回 (share_code, receive_code)"""
    # 同时匹配 115cdn.com 和 115.com
    match = re.search(r'115(?:cdn)?\.com/s/([a-zA-Z0-9]+)', url)
    share_code = match.group(1) if match else None
    
    # 解析 password，排除 ***
    pwd_match = re.search(r'[?&](?:password|pwd)=([a-zA-Z0-9]+)', url)
    password = pwd_match.group(1) if pwd_match else ""
    # 如果密码是 ***，则视为空
    if password == "***":
        password = ""
    
    return share_code, password

def get_115_files(share_code, password, cookie):
    """调用 p115client API 获取分享文件列表（自动分页）"""
    try:
        from p115client import P115Client
    except ImportError:
        print("  错误: p115client 未安装，请运行: pip3 install p115client")
        return None, "p115client 未安装"
    
    try:
        client = P115Client(cookie)
        # 初始化验证
        user_info = client.user_info()
        if not user_info.get("state"):
            return None, "115 账号验证失败"
        
        # 获取全部文件列表（自动分页）
        all_files = []
        offset = 0
        limit = 100
        
        while True:
            resp = client.share_snap({
                "share_code": share_code,
                "receive_code": password,
                "cid": 0,
                "limit": limit,
                "offset": offset,
            })
            
            if not resp.get("state"):
                error = resp.get("error", "未知错误")
                return None, f"获取分享列表失败: {error}"
            
            data = resp.get("data", {})
            files = data.get("list", [])
            total = data.get("count", 0)
            
            if not files:
                break
            
            all_files.extend(files)
            offset += len(files)
            
            # 如果返回数量少于 limit 或达到总数，结束
            if len(files) < limit or offset >= total:
                break
        
        return all_files, None
        
    except Exception as e:
        return None, f"API 调用异常: {type(e).__name__}: {e}"

def build_file_tasks(files, record, savepath):
    """从文件列表构建转存任务
    
    每个文件生成一个任务，使用 quark_auto_save.py 的 115 任务格式
    """
    tasks = []
    name = record.get('名称', '')
    clean_name = re.sub(r'[🔥🔚📆]', '', name).strip()
    
    for f in files:
        # 文件信息
        fname = f.get("n", "")  # 文件名
        fsize = f.get("s", 0)   # 文件大小
        ftime = f.get("created_at", "")  # 创建时间
        
        # 增量标识: 文件名 + 文件大小
        # 注意：quark_auto_save.py 的 115 转存是按分享链接转存整个目录
        # 这里我们生成的是整个分享链接的转存任务，不是单个文件
        # 所以增量逻辑是在分享链接级别，但记录的是文件列表
        
        # 对于 115，quark_auto_save.py 的 P115 类会处理整个分享链接
        # 所以我们仍然生成一个任务，但记录文件列表用于增量检测
        
        # 任务名称
        taskname = clean_name
        if f.get("dir", 0) == 0:  # 文件
            taskname = f"{clean_name}/{fname}"
        
        tasks.append({
            "taskname": taskname,
            "shareurl": record.get('链', ''),
            "savepath": savepath,
            "pattern": "",
            "replace": "",
            "platform": "115",
            # 额外信息用于增量检测
            "_files": [
                {"name": f.get("n", ""), "size": f.get("s", 0), "time": f.get("created_at", "")}
                for f in files
            ],
        })
        break  # 只生成一个任务（整个分享链接）
    
    return tasks

def detect_changes_v2(records, tracked, cookie):
    """检测新增和更新的记录（文件级增量）
    
    增量标识: 文件名 + 文件大小
    """
    new_tasks = []
    
    for rec in records:
        name = rec.get('名称', '')
        url = rec.get('链', '')
        password = rec.get('提取码', '')
        update_time = rec.get('更新时间', '')
        
        if not url:
            continue
        
        # 解析 URL
        share_code, url_password = extract_url(url)
        if not share_code:
            print(f"  警告: 无法解析 URL: {url}")
            continue
        
        # 优先使用提取码字段，其次使用 URL 中的密码
        effective_password = password if password else url_password
        
        # 如果都没有提取码，跳过（需要用户配置）
        if not effective_password:
            print(f"  跳过: {name} - 缺少提取码")
            continue
        
        # 调用 API 获取文件列表
        files, error = get_115_files(share_code, effective_password, cookie)
        if error:
            print(f"  错误: {name} - {error}")
            continue
        
        # 构建文件列表的标识
        file_list_hash = hashlib.md5(
            json.dumps(sorted([
                {"name": f.get("n", ""), "size": f.get("s", 0)}
                for f in files
            ]), ensure_ascii=False).encode()
        ).hexdigest()
        
        # 以 share_code 为键
        key = share_code
        
        if key not in tracked:
            # 全新记录
            savepath = classify_savepath(name)
            tasks = build_file_tasks(files, rec, savepath)
            new_tasks.extend(tasks)
            
            tracked[key] = {
                'name': name,
                'url': url,
                'password': effective_password,
                'first_seen': update_time,
                'last_updated': update_time,
                'file_list_hash': file_list_hash,
                'files': [
                    {"name": f.get("n", ""), "size": f.get("s", 0), "time": f.get("created_at", "")}
                    for f in files
                ],
            }
        else:
            # 检查文件列表是否变化
            prev = tracked[key]
            if prev.get('file_list_hash') != file_list_hash:
                # 文件列表有变化
                savepath = classify_savepath(name)
                tasks = build_file_tasks(files, rec, savepath)
                new_tasks.extend(tasks)
                
                prev['last_updated'] = update_time
                prev['name'] = name
                prev['file_list_hash'] = file_list_hash
                prev['files'] = [
                    {"name": f.get("n", ""), "size": f.get("s", 0), "time": f.get("created_at", "")}
                    for f in files
                ]
    
    return new_tasks, tracked

def gen_tasks_json(records=None, tracked=None, cookie=None):
    """生成 TASKLIST JSON 字符串"""
    if records is None:
        with open(RECORDS_FILE, 'r', encoding='utf-8') as f:
            records = json.load(f)
    if tracked is None:
        tracked = load_tracked()
    if cookie is None:
        cookie = ""
    
    new_tasks, updated_tracked = detect_changes_v2(records, tracked, cookie)
    save_tracked(updated_tracked)
    
    return json.dumps(new_tasks, ensure_ascii=False)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='KDocs 115 增量注入器 v2')
    parser.add_argument('--dry-run', action='store_true', help='只显示新增，不执行')
    parser.add_argument('--gen-tasks', action='store_true', help='直接输出 TASKLIST JSON')
    parser.add_argument('--full', action='store_true', help='全量（忽略已追踪，重新转存所有）')
    parser.add_argument('--cookie', type=str, default='', help='115 Cookie')
    args = parser.parse_args()
    
    # 1. 提取最新数据
    print("=== KDocs 115 增量转存 v2 ===")
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
    print(f"[2/3] 增量检测（文件级）...")
    tracked = {} if args.full else load_tracked()
    
    cookie = args.cookie or os.environ.get('P115_COOKIE', '')
    
    if args.full:
        print(f"  全量模式: {len(records)} 条待处理")
        # 全量模式下，所有记录都视为新增
        new_tasks = []
        for rec in records:
            if not rec.get('链'):
                continue
            savepath = classify_savepath(rec.get('名称', ''))
            new_tasks.append({
                "taskname": re.sub(r'[🔥🔚📆]', '', rec.get('名称', '')).strip(),
                "shareurl": rec.get('链', ''),
                "savepath": savepath,
                "pattern": "",
                "replace": "",
                "platform": "115",
            })
    else:
        new_tasks, updated_tracked = detect_changes_v2(records, tracked, cookie)
    
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
        if not args.full:
            save_tracked(updated_tracked)
        return
    
    # 3. 执行转存
    print(f"[3/3] 执行 115 转存...")
    
    tasks_json = json.dumps(new_tasks, ensure_ascii=False)
    
    # 检查 quark_auto_save.py 是否存在
    script_paths = [
        "./quark_auto_save.py",
        os.path.join(BASE_DIR, "quark_auto_save.py"),
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
        os.makedirs(OUTDIR, exist_ok=True)
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
    if not args.full:
        save_tracked(updated_tracked)
        print(f"\n  追踪记录已更新: {len(updated_tracked)} 条")
    print("  完成")

if __name__ == "__main__":
    main()

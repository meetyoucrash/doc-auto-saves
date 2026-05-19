#!/usr/bin/env python3
"""
kdocs_115_cron.py — KDocs 115 增量子转存 Cron 包装器
一次性完成: 提取 → 增量检测 → 任务注入 → 转存执行

用法:
  python3 kdocs_115_cron.py                    # 全流程执行
  python3 kdocs_115_cron.py --scrape-only      # 只提取数据
  python3 kdocs_115_cron.py --dry-run          # 只看新增，不转存
  
作为 cron 任务:
  0 */6 * * * cd /path/to/repo && python3 kdocs_115_cron.py >> cron_kdocs.log 2>&1
"""
import json, os, sys, subprocess, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE_DIR, "data/kdocs_115")
SCRAPER = os.path.join(BASE_DIR, "kdocs_115_scraper.py")
INJECTOR = os.path.join(BASE_DIR, "kdocs_115_injector.py")

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def scrape_kdocs():
    """运行提取器"""
    log("开始提取 KDocs 数据...")
    result = subprocess.run(
        ['python3', SCRAPER],
        capture_output=True, text=True, timeout=120
    )
    for line in result.stdout.split('\n'):
        if line.strip():
            log(line.strip())
    if result.stderr:
        for line in result.stderr.split('\n'):
            if line.strip():
                log(f"ERR: {line.strip()}")
    return result.returncode == 0

def run_injector(dry_run=False):
    """运行注入器"""
    cmd = ['python3', INJECTOR]
    if dry_run:
        cmd.append('--dry-run')
    log("运行增量注入...")
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600
    )
    for line in result.stdout.split('\n'):
        if line.strip():
            log(line.strip())
    if result.stderr and 'Traceback' in result.stderr:
        log(f"注入错误 ({os.path.basename(INJECTOR)}):")
        for line in result.stderr.split('\n')[-5:]:
            if line.strip():
                log(f"  {line.strip()}")
    return result.returncode == 0

def main():
    import argparse
    parser = argparse.ArgumentParser(description='KDocs 115 Cron')
    parser.add_argument('--scrape-only', action='store_true', help='只提取数据')
    parser.add_argument('--dry-run', action='store_true', help='只看新增，不转存')
    args = parser.parse_args()
    
    log("=== KDocs 115 定时增量子转存 ===")
    
    # Step 1: 提取
    if not scrape_kdocs():
        log("❌ 提取失败，终止")
        return 1
    
    if args.scrape_only:
        log("☑ 仅提取，完成")
        return 0
    
    # Step 2: 注入转存
    if not run_injector(dry_run=args.dry_run):
        log("⚠ 注入部分失败")
    
    log("== 完成 ==")
    return 0

if __name__ == "__main__":
    sys.exit(main())
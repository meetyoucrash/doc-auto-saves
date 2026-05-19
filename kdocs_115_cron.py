#!/usr/bin/env python3
"""
KDocs 115 定时任务包装器
顺序执行: scraper -> injector

用法:
  python3 kdocs_115_cron.py              # 完整流程
  python3 kdocs_115_cron.py --scrape-only # 只提取，不转存
  python3 kdocs_115_cron.py --dry-run     # 只预览，不执行
  python3 kdocs_115_cron.py --gen-tasks   # 只生成 TASKLIST JSON

环境变量:
  P115_COOKIE - 115 网盘 Cookie（用于调用 API 获取文件列表）
"""
import os, sys, json, subprocess

# BASE_DIR: 脚本所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_scraper():
    """运行提取器"""
    scraper = os.path.join(BASE_DIR, "kdocs_115_scraper.py")
    if not os.path.exists(scraper):
        print(f"错误: 提取器不存在: {scraper}")
        return None
    
    result = subprocess.run(
        [sys.executable, scraper],
        capture_output=True, text=True, timeout=300
    )
    
    if result.returncode != 0:
        print(f"提取器失败: {result.stderr[:500]}")
        return None
    
    print(result.stdout)
    return result.stdout

def run_injector(dry_run=False, gen_tasks=False, scrape_only=False):
    """运行注入器"""
    injector = os.path.join(BASE_DIR, "kdocs_115_injector.py")
    if not os.path.exists(injector):
        print(f"错误: 注入器不存在: {injector}")
        return None
    
    args = [sys.executable, injector]
    if dry_run:
        args.append("--dry-run")
    if gen_tasks:
        args.append("--gen-tasks")
    if scrape_only:
        args.append("--scrape-only")
    
    env = os.environ.copy()
    # 传递 115 cookie
    cookie = os.environ.get('P115_COOKIE', '')
    if cookie:
        env['P115_COOKIE'] = cookie
    
    result = subprocess.run(
        args,
        capture_output=True, text=True, timeout=600,
        env=env
    )
    
    if result.returncode != 0:
        print(f"注入器失败: {result.stderr[:500]}")
        return None
    
    if gen_tasks:
        # 输出 TASKLIST JSON
        print(result.stdout)
    else:
        print(result.stdout)
    
    return result.stdout

def main():
    import argparse
    parser = argparse.ArgumentParser(description='KDocs 115 定时任务包装器')
    parser.add_argument('--scrape-only', action='store_true', help='只提取，不转存')
    parser.add_argument('--dry-run', action='store_true', help='只预览，不执行')
    parser.add_argument('--gen-tasks', action='store_true', help='只生成 TASKLIST JSON')
    args = parser.parse_args()
    
    print("=== KDocs 115 定时任务 ===")
    
    # 1. 运行提取器
    if not args.gen_tasks:
        print("[1/2] 运行提取器...")
        scraper_output = run_scraper()
        if scraper_output is None:
            print("提取失败，跳过注入")
            return
    
    # 2. 运行注入器
    if args.scrape_only:
        print("[2/2] 跳过注入（--scrape-only）")
        return
    
    print("[2/2] 运行注入器...")
    injector_output = run_injector(
        dry_run=args.dry_run,
        gen_tasks=args.gen_tasks,
        scrape_only=args.scrape_only
    )
    
    if injector_output is None:
        print("注入失败")
        return
    
    print("\n=== 完成 ===")

if __name__ == "__main__":
    main()

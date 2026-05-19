#!/usr/bin/env python3
"""
KDocs 115 链接自动提取器
从金山文档数据库中逐行点击提取 115 分享链接
输出: /tmp/kdocs_115_data/records.json

纯 Playwright 自动化，无需大模型
"""
from playwright.sync_api import sync_playwright
import json, os, re, sys

UI_SET = {
    '115追番', '仅查看', '脚本', '自动化流程', '插件', '分享', '高级权限',
    '资源汇总', '表格视图', '创建', '从模板新建', '导入/同步数据', '添加记录',
    '字段管理(17 隐藏)', '排序', '分组', '行高', '公告', '查找', '分享视图',
    '添加字段', '隐藏字段（17）', '添加插件', '116', '11',
    '立即登录', '新建', '筛选', '(2)', '登录并查看',
    '详情', '评论', '动态', '网盘', '名称', '规格信息', '提取码',
}

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data/kdocs_115")

def get_lines(page):
    """获取过滤后的文本行（支持各种换行符）"""
    text = page.evaluate("() => document.body.innerText")
    parts = re.split(r'[\r\n]+', text)
    result = []
    for s in parts:
        s = s.strip()
        if not s or len(s) < 2:
            continue
        if any(s.startswith(p) for p in ['var ', '.kd-', '!function', 'window.__', 'function ', 'export ', 'import ']):
            continue
        if len(s) > 300:
            continue
        result.append(s)
    return result

def parse_panel(lines):
    """从右面板 DOM 文本解析字段"""
    data = {'网盘': '115', '规格信息': '', '提取码': '', '更新时间': ''}
    n = len(lines)
    start = max(0, n // 2)
    
    i = start
    while i < n:
        line = lines[i].strip()
        
        if line.startswith('http') and '115cdn' in line:
            # 保留完整 URL（含 ?password=xxx）
            data['链'] = line
            # 从 URL 中提取 password
            pw_match = re.search(r'[?&](?:password|pwd)=([^&\s]+)', line)
            if pw_match and pw_match.group(1) != '***':
                data['提取码'] = pw_match.group(1)
            i += 1
            continue
        
        if line == '网盘' and i + 1 < n:
            data['网盘'] = lines[i + 1]
            i += 2
            continue
        
        if line == '名称' and i + 1 < n:
            val = lines[i + 1]
            if len(val) > 10 or '剧集' in val or '动漫' in val or '综艺' in val:
                data['名称'] = val
            i += 2
            continue
        
        if line == '规格信息':
            j = i + 1
            while j < n and lines[j] in UI_SET:
                j += 1
            if j < n and lines[j].startswith('http') and '115cdn' in lines[j]:
                # 保留完整 URL（含 ?password=xxx）
                if '链' not in data:
                    data['链'] = lines[j]
                    # 从 URL 中提取 password
                    pw_match = re.search(r'[?&](?:password|pwd)=([^&\s]+)', lines[j])
                    if pw_match and pw_match.group(1) != '***':
                        data['提取码'] = pw_match.group(1)
            elif j < n and not lines[j].startswith('http') and not re.match(r'\d{2}/\d{2} \d{2}:\d{2}', lines[j]):
                data['规格信息'] = lines[j]
            i += 1
            continue
        
        if line == '提取码':
            j = i + 1
            while j < n and lines[j] in UI_SET:
                j += 1
            if j < n:
                nv = lines[j]
                if nv not in ('更新时间', '隐藏字段（17）', '添加字段', '网盘', '名称', '规格信息', '提取码') \
                   and not re.match(r'\d{2}/\d{2} \d{2}:\d{2}', nv) \
                   and not nv.startswith('http'):
                    data['提取码'] = nv
            i += 1
            continue
        
        if line == '更新时间':
            j = i + 1
            while j < n and lines[j] in UI_SET:
                j += 1
            if j < n:
                val = lines[j]
                if re.match(r'\d{2}/\d{2} \d{2}:\d{2}', val):
                    data['更新时间'] = val
            i += 1
            continue
        
        i += 1
    
    return data

def extract_all(url, progress=True):
    """主提取函数"""
    os.makedirs(OUTDIR, exist_ok=True)
    records = []
    seen_urls = set()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        
        if progress: print("[1/4] 加载页面...")
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(15000)
        
        # 清除遮挡弹窗
        page.evaluate("""() => {
            const sel = 'div[class*="guide"], div[class*="login"], div[class*="overlay"], ' +
                        'div[class*="mask"], div[class*="modal"], div[class*="dialog"]';
            document.querySelectorAll(sel).forEach(el => el.remove());
        }""")
        page.wait_for_timeout(2000)
        
        c = page.evaluate("""() => {
            const cv = document.querySelector('canvas');
            if (!cv) return {x: 264, y: 94};
            const r = cv.getBoundingClientRect();
            return {x: r.x, y: r.y};
        }""")
        
        if progress: print(f"[2/4] Canvas 就绪")
        if progress: print(f"[3/4] 扫描提取中...")
        
        def try_extract(y_off):
            page.mouse.click(c['x'] + 60, c['y'] + y_off)
            page.wait_for_timeout(500)
            lines = get_lines(page)
            data = parse_panel(lines)
            name = data.get('名称', '')
            url_raw = data.get('链', '')
            if not name or not url_raw or url_raw in seen_urls:
                return False
            seen_urls.add(url_raw)
            records.append(data)
            if progress:
                code = data.get('提取码', '') or '空'
                print(f"  ✓ #{len(records):2d}: {name[:33]:33s} 提取码={code} | {data.get('更新时间','')}")
            return True
        
        # 主扫描: 每28px
        for y in range(10, 700, 28):
            try_extract(y)
            if y % 420 == 0 and y > 10:
                page.evaluate("window.scrollBy(0, 400)")
                page.wait_for_timeout(1000)
        
        # 补扫: +14px 偏移（覆盖空缺位置）
        for y in range(10, 700, 28):
            try_extract(y + 14)
        
        page.screenshot(path=f"{OUTDIR}/result.png")
        browser.close()
    
    if progress: print(f"[4/4] 提取完成: {len(records)} 条")
    return records

def scrape(url="https://www.kdocs.cn/l/ciyPP80yjloc"):
    """对外接口: 提取并保存"""
    records = extract_all(url)
    records.sort(key=lambda r: r.get('更新时间', ''), reverse=True)
    
    outfile = os.path.join(OUTDIR, "records.json")
    with open(outfile, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果: {outfile} ({len(records)} 条)")
    return records

if __name__ == "__main__":
    scrape()
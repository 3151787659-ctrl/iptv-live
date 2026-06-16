#!/usr/bin/env python3
"""
IPTV 直播源自动更新脚本 - 用于 GitHub Actions
每天自动下载最新源 → 测速筛选 → 更新 cq_live.m3u
"""

import re, time, urllib.request, urllib.error, json, base64, os, sys
from datetime import datetime

def download_m3u(url, timeout=30):
    """下载 M3U 文件"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='ignore')

def parse_m3u(content):
    """解析 M3U 内容为频道列表"""
    lines = content.strip().split('\n')
    channels = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            extinf = line
            url = lines[i+1].strip() if i+1 < len(lines) else ''
            channels.append((extinf, url))
            i += 2
        else:
            i += 1
    return channels

def test_stream(name, url, timeout=6):
    """测试单个直播源：响应时间 + 码率"""
    result = {
        'name': name,
        'url': url,
        'ok': False,
        'ms': 99999,
        'bandwidth': 0,
        'quality': '?',
    }
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*'
        })
        start = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.time() - start) * 1000
            result['ms'] = int(elapsed)
            # 读取前 32KB 解析 m3u8 中的 BANDWIDTH
            try:
                chunk = resp.read(32768).decode('utf-8', errors='ignore')
                bw_values = [int(m) for m in re.findall(r'BANDWIDTH=(\d+)', chunk)]
                if bw_values:
                    result['bandwidth'] = max(bw_values)
            except:
                pass
            
            # 判断画质
            bw = result['bandwidth']
            if bw >= 15000000:
                result['quality'] = '4K'
            elif bw >= 5000000:
                result['quality'] = '1080p+'
            elif bw >= 2500000:
                result['quality'] = '1080p'
            elif bw >= 1200000:
                result['quality'] = '720p'
            elif bw > 0:
                result['quality'] = f'{bw//1000}k'
            else:
                # 无 BANDWIDTH 标记，从名称判断
                if '4K' in name or '2160' in name:
                    result['quality'] = '4K?'
                elif '1080' in name or 'HD' in name:
                    result['quality'] = '1080p?'
                else:
                    result['quality'] = 'unknown'
            
            result['ok'] = True
    except Exception as e:
        pass
    return result

def get_cqccn_sources():
    """获取重庆地方频道源（硬编码备用，因为 cqccn 需要本地网络）"""
    # 这些源可能只在重庆本地可用，作为备用
    return {
        '重庆卫视': 'http://36.32.174.67:60080/newlive/live/hls/34/live.m3u8',
        '重庆新闻': 'http://36.32.174.67:60080/newlive/live/hls/35/live.m3u8',
        '重庆影视': 'http://36.32.174.67:60080/newlive/live/hls/36/live.m3u8',
        '重庆文体娱乐': 'http://36.32.174.67:60080/newlive/live/hls/37/live.m3u8',
        '重庆少儿': 'http://36.32.174.67:60080/newlive/live/hls/38/live.m3u8',
        '重庆时尚生活': 'http://36.32.174.67:60080/newlive/live/hls/39/live.m3u8',
        '重庆科教': 'http://36.32.174.67:60080/newlive/live/hls/40/live.m3u8',
    }

def main():
    print(f"[{datetime.now()}] IPTV 直播源自动更新开始")
    
    # 1. 下载最新源
    print("\n[1/4] 下载最新直播源...")
    try:
        zbds_content = download_m3u('https://live.zbds.top/tv/iptv4.m3u', timeout=60)
        print(f"  zbds.top: {len(zbds_content)} bytes")
    except Exception as e:
        print(f"  zbds.top 下载失败: {e}")
        # 使用已有的文件
        if os.path.exists('cq_live.m3u'):
            zbds_content = open('cq_live.m3u', 'r', encoding='utf-8').read()
            print("  使用本地缓存")
        else:
            print("  无本地缓存，退出")
            return
    
    # 2. 解析频道
    print("\n[2/4] 解析频道...")
    all_channels = parse_m3u(zbds_content)
    print(f"  共 {len(all_channels)} 个频道")
    
    # 3. 筛选：CCTV + 卫视 + 重庆 + 4K
    print("\n[3/4] 筛选频道...")
    filtered = []
    for extinf, url in all_channels:
        name_match = re.search(r',(.+)$', extinf)
        name = name_match.group(1).strip() if name_match else ''
        if re.search(r'CCTV|卫视|重庆|4K', name):
            filtered.append((extinf, url, name))
    
    print(f"  筛选后: {len(filtered)} 个频道")
    
    # 4. 测速（GitHub Actions 环境，网络不同，主要测可达性）
    print("\n[4/4] 测速筛选...")
    fast_channels = []
    
    for i, (extinf, url, name) in enumerate(filtered):
        print(f"  [{i+1}/{len(filtered)}] {name[:20]:20s} ... ", end='', flush=True)
        r = test_stream(name, url, timeout=6)
        if r['ok']:
            bw_mbps = r['bandwidth'] / 1000000 if r['bandwidth'] > 0 else 0
            print(f"{r['ms']}ms  {r['quality']:8s}")
            # 保留条件：响应<5000ms（GitHub 服务器网络好）
            if r['ms'] < 5000:
                fast_channels.append((extinf, url))
        else:
            print("timeout")
    
    # 5. 生成 M3U
    print(f"\n生成 M3U: {len(fast_channels)} 个频道")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    lines = [
        '#EXTM3U',
        f'#PLAYLIST: 雪月IPTV（每日自动更新）',
        f'#Generated: {now}',
        '#Source: https://live.zbds.top/tv/iptv4.m3u',
        '',
    ]
    
    # 按分组排序
    groups_order = ['4K频道', '央视频道', '卫视频道', '重庆地方']
    grouped = {g: [] for g in groups_order}
    ungrouped = []
    
    for extinf, url in fast_channels:
        g = re.search(r'group-title="([^"]+)"', extinf)
        grp = g.group(1) if g else ''
        if grp in grouped:
            grouped[grp].append((extinf, url))
        else:
            ungrouped.append((extinf, url))
    
    for grp in groups_order:
        for extinf, url in grouped[grp]:
            lines.append(extinf)
            lines.append(url)
    
    for extinf, url in ungrouped:
        lines.append(extinf)
        lines.append(url)
    
    output = '\n'.join(lines) + '\n'
    
    with open('cq_live.m3u', 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"  输出: cq_live.m3u ({len(output)} bytes)")
    print(f"\n[{datetime.now()}] 更新完成 ✅")

if __name__ == '__main__':
    main()

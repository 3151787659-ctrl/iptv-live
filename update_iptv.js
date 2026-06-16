/**
 * update_iptv.js — 每日自动更新直播源
 * 从多个在线源抓取最新URL，合并输出cq_live.m3u
 */

const https = require('https');
const fs = require('fs');
const { execSync } = require('child_process');

// 抓取URL内容（Promise封装）
function fetchText(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: 10000 }, res => {
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error(`Timeout: ${url}`)); });
  });
}

// 解析M3U内容，返回 { name, logo, group, urls: [] }
function parseM3U(text) {
  const lines = text.split('\n');
  const channels = [];
  let current = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('#EXTINF')) {
      // 解析属性
      const nameMatch = trimmed.match(/tvg-name="([^"]*)"/);
      const logoMatch = trimmed.match(/tvg-logo="([^"]*)"/);
      const groupMatch = trimmed.match(/group-title="([^"]*)"/);
      const nameAfterComma = trimmed.split(',').slice(1).join(',').trim();

      current = {
        name: nameMatch ? nameMatch[1] : nameAfterComma,
        logo: logoMatch ? logoMatch[1] : '',
        group: groupMatch ? groupMatch[1] : '',
        urls: []
      };
    } else if (current && trimmed && !trimmed.startsWith('#')) {
      current.urls.push(trimmed);
      channels.push(current);
      current = null;
    }
  }
  return channels;
}

// 主更新逻辑
async function main() {
  console.log(`[${new Date().toISOString()}] 开始更新直播源...`);

  const sources = [
    {
      name: 'lalifeier/IPTV (IPv4)',
      url: 'https://raw.githubusercontent.com/lalifeier/IPTV/main/m3u/IPTV.m3u',
      priority: 1
    },
    {
      name: 'zbds.top IPv4',
      url: 'https://live.zbds.top/tv/iptv4.m3u',
      priority: 2
    },
    {
      name: 'fanmingming IPv6',
      url: 'https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u',
      priority: 3
    }
  ];

  const allChannels = new Map(); // name -> { logo, group, urls: Set }

  for (const src of sources) {
    try {
      console.log(`  抓取: ${src.name}...`);
      const text = await fetchText(src.url);
      const channels = parseM3U(text);
      console.log(`  ✅ ${src.name}: ${channels.length} 条目`);

      for (const ch of channels) {
        if (!ch.name) continue;
        if (!allChannels.has(ch.name)) {
          allChannels.set(ch.name, {
            logo: ch.logo,
            group: ch.group,
            urls: new Set()
          });
        }
        const entry = allChannels.get(ch.name);
        // 如果新源有logo且旧源没有，更新logo
        if (ch.logo && !entry.logo) entry.logo = ch.logo;
        if (ch.group && !entry.group) entry.group = ch.group;
        for (const url of ch.urls) {
          entry.urls.add(url);
        }
      }
    } catch (e) {
      console.log(`  ❌ ${src.name}: ${e.message}`;
    }
  }

  // 生成M3U内容
  let m3u = '#EXTM3U x-tvg-url="https://epg.51zmt.top:8000/e.xml"\n\n';
  m3u += '# 圆圆IPTV直播源 — 自动更新\n';
  m3u += `# 更新时间: ${new Date().toISOString().split('T')[0]}\n\n`;

  // 按分组排序：央视 → 卫视 → 其他
  const groupOrder = ['央视', '卫视频道', '重庆', 'CGTN', '教育', '休闲'];
  const sortedChannels = [...allChannels.entries()].sort((a, b) => {
    const ga = groupOrder.indexOf(a[1].group) >= 0 ? groupOrder.indexOf(a[1].group) : 999;
    const gb = groupOrder.indexOf(b[1].group) >= 0 ? groupOrder.indexOf(b[1].group) : 999;
    if (ga !== gb) return ga - gb;
    return a[0].localeCompare(b[0], 'zh');
  });

  for (const [name, data] of sortedChannels) {
    const urls = [...data.urls].slice(0, 3); // 最多3个备用源
    for (let i = 0; i < urls.length; i++) {
      const suffix = i === 0 ? '' : ` [备用${i}]`;
      m3u += `#EXTINF:-1 tvg-name="${name}" tvg-logo="${data.logo}" group-title="${data.group}",${name}${suffix}\n`;
      m3u += `${urls[i]}\n`;
    }
  }

  // 写入文件
  const outputPath = 'cq_live.m3u';
  fs.writeFileSync(outputPath, m3u, 'utf-8');
  const entryCount = (m3u.match(/#EXTINF/g) || []).length;
  console.log(`\n✅ 更新完成！频道数: ${allChannels.size}, 条目数: ${entryCount}`);
  console.log(`   文件: ${outputPath}`);
}

main().catch(e => {
  console.error('更新失败:', e.message);
  process.exit(1);
});

#!/usr/bin/env node
'use strict';

// npx 只负责取得发布包；安装仍复用经哈希校验、备份和回滚保护的 Python 安装器。
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

function main(argv) {
  const metadata = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(`GM Scene Handoff ${metadata.version}

用法：gm-scene-handoff [install|update|status] [选项]
  install / update       安装本次下载的发布版本；重复执行时检查并升级
  status                 只读查询本机已安装的版本、目录和文件完整性
  --workspace <目录>     同时停用指定 GMGame 项目内的旧技能入口
  --python <程序路径>    指定 Python 3.11+，默认自动寻找
  --user-home <目录>     自定义个人安装根目录
  --codex-home <目录>    自定义 Codex 配置目录
  --json                 输出机器可读的安装结果
  --version              显示本次发布包的版本

不指定 --workspace 时可从任意目录安装。实际使用仍需要 GMGame、Git、Unity 和 Unity MCP。`);
    return 0;
  }
  if (argv.length === 1 && argv[0] === '--version') {
    console.log(metadata.version);
    return 0;
  }
  const args = [...argv];
  const command = ['install', 'update', 'status'].includes(args[0]) ? args.shift() : 'install';
  const options = new Map();
  let json = false;
  const valueFlags = new Set(['--workspace', '--python', '--user-home', '--codex-home']);
  while (args.length) {
    const flag = args.shift();
    if (flag === '--json' && !json) { json = true; continue; }
    if (!valueFlags.has(flag) || options.has(flag) || !args.length || args[0].startsWith('--')) {
      throw new Error(`参数无效或缺少值：${flag}。运行 --help 查看用法。`);
    }
    options.set(flag, args.shift());
  }
  if (command === 'status' && (options.has('--workspace') || options.has('--codex-home'))) {
    throw new Error('status 只检查个人技能目录；自定义位置请使用 --user-home。');
  }
  const probe = 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)';
  const candidates = options.has('--python') ? [[options.get('--python')]] :
    (process.platform === 'win32' ? [['py', '-3'], ['python'], ['python3']] : [['python3'], ['python']]);
  const python = candidates.find(([command, ...prefix]) =>
    spawnSync(command, [...prefix, '-B', '-c', probe], { encoding: 'utf8', timeout: 15000 }).status === 0);
  if (!python) throw new Error('未找到 Python 3.11+。请先安装，或使用 --python 指定程序路径。');
  const script = path.join(__dirname, 'skill', 'scripts', 'install.py');
  const installArgs = [...python.slice(1), '-B', '-X', 'utf8', script];
  if (command === 'status') installArgs.push('--status');
  if (options.has('--workspace')) installArgs.push('--workspace', path.resolve(options.get('--workspace')));
  else installArgs.push('--global');
  for (const flag of ['--user-home', '--codex-home']) {
    if (options.has(flag)) installArgs.push(flag, path.resolve(options.get(flag)));
  }
  const result = spawnSync(python[0], installArgs, { encoding: 'utf8', maxBuffer: 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error((result.stderr || result.stdout || '安装进程未正常结束').trim());
  const receipt = JSON.parse(result.stdout);
  if (json) console.log(JSON.stringify(receipt, null, 2));
  else if (command === 'status') {
    console.log(receipt.status === 'not_installed' ? '本地尚未安装 GM Scene Handoff。' :
      `本地已安装版本：GM Scene Handoff ${receipt.version}`);
    console.log(`位置：${receipt.installed}`);
    console.log(`本次下载包版本：${receipt.available_version}`);
    if (receipt.status === 'installed') console.log(`文件完整性：${receipt.files_verified} 个文件校验通过。`);
  }
  else {
    if (receipt.status === 'unchanged') console.log(`已经是完整的当前发布版本：GM Scene Handoff ${receipt.version}`);
    else if (receipt.previous_version && receipt.previous_version !== receipt.version) {
      console.log(`更新完成：GM Scene Handoff ${receipt.previous_version} → ${receipt.version}`);
    } else console.log(`安装完成：GM Scene Handoff ${receipt.version}`);
    console.log(`位置：${receipt.installed}`);
    if (receipt.backup) console.log(`备份：${receipt.backup}`);
    if (receipt.project) console.log(`项目：${receipt.project.project}`);
    if (receipt.restart_codex) console.log('请刷新技能列表；未显示新版时重启 Codex。');
    console.log('在 GMGame 项目中调用 $gm-scene-handoff。安装不会执行场景合并。');
  }
  return 0;
}

if (require.main === module) {
  try { process.exitCode = main(process.argv.slice(2)); }
  catch (error) { console.error(`操作失败：${error.message}`); process.exitCode = 1; }
}

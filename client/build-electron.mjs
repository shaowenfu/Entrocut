/**
 * Electron 主进程打包脚本
 *
 * 使用 esbuild 将 TypeScript 编译为 CommonJS 格式
 */

import { build } from 'esbuild';
import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ============================================
// 配置
// ============================================

const BASE_CONFIG = {
  platform: 'node',
  target: 'node18',
  format: 'cjs',
  sourcemap: true,
  bundle: true,
  external: [
    'electron',
    'path',
    'url',
    'child_process',
    'fs',
    'os',
    'better-sqlite3',
  ],
};

// ============================================
// 构建
// ============================================

async function buildMain() {
  console.log('🔨 Building Electron main process...');

  try {
    // 构建 main.cjs
    await build({
      ...BASE_CONFIG,
      entryPoints: ['main/main.ts'],
      outfile: 'dist-main/main.cjs',
    });

    // 构建 preload.cjs
    await build({
      ...BASE_CONFIG,
      entryPoints: ['main/preload.ts'],
      outfile: 'dist-main/preload.cjs',
    });

    // 构建 sidecar.cjs
    await build({
      ...BASE_CONFIG,
      entryPoints: ['main/sidecar.ts'],
      outfile: 'dist-main/sidecar.cjs',
    });

    console.log('✅ Build completed!');
  } catch (error) {
    console.error('❌ Build failed:', error);
    process.exit(1);
  }
}

buildMain();

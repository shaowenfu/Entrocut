/**
 * EntroCut Brand Icon Component
 *
 * 设计概念: AI 魔法闪光
 * - 四角星/魔法闪光 - AI 的魔法感和智能
 * - 渐变背景 - 品牌色 (Indigo → Cyan)
 * - 用于顶部栏、启动页等品牌展示位置
 */

import type { CSSProperties } from "react";

interface BrandIconProps {
  /** 图标尺寸，默认 28 */
  size?: number;
  /** 额外的 className */
  className?: string;
  /** 额外的 style */
  style?: CSSProperties;
}

export function BrandIcon({ size = 28, className, style }: BrandIconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={className}
      style={style}
      aria-label="EntroCut"
      role="img"
    >
      <defs>
        <linearGradient id="brandIconGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: "#6d63ff" }} />
          <stop offset="50%" style={{ stopColor: "#9a63ff" }} />
          <stop offset="100%" style={{ stopColor: "#4ad3f5" }} />
        </linearGradient>
        <linearGradient id="sparkleGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: "#ffffff" }} />
          <stop offset="100%" style={{ stopColor: "#4ad3f5" }} />
        </linearGradient>
      </defs>

      {/* 圆角矩形背景 */}
      <rect x="2" y="2" width="28" height="28" rx="6" ry="6" fill="url(#brandIconGradient)" />

      {/* 主闪光星 */}
      <polygon
        points="16,6 18,14 26,16 18,18 16,26 14,18 6,16 14,14"
        fill="url(#sparkleGradient)"
        opacity="0.95"
      />

      {/* 内部小闪光 */}
      <polygon
        points="16,10 17,15 22,16 17,17 16,22 15,17 10,16 15,15"
        fill="#ffffff"
        opacity="0.85"
      />
    </svg>
  );
}

export default BrandIcon;

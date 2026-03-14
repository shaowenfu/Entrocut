import { forwardRef, type HTMLAttributes } from "react";
import "./StatusBadge.css";

export type StatusState = "online" | "offline" | "checking";

export interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  state: StatusState;
  label?: string;
  showDot?: boolean;
  size?: "sm" | "md";
  variant?: "default" | "pill";
}

/**
 * StatusBadge - 状态指示器组件
 * 替换健康状态 pills，使用点 + 标签模式
 */
export const StatusBadge = forwardRef<HTMLSpanElement, StatusBadgeProps>(
  (
    {
      state,
      label,
      showDot = true,
      size = "sm",
      variant = "pill",
      className = "",
      ...props
    },
    ref
  ) => {
    const classNames = [
      "status-badge",
      `status-${state}`,
      `status-${size}`,
      `status-${variant}`,
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <span ref={ref} className={classNames} {...props}>
        {showDot && <span className="status-dot" />}
        {label && <span className="status-label">{label}</span>}
      </span>
    );
  }
);

StatusBadge.displayName = "StatusBadge";

export default StatusBadge;

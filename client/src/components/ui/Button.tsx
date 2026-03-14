import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  iconPosition?: "left" | "right";
  isLoading?: boolean;
  fullWidth?: boolean;
}

/**
 * Button - 统一的按钮组件
 *
 * 变体：
 * - primary: 主要操作按钮（渐变背景）
 * - secondary: 次要操作按钮（边框样式）
 * - ghost: 幽灵按钮（透明背景）
 *
 * 尺寸：
 * - sm: 32px 高度
 * - md: 38px 高度
 * - lg: 44px 高度
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "secondary",
      size = "md",
      icon,
      iconPosition = "left",
      isLoading = false,
      fullWidth = false,
      className = "",
      children,
      disabled,
      ...props
    },
    ref
  ) => {
    const classNames = [
      "btn",
      `btn-${variant}`,
      `btn-${size}`,
      fullWidth && "btn-full-width",
      isLoading && "btn-loading",
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <button
        ref={ref}
        className={classNames}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && <span className="btn-spinner" />}
        {icon && iconPosition === "left" && !isLoading && (
          <span className="btn-icon">{icon}</span>
        )}
        {children && <span className="btn-text">{children}</span>}
        {icon && iconPosition === "right" && !isLoading && (
          <span className="btn-icon">{icon}</span>
        )}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;

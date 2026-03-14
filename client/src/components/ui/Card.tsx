import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import "./Card.css";

export type CardVariant = "default" | "elevated" | "interactive";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  padding?: "none" | "sm" | "md" | "lg";
  active?: boolean;
}

export interface CardHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}

export interface CardBodyProps extends HTMLAttributes<HTMLDivElement> {
  /** 是否撑满剩余空间 */
  flex?: boolean;
}

export interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {}

/**
 * Card - 统一的卡片组件
 *
 * 变体：
 * - default: 默认样式，适合静态内容
 * - elevated: 提升阴影，适合重要内容
 * - interactive: 可交互样式，有 hover 效果
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(
  (
    {
      variant = "default",
      padding = "md",
      active = false,
      className = "",
      children,
      ...props
    },
    ref
  ) => {
    const classNames = [
      "card",
      `card-${variant}`,
      `card-padding-${padding}`,
      active && "card-active",
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <article ref={ref} className={classNames} {...props}>
        {children}
      </article>
    );
  }
);

Card.displayName = "Card";

/**
 * CardHeader - 卡片头部
 */
export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ title, subtitle, action, className = "", children, ...props }, ref) => {
    const classNames = ["card-header", className].filter(Boolean).join(" ");

    return (
      <header ref={ref} className={classNames} {...props}>
        {(title || subtitle) && (
          <div className="card-header-content">
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <span className="card-subtitle">{subtitle}</span>}
          </div>
        )}
        {action && <div className="card-header-action">{action}</div>}
        {children}
      </header>
    );
  }
);

CardHeader.displayName = "CardHeader";

/**
 * CardBody - 卡片主体
 */
export const CardBody = forwardRef<HTMLDivElement, CardBodyProps>(
  ({ flex = false, className = "", children, ...props }, ref) => {
    const classNames = ["card-body", flex && "card-body-flex", className]
      .filter(Boolean)
      .join(" ");

    return (
      <div ref={ref} className={classNames} {...props}>
        {children}
      </div>
    );
  }
);

CardBody.displayName = "CardBody";

/**
 * CardFooter - 卡片底部
 */
export const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ className = "", children, ...props }, ref) => {
    const classNames = ["card-footer", className].filter(Boolean).join(" ");

    return (
      <footer ref={ref} className={classNames} {...props}>
        {children}
      </footer>
    );
  }
);

CardFooter.displayName = "CardFooter";

export default Card;

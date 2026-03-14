import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from "react";
import "./Input.css";

export type InputSize = "sm" | "md" | "lg";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: InputSize;
  icon?: ReactNode;
  iconPosition?: "left" | "right";
  error?: boolean;
  errorMessage?: string;
  fullWidth?: boolean;
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
  errorMessage?: string;
  fullWidth?: boolean;
}

/**
 * Input - 统一的文本输入组件
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      size = "md",
      icon,
      iconPosition = "left",
      error = false,
      errorMessage,
      fullWidth = false,
      className = "",
      ...props
    },
    ref
  ) => {
    const containerClasses = [
      "input-container",
      fullWidth && "input-full-width",
      className,
    ]
      .filter(Boolean)
      .join(" ");

    const inputClasses = [
      "input",
      `input-${size}`,
      icon && `input-with-icon input-icon-${iconPosition}`,
      error && "input-error",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div className={containerClasses}>
        <div className="input-wrapper">
          {icon && iconPosition === "left" && (
            <span className="input-icon input-icon-left">{icon}</span>
          )}
          <input ref={ref} className={inputClasses} {...props} />
          {icon && iconPosition === "right" && (
            <span className="input-icon input-icon-right">{icon}</span>
          )}
        </div>
        {error && errorMessage && (
          <span className="input-error-message">{errorMessage}</span>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";

/**
 * Textarea - 统一的多行文本输入组件
 */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      error = false,
      errorMessage,
      fullWidth = false,
      className = "",
      ...props
    },
    ref
  ) => {
    const containerClasses = [
      "input-container",
      fullWidth && "input-full-width",
      className,
    ]
      .filter(Boolean)
      .join(" ");

    const textareaClasses = ["textarea", error && "input-error"]
      .filter(Boolean)
      .join(" ");

    return (
      <div className={containerClasses}>
        <textarea ref={ref} className={textareaClasses} {...props} />
        {error && errorMessage && (
          <span className="input-error-message">{errorMessage}</span>
        )}
      </div>
    );
  }
);

Textarea.displayName = "Textarea";

export default Input;

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ChevronDown, LogIn, LogOut, ShieldCheck, WalletCards } from "lucide-react";
import { createPortal } from "react-dom";
import { useAuthStore } from "../../store/useAuthStore";
import "./AccountMenu.css";

type AccountMenuVariant = "launchpad" | "workspace";

interface AccountMenuProps {
  variant?: AccountMenuVariant;
}

type CreditsTone = "neutral" | "healthy" | "warning" | "danger";
type PopoverPosition = {
  top: number;
  left: number;
  arrowLeft: number;
};

function humanizeToken(value: string | null | undefined, fallback: string): string {
  const normalized = value?.trim();
  if (!normalized) {
    return fallback;
  }
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getDisplayName(email: string | null | undefined, displayName: string | null | undefined): string {
  const normalizedName = displayName?.trim();
  if (normalizedName) {
    return normalizedName;
  }
  const normalizedEmail = email?.trim();
  if (normalizedEmail) {
    return normalizedEmail.split("@")[0] ?? normalizedEmail;
  }
  return "Guest";
}

function getInitials(label: string): string {
  const words = label
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (words.length === 0) {
    return "GU";
  }
  return words.map((word) => word.slice(0, 1).toUpperCase()).join("");
}

function getCreditsTone(quotaStatus: string | null | undefined): CreditsTone {
  const normalized = quotaStatus?.trim().toLowerCase() ?? "";
  if (!normalized) {
    return "neutral";
  }
  if (/(exhaust|empty|deplet|limit_reached|blocked)/.test(normalized)) {
    return "danger";
  }
  if (/(warn|limit|low|near|trial)/.test(normalized)) {
    return "warning";
  }
  if (/(ok|active|available|healthy|ready)/.test(normalized)) {
    return "healthy";
  }
  return "neutral";
}

function getCreditsSummary(
  authStatus: string,
  plan: string | null | undefined,
  quotaStatus: string | null | undefined
): { label: string; detail: string; tone: CreditsTone } {
  if (authStatus !== "authenticated") {
    return {
      label: "Guest mode",
      detail: "Sign in to unlock cloud features",
      tone: "neutral",
    };
  }
  const tone = getCreditsTone(quotaStatus);
  const quotaLabel = humanizeToken(quotaStatus, "Not synced");
  const planLabel = humanizeToken(plan, "Standard");
  if (tone === "danger") {
    return {
      label: "Action needed",
      detail: `${quotaLabel} on ${planLabel}`,
      tone,
    };
  }
  if (tone === "warning") {
    return {
      label: "Monitor usage",
      detail: `${quotaLabel} on ${planLabel}`,
      tone,
    };
  }
  if (tone === "healthy") {
    return {
      label: "Available",
      detail: `${planLabel} plan`,
      tone,
    };
  }
  return {
    label: quotaLabel,
    detail: `${planLabel} plan`,
    tone,
  };
}

function AccountMenu({ variant = "workspace" }: AccountMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState<PopoverPosition | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const authStatus = useAuthStore((state) => state.status);
  const authUser = useAuthStore((state) => state.user);
  const startGoogleLogin = useAuthStore((state) => state.startGoogleLogin);
  const logout = useAuthStore((state) => state.logout);

  const displayName = useMemo(
    () => getDisplayName(authUser?.email, authUser?.display_name),
    [authUser?.display_name, authUser?.email]
  );
  const initials = useMemo(() => getInitials(displayName), [displayName]);
  const credits = useMemo(
    () => getCreditsSummary(authStatus, authUser?.plan, authUser?.quota_status),
    [authStatus, authUser?.plan, authUser?.quota_status]
  );
  const profileLabel = authStatus === "authenticated" ? "Signed in" : "Guest session";
  const profileDetail =
    authStatus === "authenticated"
      ? authUser?.email?.trim() || "Account connected"
      : "Local work stays available before login";

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    function handlePointerDown(event: PointerEvent) {
      const targetNode = event.target as Node;
      if (shellRef.current?.contains(targetNode) || popoverRef.current?.contains(targetNode)) {
        return;
      }
      setIsOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  useLayoutEffect(() => {
    if (!isOpen) {
      setPopoverPosition(null);
      return;
    }

    function updatePopoverPosition() {
      const triggerRect = shellRef.current?.getBoundingClientRect();
      const popoverRect = popoverRef.current?.getBoundingClientRect();
      if (!triggerRect || !popoverRect) {
        return;
      }

      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const margin = 12;
      const popoverWidth = popoverRect.width;
      const popoverHeight = popoverRect.height;

      const left = Math.min(
        Math.max(margin, triggerRect.right - popoverWidth),
        viewportWidth - margin - popoverWidth
      );
      const top = Math.min(
        Math.max(margin, triggerRect.bottom + 14),
        viewportHeight - margin - popoverHeight
      );
      const arrowAnchorX = Math.min(
        Math.max(triggerRect.right - 30, left + 24),
        left + popoverWidth - 24
      );

      setPopoverPosition({
        top,
        left,
        arrowLeft: arrowAnchorX - left,
      });
    }

    updatePopoverPosition();
    const rafId = window.requestAnimationFrame(updatePopoverPosition);
    window.addEventListener("resize", updatePopoverPosition);
    window.addEventListener("scroll", updatePopoverPosition, true);

    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener("resize", updatePopoverPosition);
      window.removeEventListener("scroll", updatePopoverPosition, true);
    };
  }, [isOpen]);

  async function handlePrimaryAction() {
    setIsOpen(false);
    if (authStatus === "authenticated") {
      await logout();
      return;
    }
    await startGoogleLogin();
  }

  const popoverStyle: (CSSProperties & Record<"--account-popover-arrow-left", string>) | undefined = popoverPosition
    ? {
        top: popoverPosition.top,
        left: popoverPosition.left,
        "--account-popover-arrow-left": `${popoverPosition.arrowLeft}px`,
      }
    : undefined;

  const popover =
    isOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={popoverRef}
            className="account-popover"
            style={popoverStyle}
            role="menu"
            aria-label="profile menu"
          >
            <div className="account-popover-header">
              <div className="account-popover-avatar">{initials}</div>
              <div className="account-popover-copy">
                <span className="account-popover-eyebrow">Profile</span>
                <strong>{displayName}</strong>
                <span>{profileDetail}</span>
              </div>
            </div>

            <div className="account-summary-grid">
              <article className="account-summary-card">
                <span>Plan</span>
                <strong>{humanizeToken(authUser?.plan, authStatus === "authenticated" ? "Standard" : "Guest")}</strong>
                <small>{authStatus === "authenticated" ? "Current account tier" : "Local-first workspace"}</small>
              </article>
              <article className={`account-summary-card account-summary-card-${credits.tone}`}>
                <span>Credits</span>
                <strong>{credits.label}</strong>
                <small>{credits.detail}</small>
              </article>
            </div>

            <div className="account-state-panel">
              <div className="account-state-row">
                <ShieldCheck size={14} />
                <div>
                  <strong>{profileLabel}</strong>
                  <span>
                    {authStatus === "authenticated"
                      ? "Account actions live here, editor stays focused."
                      : "Sign in only when you need cloud sync or credits."}
                  </span>
                </div>
              </div>
              <div className="account-state-row">
                <WalletCards size={14} />
                <div>
                  <strong>Usage status</strong>
                  <span>{credits.detail}</span>
                </div>
              </div>
            </div>

            <button
              type="button"
              className={`account-primary-action ${
                authStatus === "authenticated" ? "account-primary-action-danger" : ""
              }`}
              onClick={() => {
                void handlePrimaryAction();
              }}
              disabled={authStatus === "authenticating"}
            >
              {authStatus === "authenticated" ? <LogOut size={15} /> : <LogIn size={15} />}
              <span>
                {authStatus === "authenticated"
                  ? "Sign out"
                  : authStatus === "authenticating"
                    ? "Connecting..."
                    : "Continue with Google"}
              </span>
            </button>
          </div>,
          document.body
        )
      : null;

  return (
    <div
      ref={shellRef}
      className={`account-shell account-shell-${variant} ${isOpen ? "is-open" : ""}`}
    >
      <button
        type="button"
        className={`account-credits-pill account-tone-${credits.tone}`}
        onClick={() => setIsOpen((current) => !current)}
        aria-label="toggle profile menu"
        aria-expanded={isOpen}
      >
        <span className="account-credits-eyebrow">Credits</span>
        <strong>{credits.label}</strong>
      </button>

      <button
        type="button"
        className={`account-trigger account-trigger-${variant}`}
        onClick={() => setIsOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        {variant === "launchpad" ? (
          <span className="account-trigger-copy">
            <span className="account-trigger-name">{displayName}</span>
            <span className="account-trigger-meta">{profileLabel}</span>
          </span>
        ) : null}
        <span className="account-avatar">{initials}</span>
        <ChevronDown size={14} className={`account-trigger-chevron ${isOpen ? "is-open" : ""}`} />
      </button>
      {popover}
    </div>
  );
}

export default AccountMenu;

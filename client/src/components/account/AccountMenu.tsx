import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ChevronDown, Github, LogIn, LogOut, ShieldCheck, WalletCards } from "lucide-react";
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

function formatCreditsBalance(balance: number | null | undefined): string {
  const safe = Math.max(0, Math.floor(balance ?? 0));
  if (safe >= 1_000_000) {
    return `${(safe / 1_000_000).toFixed(safe % 1_000_000 === 0 ? 0 : 1)}M`;
  }
  if (safe >= 10_000) {
    return `${Math.floor(safe / 1_000)}k`;
  }
  if (safe >= 1_000) {
    return `${(safe / 1_000).toFixed(1)}k`;
  }
  return `${safe}`;
}

function getCreditsTone(balance: number | null | undefined): CreditsTone {
  const safe = Math.max(0, Math.floor(balance ?? 0));
  if (safe <= 0) {
    return "danger";
  }
  if (safe < 5_000) {
    return "warning";
  }
  return "healthy";
}

function getCreditsSummary(
  authStatus: string,
  creditsBalance: number | null | undefined
): { label: string; detail: string; tone: CreditsTone } {
  if (authStatus !== "authenticated") {
    return {
      label: "Guest mode",
      detail: "Sign in to unlock cloud features and credits",
      tone: "neutral",
    };
  }
  const tone = getCreditsTone(creditsBalance);
  const balanceLabel = formatCreditsBalance(creditsBalance);
  if (tone === "danger") {
    return {
      label: balanceLabel,
      detail: "Credits depleted",
      tone,
    };
  }
  if (tone === "warning") {
    return {
      label: balanceLabel,
      detail: "Credits running low",
      tone,
    };
  }
  return {
    label: balanceLabel,
    detail: "Credits available",
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
  const startGithubLogin = useAuthStore((state) => state.startGithubLogin);
  const logout = useAuthStore((state) => state.logout);

  const displayName = useMemo(
    () => getDisplayName(authUser?.email, authUser?.display_name),
    [authUser?.display_name, authUser?.email]
  );
  const initials = useMemo(() => getInitials(displayName), [displayName]);
  const credits = useMemo(
    () => getCreditsSummary(authStatus, authUser?.credits_balance),
    [authStatus, authUser?.credits_balance]
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

  async function handleGithubLogin() {
    setIsOpen(false);
    await startGithubLogin();
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
                <span>Account</span>
                <strong>{authStatus === "authenticated" ? "Connected" : "Guest"}</strong>
                <small>{authStatus === "authenticated" ? "OAuth session is active" : "Local-first workspace"}</small>
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

            {authStatus === "authenticated" ? (
              <button
                type="button"
                className="account-primary-action account-primary-action-danger"
                onClick={() => {
                  void handlePrimaryAction();
                }}
              >
                <LogOut size={15} />
                <span>Sign out</span>
              </button>
            ) : (
              <div className="account-action-stack">
                <button
                  type="button"
                  className="account-primary-action"
                  onClick={() => {
                    void handlePrimaryAction();
                  }}
                  disabled={authStatus === "authenticating"}
                >
                  <LogIn size={15} />
                  <span>{authStatus === "authenticating" ? "Connecting..." : "Continue with Google"}</span>
                </button>
                <button
                  type="button"
                  className="account-secondary-action"
                  onClick={() => {
                    void handleGithubLogin();
                  }}
                  disabled={authStatus === "authenticating"}
                >
                  <Github size={15} />
                  <span>Continue with GitHub</span>
                </button>
              </div>
            )}
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

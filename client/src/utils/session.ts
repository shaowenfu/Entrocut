const SESSION_KEY_PREFIX = "entrocut.session";

function randomPart(): string {
  if (typeof window !== "undefined" && window.crypto?.getRandomValues) {
    const values = new Uint32Array(2);
    window.crypto.getRandomValues(values);
    return `${values[0].toString(36)}${values[1].toString(36)}`;
  }
  return Math.random().toString(36).slice(2, 12);
}

function newSessionId(): string {
  return `sess_${Date.now().toString(36)}_${randomPart()}`;
}

export function getOrCreateSessionId(projectId: string): string {
  const storageKey = `${SESSION_KEY_PREFIX}.${projectId}`;

  try {
    const existing = window.sessionStorage.getItem(storageKey);
    if (existing) {
      return existing;
    }
    const next = newSessionId();
    window.sessionStorage.setItem(storageKey, next);
    return next;
  } catch {
    return newSessionId();
  }
}

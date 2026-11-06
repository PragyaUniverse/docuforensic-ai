import type { Mood } from "@/components/Mascot";

const EVENT = "doc-says";

/** Lets any screen make Doc react. Doc only ever repeats what the app has already established. */
export function docSays(text: string, mood: Mood = "happy") {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { text, mood } }));
}

const OPEN = "doc-open-chat";

export function openDocChat() {
  window.dispatchEvent(new CustomEvent(OPEN));
}

export function onOpenDocChat(handler: () => void): () => void {
  window.addEventListener(OPEN, handler);
  return () => window.removeEventListener(OPEN, handler);
}

export function onDocSays(handler: (text: string, mood: Mood) => void): () => void {
  const listener = (e: Event) => {
    const { text, mood } = (e as CustomEvent<{ text: string; mood: Mood }>).detail;
    handler(text, mood);
  };
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}

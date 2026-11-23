/** Safari may reset `isComposing` before the confirming Enter keydown, so keep
 *  the VK_PROCESSKEY fallback recommended for IME-safe submit handlers. */
export function isImeComposing(event: Pick<KeyboardEvent, 'isComposing' | 'keyCode'>): boolean {
  return event.isComposing || event.keyCode === 229
}

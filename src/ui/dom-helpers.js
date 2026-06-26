export function qs(selector, root = document) {
  return root.querySelector(selector);
}

export function qsa(selector, root = document) {
  return [...root.querySelectorAll(selector)];
}

export function setHidden(element, hidden) {
  if (element) element.hidden = Boolean(hidden);
}

export function setText(element, value) {
  if (element) element.textContent = String(value ?? '');
}

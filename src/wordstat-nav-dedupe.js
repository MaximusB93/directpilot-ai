function dedupeWordstatNav() {
  document.querySelectorAll('[data-wordstat-view]').forEach((button) => button.remove());
}

if (document.body.matches('[data-page="app"]')) {
  dedupeWordstatNav();
  const observer = new MutationObserver(dedupeWordstatNav);
  observer.observe(document.body, { childList: true, subtree: true });
}

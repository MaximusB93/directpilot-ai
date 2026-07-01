function dedupeWordstatNav() {
  const legacyButtons = document.querySelectorAll('[data-wordstat-view]');
  legacyButtons.forEach((button) => button.remove());

  const wordstatButtons = [...document.querySelectorAll('button[data-view="wordstat"], button')]
    .filter((button) => /wordstat/i.test(button.textContent || '') || /Спрос\s*\/\s*Wordstat/i.test(button.textContent || ''));

  const primary = wordstatButtons.find((button) => button.dataset.view === 'wordstat') || wordstatButtons[0];
  wordstatButtons.forEach((button) => {
    if (button !== primary) button.remove();
  });
}

if (document.body.matches('[data-page="app"]')) {
  dedupeWordstatNav();
  const observer = new MutationObserver(dedupeWordstatNav);
  observer.observe(document.body, { childList: true, subtree: true });
}

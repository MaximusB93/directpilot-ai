const appRoot = document.getElementById('app');

function addClass(element, className) {
  if (element && !element.classList.contains(className)) {
    element.classList.add(className);
  }
}

function enhanceCabinetUi() {
  if (!document.body.matches('[data-page="app"]')) return;

  addClass(document.querySelector('.dashboard'), 'workspace');
  addClass(document.querySelector('.dashboardHeader'), 'appHeader');
  addClass(document.querySelector('.sidebar .brand'), 'appBrand');
  addClass(document.querySelector('.sidebar nav'), 'sideNav');

  document.querySelectorAll('.sidebar nav button[data-view]').forEach((button) => {
    addClass(button, 'sideNavItem');
    button.type = 'button';
  });

  document.querySelectorAll('button:not([type])').forEach((button) => {
    button.type = 'button';
  });

  document.querySelectorAll('[data-go-view], [data-view], [data-sync-client], [data-load-performance], [data-load-optimization-plan], [data-load-optimization-actions], [data-create-optimization-drafts], [data-refresh-client-yandex], [data-open-settings], [data-client-menu-toggle]').forEach((element) => {
    element.style.pointerEvents = 'auto';
  });
}

if (appRoot) {
  enhanceCabinetUi();

  const observer = new MutationObserver(() => {
    enhanceCabinetUi();
  });

  observer.observe(appRoot, {
    childList: true,
    subtree: true,
  });
}

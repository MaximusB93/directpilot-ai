function noop() {}

function closest(event, selector) {
  return event?.target?.closest?.(selector) || null;
}

function matches(event, selector) {
  return Boolean(event?.target?.matches?.(selector));
}

export function createWordstatEventHandlers({
  state,
  render = noop,
  openView,
  submitForm,
  comparePeriod,
  copyJson,
  previousPeriodRange,
  setNavActive = noop,
  showTooltip = noop,
  hideTooltip = noop,
} = {}) {
  if (!state) throw new Error('Wordstat state is required');
  if (typeof openView !== 'function') throw new Error('Wordstat openView dependency is required');
  if (typeof submitForm !== 'function') throw new Error('Wordstat submitForm dependency is required');
  if (typeof comparePeriod !== 'function') throw new Error('Wordstat comparePeriod dependency is required');
  if (typeof copyJson !== 'function') throw new Error('Wordstat copyJson dependency is required');
  if (typeof previousPeriodRange !== 'function') throw new Error('Wordstat previousPeriodRange dependency is required');

  function handleMouseMoveEvent(event) {
    showTooltip(event);
  }

  function handleMouseOutEvent(event) {
    if (closest(event, '[data-wordstat-chart-point]')) hideTooltip();
  }

  function handleInputEvent(event) {
    if (matches(event, '[data-wordstat-region-custom]')) {
      state.regionDraftCustom = event.target.value;
    }
    if (matches(event, '[name="compareFromDate"]')) state.form.compareFromDate = event.target.value;
    if (matches(event, '[name="compareToDate"]')) state.form.compareToDate = event.target.value;
  }

  function handleChangeEvent(event) {
    if (matches(event, '[data-wordstat-region-modal]')) {
      const value = event.target.value;
      state.regionDraftRegions = event.target.checked
        ? [...new Set([...state.regionDraftRegions, value])]
        : state.regionDraftRegions.filter((id) => id !== value);
      render();
    }
    if (matches(event, '[data-wordstat-region-all]')) {
      state.regionDraftRegions = [];
      state.regionDraftCustom = '';
      render();
    }
  }

  async function handleClickEvent(event) {
    const navButton = closest(event, '[data-wordstat-view]');
    if (navButton) {
      event.preventDefault();
      await openView();
      return;
    }
    if (closest(event, '[data-wordstat-open-region-modal]')) {
      state.regionDraftRegions = [...(state.form.regions || [])];
      state.regionDraftCustom = state.form.customRegions || '';
      state.regionModalOpen = true;
      render();
      return;
    }
    if (closest(event, '[data-wordstat-close-region-modal]')) {
      state.regionModalOpen = false;
      render();
      return;
    }
    const toggleNode = closest(event, '[data-wordstat-toggle-region-node]');
    if (toggleNode) {
      const id = toggleNode.dataset.wordstatToggleRegionNode;
      if (state.expandedRegions.has(id)) state.expandedRegions.delete(id);
      else state.expandedRegions.add(id);
      render();
      return;
    }
    if (closest(event, '[data-wordstat-clear-regions]')) {
      state.regionDraftRegions = [];
      state.regionDraftCustom = '';
      render();
      return;
    }
    if (closest(event, '[data-wordstat-apply-regions]')) {
      state.form.regions = [...new Set(state.regionDraftRegions)];
      state.form.customRegions = state.regionDraftCustom;
      state.regionModalOpen = false;
      render();
      return;
    }
    if (closest(event, '[data-wordstat-toggle-compare]')) {
      state.comparePanelOpen = !state.comparePanelOpen;
      const range = previousPeriodRange();
      if (range && !state.form.compareFromDate) state.form.compareFromDate = range.fromDate;
      if (range && !state.form.compareToDate) state.form.compareToDate = range.toDate;
      render();
      return;
    }
    if (closest(event, '[data-wordstat-fill-previous-period]')) {
      const range = previousPeriodRange();
      if (range) {
        state.form.compareFromDate = range.fromDate;
        state.form.compareToDate = range.toDate;
      }
      render();
      return;
    }
    if (closest(event, '[data-wordstat-run-compare]')) {
      await comparePeriod();
      return;
    }
    if (closest(event, '[data-wordstat-copy-json]')) await copyJson();
  }

  function handleRouteClickEvent(event) {
    if (closest(event, '[data-view], [data-go-view]') && !closest(event, '[data-wordstat-view]')) {
      state.active = false;
      setNavActive(false);
    }
  }

  async function handleSubmitEvent(event) {
    const form = closest(event, '[data-wordstat-form]');
    if (!form) return;
    event.preventDefault();
    await submitForm(form);
  }

  return {
    handleMouseMoveEvent,
    handleMouseOutEvent,
    handleInputEvent,
    handleChangeEvent,
    handleClickEvent,
    handleRouteClickEvent,
    handleSubmitEvent,
  };
}

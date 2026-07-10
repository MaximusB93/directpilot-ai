export async function handleAiSubmitEvent(event, {
  sendChatMessage,
}) {
  const aiChatForm = event.target.closest('[data-ai-chat-form]');
  if (!aiChatForm) return false;

  event.preventDefault();
  const message = new FormData(aiChatForm).get('message')?.toString();
  await sendChatMessage(message);
  return true;
}

export function handleAiInputEvent(event, {
  setCustomModel,
  setSearchQueryLimit,
}) {
  if (event.target.matches('[data-ai-custom-model]')) {
    setCustomModel?.(event.target.value);
    return true;
  }

  if (event.target.matches('[data-ai-search-query-limit]')) {
    setSearchQueryLimit?.(event.target.value);
    return true;
  }

  return false;
}

export function handleAiChangeEvent(event, {
  setModel,
  setPreset,
  setMaxTokensMode,
  setToolResultsMode,
  setChatHistoryLimit,
  setCompactContext,
  setChatCampaign,
  render,
}) {
  if (event.target.matches('[data-ai-model]')) {
    const value = event.target.value;
    setModel?.(value);
    render?.();
    return true;
  }

  if (event.target.matches('[data-ai-preset]')) {
    setPreset?.(event.target.value);
    render?.();
    return true;
  }

  if (event.target.matches('[data-ai-max-tokens-mode]')) {
    setMaxTokensMode?.(event.target.value);
    render?.();
    return true;
  }

  if (event.target.matches('[data-ai-tool-results-mode]')) {
    setToolResultsMode?.(event.target.value);
    render?.();
    return true;
  }

  if (event.target.matches('[data-ai-chat-history-limit]')) {
    setChatHistoryLimit?.(Number(event.target.value) || 3);
    render?.();
    return true;
  }

  if (event.target.matches('[data-ai-compact-context]')) {
    setCompactContext?.(event.target.checked);
    render?.();
    return true;
  }

  if (event.target.matches('[data-ai-chat-campaign]')) {
    setChatCampaign?.(event.target.value);
    return true;
  }

  return false;
}

export async function handleAiClickEvent(event, {
  loadPromptDebug,
  requestRecommendations,
  setChatInput,
  generateInsight,
  promptFor,
  render,
}) {
  if (event.target.closest('[data-ai-prompt-debug]')) {
    await loadPromptDebug();
    return true;
  }

  if (event.target.closest('[data-client-ai-recommendations]')) {
    await requestRecommendations();
    return true;
  }

  const sampleButton = event.target.closest('[data-ai-chat-sample]');
  if (sampleButton) {
    setChatInput?.(sampleButton.dataset.aiChatSample || '');
    render?.();
    return true;
  }

  const promptButton = event.target.closest('[data-ai-prompt]');
  if (promptButton) {
    await generateInsight(promptFor(promptButton.dataset.aiPrompt));
    return true;
  }

  return false;
}

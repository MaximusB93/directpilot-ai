export const DEFAULT_CAMPAIGN_FILTER = 'all';

export function normalizeCampaignName(value) {
  return String(value || '').trim();
}

export function getCampaignName(campaign) {
  if (!campaign || typeof campaign !== 'object') return '';
  return normalizeCampaignName(campaign.name || campaign.campaignName || campaign.campaign_name || campaign.title);
}

export function getCampaignId(campaign) {
  if (!campaign || typeof campaign !== 'object') return '';
  return String(campaign.id || campaign.campaignId || campaign.campaign_id || getCampaignName(campaign) || '').trim();
}

export function getCampaignsFromPerformanceSummary(performanceSummary) {
  return Array.isArray(performanceSummary?.campaigns) ? performanceSummary.campaigns : [];
}

export function getCampaignOptions(performanceSummary) {
  const names = getCampaignsFromPerformanceSummary(performanceSummary)
    .map(getCampaignName)
    .filter(Boolean);

  return [...new Set(names)];
}

export function normalizeCampaignFilter(value) {
  const normalized = normalizeCampaignName(value);
  return normalized || DEFAULT_CAMPAIGN_FILTER;
}

export function isCampaignSelected(campaign, selectedCampaignName) {
  const selected = normalizeCampaignFilter(selectedCampaignName);
  if (selected === DEFAULT_CAMPAIGN_FILTER) return true;
  return getCampaignName(campaign) === selected;
}

export function filterCampaignsBySelectedName(campaigns, selectedCampaignName = DEFAULT_CAMPAIGN_FILTER) {
  const list = Array.isArray(campaigns) ? campaigns : [];
  return list.filter((campaign) => isCampaignSelected(campaign, selectedCampaignName));
}

export function createCampaignStore() {
  return {
    getCampaignId,
    getCampaignName,
    getCampaignOptions,
    getCampaignsFromPerformanceSummary,
    normalizeCampaignFilter,
    isCampaignSelected,
    filterCampaignsBySelectedName,
  };
}

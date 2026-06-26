import { escapeHtml } from './core/html.js';

function ensureWordstatTooltip() {
  let tooltip = document.querySelector('.wordstatChartTooltip');
  if (tooltip) return tooltip;
  tooltip = document.createElement('div');
  tooltip.className = 'wordstatChartTooltip';
  document.body.appendChild(tooltip);
  return tooltip;
}

function parseSvgPoints(pointsAttribute) {
  return String(pointsAttribute || '')
    .trim()
    .split(/\s+/)
    .map((pair) => {
      const [x, y] = pair.split(',').map(Number);
      return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
    })
    .filter(Boolean);
}

function tooltipHtml(rawText) {
  const [phrase = 'Фраза', date = '—', value = '—'] = String(rawText || '').split('\n');
  return `<strong>${escapeHtml(phrase)}</strong><span>${escapeHtml(date)}</span><b>${escapeHtml(value)}</b>`;
}

function placeTooltip(tooltip, event) {
  const offset = 18;
  const width = tooltip.offsetWidth || 260;
  const height = tooltip.offsetHeight || 110;
  const left = Math.min(window.innerWidth - width - 12, event.clientX + offset);
  const top = Math.min(window.innerHeight - height - 12, event.clientY + offset);
  tooltip.style.left = `${Math.max(12, left)}px`;
  tooltip.style.top = `${Math.max(12, top)}px`;
}

function showTooltip(event, text) {
  const tooltip = ensureWordstatTooltip();
  tooltip.innerHTML = tooltipHtml(text);
  tooltip.classList.add('visible');
  placeTooltip(tooltip, event);
}

function hideTooltip() {
  const tooltip = document.querySelector('.wordstatChartTooltip');
  if (tooltip) tooltip.classList.remove('visible');
}

function pointerToSvgPoint(svg, event) {
  const rect = svg.getBoundingClientRect();
  const viewBox = svg.viewBox?.baseVal;
  if (!viewBox || !rect.width || !rect.height) return null;
  return {
    x: viewBox.x + ((event.clientX - rect.left) / rect.width) * viewBox.width,
    y: viewBox.y + ((event.clientY - rect.top) / rect.height) * viewBox.height,
  };
}

function nearestPointIndex(points, svgPoint) {
  if (!points.length || !svgPoint) return 0;
  let bestIndex = 0;
  let bestDistance = Infinity;
  points.forEach((point, index) => {
    const distance = Math.abs(point.x - svgPoint.x) + Math.abs(point.y - svgPoint.y) * 0.18;
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function clearWordstatHover(panel) {
  panel.classList.remove('has-hover');
  panel.querySelectorAll('.wordstat-hovered-series').forEach((item) => item.classList.remove('wordstat-hovered-series'));
  panel.querySelectorAll('.wordstat-hovered-point').forEach((item) => item.classList.remove('wordstat-hovered-point'));
  hideTooltip();
}

function enhanceWordstatChart(panel) {
  if (!panel || panel.dataset.wordstatEnhanced === 'true') return;
  const header = panel.querySelector('.panelHeader h3');
  if (!header || !/График динамики/i.test(header.textContent || '')) return;
  const svg = panel.querySelector('svg');
  if (!svg) return;

  panel.dataset.wordstatEnhanced = 'true';
  panel.classList.add('wordstatChartPanel');

  const originalPolylines = [...svg.querySelectorAll('polyline')].filter((line) => !line.classList.contains('wordstat-chart-hit'));
  const originalCircles = [...svg.querySelectorAll('[data-wordstat-chart-point]')];
  let circleOffset = 0;

  originalPolylines.forEach((line, seriesIndex) => {
    const points = parseSvgPoints(line.getAttribute('points'));
    const relatedCircles = originalCircles.slice(circleOffset, circleOffset + points.length);
    circleOffset += points.length;

    const hitLine = line.cloneNode(false);
    hitLine.removeAttribute('stroke-dasharray');
    hitLine.setAttribute('stroke', 'transparent');
    hitLine.setAttribute('stroke-width', '24');
    hitLine.setAttribute('fill', 'none');
    hitLine.setAttribute('class', 'wordstat-chart-hit');
    hitLine.dataset.seriesIndex = String(seriesIndex);
    line.after(hitLine);

    const activate = (event, pointIndex = null) => {
      const index = pointIndex ?? nearestPointIndex(points, pointerToSvgPoint(svg, event));
      const circle = relatedCircles[index] || relatedCircles[0];
      const tooltipText = circle?.dataset.tooltip || 'Нет данных';
      panel.classList.add('has-hover');
      originalPolylines.forEach((item) => item.classList.remove('wordstat-hovered-series'));
      originalCircles.forEach((item) => item.classList.remove('wordstat-hovered-point'));
      line.classList.add('wordstat-hovered-series');
      if (circle) circle.classList.add('wordstat-hovered-point');
      showTooltip(event, tooltipText);
    };

    hitLine.addEventListener('mousemove', activate);
    hitLine.addEventListener('mouseenter', activate);
    hitLine.addEventListener('mouseleave', () => clearWordstatHover(panel));

    relatedCircles.forEach((circle, index) => {
      circle.addEventListener('mousemove', (event) => activate(event, index));
      circle.addEventListener('mouseenter', (event) => activate(event, index));
      circle.addEventListener('mouseleave', () => clearWordstatHover(panel));
    });
  });
}

function enhanceWordstatCharts() {
  document.querySelectorAll('.panel').forEach(enhanceWordstatChart);
}

const observer = new MutationObserver(() => enhanceWordstatCharts());
observer.observe(document.body, { childList: true, subtree: true });
window.addEventListener('resize', hideTooltip);
document.addEventListener('scroll', hideTooltip, true);

enhanceWordstatCharts();

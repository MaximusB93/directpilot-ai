export const clients = [];

export const agencyMetrics = [
  { label: 'Клиентов в ЛК', value: '0', delta: 'добавьте первого клиента' },
  { label: 'Расход', value: '—', delta: 'появится после подключения Директа' },
  { label: 'Конверсии', value: '—', delta: 'появятся после подключения Метрики' },
  { label: 'Средний CPA', value: '—', delta: 'рассчитаем после загрузки данных' },
];

export const auditIssues = [];
export const recommendations = [];
export const campaigns = [];

export const reportBullets = {
  happened: ['Подключите клиента и источники данных, чтобы сформировать отчёт.'],
  done: ['После подключения Директа и Метрики здесь появятся действия специалиста.'],
  next: ['Добавить клиента', 'Подключить Яндекс.Директ', 'Подключить цели Метрики'],
};

export const autopilotRules = [
  { label: 'Добавлять минус-фразы', enabled: false },
  { label: 'Останавливать ключи без конверсий', enabled: false },
  { label: 'Создавать черновики объявлений', enabled: false },
  { label: 'Увеличивать общий бюджет', enabled: false },
  { label: 'Удалять кампании', enabled: false },
  { label: 'Менять стратегию без подтверждения', enabled: false },
];

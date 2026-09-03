# ТЗ №1. Ядро метрик: сравнение периодов, декомпозиция CPA, значимость

## Зачем

Все продуктовые режимы DirectPilot (утренняя сводка, полный аудит, точечное расследование, контроль после изменения) отвечают на один вопрос: **где теряется стоимость заявки и на сколько рублей**. Сейчас каждый режим считает это по-своему, пороги заданы константами, а «на сколько рублей» не считается нигде.

Этот модуль — единственный источник истины для сравнения периодов. После него ИИ перестаёт заниматься арифметикой и занимается только интерпретацией.

## Границы задачи

**Делаем:** один новый чистый модуль `backend/app/services/metrics_core.py` + тесты.

**Не делаем в этой задаче:** не меняем UI, не меняем промпты, не меняем `ai_audit_jobs.py`, не меняем `campaign_dynamics_analyzer.py`, не трогаем схему БД, не добавляем запросов к Яндекс.Директу.

**Модуль не должен:** обращаться к базе, к сети, к `settings`, импортировать `app.models`, `sqlalchemy`, `httpx`, `fastapi`. Только стандартная библиотека и `dataclasses`. Это обязательное требование — модуль должен быть тестируемым без окружения.

Перевод существующих сервисов на этот модуль — отдельная последующая задача. Сейчас ничего не переключаем.

---

## 1. Модель данных периода

```python
@dataclass(frozen=True)
class PeriodMetrics:
    date_from: date
    date_to: date
    cost: float
    impressions: int
    clicks: int
    conversions: float | None   # None = данные о конверсиях недоступны
```

Производные значения — свойства, не поля:

| Свойство | Формула | Когда None |
|---|---|---|
| `ctr` | `clicks / impressions * 100` | `impressions == 0` |
| `cpc` | `cost / clicks` | `clicks == 0` |
| `cr` | `conversions / clicks * 100` | `conversions is None` или `clicks == 0` |
| `cpa` | `cost / conversions` | `conversions is None` или `conversions == 0` |
| `days` | число дней в периоде включительно | — |

**Критическое правило:** `conversions = None` означает «неизвестно» и обязано оставаться `None` на всём пути вычислений. `conversions = 0` означает «достоверно ноль конверсий». Эти два состояния нигде не должны схлопываться. Ни одна функция модуля не имеет права подставить `0` вместо `None`.

Ни одно деление не должно бросать исключение. Отсутствие результата — всегда `None`, никогда `0` и никогда `inf`.

---

## 2. Окна сравнения

```python
def build_windows(reference_date: date) -> dict[str, tuple[date, date]]
```

`reference_date` — последний день с данными (обычно вчера). Возвращает словарь окон:

| Ключ | Период | Пара для сравнения |
|---|---|---|
| `yesterday` | reference_date | `same_weekday_prev_week` |
| `same_weekday_prev_week` | reference_date − 7 дней | — |
| `prev_day` | reference_date − 1 день | — |
| `last7` | reference_date − 6 … reference_date | `previous7` |
| `previous7` | reference_date − 13 … reference_date − 7 | — |
| `last28` | reference_date − 27 … reference_date | `previous28` |
| `previous28` | reference_date − 55 … reference_date − 28 | — |
| `last90` | reference_date − 89 … reference_date | — |

**Почему день сравнивается с тем же днём недели неделю назад, а не со вчерашним.** В контекстной рекламе недельная сезонность сильнее любого тренда: понедельник против воскресенья даст «падение конверсий на 60 %» на ровном месте. Сравнение «вторник против прошлого вторника» — единственное корректное дневное сравнение. Окно `prev_day` возвращаем для отображения, но использовать его как базу для выводов запрещено.

Используем 28 дней вместо 30: 28 = ровно 4 недели, поэтому в текущем и предыдущем окне одинаковое число каждого дня недели. Сравнение 30 на 30 систематически смещено.

---

## 3. Сравнение периодов

```python
def compare(current: PeriodMetrics, previous: PeriodMetrics) -> MetricComparison
```

Для каждой метрики (`cost`, `impressions`, `clicks`, `ctr`, `cpc`, `conversions`, `cr`, `cpa`) вернуть:

```python
@dataclass(frozen=True)
class MetricDelta:
    current: float | None
    previous: float | None
    absolute: float | None      # current - previous
    percent: float | None       # (current - previous) / previous * 100
    direction: str              # "up" | "down" | "flat" | "unknown"
    is_significant: bool        # см. раздел 4
    confidence: str             # "high" | "medium" | "low" | "insufficient"
```

Правила для `percent`:

- `previous` равен нулю или `None` → `percent = None`, `direction = "unknown"`. **Не возвращать 0 и не возвращать бесконечность.** Это отдельно проверяется тестом: сейчас в `campaign_dynamics_analyzer._pct_delta` рост с нуля даёт `None`, а «оба нуля» даёт `0.0` — из-за этого «конверсий не было и не стало» и «конверсии появились» выглядят одинаково.
- Оба значения `None` → всё `None`, `direction = "unknown"`.
- `direction = "flat"` при `abs(percent) < 1`.

---

## 4. Значимость изменения

Замена фиксированных порогов (сейчас 30 %, 25 %, 20 % независимо от объёма). При 15 кликах рост CPA на 40 % — шум; при 1 500 кликах — событие.

### Для счётных метрик (`conversions`, `clicks`, `impressions`)

Считаем шум по Пуассону. Порог значимости относительного изменения:

```
threshold_pct = 200 * sqrt(1 / n_current + 1 / n_previous)
```

где `n` — само счётное значение в соответствующем окне. Изменение значимо, если `abs(percent) > threshold_pct`.

Ориентиры (для проверки реализации): при 10 и 10 конверсиях порог ≈ 89 %; при 50 и 50 ≈ 40 %; при 200 и 200 ≈ 20 %; при 1000 и 1000 ≈ 9 %.

Если любое из `n` меньше 1 — `is_significant = False`, `confidence = "insufficient"`.

### Для метрик-долей (`ctr`, `cr`)

Биномиальная ошибка. Для `cr`: `p = conversions / clicks`, `n = clicks`.

```
se = sqrt(p_pooled * (1 - p_pooled) * (1 / n_current + 1 / n_previous))
```

где `p_pooled = (conv_current + conv_previous) / (clicks_current + clicks_previous)`.

Значимо, если `abs(p_current - p_previous) > 2 * se`.

Для `ctr` — то же самое, где `p = clicks / impressions`, `n = impressions`.

### Для производных метрик (`cpa`, `cpc`)

`cpa` наследует значимость от `conversions`: если изменение числа конверсий не значимо, вывод об изменении CPA тоже не значим. `cpc` наследует от `clicks`.

### Уровни уверенности

Считаются по числу конверсий в меньшем из двух окон (для метрик, зависящих от конверсий) либо по числу кликов (для остальных):

| Уровень | Конверсии | Клики |
|---|---|---|
| `high` | ≥ 50 | ≥ 1000 |
| `medium` | ≥ 15 | ≥ 300 |
| `low` | ≥ 3 | ≥ 50 |
| `insufficient` | < 3 | < 50 |

Если `conversions is None` — `confidence = "insufficient"` для всех зависящих от конверсий метрик.

---

## 5. Декомпозиция CPA — ключевая функция модуля

Тождество: `CPA = Расход / Конверсии = (Клики × CPC) / (Клики × CR) = CPC / CR`.

Значит **любое** изменение CPA раскладывается на вклад цены клика и вклад конверсионности, без остатка.

```python
def decompose_cpa(current: PeriodMetrics, previous: PeriodMetrics) -> CpaDecomposition
```

```python
@dataclass(frozen=True)
class CpaDecomposition:
    cpa_previous: float | None
    cpa_current: float | None
    cpa_change: float | None          # в рублях
    cpc_contribution: float | None    # рублей CPA, вызванных изменением CPC
    cr_contribution: float | None     # рублей CPA, вызванных изменением CR
    dominant_factor: str              # "cpc" | "cr" | "both" | "unknown"
```

Формулы (доли, не проценты: `cr = conversions / clicks`):

```
cpc_contribution = (cpc_current - cpc_previous) / cr_previous
cr_contribution  = cpc_current * (1 / cr_current - 1 / cr_previous)
```

**Обязательная проверка тестом:** `cpc_contribution + cr_contribution` равно `cpa_current - cpa_previous` с точностью до 0.01 ₽ на любых валидных входных данных.

`dominant_factor`: `"cpc"` если вклад CPC даёт больше 65 % от суммы модулей вкладов, `"cr"` — симметрично, иначе `"both"`. При любом `None` во входных данных — `"unknown"` и все вклады `None`.

Пример вывода, ради которого всё делается: *«CPA вырос с 6 200 до 8 900 ₽. Из 2 700 ₽ роста 1 900 ₽ дало подорожание клика, 800 ₽ — падение конверсионности.»*

---

## 6. Пустой расход

Самый быстрый способ снизить CPA — убрать расход, который не даёт конверсий вообще.

```python
def empty_spend(segments: list[SegmentMetrics]) -> EmptySpendSummary
```

```python
@dataclass(frozen=True)
class SegmentMetrics:
    key: str                    # id кампании / запрос / регион / площадка
    label: str                  # человеческое название
    metrics: PeriodMetrics

@dataclass(frozen=True)
class EmptySpendSummary:
    total_cost: float           # расход по всем сегментам
    empty_cost: float           # расход по сегментам с conversions == 0
    empty_share_pct: float
    unknown_cost: float         # расход там, где conversions is None
    segments: list[EmptySpendItem]   # по убыванию потерь
```

`EmptySpendItem` содержит `key`, `label`, `cost`, `clicks`, `reliable` и `reason`.

Правила:

- В `empty_cost` попадают только сегменты, где `conversions == 0` — достоверный ноль. Сегменты с `conversions is None` идут в `unknown_cost` и **никогда** не считаются пустыми.
- `reliable = True` только если кликов в сегменте достаточно, чтобы ноль конверсий что-то значил. Порог: `clicks >= 30` при неизвестном ориентире CR; если передан `baseline_cr` (аккаунтный CR в долях) — `clicks >= 3 / baseline_cr`, то есть столько кликов, при которых ожидалось бы не менее трёх конверсий. При меньшем числе кликов `reliable = False`, `reason = "insufficient_clicks"`.
- Сегменты с `cost == 0` отбрасываются.

---

## 7. Оценка эффекта в рублях

```python
def estimate_savings(segment: SegmentMetrics, *, baseline_cpa: float | None) -> SavingsEstimate
```

Возвращает `monthly_cost_saved`, `conversions_at_risk`, `confidence`, `assumption` (текстовая формулировка допущения).

- `monthly_cost_saved` = расход сегмента, приведённый к 30 дням: `cost / days * 30`.
- `conversions_at_risk` = `conversions` сегмента, приведённые к 30 дням. Для пустого расхода это ноль — в этом весь смысл.
- Если `conversions is None` → `monthly_cost_saved` считаем, `conversions_at_risk = None`, `confidence = "low"`, в `assumption` пишем, что конверсии по сегменту неизвестны.

Ни одна функция не должна возвращать «ожидаемый эффект» без числа. Формулировки вида «снизить CPA в направлении целевого значения» этот модуль не производит.

---

## 8. Тесты

Создать `backend/tests/test_metrics_core.py`. Обязательное покрытие:

1. Все производные метрики при нулевых знаменателях возвращают `None`, а не 0 и не исключение.
2. `conversions=None` не превращается в `0` ни в одной функции: сравнение, декомпозиция, пустой расход, оценка эффекта.
3. `percent` при `previous=0` равен `None`; при обоих нулях — тоже `None` с `direction="unknown"`.
4. **Декомпозиция сходится:** на десяти наборах случайных валидных значений сумма вкладов равна изменению CPA с точностью 0.01.
5. Декомпозиция при неизменном CR относит весь рост CPA на CPC, и наоборот.
6. Пороги значимости соответствуют ориентирам из раздела 4 (10/10 ≈ 89 %, 200/200 ≈ 20 %) с допуском 1 п.п.
7. Изменение на 40 % при 12 конверсиях не значимо; такое же изменение при 300 конверсиях значимо.
8. Окна: `same_weekday_prev_week` отстоит ровно на 7 дней; `last28` и `previous28` не пересекаются и содержат по 28 дней; границы включительные.
9. Пустой расход: сегмент с `conversions=None` не попадает в `empty_cost`; сегмент с 5 кликами и нулём конверсий имеет `reliable=False`.
10. `estimate_savings` приводит период любой длины к 30 дням корректно.

---

## Критерии приёмки

- Модуль не импортирует ничего, кроме стандартной библиотеки (проверяется тестом на импорты).
- `python -m pytest -q backend/tests` — все тесты проходят, включая 429 существующих.
- `python -m compileall -q backend/app index.py backend/index.py` — без ошибок.
- Ни один существующий файл не изменён, кроме добавления двух новых.
- В коде нет ни одного места, где `None` заменяется на `0` для конверсий.

## Проверка руками

После реализации прогнать в консоли на реальных числах из кабинета Green Flow:

```
CPA кампании «ЕПК | Поиск | Бренд | ЮФО»: расход 181 054,15 ₽, клики 959, конверсии 13
```

Проверить, что `cpa ≈ 13 927 ₽`, `cpc ≈ 188,79 ₽`, `cr ≈ 1,36 %`, и что при сравнении с любым предыдущим периодом сумма вкладов CPC и CR сходится с изменением CPA.

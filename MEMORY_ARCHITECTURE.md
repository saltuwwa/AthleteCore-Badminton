# AthleteCore Memory Architecture (v0.1)

> Исследование подходов, обоснование стека (extraction, hybrid retrieval, supersession, gating) и реализация MVP — в [`backend/README.md`](backend/README.md).

## 1) Цель memory в AthleteCore

Memory нужна не для "красивого чата", а для:
- обнаружения повторяющихся ошибок у конкретного спортсмена;
- персонализации расписания и recovery-рекомендаций;
- continuity между сессиями (пользователь не повторяет одно и то же);
- объяснимости рекомендаций ("на основе каких прошлых событий").

---

## 2) Выбранная стратегия

### 2.1 Двухслойная память
- **Short-term memory (STM)**: thread-level, хранится через LangGraph checkpointer.
- **Long-term memory (LTM)**: user-level, хранится независимо от thread, keyed by `user_id`.

### 2.2 Типы LTM (раздельно)
- **Semantic**: стабильные факты (предпочтения времени, ограничения, цели).
- **Episodic**: события во времени (матчи, тренировки, логи, подтверждения/отклонения плана).
- **Procedural**: как агенту лучше взаимодействовать с пользователем (формат ответа, чувствительность к нагрузке, правила подтверждения).

### 2.3 Read/Write paths
- **Hot path (sync)**: retrieval Top-K memories для текущего ответа.
- **Cold path (async)**: извлечение фактов, дедуп, конфликт-резолв, TTL/санитизация.

---

## 3) За и против стратегии именно для AthleteCore

## Плюсы (существенные)

1. **Сильный персональный Analyst**
   - Паттерны ошибок становятся индивидуальными, а не "общие советы".

2. **Стабильный UX**
   - Пользователь не объясняет контекст заново каждый раз.

3. **Корректный HITL и контроль нагрузки**
   - Подтверждения/отклонения расписания становятся обучающим сигналом.

4. **Объяснимость на защите**
   - Можно показать, какие события и факты повлияли на вывод.

5. **Масштабируемость**
   - Раздельные memory-типы позволяют развиваться без "снежного кома".

6. **Совместимость с LangGraph**
   - Встроенные механизмы checkpointer/store, меньше риска "самописного хаоса".

## Минусы (реальные)

1. **Дополнительная сложность**
   - Нужно поддерживать extraction, scoring, conflict-resolution.

2. **Рост latency при плохом retrieval**
   - Без ограничений Top-K и async write path можно замедлить ответы.

3. **Риск накопления мусора**
   - Если write-gate слабый, memory быстро деградирует.

4. **Больше surface area по безопасности**
   - Нужно жёстко следить за `user_id`-изоляцией и удалением данных.

## Вывод

Для AthleteCore **плюсов больше**, и они критичны для core-value продукта.  
Без memory система превращается в обычный "one-off chatbot", что против цели проекта.

---

## 4) Конкретная модель данных (без кода)

### 4.1 STM (thread scope)
- `thread_id`
- текущий диалоговый контекст
- промежуточное состояние графа
- pending interrupt state (HITL)

### 4.2 LTM Semantic
- `user_id`
- `fact_key` (например `preferred_training_time`)
- `value`
- `confidence`
- `source_event_id`
- `updated_at`

### 4.3 LTM Episodic
- `user_id`
- `event_id`
- `event_type` (`match_log`, `training_log`, `health_note`, `schedule_confirmation`)
- `timestamp`
- `payload` (структурно: ошибки, риск, рекомендации)
- `importance`

### 4.4 LTM Procedural
- `user_id`
- `rule_key` (например `response_style`, `confirmation_strictness`)
- `rule_value`
- `reason/source`
- `updated_at`

---

## 5) Retrieval политика

Перед каждым ответом:
- `semantic`: 2-3 записи
- `episodic`: 3-5 записей
- `procedural`: 1-2 записи

Финальный скоринг:
`score = 0.6 * relevance + 0.25 * recency + 0.15 * importance`

Hard rules:
- high-risk health memory всегда подмешивается;
- retrieval всегда по namespace `(user_id, memory_type)`.

---

## 6) Write-gate (что вообще записывать)

Записывать только если выполняется хотя бы одно:
- факт влияет на будущие рекомендации (`goal`, `constraint`, `preference`);
- событие повторяемо (ошибка, паттерн, recovery response);
- результат подтверждён пользователем (HITL decision);
- риск уровня `MED/HIGH`.

Не записывать:
- small talk;
- дублирующие шумовые фразы;
- transient эмоции без решения/действия.

---

## 7) Конфликты и "забывание"

### Конфликты
- новые факты не стирают старые "в лоб";
- применяется `valid_from/valid_to` или "last-confirmed wins";
- при конфликте low confidence — пометка для уточняющего вопроса.

### TTL/Retention
- raw episodic: 180 дней
- derived summaries/patterns: 365 дней
- procedural rules: до ручного пересмотра

---

## 8) Безопасность и приватность

Обязательно:
- строгий фильтр `user_id` на каждом search;
- PII sanitization в cold path;
- delete-by-user (право на удаление);
- audit-log memory writes (кто/когда/что/почему).

---

## 9) План внедрения (по шагам)

### Шаг 1 (день 1)
- утвердить memory schema (этот документ);
- подключить STM checkpointer.

### Шаг 2 (день 2-3)
- поднять LTM store с namespace;
- реализовать hot-path retrieval для Analyst.

### Шаг 3 (день 4)
- добавить async extractor (cold path) + write-gate.

### Шаг 4 (день 5)
- conflict resolution + TTL + delete flow.

### Шаг 5 (день 6)
- memory quality metrics и eval.

---

## 10) Метрики качества memory

- Memory hit rate (сколько retrieval реально использовано в ответе)
- Contradiction rate (конфликтующих фактов на пользователя)
- Personalization uplift (дельта релевантности с/без memory)
- Avg retrieval latency (p50/p95)
- Stale memory rate (доля протухших воспоминаний в Top-K)

---

## 11) Решение на текущий момент

Для AthleteCore принимаем стратегию:
- **LangGraph STM + LTM с разделением semantic/episodic/procedural + hot/cold paths**.

Это даёт лучший баланс:
- качество рекомендаций;
- UX continuity;
- объяснимость и защита решения на Demo/mentor review.


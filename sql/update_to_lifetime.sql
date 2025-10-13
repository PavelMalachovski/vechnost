-- Миграция: Сделать expires_at nullable для поддержки вечных подписок

-- 1. Изменить колонку expires_at, чтобы она могла быть NULL
ALTER TABLE subscriptions ALTER COLUMN expires_at DROP NOT NULL;

-- 2. Обновить существующие подписки на вечные (опционально)
-- Раскомментируйте, если хотите сделать все существующие подписки вечными:
-- UPDATE subscriptions SET expires_at = NULL, period = 'lifetime' WHERE status = 'active';

-- 3. Или обновить конкретную подписку пользователя 1115719673:
UPDATE subscriptions
SET expires_at = NULL, period = 'lifetime'
WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = 1115719673)
AND status = 'active';

-- 4. Проверка результата
SELECT
    u.telegram_user_id,
    u.first_name,
    s.status,
    s.period,
    s.expires_at,
    CASE
        WHEN s.expires_at IS NULL THEN 'LIFETIME'
        ELSE 'Expires: ' || s.expires_at::text
    END as subscription_type
FROM users u
LEFT JOIN subscriptions s ON s.user_id = u.id
WHERE u.telegram_user_id = 1115719673;


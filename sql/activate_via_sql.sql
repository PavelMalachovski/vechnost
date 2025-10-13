-- Активация пользователя 1115719673 на 30 дней

-- 1. Создаём или обновляем пользователя (если нужно)
INSERT INTO users (telegram_user_id, username, first_name, last_name, created_at)
VALUES (1115719673, NULL, 'User', NULL, NOW())
ON CONFLICT (telegram_user_id) DO NOTHING;

-- 2. Создаём подписку на 30 дней
INSERT INTO subscriptions (
    user_id,
    tribute_subscription_id,
    status,
    start_date,
    end_date,
    created_at
)
SELECT
    id,
    'manual_1115719673_' || EXTRACT(EPOCH FROM NOW())::bigint,
    'active',
    NOW(),
    NOW() + INTERVAL '30 days',
    NOW()
FROM users
WHERE telegram_user_id = 1115719673
ON CONFLICT DO NOTHING;

-- 3. Проверка результата
SELECT
    u.telegram_user_id,
    u.first_name,
    s.status,
    s.start_date,
    s.end_date,
    EXTRACT(DAY FROM (s.end_date - NOW())) as days_left
FROM users u
LEFT JOIN subscriptions s ON s.user_id = u.id
WHERE u.telegram_user_id = 1115719673;


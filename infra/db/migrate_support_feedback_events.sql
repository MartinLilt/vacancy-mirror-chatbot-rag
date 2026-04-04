-- Add support_feedback_events table for Telegram Contact Support dashboard

CREATE TABLE IF NOT EXISTS support_feedback_events (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    telegram_username TEXT NOT NULL DEFAULT '',
    telegram_full_name TEXT NOT NULL DEFAULT '',
    reply_channel TEXT NOT NULL, -- telegram | email | none
    reply_email TEXT NOT NULL DEFAULT '',
    feedback_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS support_feedback_events_created_at_idx
    ON support_feedback_events (created_at DESC);

CREATE INDEX IF NOT EXISTS support_feedback_events_user_id_idx
    ON support_feedback_events (telegram_user_id);


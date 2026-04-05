-- Add support_feedback_events table for Telegram Contact Support dashboard

CREATE TABLE IF NOT EXISTS support_feedback_events (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    telegram_username TEXT NOT NULL DEFAULT '',
    telegram_full_name TEXT NOT NULL DEFAULT '',
    reply_channel TEXT NOT NULL, -- telegram | email | none
    reply_email TEXT NOT NULL DEFAULT '',
    feedback_message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new', -- new | in_progress | replied | closed
    assigned_to TEXT NOT NULL DEFAULT '',
    last_reply_at TIMESTAMPTZ,
    chatwoot_conversation_id BIGINT,
    chatwoot_contact_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE support_feedback_events
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';
ALTER TABLE support_feedback_events
    ADD COLUMN IF NOT EXISTS assigned_to TEXT NOT NULL DEFAULT '';
ALTER TABLE support_feedback_events
    ADD COLUMN IF NOT EXISTS last_reply_at TIMESTAMPTZ;
ALTER TABLE support_feedback_events
    ADD COLUMN IF NOT EXISTS chatwoot_conversation_id BIGINT;
ALTER TABLE support_feedback_events
    ADD COLUMN IF NOT EXISTS chatwoot_contact_id BIGINT;

CREATE INDEX IF NOT EXISTS support_feedback_events_created_at_idx
    ON support_feedback_events (created_at DESC);

CREATE INDEX IF NOT EXISTS support_feedback_events_user_id_idx
    ON support_feedback_events (telegram_user_id);

CREATE INDEX IF NOT EXISTS support_feedback_events_status_idx
    ON support_feedback_events (status);

CREATE INDEX IF NOT EXISTS support_feedback_events_chatwoot_conversation_idx
    ON support_feedback_events (chatwoot_conversation_id);

CREATE TABLE IF NOT EXISTS support_replies (
    id BIGSERIAL PRIMARY KEY,
    feedback_event_id BIGINT NOT NULL REFERENCES support_feedback_events(id) ON DELETE CASCADE,
    channel TEXT NOT NULL, -- telegram | email
    sent_to TEXT NOT NULL DEFAULT '',
    reply_text TEXT NOT NULL,
    operator_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL, -- sent | failed
    source TEXT NOT NULL DEFAULT 'support_api', -- support_api | chatwoot
    external_message_id TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE support_replies
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'support_api';
ALTER TABLE support_replies
    ADD COLUMN IF NOT EXISTS external_message_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS support_replies_event_id_idx
    ON support_replies (feedback_event_id);

CREATE INDEX IF NOT EXISTS support_replies_created_at_idx
    ON support_replies (created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS support_replies_external_message_id_uidx
    ON support_replies (external_message_id)
    WHERE external_message_id <> '';


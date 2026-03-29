-- Migration: create subscriptions table
-- Run once against an existing database.
-- Safe to re-run (uses IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    plan TEXT NOT NULL, -- 'free' | 'plus' | 'pro_plus'
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- 'active' | 'cancelled' | 'past_due'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
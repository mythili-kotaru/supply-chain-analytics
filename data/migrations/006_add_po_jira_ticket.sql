-- Migration: Add jira_ticket_key column to purchase_orders table
-- Day 12/Enhancement: Jira integration

ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS jira_ticket_key TEXT;

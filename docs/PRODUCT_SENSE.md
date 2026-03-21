# Product Sense

## Purpose

This file explains how to choose product-friendly behavior when multiple technical options are possible.

## Rules

- Optimize for fast and readable delivery in Telegram chats.
- Treat mobile readability as the default UX constraint.
- Avoid noisy captions and confusing partial-success behavior.
- Prefer graceful degradation over brittle feature promises.
- Keep stable sources predictable; treat experimental sources as explicitly non-stable.

## Practical Defaults

- captions should be compact and useful on phone screens;
- content titles should not degrade into hashtag spam;
- partial success should be explained clearly instead of silently looking complete;
- command behavior in a chat should feel predictable and local to that chat;
- unsupported sources should fail clearly without pretending to be temporarily stable.

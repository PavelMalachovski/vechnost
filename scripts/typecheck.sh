#!/usr/bin/env bash
# Strict type checking, on the modules that can hold the line.
#
# The repository as a whole does not type-check cleanly yet (run
# `mypy vechnost_bot` to see the backlog; most of it is missing annotations,
# and the `union-attr` findings in the Telegram handlers are worth a pass of
# their own). Gating CI on the whole thing would mean turning the strict
# settings off, which would gate on nothing.
#
# So the gate is this list instead: the domain layer, the models and the
# content loaders - everything that imports neither FastAPI nor
# python-telegram-bot, plus the small modules around it that already pass.
# `--follow-imports=silent` type-checks their dependencies without reporting
# errors inside them, so a module joins the list by being clean itself.
#
# Add new domain modules here. Removing one needs a reason.
set -euo pipefail

cd "$(dirname "$0")/.."

# `python -m mypy`, not `mypy`: a mypy installed as a standalone tool runs
# on its own interpreter and cannot see the project's dependencies, so it
# reports every third-party import as missing.
exec python -m mypy --follow-imports=silent \
    vechnost_bot/broadcast.py \
    vechnost_bot/callback_models.py \
    vechnost_bot/compat.py \
    vechnost_bot/compat_notify.py \
    vechnost_bot/config.py \
    vechnost_bot/freemium.py \
    vechnost_bot/i18n.py \
    vechnost_bot/invites.py \
    vechnost_bot/keyboards.py \
    vechnost_bot/library.py \
    vechnost_bot/logic.py \
    vechnost_bot/models.py \
    vechnost_bot/referrals.py \
    vechnost_bot/retention.py \
    vechnost_bot/steps69.py \
    vechnost_bot/steps69_notify.py \
    vechnost_bot/payments/signature.py \
    vechnost_bot/payments/tribute_event.py

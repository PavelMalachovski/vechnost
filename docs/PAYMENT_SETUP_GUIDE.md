# Payments with Tribute

How the paywall is wired to [Tribute](https://tribute.to), how to set it up,
and where to look when a payment does not turn into access. Every setting
named here is in [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md).

## How it works

- **Access is a row, not a payment.** A person has access when they hold an
  active, unexpired `subscriptions` row (a one-time purchase is a row with
  no expiry), or a redeemed certificate that has not been revoked, or when
  `ENABLE_PAYMENT` is off. A `payments` row is a journal entry and never
  counts by itself. The one function that decides is
  `payments/services.py::user_has_access`.
- **Tribute tells the web process.** Every event is a `POST` to
  `/webhooks/tribute`, signed: HMAC-SHA256 of the raw body, keyed by
  `TRIBUTE_API_KEY`, in the `trbt-signature` header. `WEBHOOK_SECRET` is an
  optional second key for a relay or a test harness, accepted alongside the
  API key, never instead of it. With `ENABLE_PAYMENT=true` and no key, every
  delivery is refused. Bodies are cut off at 64 KB.
- **What an event does is a table** (`payments/tribute_event.py`):

  | Event | Effect |
  |---|---|
  | `new_digital_product`, `new_subscription`, `renewed_subscription` | Grant: a lifetime row for a product, a row until `expires_at` for a subscription |
  | `cancelled_subscription` | Cancel: access stays until the `expires_at` already paid for |
  | a refund or a chargeback | Revoke, at once |
  | anything else | Acknowledged with a 200, recorded in `webhook_events`, changes nothing |

  Events apply in the order they happened (`created_at`), so a purchase
  redelivered after its own refund does not grant again, and one event is
  processed once however many times Tribute sends it.
- **Three products, told apart by id or page.** The access itself
  (`ACCESS_PRODUCT_ID`; unset, the cheapest synced product that is neither
  of the next two), the gift (`GIFT_PRODUCT_ID`: a purchase mints a
  certificate for the buyer to hand on, and its refund revokes that
  certificate, never the buyer's own access) and, optionally, the referral
  discount (`REFERRAL_PAYMENT_URL`: the page shown to someone who arrived
  on an invite link; Tribute owns the price).
- **The buyer is told.** After a grant the bot sends «всё открыто»
  (`payments/grant_notify.py`); the Mini App asks for access again when it
  comes back into view.

## Setting it up

1. In Tribute, create the access product (and, if you want them, the gift
   and the discounted referral product). Note their ids and payment pages.
2. Set, on the production service: `ENABLE_PAYMENT=true`,
   `TRIBUTE_API_KEY`, `TRIBUTE_PAYMENT_URL` (the access product's page),
   `ACCESS_PRODUCT_ID`, and `ADMIN_TOKEN` for the admin endpoint; the gift
   and referral variables if you use them.
3. In the Tribute dashboard, point the webhook at
   `https://<your web process>/webhooks/tribute`. Tribute signs with the API
   key; there is no separate secret to enter there.
4. Pull the products into the database, so prices and links are known:

   ```bash
   curl -X POST https://<your web process>/admin/sync-products \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   # or, in a shell with the production settings:
   python scripts/sync_products.py
   ```

   `/admin/*` authenticates against `ADMIN_TOKEN` (falling back to
   `TRIBUTE_API_KEY`) and answers 503 when neither is set.

No migration step is needed: the tables are created, and new columns added,
when the process starts.

## Locally

With `ENABLE_PAYMENT` unset (false) everything is open and no Tribute setup
is needed. To exercise the paywall, set `ENABLE_PAYMENT=true` and any
`TRIBUTE_API_KEY`, start the web process, and send it deliveries signed with
that key:

```bash
python scripts/test_webhook.py                          # a purchase by a fake buyer
python scripts/test_webhook.py cancelled_subscription --user 123456789
python scripts/test_webhook.py --bad-signature          # must come back 401
```

The two-user suite (`tests/e2e`) buys access the same way, with a signed
webhook, in every run.

## When a payment did not become access

1. `python scripts/check_user_simple.py <telegram id>` shows the person's
   row, subscriptions (lifetime ones too), payments, and whether they have
   access, through the same repositories the bot uses.
2. Look for the delivery in `webhook_events`: its `status_code` and `error`
   say what happened. A rejected delivery leaves no row, so Tribute's retry
   is judged on its own.
3. Rows whose `body_sha256` starts with `released:` are deliveries an older
   version rejected; redeliver them from the Tribute dashboard:
   `SELECT name, sent_at, created_at, error FROM webhook_events WHERE body_sha256 LIKE 'released:%';`
4. To grant access by hand, mint one certificate
   (`python scripts/generate_certificates.py 1`) and send the person the
   code; they redeem it with `/activate`.

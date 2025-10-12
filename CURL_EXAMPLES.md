# cURL Examples for Testing Tribute Webhooks

## Prerequisites

Set your Tribute API key:
```bash
export TRIBUTE_API_KEY="your_actual_tribute_api_key_here"
```

---

## How Signature Verification Works

The webhook handler verifies the `trbt-signature` header using HMAC-SHA256:

```python
# Server-side verification (what the API does)
expected_signature = hmac.new(
    TRIBUTE_API_KEY.encode(),
    raw_body_bytes,
    hashlib.sha256
).hexdigest()

# Compare with header value
if hmac.compare_digest(expected_signature, received_signature):
    # Valid signature
```

**Important**: The signature is computed on the **raw body bytes**, not parsed JSON!

---

## Example 1: New Digital Product

```bash
# Set variables
API_KEY="${TRIBUTE_API_KEY}"
URL="http://localhost:8000/webhook/tribute"

# JSON payload
BODY='{"event_name":"new_digital_product","telegram_user_id":123456789,"username":"testuser","first_name":"John","last_name":"Doe","amount":299,"currency":"RUB","product_id":1}'

# Generate HMAC-SHA256 signature
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

# Send webhook
curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"

# Expected response:
# {"ok":true}
```

---

## Example 2: New Subscription

```bash
API_KEY="${TRIBUTE_API_KEY}"
URL="http://localhost:8000/webhook/tribute"

BODY='{"event_name":"new_subscription","telegram_user_id":123456789,"username":"testuser","first_name":"John","last_name":"Doe","subscription_id":456,"period":"monthly","amount":299,"currency":"RUB","expires_at":"2025-02-12T00:00:00Z"}'

SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"

# Expected response:
# {"ok":true}
```

---

## Example 3: Cancelled Subscription

```bash
API_KEY="${TRIBUTE_API_KEY}"
URL="http://localhost:8000/webhook/tribute"

BODY='{"event_name":"cancelled_subscription","telegram_user_id":123456789,"subscription_id":456}'

SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"

# Expected response:
# {"ok":true}
```

---

## Example 4: Test Idempotency (Duplicate Detection)

Send the same webhook twice:

```bash
API_KEY="${TRIBUTE_API_KEY}"
URL="http://localhost:8000/webhook/tribute"

# Same body for both requests
BODY='{"event_name":"new_digital_product","telegram_user_id":999999,"amount":100,"currency":"RUB","product_id":1}'

SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

# First request
echo "=== First Request ==="
curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"
echo ""

# Second request (duplicate)
echo "=== Second Request (Duplicate) ==="
curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"
echo ""

# Expected responses:
# First:  {"ok":true}
# Second: {"ok":true,"dup":true}
```

---

## Example 5: Invalid Signature (Should Fail)

```bash
URL="http://localhost:8000/webhook/tribute"

BODY='{"event_name":"new_digital_product","telegram_user_id":123,"amount":100}'

# Wrong signature
SIGNATURE="invalid_signature_1234567890abcdef"

curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"

# Expected response:
# {"detail":"Invalid signature"}
# HTTP Status: 401 Unauthorized
```

---

## Example 6: Missing Signature Header

```bash
URL="http://localhost:8000/webhook/tribute"

BODY='{"event_name":"new_digital_product","telegram_user_id":123,"amount":100}'

# No trbt-signature header
curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$BODY"

# Expected response:
# {"detail":"Invalid signature"}
# HTTP Status: 401 Unauthorized
```

---

## Example 7: Malformed JSON

```bash
API_KEY="${TRIBUTE_API_KEY}"
URL="http://localhost:8000/webhook/tribute"

# Invalid JSON
BODY='{"event_name":"new_digital_product",invalid json here}'

SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "trbt-signature: $SIGNATURE" \
  -d "$BODY"

# Expected response:
# {"detail":"Invalid JSON body"}
# HTTP Status: 400 Bad Request
```

---

## Generating Signatures in Different Languages

### Python
```python
import hmac
import hashlib
import json

api_key = "your_tribute_api_key"
body = {"event_name": "new_digital_product", "telegram_user_id": 123}

# Convert to JSON bytes
body_bytes = json.dumps(body, separators=(',', ':')).encode()

# Generate signature
signature = hmac.new(
    api_key.encode(),
    body_bytes,
    hashlib.sha256
).hexdigest()

print(f"trbt-signature: {signature}")
```

### Node.js
```javascript
const crypto = require('crypto');

const apiKey = 'your_tribute_api_key';
const body = {event_name: 'new_digital_product', telegram_user_id: 123};

// Convert to JSON string
const bodyStr = JSON.stringify(body);

// Generate signature
const signature = crypto
  .createHmac('sha256', apiKey)
  .update(bodyStr)
  .digest('hex');

console.log(`trbt-signature: ${signature}`);
```

### PHP
```php
<?php
$apiKey = 'your_tribute_api_key';
$body = ['event_name' => 'new_digital_product', 'telegram_user_id' => 123];

// Convert to JSON
$bodyJson = json_encode($body);

// Generate signature
$signature = hash_hmac('sha256', $bodyJson, $apiKey);

echo "trbt-signature: $signature\n";
?>
```

### Go
```go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
)

func main() {
    apiKey := "your_tribute_api_key"
    body := map[string]interface{}{
        "event_name": "new_digital_product",
        "telegram_user_id": 123,
    }

    // Convert to JSON
    bodyBytes, _ := json.Marshal(body)

    // Generate signature
    h := hmac.New(sha256.New, []byte(apiKey))
    h.Write(bodyBytes)
    signature := hex.EncodeToString(h.Sum(nil))

    fmt.Printf("trbt-signature: %s\n", signature)
}
```

---

## Testing with HTTPie (Alternative to curl)

If you have HTTPie installed:

```bash
API_KEY="${TRIBUTE_API_KEY}"
BODY='{"event_name":"new_digital_product","telegram_user_id":123,"amount":299}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

http POST http://localhost:8000/webhook/tribute \
  trbt-signature:$SIG \
  event_name=new_digital_product \
  telegram_user_id:=123 \
  amount:=299
```

---

## Verifying Database After Webhook

After sending webhooks, check the database:

```bash
# SQLite
sqlite3 tribute.db << EOF
.headers on
.mode column

SELECT * FROM users;
SELECT * FROM payments ORDER BY created_at DESC LIMIT 5;
SELECT * FROM subscriptions;
SELECT * FROM webhook_events ORDER BY created_at DESC LIMIT 5;
EOF
```

---

## Health Check

```bash
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","service":"tribute-webhook"}
```

---

## API Documentation

Open in browser:
- Interactive docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Notes

1. **Signature must match exactly** - any change to the body invalidates the signature
2. **Use raw body bytes** - don't pretty-print JSON or add whitespace
3. **Lowercase hex** - signature should be lowercase hexadecimal
4. **Test idempotency** - same body + signature = duplicate detection
5. **Secure your API key** - never commit to git, use environment variables

---

## Automated Testing

Use the provided script:

```bash
# Make executable (Linux/Mac)
chmod +x test_webhook.sh

# Run all tests
./test_webhook.sh

# Or manually set variables
TRIBUTE_API_KEY="your_key" ./test_webhook.sh
```

---

## Production Webhook URL

When deploying to production, Tribute will send webhooks to:

```
POST https://your-domain.com/webhook/tribute
```

Make sure:
- ✅ HTTPS enabled (required for security)
- ✅ Firewall allows incoming connections
- ✅ DNS properly configured
- ✅ API key matches Tribute dashboard
- ✅ Server logs webhook attempts for debugging


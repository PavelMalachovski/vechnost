#!/bin/bash
# Test webhook with proper signature

# Configuration
API_KEY="${TRIBUTE_API_KEY:-your_api_key_here}"
URL="${WEBHOOK_URL:-http://localhost:8000/webhook/tribute}"

# Test payloads
test_new_digital_product() {
  echo "Testing: new_digital_product"
  BODY='{"event_name":"new_digital_product","telegram_user_id":123456789,"username":"testuser","first_name":"Test","last_name":"User","amount":299,"currency":"RUB","product_id":1}'
  SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "trbt-signature: $SIGNATURE" \
    -d "$BODY"
  echo -e "\n"
}

test_new_subscription() {
  echo "Testing: new_subscription"
  BODY='{"event_name":"new_subscription","telegram_user_id":123456789,"username":"testuser","subscription_id":456,"period":"monthly","amount":299,"currency":"RUB","expires_at":"2025-02-12T00:00:00Z"}'
  SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "trbt-signature: $SIGNATURE" \
    -d "$BODY"
  echo -e "\n"
}

test_cancelled_subscription() {
  echo "Testing: cancelled_subscription"
  BODY='{"event_name":"cancelled_subscription","telegram_user_id":123456789,"subscription_id":456}'
  SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "trbt-signature: $SIGNATURE" \
    -d "$BODY"
  echo -e "\n"
}

test_duplicate() {
  echo "Testing: duplicate webhook (should return dup:true)"
  # Send same payload twice
  BODY='{"event_name":"new_digital_product","telegram_user_id":999999,"amount":100,"currency":"RUB"}'
  SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$API_KEY" | awk '{print $2}')

  echo "First request:"
  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "trbt-signature: $SIGNATURE" \
    -d "$BODY"
  echo -e "\n"

  echo "Second request (duplicate):"
  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "trbt-signature: $SIGNATURE" \
    -d "$BODY"
  echo -e "\n"
}

test_invalid_signature() {
  echo "Testing: invalid signature (should return 401)"
  BODY='{"event_name":"new_digital_product","telegram_user_id":123,"amount":100}'
  SIGNATURE="invalid_signature_12345"

  curl -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "trbt-signature: $SIGNATURE" \
    -d "$BODY"
  echo -e "\n"
}

# Run tests
echo "=== Tribute Webhook Tests ==="
echo "API Key: ${API_KEY:0:10}..."
echo "URL: $URL"
echo ""

test_new_digital_product
test_new_subscription
test_cancelled_subscription
test_duplicate
test_invalid_signature

echo "=== Tests Complete ==="


# Webhook integration guide

## Signing

Webhook payloads are signed with HMAC-SHA256. Verify the signature using the endpoint secret before processing the event.

## Retries

Failed webhook deliveries are retried after 1, 5, and 30 minutes. No further automatic retries are scheduled after the third retry.

## Acknowledgment

Return a 2xx status within 5 seconds to acknowledge a webhook. Perform slow processing after acknowledgment.

## Deduplication

Store the event_id for 24 hours and ignore already processed event IDs. Delivery is at least once, not exactly once.

## Secret rotation

During secret rotation, old and new secrets overlap for 60 minutes. After that interval the old secret is invalid.

## Error W409

Error W409 indicates an endpoint URL is already registered in the same workspace. Update the existing endpoint instead of registering it again.

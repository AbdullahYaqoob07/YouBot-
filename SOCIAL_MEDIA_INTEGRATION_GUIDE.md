# Social Media Integration Guide

This guide explains how to connect social channels to YouBot using the new social integration APIs.

## 1. What Is Implemented

You now have two onboarding paths:

1. Generic adapter path (works with any social platform)
- Inbound endpoint: `POST /integrations/social/{connection_key}/messages`
- You can keep your own platform adapter and just forward normalized messages to YouBot.

2. Direct Meta webhook path (WhatsApp/Facebook/Instagram via Meta webhooks)
- Verify endpoint: `GET /integrations/social/meta/{connection_key}/webhook`
- Event endpoint: `POST /integrations/social/meta/{connection_key}/webhook`
- Signature validation supported with `X-Hub-Signature-256` when `appSecret` is configured.

Admin APIs are available to register and manage social connections per workspace.

## 2. Prerequisites

1. Backend is running.
2. `LLM_CONFIG_ENCRYPTION_KEY` is configured in `.env`.
3. Tenant/workspace context headers are known:
- `X-Tenant-Id`
- `X-Workspace-Id`
4. Admin key is known:
- `X-Admin-Key`

## 3. Create a Social Connection (Admin)

### Endpoint
`POST /admin/workspaces/{workspace_id}/social-connections`

### Headers
- `X-Tenant-Id: public` (example)
- `X-Workspace-Id: default` (example)
- `X-Admin-Key: <ADMIN_KEY>`

### Body (Meta example)
```json
{
  "name": "Meta WhatsApp Primary",
  "provider": "meta",
  "channel": "whatsapp",
  "verifyToken": "my_meta_verify_token",
  "accessToken": "EAAB...",
  "appSecret": "meta_app_secret",
  "metadata": {
    "graph_api_version": "v21.0",
    "phone_number_id": "1234567890"
  },
  "isActive": true
}
```

### Body (Generic adapter example)
```json
{
  "name": "Custom Social Adapter",
  "provider": "generic",
  "channel": "social",
  "outboundWebhookUrl": "https://my-adapter.example.com/youbot/replies",
  "outboundAuthHeaders": {
    "Authorization": "Bearer <adapter-token>"
  },
  "isActive": true
}
```

### Response
Response includes:
- `connection.connection_key`
- `connection.integrationPaths.generic`
- `connection.integrationPaths.metaWebhook`

Use these URLs in your provider dashboards.

## 4. List and Manage Connections

1. List:
- `GET /admin/workspaces/{workspace_id}/social-connections`

2. Enable/disable:
- `PUT /admin/workspaces/{workspace_id}/social-connections/{connection_id}`
- Body:
```json
{ "isActive": false }
```

## 5. Generic Adapter Integration (Any Social Platform)

Your adapter normalizes incoming events to this payload:

`POST /integrations/social/{connection_key}/messages`

```json
{
  "message": "How can I start?",
  "userId": "social_user_123",
  "channel": "instagram",
  "sessionId": "optional-session-id",
  "userName": "Sara",
  "metadata": {
    "provider": "instagram",
    "thread_id": "abc123"
  }
}
```

The response includes the AI reply and routing state:
- `message`
- `handoff`
- `assignedTo`
- `queueStatus`
- `dispatch`

## 6. Direct Meta Webhook Integration

Use the returned `metaWebhook` URL in Meta App Webhooks config.

### Verification handshake
Meta sends:
- `hub.mode`
- `hub.verify_token`
- `hub.challenge`

YouBot verifies token and returns challenge automatically.

### Event handling
Meta sends message events to:
- `POST /integrations/social/meta/{connection_key}/webhook`

Supported inbound payload styles:
- WhatsApp Cloud API message events
- Messenger/Instagram messaging events that contain `entry[].messaging[].message.text`

### Outbound behavior
Outbound priority:
1. If `outboundWebhookUrl` is configured, YouBot POSTs replies there.
2. Else for `provider=meta`:
- WhatsApp: direct send via Graph API (requires `accessToken` and `phone_number_id`)
- Facebook/Instagram: best-effort send via Graph `/me/messages`
3. Else no outbound dispatch (response still returned to caller).

## 7. Security Notes

1. Keep admin endpoints behind admin key only.
2. Use `appSecret` for Meta signature validation.
3. Rotate `accessToken` and `verifyToken` periodically.
4. Keep `connection_key` private.
5. Restrict outbound callback URLs to trusted domains.

## 8. Minimum Production Checklist

1. Create connection and verify active status.
2. Confirm Meta webhook verification passes.
3. Send a real social message and verify AI reply.
4. Confirm handoff path appears in supervision queue when needed.
5. Confirm tenant/workspace routing is correct.
6. Confirm outbound dispatch succeeds (provider API or callback URL).

# WorkIQ Teams MCP Server — Input & Output Schemas

> Generated 2026-05-12 via live calls against the ProjectRoma tenant.
> Each tool's **Input Schema** lists all parameters; **Output Schema** shows the actual JSON response from a live call.

---

## 1. ListTeams

### Input Schema
```json
{
  // No parameters
}
```

### Output Schema
```json
{
  "teams": [
    {
      "id": "4050da83-663a-40fc-9a3f-4267ff7097d6",
      "displayName": "ProjectRoma",
      "description": "ProjectRoma",
      "webUrl": null
    }
  ]
}
```

---

## 2. GetTeam

### Input Schema
```json
{
  "teamId": "(string, required) The team's GUID from ListTeams.",
  "select": "(string, optional) Comma-separated fields to return. Defaults to id, displayName, description, createdDateTime, webUrl.",
  "expand": "(string, optional) Relationship to expand inline. Use 'members' to include team members."
}
```

### Output Schema
```json
{
  "id": "4050da83-663a-40fc-9a3f-4267ff7097d6",
  "displayName": "ProjectRoma",
  "description": "ProjectRoma",
  "createdDateTime": "2026-04-24T12:51:08Z",
  "webUrl": "https://teams.microsoft.com/l/team/19%3aoE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1%40thread.tacv2/conversations?groupId=4050da83-663a-40fc-9a3f-4267ff7097d6&tenantId=090fc601-8371-4167-8b63-dd3a11028a43"
}
```

---

## 3. ListChannels

### Input Schema
```json
{
  "teamId": "(string, required) The team's GUID from ListTeams.",
  "select": "(string, optional) Comma-separated fields. Defaults to id, displayName, description, createdDateTime, webUrl, membershipType.",
  "filter": "(string, optional) OData filter expression, e.g. \"membershipType eq 'standard'\"."
}
```

### Output Schema
```json
{
  "channels": [
    {
      "id": "19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2",
      "displayName": "General",
      "description": "ProjectRoma",
      "membershipType": "Standard",
      "createdDateTime": "2026-04-24T12:51:08Z",
      "webUrl": "https://teams.cloud.microsoft/l/channel/19%3AoE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1%40thread.tacv2/ProjectRoma?groupId=4050da83-663a-40fc-9a3f-4267ff7097d6&tenantId=090fc601-8371-4167-8b63-dd3a11028a43&allowXTenantAccess=False"
    }
  ]
}
```

---

## 4. GetChannel

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "select": "(string, optional) Comma-separated fields. Defaults to id, displayName, description, createdDateTime, webUrl, membershipType."
}
```

### Output Schema
```json
{
  "id": "19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2",
  "displayName": "General",
  "description": "ProjectRoma",
  "membershipType": "Standard",
  "createdDateTime": "2026-04-24T12:51:08Z",
  "webUrl": "https://teams.cloud.microsoft/l/channel/19%3AoE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1%40thread.tacv2/General?groupId=4050da83-663a-40fc-9a3f-4267ff7097d6&tenantId=090fc601-8371-4167-8b63-dd3a11028a43&allowXTenantAccess=False"
}
```

---

## 5. ListChannelMembers

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "top": "(integer, optional, default: 100) Maximum number of members to return (1-100)."
}
```

### Output Schema
```json
{
  "members": [
    {
      "id": "MCMjMiMj...base64-encoded-membership-id...",
      "displayName": "Boris Admin",
      "email": "bdmin@projectroma.onmicrosoft.com",
      "userId": "a5ec5c13-1974-4ad6-b549-9169907d9e32",
      "roles": ["owner"]
    },
    {
      "id": "MCMjMiMj...base64-encoded-membership-id...",
      "displayName": "Boris",
      "email": "boris@projectroma.onmicrosoft.com",
      "userId": "c7844335-ebd8-4c3a-8dc9-53e198cea9ba",
      "roles": []
    },
    {
      "id": "MCMjMiMj...base64-encoded-membership-id...",
      "displayName": "Santiago",
      "email": "santiago@projectroma.onmicrosoft.com",
      "userId": "9336459d-7269-40d5-8506-cb314cbfab59",
      "roles": ["owner"]
    }
  ]
}
```

---

## 6. ListChannelMessages

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "top": "(integer, optional, default: 20) Number of messages per page (1-50). Most recent first.",
  "nextLink": "(string, optional) Pagination URL from a previous response."
}
```

### Output Schema
```json
{
  "messages": [
    {
      "id": "1778503455487",
      "createdDateTime": "2026-05-11T12:44:15Z",
      "from": {
        "displayName": "Shruti",
        "userId": "e0110cac-2412-404e-9635-db9a2a07ed3e"
      },
      "body": {
        "contentType": "Text",
        "content": ""
      }
    },
    {
      "id": "1778367232829",
      "createdDateTime": "2026-05-09T22:53:52Z",
      "from": null,
      "body": {
        "contentType": "Html",
        "content": "<systemEventMessage/>"
      }
    },
    {
      "id": "1777557658280",
      "createdDateTime": "2026-04-30T14:00:58Z",
      "from": {
        "displayName": "Amaury",
        "userId": "cfa80a45-1c1f-4863-88f2-bd3d6eb70ad2"
      },
      "body": {
        "contentType": "Text",
        "content": "Current mcp config:..."
      }
    }
  ],
  "hasMoreResults": true,
  "nextLink": "https://graph.microsoft.com/v1.0/teams/{teamId}/channels/{channelId}/messages?$top=5&$skiptoken=..."
}
```

---

## 7. ListChannelMessageReplies

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "messageId": "(string, required) Parent message ID to fetch replies for.",
  "maxReplies": "(integer, optional, default: 50) Max replies per page (1-50).",
  "nextLink": "(string, optional) Pagination URL from a previous response."
}
```

### Output Schema
```json
{
  "replies": [
    {
      "id": "1778589398069",
      "createdDateTime": "2026-05-12T12:36:38Z",
      "from": {
        "displayName": "Rishi",
        "userId": "306c0249-7495-4140-bd5f-f476364a9653"
      },
      "body": {
        "contentType": "Text",
        "content": "Schema capture reply test — safe to ignore"
      }
    }
  ],
  "hasMoreResults": false,
  "parentMessageId": "1778589372628"
}
```

---

## 8. ListChannelFiles

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "top": "(integer, optional, default: 50) Number of files per page (1-50).",
  "nextLink": "(string, optional) Pagination URL from a previous response."
}
```

### Output Schema
```json
{
  "files": [
    {
      "id": "014EQSQX7EOK3UU5QUFVF242BDUDHLHAKK",
      "name": "schema-test.txt",
      "size": 24,
      "webUrl": "https://projectroma.sharepoint.com/sites/ProjectRoma/Shared%20Documents/General/schema-test.txt",
      "isFolder": false,
      "lastModifiedDateTime": "2026-05-12T12:37:33Z",
      "lastModifiedBy": "Rishi"
    }
  ],
  "hasMoreResults": false
}
```

---

## 9. ListChats

### Input Schema
```json
{
  "topic": "(string, optional) Filter chats by topic (case-insensitive, partial match).",
  "memberUpns": "(string[], optional) Filter chats by member UPN emails.",
  "fetchAllPages": "(boolean, optional, default: false) When true, fetches all pages with no cap."
}
```

### Output Schema
```json
{
  "chats": [
    {
      "id": "19:306c0249-7495-4140-bd5f-f476364a9653_9336459d-7269-40d5-8506-cb314cbfab59@unq.gbl.spaces",
      "topic": "",
      "chatType": "OneOnOne",
      "hasUnreadMessages": false,
      "lastMessagePreview": {
        "body": "",
        "createdDateTime": "2026-05-12T12:37:36Z",
        "from": "Rishi"
      },
      "members": [
        {
          "displayName": "Santiago",
          "email": "santiago@projectroma.onmicrosoft.com",
          "id": "9336459d-7269-40d5-8506-cb314cbfab59"
        },
        {
          "displayName": "Rishi",
          "email": "rishi@projectroma.onmicrosoft.com",
          "id": "306c0249-7495-4140-bd5f-f476364a9653"
        }
      ]
    }
  ],
  "totalScanned": 1,
  "hasMoreResults": false
}
```

> **Note:** `members` array is included when `memberUpns` filter is used. `lastMessagePreview` is an object with `{ body, createdDateTime, from }`. `topic` is empty string for 1:1 chats.

---

## 10. GetChat

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 or unq.gbl.spaces format."
}
```

### Output Schema
```json
{
  "id": "19:306c0249-7495-4140-bd5f-f476364a9653_9336459d-7269-40d5-8506-cb314cbfab59@unq.gbl.spaces",
  "topic": null,
  "chatType": "OneOnOne",
  "createdDateTime": "2026-05-12T12:36:11Z",
  "lastUpdatedDateTime": "2026-05-12T12:36:11Z"
}
```

---

## 11. ListChatMembers

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format."
}
```

### Output Schema
```json
{
  "members": [
    {
      "id": "MCMjMCMj...base64-encoded-membership-id...",
      "displayName": "Rishi",
      "email": "rishi@projectroma.onmicrosoft.com",
      "userId": "306c0249-7495-4140-bd5f-f476364a9653",
      "roles": ["owner"]
    },
    {
      "id": "MCMjMCMj...base64-encoded-membership-id...",
      "displayName": "Santiago",
      "email": "santiago@projectroma.onmicrosoft.com",
      "userId": "9336459d-7269-40d5-8506-cb314cbfab59",
      "roles": ["owner"]
    }
  ]
}
```

---

## 12. ListChatMessages

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "top": "(integer, optional, default: 20) Number of messages per page (1-50). Most recent first.",
  "nextLink": "(string, optional) Pagination URL from a previous response."
}
```

### Output Schema
```json
{
  "messages": [
    {
      "id": "1778589371672",
      "createdDateTime": "2026-05-12T12:36:11Z",
      "lastModifiedDateTime": "2026-05-12T12:36:11Z",
      "from": {
        "displayName": "Rishi",
        "id": "306c0249-7495-4140-bd5f-f476364a9653"
      },
      "body": {
        "contentType": "Text",
        "content": "Schema capture test — safe to ignore"
      }
    },
    {
      "id": "1778589371367",
      "createdDateTime": "2026-05-12T12:36:11Z",
      "lastModifiedDateTime": "2026-05-12T12:36:11Z",
      "from": {
        "displayName": null,
        "id": null
      },
      "body": {
        "contentType": "Html",
        "content": "<systemEventMessage/>"
      }
    }
  ],
  "hasMoreResults": false
}
```

---

## 13. GetChatMessage

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "messageId": "(string, required) Message ID."
}
```

### Output Schema
```json
{
  "id": "1778589371672",
  "createdDateTime": "2026-05-12T12:36:11Z",
  "lastModifiedDateTime": "2026-05-12T12:36:11Z",
  "from": {
    "displayName": "Rishi",
    "id": "306c0249-7495-4140-bd5f-f476364a9653"
  },
  "body": {
    "contentType": "Text",
    "content": "Schema capture test — safe to ignore"
  }
}
```

---

## 14. GetRichMessageFormats

### Input Schema
```json
{
  // No parameters
}
```

### Output Schema
```
Returns a plain-text reference guide (not JSON) containing:
- Supported HTML tags (b, i, strike, ul/ol/li, pre, blockquote, a, br, p, codeblock)
- @Mention syntax for users, teams, channels, apps (via the `mentions` parameter)
- Adaptive Card templates (Status/Report, Notification with Link, Summary List)
- Importance levels (normal, high, urgent)
- Combined example showing mentions + cards + importance
```

---

## 15. SearchTeamsMessages

### Input Schema
```json
{
  "message": "(string, required) Natural language search query.",
  "conversationId": "(string, optional) Existing conversation GUID for follow-up queries. Auto-created if missing."
}
```

### Output Schema
```json
{
  "conversationId": "ae4e0750-d029-4f77-a487-ff6e022a4a92",
  "timeZone": "America/Los_Angeles",
  "reply": "I searched your **Microsoft Teams messages**... (natural language summary with [N] citations)",
  "chatIds": [
    "19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2"
  ],
  "rawResponse": "{\"@odata.context\":\"...\",\"id\":\"ae4e0750-...\",\"createdDateTime\":\"...\",\"displayName\":\"...\",\"state\":\"active\",\"turnCount\":1,\"messages\":[{\"@odata.type\":\"#microsoft.graph.copilotConversationResponseMessage\",\"id\":\"...\",\"text\":\"...\",\"createdDateTime\":\"...\",\"adaptiveCards\":[],\"attributions\":[{\"attributionType\":\"citation\",\"providerDisplayName\":\"ProjectRoma\",\"attributionSource\":\"model\",\"seeMoreWebUrl\":\"...\"}],\"sensitivityLabel\":{\"sensitivityLabelId\":null,\"displayName\":null,\"tooltip\":null,\"priority\":null,\"color\":null}}]}",
  "message": "Teams messages searched successfully."
}
```

---

## 16. SearchTeamMessagesQueryParameters

### Input Schema
```json
{
  "queryString": "(string, required) KQL query string. Supports: plain keywords, from:, sent:, boolean operators (AND, OR, NOT), phrase matching.",
  "size": "(integer, optional, default: 25, max: 25) Number of results per request.",
  "from": "(integer, optional) Zero-based pagination offset."
}
```

### Output Schema
```json
{
  "rawResponse": "{\"value\":[{\"searchTerms\":[\"project\"],\"hitsContainers\":[{\"hits\":[{\"hitId\":\"AAMkAGY5...\",\"rank\":1,\"summary\":\"Current mcp config: ...\",\"resource\":{\"@odata.type\":\"microsoft.graph.chatMessage\",\"id\":\"1777557658280\",\"createdDateTime\":\"2026-04-30T14:00:59Z\",\"lastModifiedDateTime\":\"2026-04-30T14:06:00Z\",\"importance\":\"normal\",\"webLink\":\"https://teams.microsoft.com/l/message/...\",\"from\":{\"emailAddress\":{\"name\":\"Amaury\",\"address\":\"amchamay@projectroma.onmicrosoft.com\"}},\"channelIdentity\":{\"channelId\":\"19:oE5...@thread.tacv2\",\"teamId\":\"4050da83-...\"},\"etag\":\"1777557658280\",\"chatId\":\"19:oE5...@thread.tacv2\"}}],\"total\":7,\"moreResultsAvailable\":true}]}],\"@odata.context\":\"https://graph.microsoft.com/v1.0/$metadata#Collection(microsoft.graph.searchResponse)\"}",
  "message": "Teams messages searched with query parameters successfully."
}
```

---

## 17. SendMessageToSelf

### Input Schema
```json
{
  "content": "(string, required) Message text content.",
  "contentType": "(string, optional) 'text' or 'html'. Auto-switches to 'html' when mentions/cards present.",
  "importance": "(string, optional) 'normal' (default), 'high', or 'urgent'.",
  "mentions": "(string, optional) JSON array of @mentions.",
  "adaptiveCardJson": "(string, optional) Adaptive Card JSON."
}
```

### Output Schema
```json
{
  "id": "1778589366617",
  "chatId": "48:notes",
  "createdDateTime": "2026-05-12T12:36:06Z",
  "message": "Message sent to self successfully."
}
```

---

## 18. SendMessageToUser

### Input Schema
```json
{
  "userIdOrUpn": "(string, required) Target user's UPN email or GUID.",
  "content": "(string, required) Message text content.",
  "contentType": "(string, optional) 'text' or 'html'.",
  "importance": "(string, optional) 'normal' (default), 'high', or 'urgent'.",
  "mentions": "(string, optional) JSON array of @mentions.",
  "adaptiveCardJson": "(string, optional) Adaptive Card JSON."
}
```

### Output Schema
```json
{
  "id": "1778589371672",
  "chatId": "19:306c0249-7495-4140-bd5f-f476364a9653_9336459d-7269-40d5-8506-cb314cbfab59@unq.gbl.spaces",
  "userIdOrUpn": "santiago@projectroma.onmicrosoft.com",
  "createdDateTime": "2026-05-12T12:36:11Z",
  "message": "Message sent to user successfully."
}
```

---

## 19. SendMessageToChannel

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "content": "(string, required) Message text content.",
  "contentType": "(string, optional) 'text' or 'html'.",
  "importance": "(string, optional) 'normal' (default), 'high', or 'urgent'.",
  "mentions": "(string, optional) JSON array of @mentions.",
  "subject": "(string, optional) Subject line for the channel post (bold header).",
  "adaptiveCardJson": "(string, optional) Adaptive Card JSON."
}
```

### Output Schema
```json
{
  "id": "1778589372628",
  "teamId": "4050da83-663a-40fc-9a3f-4267ff7097d6",
  "channelId": "19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2",
  "createdDateTime": "2026-05-12T12:36:12Z",
  "message": "Message sent successfully."
}
```

---

## 20. SendMessageToChat

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "content": "(string, required) Message text content.",
  "contentType": "(string, optional) 'text' or 'html'.",
  "importance": "(string, optional) 'normal' (default), 'high', or 'urgent'.",
  "mentions": "(string, optional) JSON array of @mentions.",
  "adaptiveCardJson": "(string, optional) Adaptive Card JSON."
}
```

### Output Schema
```json
{
  "id": "1778589434289",
  "chatId": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "createdDateTime": "2026-05-12T12:37:14Z",
  "message": "Message sent successfully."
}
```

---

## 21. ReplyToChannelMessage

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "messageId": "(string, required) Parent message ID to reply to.",
  "content": "(string, required) Reply text content.",
  "contentType": "(string, optional) 'text' or 'html'.",
  "importance": "(string, optional) 'normal' (default), 'high', or 'urgent'.",
  "mentions": "(string, optional) JSON array of @mentions.",
  "adaptiveCardJson": "(string, optional) Adaptive Card JSON."
}
```

### Output Schema
```json
{
  "id": "1778589398069",
  "teamId": "4050da83-663a-40fc-9a3f-4267ff7097d6",
  "channelId": "19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2",
  "parentMessageId": "1778589372628",
  "createdDateTime": "2026-05-12T12:36:38Z",
  "message": "Reply posted successfully."
}
```

---

## 22. CreateChat

### Input Schema
```json
{
  "chatType": "(string, required) 'oneOnOne' or 'group'.",
  "members_upns": "(string[], required) Array of UPN emails for participants. You are auto-added.",
  "topic": "(string, optional) Chat title (group chats only)."
}
```

### Output Schema
```json
{
  "id": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "chatType": "Group",
  "topic": "Schema Capture Test Chat",
  "createdDateTime": "2026-05-12T12:36:47Z",
  "message": "Chat created successfully."
}
```

---

## 23. CreateChannel

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "displayName": "(string, required) Channel display name.",
  "description": "(string, optional) Channel description.",
  "membershipType": "(string, optional, default: 'standard') 'standard', 'private', or 'shared'."
}
```

### Output Schema
```json
{
  "id": "19:6RW9gnU7hweuf3wkLAUruTzdni0MYZYIFwfbQ8WU06E1@thread.tacv2",
  "displayName": "Schema Capture Test Channel",
  "description": "Temporary channel for schema capture — safe to delete",
  "membershipType": "Private",
  "createdDateTime": "2026-05-12T12:41:53Z",
  "message": "Channel created successfully."
}
```

---

## 24. UpdateChat

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "topic": "(string, required) New display name for the group chat."
}
```

### Output Schema
```json
{
  "id": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "topic": "Schema Capture Test Chat (Updated)",
  "message": "Chat updated successfully."
}
```

---

## 25. UpdateChannel

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "displayName": "(string, optional) New channel display name.",
  "description": "(string, optional) New channel description."
}
```

### Output Schema
```json
{
  "id": "19:6RW9gnU7hweuf3wkLAUruTzdni0MYZYIFwfbQ8WU06E1@thread.tacv2",
  "displayName": null,
  "description": "Updated description for schema capture test",
  "message": "Channel updated successfully.",
  "status": "success"
}
```

> **Note:** Works on private/shared channels. May fail on the General/standard channel with: `"Channel Properties Update failed"`. Fields not updated are returned as `null`.

---

## 26. UpdateChatMessage

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "messageId": "(string, required) Message ID to update.",
  "content": "(string, required) New message text content.",
  "contentType": "(string, optional) 'text' or 'html'."
}
```

### Output Schema
```json
{
  "id": "1778589434289",
  "chatId": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "message": "Message updated successfully.",
  "status": "success"
}
```

---

## 27. UpdateChannelMember

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "membershipId": "(string, required) Membership record ID from ListChannelMembers (the 'id' field).",
  "role": "(string, required) 'owner' or 'member'."
}
```

### Output Schema
```json
{
  "id": "MCMjMyMj...base64-encoded-membership-id...",
  "teamId": "4050da83-663a-40fc-9a3f-4267ff7097d6",
  "channelId": "19:6RW9gnU7hweuf3wkLAUruTzdni0MYZYIFwfbQ8WU06E1@thread.tacv2",
  "message": "Channel member updated successfully."
}
```

> **Note:** Only works on private/shared channels. Standard channels return: `"Operation not supported for this Channel"`.

---

## 28. AddChannelMember

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "userId": "(string, required) User GUID or UPN.",
  "role": "(string, optional, default: 'owner') 'owner' or 'member'. For private/shared channels only."
}
```

### Output Schema
```json
{
  "id": "MCMjMyMj...base64-encoded-membership-id...",
  "teamId": "4050da83-663a-40fc-9a3f-4267ff7097d6",
  "channelId": "19:6RW9gnU7hweuf3wkLAUruTzdni0MYZYIFwfbQ8WU06E1@thread.tacv2",
  "userId": "santiago@projectroma.onmicrosoft.com",
  "role": "member",
  "message": "Member added successfully to channel.",
  "status": "success"
}
```

> **Note:** Only works on private/shared channels. Standard channels return: `"Operation not supported for this Channel"`.

---

## 29. AddChatMember

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "userId": "(string, required) User GUID or UPN.",
  "isGuest": "(boolean, optional, default: false) Set true for in-tenant guests."
}
```

### Output Schema
```json
{
  "id": "unknown",
  "chatId": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "userId": "boris@projectroma.onmicrosoft.com",
  "message": "Member added successfully to chat.",
  "status": "success"
}
```

---

## 30. DeleteChat

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format."
}
```

### Output Schema
```json
{
  "chatId": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "message": "Chat deleted successfully."
}
```

---

## 31. DeleteChatMessage

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "messageId": "(string, required) Message ID to delete."
}
```

### Output Schema
> **ERROR** — API not supported:
```json
{
  "error": "Failed to delete chat message: Requested API is not supported. Please check the path."
}
```
> Expected success response:
```json
{
  "chatId": "(string)",
  "messageId": "(string)",
  "message": "Message deleted successfully."
}
```

---

## 32. SendFileToChannel

### Input Schema
```json
{
  "teamId": "(string, required) Team GUID.",
  "channelId": "(string, required) Channel ID in thread.tacv2 format.",
  "fileUrl": "(string, optional) Existing SharePoint/OneDrive file URL. Provide this OR fileContentBase64.",
  "fileContentBase64": "(string, optional) Base64-encoded file content (max 4 MB). Provide this + fileName OR fileUrl.",
  "fileName": "(string, optional) File name for upload. Required when using fileContentBase64.",
  "message": "(string, optional) Text message to accompany the file."
}
```

### Output Schema
```json
{
  "id": "1778589453520",
  "teamId": "4050da83-663a-40fc-9a3f-4267ff7097d6",
  "channelId": "19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2",
  "fileName": "schema-test.txt",
  "fileUrl": "https://projectroma.sharepoint.com/sites/ProjectRoma/Shared%20Documents/General/schema-test.txt",
  "createdDateTime": "2026-05-12T12:37:33Z",
  "message": "File sent to channel successfully."
}
```

---

## 33. SendFileToChat

### Input Schema
```json
{
  "chatId": "(string, required) Chat ID in thread.v2 format.",
  "fileUrl": "(string, optional) Existing SharePoint/OneDrive file URL. Provide this OR fileContentBase64.",
  "fileContentBase64": "(string, optional) Base64-encoded file content (max 4 MB). Provide this + fileName OR fileUrl.",
  "fileName": "(string, optional) File name for upload. Required when using fileContentBase64.",
  "message": "(string, optional) Text message to accompany the file."
}
```

### Output Schema
```json
{
  "id": "1778589471145",
  "chatId": "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2",
  "fileName": "schema-test-chat.txt",
  "fileUrl": "https://projectroma-my.sharepoint.com/personal/rishi_projectroma_onmicrosoft_com/Documents/Microsoft%20Teams%20Chat%20Files/schema-test-chat.txt",
  "createdDateTime": "2026-05-12T12:37:51Z",
  "message": "File sent successfully."
}
```

---

## 34. SendFileToUser

### Input Schema
```json
{
  "userIdOrUpn": "(string, required) Target user's UPN email or GUID.",
  "fileUrl": "(string, optional) Existing SharePoint/OneDrive file URL. Provide this OR fileContentBase64.",
  "fileContentBase64": "(string, optional) Base64-encoded file content (max 4 MB). Provide this + fileName OR fileUrl.",
  "fileName": "(string, optional) File name for upload. Required when using fileContentBase64.",
  "message": "(string, optional) Text message to accompany the file."
}
```

### Output Schema
```json
{
  "id": "1778589456091",
  "chatId": "19:306c0249-7495-4140-bd5f-f476364a9653_9336459d-7269-40d5-8506-cb314cbfab59@unq.gbl.spaces",
  "userIdOrUpn": "santiago@projectroma.onmicrosoft.com",
  "fileName": "schema-test.txt",
  "fileUrl": "https://projectroma-my.sharepoint.com/personal/rishi_projectroma_onmicrosoft_com/Documents/Microsoft%20Teams%20Chat%20Files/schema-test.txt",
  "createdDateTime": "2026-05-12T12:37:36Z",
  "message": "File sent to user successfully."
}
```

---

## Common Response Patterns

### Identifiers
| ID Type | Format | Example |
|---------|--------|---------|
| Team ID | GUID | `4050da83-663a-40fc-9a3f-4267ff7097d6` |
| Channel ID | `19:...@thread.tacv2` | `19:oE5wRX9MMSE72Ri3Y3G0ck0_isMN_pqot67ZBlC-Wys1@thread.tacv2` |
| 1:1 Chat ID | `19:{userId1}_{userId2}@unq.gbl.spaces` | `19:306c0249-..._9336459d-...@unq.gbl.spaces` |
| Group Chat ID | `19:{guid}@thread.v2` | `19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2` |
| Self Chat ID | `48:notes` | `48:notes` |
| Message ID | Numeric string (epoch-like) | `1778589372628` |
| Membership ID | Base64-encoded string | `MCMjMiMj...` |
| User ID | GUID | `9336459d-7269-40d5-8506-cb314cbfab59` |

### Shared Fields Across Responses
- **`message`** — Human-readable status string (e.g., "Message sent successfully.", "Chat created successfully.")
- **`createdDateTime`** — ISO 8601 UTC timestamp
- **`id`** — Entity identifier (message, chat, channel, team)
- **`displayName`** — Human-readable name for teams, channels, members

### Pagination Pattern
Tools that return lists support pagination via:
```json
{
  "hasMoreResults": true,
  "nextLink": "https://graph.microsoft.com/v1.0/..."
}
```
Pass the `nextLink` value back to the same tool to fetch the next page.

### Error Pattern
Errors are returned as MCP server error strings:
```
MCP server 'WorkIQ-TeamsServer': Error: Error executing tool: <specific error message>
```
Common errors:
- **"Operation not supported for this Channel"** — Trying to add/update members on a standard channel (only private/shared channels support this)
- **"Requested API is not supported"** — API endpoint not available (e.g., DeleteChatMessage)
- **"Channel Properties Update failed"** — Insufficient permissions or backend restriction on channel updates

### Message Body Shape
```json
{
  "body": {
    "contentType": "Text | Html",
    "content": "..."
  }
}
```

### From/Sender Shape
```json
// In channel messages:
"from": { "displayName": "Name", "userId": "GUID" }

// In chat messages:
"from": { "displayName": "Name", "id": "GUID" }

// In search results:
"from": { "emailAddress": { "name": "Name", "address": "user@domain.com" } }
```

### Member Shape
```json
{
  "id": "base64-membership-id",
  "displayName": "Name",
  "email": "user@domain.com",
  "userId": "GUID",
  "roles": ["owner"] // or [] for regular members
}
```

### File Attachment Response Shape
```json
{
  "id": "message-id",
  "fileName": "file.txt",
  "fileUrl": "https://sharepoint-url/...",
  "createdDateTime": "ISO-8601",
  "message": "File sent successfully."
}
```
Channel files go to SharePoint (`projectroma.sharepoint.com/sites/...`).
Chat/user files go to sender's OneDrive (`projectroma-my.sharepoint.com/personal/...`).

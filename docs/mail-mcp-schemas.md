# WorkIQ Mail MCP Server — Input & Output Schemas

All output schemas captured via live calls on 2026-05-12.
Input schemas derived from tool definitions.

---

## 1. SearchMessagesQueryParameters

### Input Schema
```json
{
  "queryParameters": "(string, required) OData query params starting with '?'. E.g. '?$filter=isRead eq false&$top=25'. Supports $search (KQL), $filter, $select, $top, $skip, $orderby. Cannot combine $search with $filter/$orderBy/$skip.",
  "nextLink": "(string, optional) Full @odata.nextLink URL from previous response for pagination. When provided, queryParameters is ignored.",
  "preferTextBody": "(boolean, optional, default: true) When true, returns plain text bodies. Set false for HTML."
}
```

### Output Schema
```json
{
  "rawResponse": "<raw Graph API JSON string — see parsed structure below>",
  "hasMoreResults": true,
  "message": "Messages searched with query parameters successfully.",
  "nextLink": "https://graph.microsoft.com/v1.0/me/messages?%24top=1&%24skip=1"
}
```

**rawResponse contents** (parsed — full field set without $select):
```json
{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('306c0249-7495-4140-bd5f-f476364a9653')/messages",
  "value": [
    {
      "@odata.etag": "W/\"CQAAABYAAAA8FKdpSVSBSZvAPYoa4qwUAAAUvHBR\"",
      "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABG...",
      "createdDateTime": "2026-05-17T12:36:07Z",
      "lastModifiedDateTime": "2026-05-17T12:41:19Z",
      "changeKey": "CQAAABYAAAA8FKdpSVSBSZvAPYoa4qwUAAAUvHBR",
      "categories": [],
      "receivedDateTime": "2026-05-17T12:36:07Z",
      "sentDateTime": "2026-05-17T12:36:01Z",
      "hasAttachments": false,
      "internetMessageId": "<7IAT5DUEATU4.ICRVQVXW0DU01@ds3pepf000184fa>",
      "subject": "Your weekly PIM digest for ProjectRoma...",
      "bodyPreview": "Here's a summary of activities over the last seven days...",
      "importance": "normal",
      "parentFolderId": "AQMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjYAOC0wZTllZmQ2YjJkNmQALgAAAzU_mBUZnXpJrjmNjMWDf5IBADwUp2lJVIFJm8A9ihrirBQAAAIBDAAAAA==",
      "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAIbdLdbxHFFBgB_2BxNjKR0=",
      "conversationIndex": "AQHc5fm7ht0t1vEcUUGAH7YHE2MpHQ==",
      "isDeliveryReceiptRequested": null,
      "isReadReceiptRequested": false,
      "isRead": false,
      "isDraft": false,
      "webLink": "https://outlook.office365.com/owa/?ItemID=...&exvsurl=1&viewmodel=ReadMessageItem",
      "inferenceClassification": "focused",
      "body": {
        "contentType": "text",
        "content": "<full message body text>"
      },
      "sender": {
        "emailAddress": {
          "name": "Microsoft Security",
          "address": "MSSecurity-noreply@microsoft.com"
        }
      },
      "from": {
        "emailAddress": {
          "name": "Microsoft Security",
          "address": "MSSecurity-noreply@microsoft.com"
        }
      },
      "toRecipients": [
        {
          "emailAddress": {
            "name": "Rishi",
            "address": "rishi@projectroma.onmicrosoft.com"
          }
        }
      ],
      "ccRecipients": [],
      "bccRecipients": [],
      "replyTo": [],
      "flag": {
        "flagStatus": "notFlagged"
      }
    }
  ],
  "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?%24top=1&%24skip=1"
}
```

---

## 2. SearchMessages (Natural Language / Copilot-powered)

### Input Schema
```json
{
  "message": "(string, required) Natural language search query. E.g. 'emails from John about the project', 'unread messages from last week'.",
  "conversationId": "(string, optional) Existing conversation GUID for follow-up queries. Auto-created if missing."
}
```

### Output Schema
```json
{
  "conversationId": "1ab1503b-9a9e-4f45-b556-146cbfd0fa96",
  "timeZone": "America/Los_Angeles",
  "reply": "<markdown formatted natural language reply>",
  "messageIds": ["AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4...", "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4..."],
  "rawResponse": "<full Graph Copilot conversation JSON — see parsed structure below>",
  "message": "Messages searched successfully."
}
```

**rawResponse contents** (parsed):
```json
{
  "@odata.context": "https://graph.microsoft.com/beta/$metadata#microsoft.graph.copilotConversation",
  "id": "1ab1503b-9a9e-4f45-b556-146cbfd0fa96",
  "createdDateTime": "2026-05-12T12:20:06.6241424Z",
  "displayName": "Search my emails for: most recent email about Roma",
  "state": "active",
  "turnCount": 1,
  "messages": [
    {
      "@odata.type": "#microsoft.graph.copilotConversationResponseMessage",
      "id": "4d69f3ea-4c2f-4525-af7d-8fc857a60441",
      "text": "Search my emails for: most recent email about Roma test. Focus on email messages, subjects, senders, recipients, and email content.",
      "createdDateTime": "2026-05-12T12:20:06.7702923Z",
      "adaptiveCards": [],
      "attributions": [],
      "sensitivityLabel": {
        "sensitivityLabelId": null,
        "displayName": null,
        "tooltip": null,
        "priority": null,
        "color": null
      }
    },
    {
      "@odata.type": "#microsoft.graph.copilotConversationResponseMessage",
      "id": "923bc9d4-a032-41ae-8790-8c6fb8e39b64",
      "text": "<markdown response text>",
      "createdDateTime": "2026-05-12T12:20:16.8278399Z",
      "adaptiveCards": [],
      "attributions": [
        {
          "attributionType": "citation",
          "providerDisplayName": "Roma test",
          "attributionSource": "model",
          "seeMoreWebUrl": "https://outlook.office365.com/owa/?ItemID=...",
          "imageWebUrl": "",
          "imageFavIcon": "",
          "imageWidth": 0,
          "imageHeight": 0
        }
      ],
      "sensitivityLabel": {
        "sensitivityLabelId": null,
        "displayName": null,
        "tooltip": null,
        "priority": null,
        "color": null
      }
    }
  ]
}
```

---

## 3. GetMessage

### Input Schema
```json
{
  "id": "(string, required) Message ID.",
  "bodyPreviewOnly": "(boolean, optional) If true, returns only ~255 char body preview instead of full body.",
  "preferHtml": "(boolean, optional) If true, request HTML body format."
}
```

### Output Schema
```json
{
  "message": "Message retrieved successfully.",
  "data": {
    "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABG...",
    "internetMessageId": "<LO4P265MB6234465A4BA4B52EB5DDEFEAE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "subject": "Roma test",
    "from": "rishi@projectroma.onmicrosoft.com",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bodyPreview": "1. Roma test (Unread)\r\n\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "body": "<html><head>...</head><body>...</body></html>",
    "receivedDateTime": "2026-05-12T12:06:57+00:00",
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfOw==",
    "sensitivityLabel": null
  }
}
```

**Note:** GetMessage returns a different (smaller) field set than other tools. It uses `id` (not `messageId`), and does NOT return: `webLink`, `bccRecipients`, `draft`, `sent`, `bodyLength`, `bodyTruncated`, `createdDateTime`, `sentDateTime`.

---

## 4. GetAttachments

### Input Schema
```json
{
  "messageId": "(string, required) Message ID to get attachments from."
}
```

### Output Schema (empty)
```json
{
  "message": "Attachments retrieved successfully.",
  "data": []
}
```

### Output Schema (with attachments)
```json
{
  "message": "Attachments retrieved successfully.",
  "data": [
    {
      "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABG...BEgAQAPJ_fSY1GKBOuTaUL7gVOL8=",
      "name": "test-schema.txt",
      "contentType": "text/plain",
      "size": 238,
      "isInline": false,
      "type": "#microsoft.graph.fileAttachment"
    }
  ]
}
```

---

## 5. DownloadAttachment

### Input Schema
```json
{
  "messageId": "(string, required) Message ID.",
  "attachmentId": "(string, required) Attachment ID."
}
```

### Output Schema
```json
{
  "message": "Attachment downloaded successfully.",
  "data": {
    "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABG...BEgAQAPJ_fSY1GKBOuTaUL7gVOL8=",
    "name": "test-schema.txt",
    "contentType": "text/plain",
    "size": 238,
    "contentBytes": "VGhpcyBpcyBhIHRlc3QgYXR0YWNobWVudCBmb3Igc2NoZW1hIGNhcHR1cmU="
  }
}
```

---

## 6. CreateDraftMessage

### Input Schema
```json
{
  "subject": "(string, optional) Subject of the email.",
  "body": "(string, optional) Body of the email.",
  "contentType": "(string, optional) 'Text' or 'HTML'. Default is 'HTML'.",
  "to": "(string[], optional) List of To recipients (names or emails).",
  "cc": "(string[], optional) List of Cc recipients.",
  "bcc": "(string[], optional) List of Bcc recipients."
}
```

### Output Schema
```json
{
  "message": "Draft message created successfully.",
  "data": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvmutgAA",
    "internetMessageId": "<LO4P265MB623446D2FE7AF6CC540A0D2BE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvmutgAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "Schema Test Draft - Safe to Delete",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAHoM0axTiBVEpYSx_EgxtWE=",
    "conversationIndex": "AQHc4gmaegzRrFOIFUSlhLH4SDG1YQ==",
    "body": "This is a test draft for capturing response schemas.",
    "bodyLength": 52,
    "bodyTruncated": false,
    "bodyPreview": "This is a test draft for capturing response schemas.",
    "createdDateTime": "2026-05-12T12:19:39+00:00",
    "sentDateTime": "2026-05-12T12:19:39+00:00",
    "receivedDateTime": "2026-05-12T12:19:39+00:00"
  }
}
```

---

## 7. UpdateDraft

### Input Schema
```json
{
  "messageId": "(string, required) Draft message ID to update.",
  "subject": "(string, optional) Updated subject.",
  "body": "(string, optional) Updated body. IMPORTANT: For reply drafts, preserve the quoted thread HTML or it will be lost.",
  "to": "(string[], optional) List of To recipients.",
  "cc": "(string[], optional) List of Cc recipients.",
  "bcc": "(string[], optional) List of Bcc recipients.",
  "sensitivity": "(string, optional) 'Normal', 'Personal', 'Private', or 'Confidential'.",
  "attachmentUris": "(string[], optional) List of file URIs to attach (OneDrive/SharePoint/Teams).",
  "directAttachments": "(object[], optional) [{\"fileName\": \"...\", \"contentBase64\": \"...\", \"contentType\": \"...\"}]"
}
```

### Output Schema
```json
{
  "message": "Draft updated successfully.",
  "data": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvmutgAA",
    "internetMessageId": "<LO4P265MB623446D2FE7AF6CC540A0D2BE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvmutgAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "Schema Test Draft UPDATED - Safe to Delete",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAHoM0axTiBVEpYSx_EgxtWE=",
    "conversationIndex": "AQHc4gmaegzRrFOIFUSlhLH4SDG1YQ==",
    "body": "This is a test draft for capturing response schemas.",
    "bodyLength": 52,
    "bodyTruncated": false,
    "bodyPreview": "This is a test draft for capturing response schemas.",
    "createdDateTime": "2026-05-12T12:19:39+00:00",
    "sentDateTime": "2026-05-12T12:19:39+00:00",
    "receivedDateTime": "2026-05-12T12:19:39+00:00"
  }
}
```

---

## 8. SendDraftMessage

### Input Schema
```json
{
  "id": "(string, required) Draft message ID to send."
}
```

### Output Schema
```json
{
  "message": "Draft message sent successfully.",
  "data": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvmutgAA",
    "internetMessageId": "<LO4P265MB623446D2FE7AF6CC540A0D2BE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvmutgAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "Schema Test Draft UPDATED - Safe to Delete",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": true,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAHoM0axTiBVEpYSx_EgxtWE=",
    "conversationIndex": "AQHc4gmaegzRrFOIFUSlhLH4SDG1YQ==",
    "body": null,
    "bodyLength": 52,
    "bodyTruncated": false,
    "bodyPreview": "This is a test draft for capturing response schemas.",
    "createdDateTime": "2026-05-12T12:19:39+00:00",
    "sentDateTime": "2026-05-12T12:21:51+00:00",
    "receivedDateTime": "2026-05-12T12:19:39+00:00"
  }
}
```

---

## 9. SendEmailWithAttachments

### Input Schema
```json
{
  "subject": "(string, optional) Subject of the email.",
  "body": "(string, optional) Body of the email.",
  "contentType": "(string, optional) 'Text' or 'HTML'.",
  "to": "(string[], optional) List of To recipients (names or emails).",
  "cc": "(string[], optional) List of Cc recipients.",
  "bcc": "(string[], optional) List of Bcc recipients.",
  "attachmentUris": "(string[], optional) List of file URIs to attach (OneDrive/SharePoint/Teams).",
  "directAttachments": "(object[], optional) [{\"fileName\": \"...\", \"contentBase64\": \"...\", \"contentType\": \"...\"}]"
}
```

### Output Schema
```json
{
  "message": "Email sent successfully.",
  "data": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKRAAA",
    "internetMessageId": "<LO4P265MB6234D1F4E8E86CA505D35B1EE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKRAAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "Schema Test - SendEmailWithAttachments",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": true,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAD55tQCJzYNFmIoQov6h8iQ=",
    "conversationIndex": "AQHc4gnpPnm1AInNg0WYihCi/qHyJA==",
    "body": null,
    "bodyLength": 31,
    "bodyTruncated": false,
    "bodyPreview": "Test email for capturing schema",
    "createdDateTime": "2026-05-12T12:21:52+00:00",
    "sentDateTime": "2026-05-12T12:21:52+00:00",
    "receivedDateTime": "2026-05-12T12:21:52+00:00"
  }
}
```

---

## 10. AddDraftAttachments

### Input Schema
```json
{
  "messageId": "(string, required) Graph message ID (draft) to update.",
  "attachmentUris": "(string[], required) List of direct file URIs to attach (must be Microsoft 365 file links: OneDrive, SharePoint, Teams, or Graph /drives/{id}/items/{id})."
}
```

### Output Schema
*Not tested — requires a SharePoint/OneDrive file URI.*

---

## 11. UploadAttachment (< 3MB)

### Input Schema
```json
{
  "messageId": "(string, required) Message ID to attach to.",
  "fileName": "(string, required) File name. E.g. 'report.pdf'.",
  "contentBase64": "(string, required) Base64-encoded file content.",
  "contentType": "(string, optional) MIME type. E.g. 'text/plain', 'application/pdf'."
}
```

### Output Schema
```json
{
  "message": "Attachment uploaded successfully.",
  "attachmentId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC_X85AAABEgAQAPJ_fSY1GKBOuTaUL7gVOL8=",
  "name": "test-schema.txt",
  "size": 238
}
```

---

## 12. UploadLargeAttachment (3–150MB)

### Input Schema
```json
{
  "messageId": "(string, required) Message ID to attach to.",
  "fileName": "(string, required) File name.",
  "contentBase64": "(string, required) Base64-encoded file content.",
  "contentType": "(string, optional) MIME type."
}
```

### Output Schema
*Not tested — same schema shape as UploadAttachment. Uses chunked upload internally for 3–150MB files.*

---

## 13. DeleteAttachment

### Input Schema
```json
{
  "messageId": "(string, required) Message ID.",
  "attachmentId": "(string, required) Attachment ID."
}
```

### Output Schema
```json
{
  "message": "Attachment deleted successfully.",
  "attachmentId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC_X85AAABEgAQAPJ_fSY1GKBOuTaUL7gVOL8=",
  "messageId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC_X85AAA="
}
```

---

## 14. ReplyToMessage

### Input Schema
```json
{
  "id": "(string, required) Message ID to reply to.",
  "comment": "(string, optional) Reply text content.",
  "sendImmediately": "(boolean, optional, default: false) If true, sends immediately. If false, creates a reply draft.",
  "toRecipients": "(string[], optional) Override To recipients (names or emails).",
  "ccRecipients": "(string[], optional) Override Cc recipients.",
  "bccRecipients": "(string[], optional) Override Bcc recipients.",
  "preferHtml": "(boolean, optional) If true, treat comment as HTML."
}
```

### Output Schema
```json
{
  "message": "Reply draft created successfully.",
  "data": {
    "messageId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC_X85AAA=",
    "internetMessageId": "<LO4P265MB6234E9CDF616D5A1161C9F56E3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3%2BSBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC%2BX85AAA%3D&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "RE: Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfO7YKT52R",
    "body": "<html><head>...</head><body><div data-mcp-intro=\"true\" style=\"font-family:Segoe UI,Arial,sans-serif; font-size:14px; line-height:20px; margin:0 0 12px 0\">Schema test reply</div><hr tabindex=\"-1\" style=\"display:inline-block; width:98%\"><div id=\"divRplyFwdMsg\" dir=\"ltr\">...quoted original...</div></body></html>",
    "bodyLength": 4290,
    "bodyTruncated": false,
    "bodyPreview": "Schema test reply\r\n________________________________\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>\r\nSent: Tuesday, 12 May 2026 12:06:55\r\nTo: Rishi <rishi@projectroma.onmicrosoft.com>\r\nSubject: Roma test...",
    "createdDateTime": "2026-05-12T12:21:19+00:00",
    "sentDateTime": "2026-05-12T12:21:19+00:00",
    "receivedDateTime": "2026-05-12T12:21:19+00:00"
  },
  "replyStatus": "draft"
}
```

---

## 15. ReplyAllToMessage

### Input Schema
```json
{
  "id": "(string, required) Message ID to reply-all to.",
  "comment": "(string, optional) Reply text content.",
  "sendImmediately": "(boolean, optional, default: false) If true, sends immediately. If false, creates a reply-all draft.",
  "toRecipients": "(string[], optional) Override To recipients.",
  "ccRecipients": "(string[], optional) Override Cc recipients.",
  "bccRecipients": "(string[], optional) Override Bcc recipients.",
  "preferHtml": "(boolean, optional) If true, treat comment as HTML."
}
```

### Output Schema
```json
{
  "message": "Reply-all draft created successfully.",
  "data": {
    "messageId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC_X86AAA=",
    "internetMessageId": "<LO4P265MB62341AEF83BF5526EA1E8FDDE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3%2BSBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC%2BX86AAA%3D&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "RE: Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfO7YKT6QG",
    "body": "<html><head>...</head><body><div data-mcp-intro=\"true\" ...>Schema test reply-all</div><hr ...><div id=\"divRplyFwdMsg\" dir=\"ltr\">...quoted original...</div></body></html>",
    "bodyLength": 4294,
    "bodyTruncated": false,
    "bodyPreview": "Schema test reply-all\r\n________________________________\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:21:24+00:00",
    "sentDateTime": "2026-05-12T12:21:25+00:00",
    "receivedDateTime": "2026-05-12T12:21:25+00:00"
  },
  "replyStatus": "draftAll"
}
```

---

## 16. ReplyWithFullThread

### Input Schema
```json
{
  "messageId": "(string, required) Original message ID to reply to.",
  "introComment": "(string, optional) Introductory comment placed above quoted thread.",
  "sendImmediately": "(boolean, optional, default: false) If true, sends immediately.",
  "replyAll": "(boolean, optional) If true, reply-all; otherwise direct reply.",
  "additionalTo": "(string[], optional) Additional To recipients.",
  "additionalCc": "(string[], optional) Additional Cc recipients.",
  "additionalBcc": "(string[], optional) Additional Bcc recipients.",
  "includeOriginalNonInlineAttachments": "(boolean, optional) If true, re-attach original files.",
  "preferHtml": "(boolean, deprecated) introComment is always rendered as HTML."
}
```

### Output Schema
```json
{
  "message": "Reply with full thread draft created successfully.",
  "data": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKMAAA",
    "internetMessageId": "<LO4P265MB6234EFF9FEF20912ED18F9C0E3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKMAAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "RE: Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfO7YKT6fK",
    "body": "<html><head>...</head><body><div data-mcp-intro=\"true\" ...>Schema test reply with full thread</div><hr ...><div id=\"divRplyFwdMsg\" dir=\"ltr\">...full quoted thread...</div></body></html>",
    "bodyLength": 4307,
    "bodyTruncated": false,
    "bodyPreview": "Schema test reply with full thread\r\n________________________________\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:21:27+00:00",
    "sentDateTime": "2026-05-12T12:21:27+00:00",
    "receivedDateTime": "2026-05-12T12:21:27+00:00"
  },
  "replyAll": false,
  "replyStatus": "draft",
  "addedRecipients": false,
  "includedOriginalAttachments": false
}
```

---

## 17. ReplyAllWithFullThread

### Input Schema
```json
{
  "messageId": "(string, required) Original message ID to reply-all to.",
  "introComment": "(string, optional) Introductory comment placed above quoted thread.",
  "sendImmediately": "(boolean, optional, default: false) If true, sends immediately.",
  "additionalTo": "(string[], optional) Additional To recipients.",
  "additionalCc": "(string[], optional) Additional Cc recipients.",
  "additionalBcc": "(string[], optional) Additional Bcc recipients.",
  "includeOriginalNonInlineAttachments": "(boolean, optional) If true, re-attach original files.",
  "preferHtml": "(boolean, deprecated) introComment is always rendered as HTML."
}
```

### Output Schema
```json
{
  "message": "Reply-all with full thread draft created successfully.",
  "data": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKNAAA",
    "internetMessageId": "<LO4P265MB62346796B890C7FE59C07148E3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKNAAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "RE: Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfO7YKT6k5",
    "body": "<html><head>...</head><body><div data-mcp-intro=\"true\" ...>Schema test reply-all with full thread</div><hr ...><div id=\"divRplyFwdMsg\" dir=\"ltr\">...full quoted thread...</div></body></html>",
    "bodyLength": 4311,
    "bodyTruncated": false,
    "bodyPreview": "Schema test reply-all with full thread\r\n________________________________\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:21:29+00:00",
    "sentDateTime": "2026-05-12T12:21:29+00:00",
    "receivedDateTime": "2026-05-12T12:21:29+00:00"
  },
  "replyAll": true,
  "replyStatus": "draft",
  "addedRecipients": false,
  "includedOriginalAttachments": false
}
```

---

## 18. ForwardMessage

### Input Schema
```json
{
  "messageId": "(string, required) Original message ID to forward.",
  "introComment": "(string, optional) Introductory comment placed above quoted thread.",
  "additionalTo": "(string[], optional) To recipients (names or emails) — required to actually forward.",
  "additionalCc": "(string[], optional) Cc recipients.",
  "additionalBcc": "(string[], optional) Bcc recipients.",
  "attachmentUris": "(string[], optional) List of file URIs to attach.",
  "directAttachments": "(object[], optional) [{\"fileName\": \"...\", \"contentBase64\": \"...\", \"contentType\": \"...\"}]",
  "preferHtml": "(boolean, optional) If true, introComment is treated as HTML."
}
```

### Output Schema
```json
{
  "message": "Message forwarded successfully.",
  "forwardMessage": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKKQAA",
    "internetMessageId": "<LO4P265MB6234009414E8A3DDC9A4DC88E3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKKQAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "FW: Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": true,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfO7YKT6VA",
    "body": null,
    "bodyLength": 4292,
    "bodyTruncated": false,
    "bodyPreview": "Schema test forward\r\n________________________________\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:21:25+00:00",
    "sentDateTime": "2026-05-12T12:21:26+00:00",
    "receivedDateTime": "2026-05-12T12:21:26+00:00"
  },
  "fastPath": false
}
```

---

## 19. ForwardMessageWithFullThread

### Input Schema
```json
{
  "messageId": "(string, required) Original message ID to forward.",
  "introComment": "(string, optional) Introductory comment placed above quoted thread.",
  "additionalTo": "(string[], required) To recipients (names or emails).",
  "additionalCc": "(string[], optional) Cc recipients.",
  "additionalBcc": "(string[], optional) Bcc recipients.",
  "includeOriginalNonInlineAttachments": "(boolean, optional) If true, re-attach original non-inline attachments.",
  "preferHtml": "(boolean, optional) If true, introComment is treated as HTML."
}
```

### Output Schema
```json
{
  "message": "Message with full thread forwarded successfully.",
  "forwardMessage": {
    "messageId": "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKNwAA",
    "internetMessageId": "<LO4P265MB62344CA3F4649E3C76D503CEE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAkALgAAAAAAHYQDEapmEc2byACqAC%2FEWg0APBSnaUlUgUmbwD2KGuKsFAAAAvnKNwAA&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "FW: Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": true,
    "sent": true,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfO7YKT6vh",
    "body": null,
    "bodyLength": 4309,
    "bodyTruncated": false,
    "bodyPreview": "Schema test forward with full thread\r\n________________________________\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:21:30+00:00",
    "sentDateTime": "2026-05-12T12:21:31+00:00",
    "receivedDateTime": "2026-05-12T12:21:31+00:00"
  },
  "sensitivityLabel": null,
  "includedOriginalAttachments": false
}
```

---

## 20. FlagEmail

### Input Schema
```json
{
  "messageId": "(string, required) ID of the email to flag.",
  "flagStatus": "(string, required) 'NotFlagged', 'Complete', or 'Flagged'.",
  "mailboxAddress": "(string, optional) Address of shared mailbox to update."
}
```

### Output Schema
```json
{
  "message": "Email flag updated successfully.",
  "data": {
    "messageId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEMAAA8FKdpSVSBSZvAPYoa4qwUAAAC_QSoAAA=",
    "internetMessageId": "<LO4P265MB6234465A4BA4B52EB5DDEFEAE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3%2BSBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEMAAA8FKdpSVSBSZvAPYoa4qwUAAAC%2BQSoAAA%3D&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": false,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfOw==",
    "body": "<html><head>...</head><body>...full HTML body content...</body></html>",
    "bodyLength": 3738,
    "bodyTruncated": false,
    "bodyPreview": "1. Roma test (Unread)\r\n\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:06:57+00:00",
    "sentDateTime": "2026-05-12T12:06:55+00:00",
    "receivedDateTime": "2026-05-12T12:06:57+00:00"
  }
}
```

---

## 21. UpdateMessage

### Input Schema
```json
{
  "id": "(string, required) Message ID.",
  "subject": "(string, optional) New subject.",
  "body": "(string, optional) New body. IMPORTANT: Preserve quoted thread HTML for reply messages.",
  "contentType": "(string, optional) 'Text' or 'HTML'.",
  "importance": "(string, optional) 'Low', 'Normal', or 'High'.",
  "sensitivity": "(string, optional) 'Normal', 'Personal', 'Private', or 'Confidential'.",
  "categories": "(string[], optional) Message categories."
}
```

### Output Schema
```json
{
  "message": "Message updated successfully.",
  "data": {
    "messageId": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEMAAA8FKdpSVSBSZvAPYoa4qwUAAAC_QSoAAA=",
    "internetMessageId": "<LO4P265MB6234465A4BA4B52EB5DDEFEAE3392@LO4P265MB6234.GBRP265.PROD.OUTLOOK.COM>",
    "webLink": "https://outlook.office365.com/owa/?ItemID=AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3%2BSBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEMAAA8FKdpSVSBSZvAPYoa4qwUAAAC%2BQSoAAA%3D&exvsurl=1&viewmodel=ReadMessageItem",
    "subject": "Roma test",
    "toRecipients": ["rishi@projectroma.onmicrosoft.com"],
    "ccRecipients": [],
    "bccRecipients": [],
    "hasAttachments": false,
    "importance": "Normal",
    "isRead": true,
    "draft": false,
    "sent": false,
    "conversationId": "AAQkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAQAEce9N5P_DpAs0RKkq2xnzs=",
    "conversationIndex": "AQHc4gexRx703k/4OkCzREqSrbGfOw==",
    "body": "<html><head>...</head><body>...full HTML body content...</body></html>",
    "bodyLength": 3738,
    "bodyTruncated": false,
    "bodyPreview": "1. Roma test (Unread)\r\n\r\nFrom: Rishi <rishi@projectroma.onmicrosoft.com>...",
    "createdDateTime": "2026-05-12T12:06:57+00:00",
    "sentDateTime": "2026-05-12T12:06:55+00:00",
    "receivedDateTime": "2026-05-12T12:06:57+00:00"
  }
}
```

---

## 22. DeleteMessage

### Input Schema
```json
{
  "id": "(string, required) Message ID to delete."
}
```

### Output Schema
```json
{
  "message": "Message deleted successfully.",
  "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZABGAAAAAAA1PpgVGZ16Sa45jYzFg3_SBwA8FKdpSVSBSZvAPYoa4qwUAAAAAAEPAAA8FKdpSVSBSZvAPYoa4qwUAAAC_X85AAA="
}
```

---

## Field Comparison Notes

**GetMessage** returns a DIFFERENT field set than other tools:
- Uses `id` instead of `messageId`
- Has `sensitivityLabel`
- Does NOT return: `webLink`, `bccRecipients`, `draft`, `sent`, `bodyLength`, `bodyTruncated`, `createdDateTime`, `sentDateTime`

**All other message-returning tools** (CreateDraft, UpdateDraft, SendDraft, SendEmail, Reply*, Forward*, Flag, Update) share this common message object:
- `messageId`, `internetMessageId`, `webLink`
- `subject`, `toRecipients`, `ccRecipients`, `bccRecipients`
- `hasAttachments`, `importance`, `isRead`, `draft`, `sent`
- `conversationId`, `conversationIndex`
- `body`, `bodyLength`, `bodyTruncated`, `bodyPreview`
- `createdDateTime`, `sentDateTime`, `receivedDateTime`

**Additional top-level keys per tool category:**
| Tool | Extra keys |
|------|-----------|
| ReplyToMessage | `replyStatus` |
| ReplyAllToMessage | `replyStatus` |
| ReplyWithFullThread | `replyAll`, `replyStatus`, `addedRecipients`, `includedOriginalAttachments` |
| ReplyAllWithFullThread | `replyAll`, `replyStatus`, `addedRecipients`, `includedOriginalAttachments` |
| ForwardMessage | `fastPath` |
| ForwardMessageWithFullThread | `sensitivityLabel`, `includedOriginalAttachments` |

**Correlation footer**: Every raw response ends with `CorrelationId: <guid>, TimeStamp: <ISO>` (not part of JSON, appended as metadata).

# WorkIQ Calendar MCP Server — Input & Output Schemas

> Captured via live calls on 2026-05-12. All test events were cleaned up after capture.

---

## 1. GetUserDateAndTimeZoneSettings

### Input Schema
```json
{
  "userIdentifier": "(string, optional, default: 'me') User identifier: email, Entra ID (GUID), display name, or 'me'."
}
```

### Output Schema
```json
{
  "additionalData": {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('<user-guid>')/mailboxSettings"
  },
  "archiveFolder": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVmZDZiMmQ2ZAAu...",
  "automaticRepliesSetting": {
    "externalAudience": "all",
    "externalReplyMessage": "",
    "internalReplyMessage": "",
    "scheduledEndDateTime": {
      "dateTime": "2026-05-13T12:00:00.0000000",
      "timeZone": "UTC"
    },
    "scheduledStartDateTime": {
      "dateTime": "2026-05-12T12:00:00.0000000",
      "timeZone": "UTC"
    },
    "status": "disabled"
  },
  "dateFormat": "",
  "delegateMeetingMessageDeliveryOptions": "sendToDelegateOnly",
  "language": {
    "displayName": "English (United States)",
    "locale": "en-US"
  },
  "timeFormat": "",
  "timeZone": "GMT Standard Time",
  "userPurpose": "user",
  "workingHours": {
    "daysOfWeek": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "endTime": {
      "dateTime": "2026-05-12T17:00:00",
      "hour": 17,
      "minute": 0,
      "second": 0
    },
    "startTime": {
      "dateTime": "2026-05-12T08:00:00",
      "hour": 8,
      "minute": 0,
      "second": 0
    },
    "timeZone": {
      "name": "GMT Standard Time"
    }
  }
}
```

---

## 2. ListCalendarView

### Input Schema
```json
{
  "userIdentifier": "(string, optional, default: 'me') User identifier.",
  "startDateTime": "(string, optional, default: current time) ISO 8601 format, UTC or with offset.",
  "endDateTime": "(string, optional, default: current time + 15 days) ISO 8601 format.",
  "subject": "(string, optional) Filter events by subject/title.",
  "timeZone": "(string, optional, default: user's timezone) e.g., 'Pacific Standard Time'.",
  "top": "(integer, optional, default: 150) Max events to return.",
  "orderby": "(string, optional, default: 'start/dateTime') Sort property.",
  "select": "(string, optional) Comma-separated properties to return."
}
```

### Output Schema
```json
{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('<user-guid>')/calendarView(id,subject,bodyPreview,start,end,isAllDay,isCancelled,isOnlineMeeting,location,locations,organizer,attendees,importance,sensitivity,showAs,categories,responseStatus,recurrence,type)",
  "value": [
    {
      "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVm...",
      "@odata.type": "#microsoft.graph.event",
      "@odata.etag": "W/\"PBSnaUlUgUmbwD2KGuKsFAAAAvYWaA==\"",
      "categories": [],
      "attendees": [
        {
          "emailAddress": {
            "address": "santiago@projectroma.onmicrosoft.com",
            "name": "Santiago"
          },
          "@odata.type": "#microsoft.graph.attendee",
          "type": "required",
          "status": {
            "response": "none",
            "time": "0001-01-01T00:00:00+00:00"
          }
        }
      ],
      "bodyPreview": "________________________________________________________________________________\r\nMicrosoft Teams meeting\r\nJoin: https://teams.microsoft.com/meet/...",
      "end": {
        "dateTime": "2026-05-13T10:30:00.0000000",
        "timeZone": "GMT Standard Time"
      },
      "importance": "normal",
      "isAllDay": false,
      "isCancelled": false,
      "isOnlineMeeting": true,
      "location": {
        "displayName": "Microsoft Teams Meeting",
        "locationType": "default",
        "uniqueId": "Microsoft Teams Meeting",
        "uniqueIdType": "private"
      },
      "locations": [
        {
          "displayName": "Microsoft Teams Meeting",
          "locationType": "default",
          "uniqueId": "Microsoft Teams Meeting",
          "uniqueIdType": "private"
        }
      ],
      "organizer": {
        "emailAddress": {
          "address": "rishi@projectroma.onmicrosoft.com",
          "name": "Rishi"
        }
      },
      "responseStatus": {
        "response": "organizer",
        "time": "0001-01-01T00:00:00+00:00"
      },
      "sensitivity": "normal",
      "showAs": "busy",
      "start": {
        "dateTime": "2026-05-13T10:00:00.0000000",
        "timeZone": "GMT Standard Time"
      },
      "subject": "Schema Capture Test Meeting (Updated)",
      "type": "singleInstance"
    }
    // ... more entries
  ]
}
```

**Note:** When no events exist, the response is the string: `"No calendar events found for the given criteria."`

---

## 3. ListEvents

### Input Schema
```json
{
  "meetingTitle": "(string, optional) Filter by meeting title.",
  "attendeeEmails": "(object, optional) Filter by attendee emails.",
  "startDateTime": "(string, optional, default: current time) ISO 8601 UTC or with offset.",
  "endDateTime": "(string, optional, default: current time + 90 days) ISO 8601 UTC or with offset.",
  "timeZone": "(string, optional, default: user's timezone) e.g., 'Pacific Standard Time'.",
  "top": "(integer, optional, default: 150) Max events to return.",
  "orderby": "(string, optional) Sort property.",
  "select": "(string, optional) Comma-separated properties to return."
}
```

### Output Schema
```json
{
  "value": [
    {
      "allowNewTimeProposals": true,
      "attendees": [
        {
          "status": {
            "response": "none",
            "time": "0001-01-01T00:00:00+00:00"
          },
          "type": "required",
          "emailAddress": {
            "address": "santiago@projectroma.onmicrosoft.com",
            "name": "Santiago"
          },
          "odataType": "#microsoft.graph.attendee"
        }
      ],
      "body": {
        "content": "<html>...Microsoft Teams meeting HTML content...</html>",
        "contentType": "html"
      },
      "bodyPreview": "________________________________________________________________________________\r\nMicrosoft Teams meeting\r\nJoin: https://teams.microsoft.com/meet/...",
      "end": {
        "dateTime": "2026-05-13T10:30:00.0000000",
        "timeZone": "GMT Standard Time"
      },
      "hasAttachments": false,
      "hideAttendees": false,
      "iCalUId": "040000008200E00074C5B7101A82E008...",
      "importance": "normal",
      "isAllDay": false,
      "isCancelled": false,
      "isDraft": false,
      "isOnlineMeeting": true,
      "isOrganizer": true,
      "isReminderOn": true,
      "location": {
        "displayName": "Microsoft Teams Meeting",
        "locationType": "default",
        "uniqueId": "Microsoft Teams Meeting",
        "uniqueIdType": "private"
      },
      "locations": [
        {
          "displayName": "Microsoft Teams Meeting",
          "locationType": "default",
          "uniqueId": "Microsoft Teams Meeting",
          "uniqueIdType": "private"
        }
      ],
      "onlineMeeting": {
        "conferenceId": "677387679",
        "joinUrl": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_...",
        "tollNumber": "+44 20 3321 5270"
      },
      "onlineMeetingProvider": "teamsForBusiness",
      "organizer": {
        "emailAddress": {
          "address": "rishi@projectroma.onmicrosoft.com",
          "name": "Rishi"
        }
      },
      "originalEndTimeZone": "GMT Standard Time",
      "originalStartTimeZone": "GMT Standard Time",
      "reminderMinutesBeforeStart": 15,
      "responseRequested": true,
      "responseStatus": {
        "response": "organizer",
        "time": "0001-01-01T00:00:00+00:00"
      },
      "sensitivity": "normal",
      "showAs": "busy",
      "start": {
        "dateTime": "2026-05-13T10:00:00.0000000",
        "timeZone": "GMT Standard Time"
      },
      "subject": "Schema Capture Test Meeting (Updated)",
      "type": "singleInstance",
      "webLink": "https://outlook.office365.com/owa/?itemid=AAMkADAxMDk4ZjdkLW...",
      "categories": [],
      "changeKey": "PBSnaUlUgUmbwD2KGuKsFAAAAvYWaA==",
      "createdDateTime": "2026-05-12T12:59:07.1287102+00:00",
      "lastModifiedDateTime": "2026-05-12T13:01:12.7199833+00:00",
      "additionalData": {
        "@odata.etag": "W/\"PBSnaUlUgUmbwD2KGuKsFAAAAvYWaA==\"",
        "uid": "040000008200E00074C5B7101A82E008...",
        "occurrenceId": null,
        "calendar@odata.associationLink": "https://graph.microsoft.com/v1.0/users('<user-guid>')/calendars('<calendar-id>')/$ref",
        "calendar@odata.navigationLink": "https://graph.microsoft.com/v1.0/users('<user-guid>')/calendars('<calendar-id>')"
      },
      "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVm...",
      "odataType": "#microsoft.graph.event"
    }
    // ... more entries
  ]
}
```

**Note:** When no events exist, the response is the string: `"No events found for the given criteria."`

---

## 4. FindMeetingTimes

### Input Schema
```json
{
  "attendeeEmails": "(string[], optional) List of attendee emails or names.",
  "meetingDuration": "(string, required) ISO 8601 duration, e.g., 'PT1H', 'PT30M'.",
  "startDateTime": "(string, optional, default: current time) ISO 8601 format.",
  "endDateTime": "(string, optional, default: start + 7 days) ISO 8601 format.",
  "timeZone": "(string, optional, default: user's timezone) e.g., 'Pacific Standard Time'.",
  "maxCandidates": "(integer, optional, default: 10) Max suggestions to return.",
  "isOrganizerOptional": "(boolean, optional, default: false) Whether organizer attendance is optional.",
  "minimumAttendeePercentage": "(number, optional, default: 100) Min percentage of attendees required (0-100).",
  "returnSuggestionReasons": "(boolean, optional, default: true) Whether to return reasons for suggestions.",
  "userIdentifier": "(string, optional, default: 'me') Organizer identifier."
}
```

### Output Schema
```json
{
  "additionalData": {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#microsoft.graph.meetingTimeSuggestionsResult"
  },
  "emptySuggestionsReason": "",
  "meetingTimeSuggestions": [
    {
      "attendeeAvailability": [
        {
          "attendee": {
            "type": "required",
            "emailAddress": {
              "address": "santiago@projectroma.onmicrosoft.com"
            },
            "odataType": "#microsoft.graph.attendeeBase"
          },
          "availability": "free"
        }
      ],
      "confidence": 100,
      "locations": [],
      "meetingTimeSlot": {
        "end": {
          "dateTime": "2026-05-12T15:30:00.0000000",
          "timeZone": "UTC"
        },
        "start": {
          "dateTime": "2026-05-12T15:00:00.0000000",
          "timeZone": "UTC"
        }
      },
      "organizerAvailability": "free",
      "suggestionReason": "Suggested because it is one of the nearest times when All attendees are available."
    }
    // ... more suggestions (up to maxCandidates)
  ]
}
```

---

## 5. GetRooms

### Input Schema
```json
{}
```
No parameters.

### Output Schema
```json
{
  "value": []
}
```

**Note:** Returns an array of room objects. Empty array when no rooms are configured in the tenant. Expected room object shape (from Microsoft Graph documentation):
```json
{
  "value": [
    {
      "address": { "city": "", "countryOrRegion": "", "postalCode": "", "state": "", "street": "" },
      "displayName": "Room Name",
      "emailAddress": "room@contoso.com",
      "geoCoordinates": null,
      "phone": ""
    }
  ]
}
```

---

## 6. CreateEvent

### Input Schema
```json
{
  "subject": "(string, required) Event title.",
  "attendeeEmails": "(string[], required) List of attendee emails. Use empty array [] for no attendees.",
  "startDateTime": "(string, required) ISO 8601 format, e.g., '2026-05-13T10:00:00'.",
  "endDateTime": "(string, required) ISO 8601 format, e.g., '2026-05-13T10:30:00'.",
  "timeZone": "(string, optional, default: user's timezone) e.g., 'GMT Standard Time'.",
  "bodyContent": "(string, optional) Event body/description.",
  "bodyContentType": "(string, optional, default: 'HTML') 'Text' or 'HTML'.",
  "location": "(string, optional) Event location display name.",
  "isOnlineMeeting": "(boolean, optional, default: true) Whether to create as online meeting. Ignored when isAllDay=true.",
  "onlineMeetingProvider": "(string, optional, default: 'teamsForBusiness') Meeting provider.",
  "isAllDay": "(boolean, optional, default: false) Whether all-day event.",
  "showAs": "(string, optional, default: 'busy') Free/busy status: 'free', 'tentative', 'busy', 'oof', 'workingElsewhere', 'unknown'.",
  "sensitivity": "(string, optional, default: 'normal') 'normal', 'personal', 'private', 'confidential'.",
  "importance": "(string, optional, default: 'normal') 'low', 'normal', 'high'.",
  "allowNewTimeProposals": "(boolean, optional, default: true) Whether invitees can propose new time.",
  "responseRequested": "(boolean, optional, default: true) Whether response is requested.",
  "recurrence": "(object, optional) Recurrence pattern and range."
}
```

### Output Schema (with attendees + online meeting)
```json
{
  "allowNewTimeProposals": true,
  "attendees": [
    {
      "status": {
        "response": "none",
        "time": "0001-01-01T00:00:00+00:00"
      },
      "type": "required",
      "emailAddress": {
        "address": "santiago@projectroma.onmicrosoft.com",
        "name": "Santiago"
      },
      "odataType": "#microsoft.graph.attendee"
    }
  ],
  "body": {
    "content": "<html>...Microsoft Teams meeting join link, meeting ID, passcode, dial-in info...</html>",
    "contentType": "html"
  },
  "bodyPreview": "________________________________________________________________________________\r\nMicrosoft Teams meeting\r\nJoin: https://teams.microsoft.com/meet/...",
  "end": {
    "dateTime": "2026-05-13T10:30:00.0000000",
    "timeZone": "GMT Standard Time"
  },
  "hasAttachments": false,
  "hideAttendees": false,
  "iCalUId": "040000008200E00074C5B7101A82E008...",
  "importance": "normal",
  "isAllDay": false,
  "isCancelled": false,
  "isDraft": false,
  "isOnlineMeeting": true,
  "isOrganizer": true,
  "isReminderOn": true,
  "location": {
    "displayName": "Microsoft Teams Meeting",
    "locationType": "default",
    "uniqueId": "Microsoft Teams Meeting",
    "uniqueIdType": "private"
  },
  "locations": [
    {
      "displayName": "Microsoft Teams Meeting",
      "locationType": "default",
      "uniqueId": "Microsoft Teams Meeting",
      "uniqueIdType": "private"
    }
  ],
  "onlineMeeting": {
    "conferenceId": "677387679",
    "joinUrl": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_...",
    "tollNumber": "+44 20 3321 5270"
  },
  "onlineMeetingProvider": "teamsForBusiness",
  "organizer": {
    "emailAddress": {
      "address": "rishi@projectroma.onmicrosoft.com",
      "name": "Rishi"
    }
  },
  "originalEndTimeZone": "GMT Standard Time",
  "originalStartTimeZone": "GMT Standard Time",
  "reminderMinutesBeforeStart": 15,
  "responseRequested": true,
  "responseStatus": {
    "response": "organizer",
    "time": "0001-01-01T00:00:00+00:00"
  },
  "sensitivity": "normal",
  "showAs": "busy",
  "start": {
    "dateTime": "2026-05-13T10:00:00.0000000",
    "timeZone": "GMT Standard Time"
  },
  "subject": "Schema Capture Test Meeting",
  "type": "singleInstance",
  "webLink": "https://outlook.office365.com/owa/?itemid=AAMkADAxMDk4ZjdkLW...",
  "categories": [],
  "changeKey": "PBSnaUlUgUmbwD2KGuKsFAAAAvYVdg==",
  "createdDateTime": "2026-05-12T12:59:07.1287102+00:00",
  "lastModifiedDateTime": "2026-05-12T12:59:11.2417054+00:00",
  "additionalData": {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('<user-guid>')/events/$entity",
    "@odata.etag": "W/\"PBSnaUlUgUmbwD2KGuKsFAAAAvYVdg==\"",
    "uid": "040000008200E00074C5B7101A82E008...",
    "occurrenceId": null
  },
  "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVm...",
  "odataType": "#microsoft.graph.event"
}
```

### Output Schema (no attendees, no online meeting)
```json
{
  "allowNewTimeProposals": true,
  "attendees": [],
  "body": {
    "content": "",
    "contentType": "html"
  },
  "bodyPreview": "",
  "end": {
    "dateTime": "2026-05-13T14:30:00.0000000",
    "timeZone": "GMT Standard Time"
  },
  "hasAttachments": false,
  "hideAttendees": false,
  "iCalUId": "040000008200E00074C5B7101A82E008...",
  "importance": "normal",
  "isAllDay": false,
  "isCancelled": false,
  "isDraft": false,
  "isOnlineMeeting": false,
  "isOrganizer": true,
  "isReminderOn": true,
  "location": {
    "address": {},
    "coordinates": {},
    "displayName": "",
    "locationType": "default",
    "uniqueIdType": "unknown"
  },
  "locations": [],
  "onlineMeetingProvider": "unknown",
  "organizer": {
    "emailAddress": {
      "address": "rishi@projectroma.onmicrosoft.com",
      "name": "Rishi"
    }
  },
  "originalEndTimeZone": "GMT Standard Time",
  "originalStartTimeZone": "GMT Standard Time",
  "reminderMinutesBeforeStart": 15,
  "responseRequested": true,
  "responseStatus": {
    "response": "organizer",
    "time": "0001-01-01T00:00:00+00:00"
  },
  "sensitivity": "normal",
  "showAs": "busy",
  "start": {
    "dateTime": "2026-05-13T14:00:00.0000000",
    "timeZone": "GMT Standard Time"
  },
  "subject": "Schema Capture Test Delete",
  "type": "singleInstance",
  "webLink": "https://outlook.office365.com/owa/?itemid=AAMkADAxMDk4ZjdkLW...",
  "categories": [],
  "changeKey": "PBSnaUlUgUmbwD2KGuKsFAAAAvYWdA==",
  "createdDateTime": "2026-05-12T13:01:29.9148282+00:00",
  "lastModifiedDateTime": "2026-05-12T13:01:30.0300054+00:00",
  "additionalData": {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('<user-guid>')/events/$entity",
    "@odata.etag": "W/\"PBSnaUlUgUmbwD2KGuKsFAAAAvYWdA==\"",
    "uid": "040000008200E00074C5B7101A82E008...",
    "occurrenceId": null
  },
  "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVm...",
  "odataType": "#microsoft.graph.event"
}
```

---

## 7. UpdateEvent

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to update.",
  "subject": "(string, optional) Updated title.",
  "startDateTime": "(string, optional) Updated start time ISO 8601.",
  "endDateTime": "(string, optional) Updated end time ISO 8601.",
  "timeZone": "(string, optional) Updated timezone.",
  "body": "(string, optional) Updated body. IMPORTANT: If updating an online meeting body, retrieve current body first and preserve the Teams meeting section.",
  "location": "(string, optional) Updated location.",
  "attendeesToAdd": "(string[], optional) Emails/names to add.",
  "attendeesToRemove": "(string[], optional) Emails/names to remove.",
  "importance": "(string, optional) 'low', 'normal', 'high'.",
  "sensitivity": "(string, optional) 'normal', 'personal', 'private', 'confidential'.",
  "showAs": "(string, optional) Free/busy status.",
  "responseRequested": "(boolean, optional) Whether response requested.",
  "recurrence": "(object, optional) Updated recurrence."
}
```

### Output Schema
```json
{
  "allowNewTimeProposals": true,
  "attendees": [
    {
      "status": {
        "response": "none",
        "time": "0001-01-01T00:00:00+00:00"
      },
      "type": "required",
      "emailAddress": {
        "address": "santiago@projectroma.onmicrosoft.com",
        "name": "Santiago"
      },
      "odataType": "#microsoft.graph.attendee"
    }
  ],
  "body": {
    "content": "<html>...Microsoft Teams meeting HTML content...</html>",
    "contentType": "html"
  },
  "bodyPreview": "...",
  "end": {
    "dateTime": "2026-05-13T09:30:00.0000000",
    "timeZone": "UTC"
  },
  "hasAttachments": false,
  "hideAttendees": false,
  "iCalUId": "040000008200E00074C5B7101A82E008...",
  "importance": "normal",
  "isAllDay": false,
  "isCancelled": false,
  "isDraft": false,
  "isOnlineMeeting": true,
  "isOrganizer": true,
  "isReminderOn": true,
  "location": {
    "displayName": "Microsoft Teams Meeting",
    "locationType": "default",
    "uniqueId": "Microsoft Teams Meeting",
    "uniqueIdType": "private"
  },
  "locations": [
    {
      "displayName": "Microsoft Teams Meeting",
      "locationType": "default",
      "uniqueId": "Microsoft Teams Meeting",
      "uniqueIdType": "private"
    }
  ],
  "onlineMeeting": {
    "conferenceId": "677387679",
    "joinUrl": "https://teams.microsoft.com/l/meetup-join/...",
    "tollNumber": "+44 20 3321 5270"
  },
  "onlineMeetingProvider": "teamsForBusiness",
  "organizer": {
    "emailAddress": {
      "address": "rishi@projectroma.onmicrosoft.com",
      "name": "Rishi"
    }
  },
  "originalEndTimeZone": "GMT Standard Time",
  "originalStartTimeZone": "GMT Standard Time",
  "reminderMinutesBeforeStart": 15,
  "responseRequested": true,
  "responseStatus": {
    "response": "organizer",
    "time": "0001-01-01T00:00:00+00:00"
  },
  "sensitivity": "normal",
  "showAs": "busy",
  "start": {
    "dateTime": "2026-05-13T09:00:00.0000000",
    "timeZone": "UTC"
  },
  "subject": "Schema Capture Test Meeting (Updated)",
  "type": "singleInstance",
  "webLink": "https://outlook.office365.com/owa/?itemid=...",
  "categories": [],
  "changeKey": "PBSnaUlUgUmbwD2KGuKsFAAAAvYVzA==",
  "createdDateTime": "2026-05-12T12:59:07.1287102+00:00",
  "lastModifiedDateTime": "2026-05-12T12:59:36.1141388+00:00",
  "additionalData": {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('<user-guid>')/events/$entity",
    "@odata.etag": "W/\"PBSnaUlUgUmbwD2KGuKsFAAAAvYVzA==\"",
    "uid": "040000008200E00074C5B7101A82E008...",
    "occurrenceId": null
  },
  "id": "AAMkADAxMDk4ZjdkLWQzZjUtNDBjNy1hNjY4LTBlOWVm...",
  "odataType": "#microsoft.graph.event"
}
```

**Note:** The output schema is identical to CreateEvent — returns the full updated event object. The `end.timeZone` in UpdateEvent response was returned as `"UTC"` rather than the original timezone — this is a Graph API behavior when timezone is not explicitly re-provided in the update.

---

## 8. AcceptEvent

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to accept.",
  "comment": "(string, optional) Comment with the acceptance.",
  "sendResponse": "(boolean, optional, default: true) Whether to notify organizer."
}
```

### Output Schema (Error — organizer cannot accept own event)
```json
{
  "error": "Error executing tool: Your request can't be completed. You can't respond to this meeting because you're the meeting organizer."
}
```

**Note:** This tool only works when the caller is an **invitee**, not the organizer. On success, the expected response is a simple confirmation string (no JSON body — Graph's POST /accept returns 202 Accepted with empty body). The MCP wrapper likely returns: `"Event accepted successfully."`

---

## 9. DeclineEvent

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to decline.",
  "comment": "(string, optional) Comment with the decline.",
  "sendResponse": "(boolean, optional, default: true) Whether to notify organizer."
}
```

### Output Schema (Error — organizer cannot decline own event)
```json
{
  "error": "Error executing tool: Your request can't be completed. You can't respond to this meeting because you're the meeting organizer."
}
```

**Note:** Same constraint as AcceptEvent — only invitees can decline. On success, the expected response is: `"Event declined successfully."` (Graph's POST /decline returns 202 Accepted with empty body).

---

## 10. TentativelyAcceptEvent

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to tentatively accept.",
  "comment": "(string, optional) Comment with the tentative acceptance.",
  "sendResponse": "(boolean, optional, default: true) Whether to notify organizer."
}
```

### Output Schema (Error — organizer cannot tentatively accept own event)
```json
{
  "error": "Error executing tool: Your request can't be completed. You can't respond to this meeting because you're the meeting organizer."
}
```

**Note:** Same constraint as AcceptEvent/DeclineEvent — only invitees can respond. On success, the expected response is: `"Event tentatively accepted successfully."` (Graph's POST /tentativelyAccept returns 202 Accepted with empty body).

---

## 11. ForwardEvent

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to forward.",
  "recipientEmails": "(string[], required) Recipient emails/names.",
  "comment": "(string, optional) Comment with the forwarded event."
}
```

### Output Schema
```text
"Event forwarded successfully to 1 recipient(s)."
```

**Note:** Returns a plain text confirmation string. No JSON body — Graph's POST /forward returns 202 Accepted with empty body. The MCP wrapper adds the recipient count.

---

## 12. CancelEvent

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to cancel (organizer-only). Sends cancellation notice to all attendees AND removes the event.",
  "comment": "(string, optional) Comment with the cancellation."
}
```

### Output Schema
```text
"Event cancelled successfully."
```

**Note:** Returns a plain text confirmation string. The event is moved to Deleted Items and cancellation notices are sent to all attendees. Do NOT call DeleteEventById after CancelEvent — the event is already gone.

---

## 13. DeleteEventById

### Input Schema
```json
{
  "eventId": "(string, required) Event ID to delete. Use when you are not the organizer or don't need to notify attendees."
}
```

### Output Schema
```text
"Event deleted successfully."
```

**Note:** Returns a plain text confirmation string. Silently removes the event without sending any notifications. Use this for events without attendees or when you're not the organizer.

---

# Common Response Patterns

## Event Object Shape

The full event object is returned by `CreateEvent`, `UpdateEvent`, `ListEvents`, and `ListCalendarView`. Core fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique event identifier (Graph format: `AAMkA...`) |
| `subject` | string | Event title |
| `body` | object | `{ content: string, contentType: "html"\|"text" }` |
| `bodyPreview` | string | Truncated plain-text preview (~255 chars) |
| `start` | object | `{ dateTime: string, timeZone: string }` |
| `end` | object | `{ dateTime: string, timeZone: string }` |
| `organizer` | object | `{ emailAddress: { address: string, name: string } }` |
| `attendees` | array | Array of Attendee objects |
| `location` | object | `{ displayName, locationType, uniqueId, uniqueIdType }` |
| `locations` | array | Array of location objects |
| `importance` | string | `"low"` \| `"normal"` \| `"high"` |
| `sensitivity` | string | `"normal"` \| `"personal"` \| `"private"` \| `"confidential"` |
| `showAs` | string | `"free"` \| `"tentative"` \| `"busy"` \| `"oof"` \| `"workingElsewhere"` |
| `isAllDay` | boolean | Whether all-day event |
| `isCancelled` | boolean | Whether event has been cancelled |
| `isDraft` | boolean | Whether event is a draft |
| `isOnlineMeeting` | boolean | Whether includes online meeting |
| `isOrganizer` | boolean | Whether current user is organizer |
| `isReminderOn` | boolean | Whether reminder is set |
| `reminderMinutesBeforeStart` | integer | Minutes before start for reminder |
| `hasAttachments` | boolean | Whether event has attachments |
| `type` | string | `"singleInstance"` \| `"occurrence"` \| `"exception"` \| `"seriesMaster"` |
| `onlineMeeting` | object | `{ conferenceId, joinUrl, tollNumber }` (null if not online) |
| `onlineMeetingProvider` | string | `"teamsForBusiness"` \| `"unknown"` |
| `responseStatus` | object | `{ response: string, time: string }` |
| `allowNewTimeProposals` | boolean | Whether attendees can propose new times |
| `responseRequested` | boolean | Whether response was requested |
| `categories` | array | Array of category strings |
| `changeKey` | string | ETag for concurrency |
| `createdDateTime` | string | ISO 8601 creation timestamp |
| `lastModifiedDateTime` | string | ISO 8601 last modified timestamp |
| `webLink` | string | Outlook Web App link to the event |
| `iCalUId` | string | iCalendar unique ID |
| `hideAttendees` | boolean | Whether attendees are hidden |
| `originalStartTimeZone` | string | Original timezone for start |
| `originalEndTimeZone` | string | Original timezone for end |

## Attendee Object Shape

```json
{
  "emailAddress": {
    "address": "user@domain.com",
    "name": "Display Name"
  },
  "type": "required",          // "required" | "optional" | "resource"
  "status": {
    "response": "none",        // "none" | "organizer" | "tentativelyAccepted" | "accepted" | "declined" | "notResponded"
    "time": "0001-01-01T00:00:00+00:00"
  }
}
```

## Time/Date Format Patterns

- **DateTime format:** `"2026-05-13T10:00:00.0000000"` — ISO 8601 with 7 decimal places
- **TimeZone in responses:** Uses Windows timezone names (e.g., `"GMT Standard Time"`, `"UTC"`)
- **Sentinel dates:** `"0001-01-01T00:00:00+00:00"` used for "not set" / "no response" timestamps
- **Input format:** `"2026-05-13T10:00:00"` — ISO 8601 without fractional seconds is accepted

## Error Patterns

Errors are returned as MCP error strings in the format:
```
MCP server 'WorkIQ-CalendarServer': Error: Error executing tool: <message>
CorrelationId: <guid>, TimeStamp: <timestamp>
```

Known error messages:
- `"Your request can't be completed. You can't respond to this meeting because you're the meeting organizer."` — RSVP tools (Accept/Decline/TentativelyAccept) on your own event
- Event not found errors when using invalid event IDs

## Correlation ID Pattern

Every response includes a trailing correlation ID:
```
CorrelationId: <guid>, TimeStamp: YYYY-MM-DD_HH:MM:SS
```

## Pagination Patterns

- `ListCalendarView` and `ListEvents` support `top` parameter to limit results
- No explicit `@odata.nextLink` pagination was observed in these responses (all results fit within the requested `top` limit)
- Both return `{ "value": [...] }` array wrapper

## Response Types Summary

| Tool | Response Type | Returns JSON? |
|------|--------------|---------------|
| GetUserDateAndTimeZoneSettings | Full JSON object | ✅ |
| ListCalendarView | JSON `{ value: [...] }` or plain text "No events found" | ✅ / ❌ |
| ListEvents | JSON `{ value: [...] }` or plain text "No events found" | ✅ / ❌ |
| FindMeetingTimes | Full JSON object | ✅ |
| GetRooms | JSON `{ value: [...] }` | ✅ |
| CreateEvent | Full event JSON object | ✅ |
| UpdateEvent | Full event JSON object | ✅ |
| AcceptEvent | Plain text confirmation | ❌ |
| DeclineEvent | Plain text confirmation | ❌ |
| TentativelyAcceptEvent | Plain text confirmation | ❌ |
| ForwardEvent | Plain text confirmation | ❌ |
| CancelEvent | Plain text confirmation | ❌ |
| DeleteEventById | Plain text confirmation | ❌ |

## `backingStore` and `additionalData` Fields

Many response objects include `backingStore` and `additionalData` fields that are Microsoft Graph SDK internal metadata. These are implementation details of the SDK serialization and can be safely ignored when parsing responses. Key patterns:
- `backingStore: { initializationCompleted: boolean, returnOnlyChangedValues: boolean }` — SDK tracking field
- `additionalData: {}` — May contain `@odata.context`, `@odata.etag`, `uid`, `occurrenceId`, and OData navigation/association links

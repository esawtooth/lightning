# lightening

Event based AI

## Event API

Deploying the infrastructure will create an Azure Function that exposes an HTTP endpoint for queuing events.

### PUT /api/events

Include a header `X-User-ID` identifying the user on whose behalf the event was
generated. Send a JSON body describing the event:

```json
{
  "timestamp": "2023-01-01T00:00:00Z",
  "source": "sensor-1",
  "type": "movement",
  "userID": "abc123",
  "metadata": {"x": 1, "y": 2}
}
```

The function validates the data and publishes it to the Service Bus queue. The `type` field is used as the topic of the message.

## Python library

The `events` package provides a dataclass `Event` that can be used to structure events before they are sent to the API or processed downstream.

### LLMChatEvent

`LLMChatEvent` extends `Event` and expects a list of chat messages stored under
`metadata.messages`. Each message should be a mapping with at least `role` and
`content` keys. When `LLMChatEvent.to_dict()` is called, the messages are
ensured to appear under the `metadata` key.

## Function Configuration

The Azure Functions rely on several environment variables for authentication and
messaging:

- `OPENAI_API_KEY` &mdash; API key used by the `ChatResponder` function when
  calling OpenAI.
- `SERVICEBUS_CONNECTION` &mdash; connection string for the Service Bus
  namespace.
- `SERVICEBUS_QUEUE` &mdash; queue name for publishing and receiving events.

Set these values in your deployment environment or in a local `.env` file when
testing the functions locally.

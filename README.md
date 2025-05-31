# lightening

Event based AI

## Event API

Deploying the infrastructure will create an Azure Function that exposes an HTTP endpoint for queuing events.

### POST /api/events

Authenticate requests with a bearer token in the `Authorization` header.
The token must be signed using the key provided in `JWT_SIGNING_KEY` and
identifies the user. Send a JSON body describing the event:

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

### POST /api/schedule

Schedule an event for future delivery. Provide the same bearer token in the
`Authorization` header and a JSON body containing the event payload and either
a one-time `timestamp` or a `cron` expression:

```json
{
  "event": { "type": "user.message", "source": "client", "metadata": {"message": "hi"} },
  "timestamp": "2023-01-01T01:00:00Z"
}
```

or

```json
{
  "event": { "type": "user.message", "source": "client", "metadata": {"message": "hi"} },
  "cron": "0 * * * *"
}
```

The function stores the schedule in durable storage and returns a schedule ID.

## Python library

The `events` package provides a dataclass `Event` that can be used to structure events before they are sent to the API or processed downstream.

### LLMChatEvent

`LLMChatEvent` extends `Event` and expects a list of chat messages stored under
`metadata.messages`. Each message should be a mapping with at least `role` and
`content` keys. When `LLMChatEvent.to_dict()` is called, the messages are
ensured to appear under the `metadata` key.

### UserMessenger function

The `UserMessenger` Azure Function listens to the Service Bus queue for events of type `user.message` and `llm.chat.response`. When such an event is processed it forwards the text to the user. If no notification endpoint is configured (via the `NOTIFY_URL` environment variable) the text is logged instead.

This allows the platform to acknowledge incoming chat messages before the LLM generates a response and then deliver the assistant's reply once it is available.

## ChatResponder function

`ChatResponder` is an Azure Function that listens to the Service Bus queue and
uses OpenAI's chat API to generate replies to incoming `LLMChatEvent` messages.

### Configuration

The function requires the following application settings:

- `SERVICEBUS_CONNECTION` – connection string for the queue.
- `SERVICEBUS_QUEUE` – name of the queue containing chat events.
- `OPENAI_API_KEY` – API key used by the `openai` library.
- `OPENAI_MODEL` – model name passed to OpenAI. Defaults to `gpt-3.5-turbo`.

### Expected event

Events must include a `metadata.messages` list of chat messages:

```json
{
  "timestamp": "2023-01-01T00:00:00Z",
  "source": "client",
  "type": "llm.chat",
  "userID": "abc123",
  "metadata": {
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }
}
```

### Example usage

Send a chat event via the HTTP endpoint:

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @event.json \
  https://<function-app>.azurewebsites.net/api/events
```

`ChatResponder` publishes a new event of type `llm.chat.response` containing the
assistant reply:

```json
{
  "timestamp": "2023-01-01T00:00:01Z",
  "source": "ChatResponder",
  "type": "llm.chat.response",
  "userID": "abc123",
  "metadata": {"reply": "..."}
}
```

### Deployment

1. Deploy the infrastructure with Pulumi:

   ```bash
   cd infra
   pip install -r requirements.txt
   pulumi up
   ```

2. Publish the functions to Azure:

   ```bash
   cd ../azure-function
   func azure functionapp publish event-function
   ```

If deploying manually, ensure `OPENAI_API_KEY` is configured on the Function App
before publishing. The GitHub Actions workflow reads the `OPENAI_API_KEY` secret
and sets this application setting automatically when running Pulumi.

## Function Configuration

The Azure Functions rely on several environment variables for authentication and
messaging:

- `OPENAI_API_KEY` &mdash; API key used by the `ChatResponder` function when
  calling OpenAI.
  When deploying with GitHub Actions, set this as the `OPENAI_API_KEY` secret
  so the workflow can configure the Function App.
- `OPENAI_MODEL` &mdash; model name for ChatResponder when calling OpenAI 
  (defaults to `gpt-3.5-turbo`).
- `SERVICEBUS_CONNECTION` &mdash; connection string for the Service Bus
  namespace.
- `SERVICEBUS_QUEUE` &mdash; queue name for publishing and receiving events.
- `NOTIFY_URL` &mdash; endpoint that `UserMessenger` calls to deliver messages
  to the chat client.
- `JWT_SIGNING_KEY` &mdash; HMAC key used to validate bearer tokens.

Set these values in your deployment environment or in a local `.env` file when
testing the functions locally.

## Local Testing

When running the project on your machine you can provide the environment
settings either through `azure-function/local.settings.json` (used by Azure
Functions Core Tools) or through a `.env` file in the repository root.

### Sample `local.settings.json`

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "OPENAI_API_KEY": "sk-...",
    "OPENAI_MODEL": "gpt-3.5-turbo",
    "SERVICEBUS_CONNECTION": "<connection-string>",
    "SERVICEBUS_QUEUE": "chat-events",
    "NOTIFY_URL": "http://localhost:8000/notify",
    "JWT_SIGNING_KEY": "secret"
  }
}
```

### Sample `.env`

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-3.5-turbo
SERVICEBUS_CONNECTION=<connection-string>
SERVICEBUS_QUEUE=chat-events
NOTIFY_URL=http://localhost:8000/notify
JWT_SIGNING_KEY=secret
AUTH_TOKEN=<jwt-token>
```

Start the functions locally from the `azure-function` directory:

```bash
cd azure-function
func start
```

In another terminal, run the chat client:

```bash
chainlit run chat_client/chainlit_app.py
```

Set `EVENT_API_URL` to `http://localhost:7071/api/events` so the client sends
events to your local Function App. Provide your bearer token in the
`AUTH_TOKEN` environment variable so the client can authenticate with the Event
API.

## Chainlit client

Run the interactive chat client using [Chainlit](https://github.com/Chainlit/chainlit):

```bash
chainlit run chat_client/chainlit_app.py
```

`EVENT_API_URL` should point to the `/api/events` endpoint of the Azure
Function. Configure `AUTH_TOKEN` with your JWT and set `NOTIFY_URL` for the
Azure Functions as `http://<chainlit_host>/notify` so `UserMessenger` can
forward messages back to the client.


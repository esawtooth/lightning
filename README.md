# lightning

Event based AI

## Event API

Deploying the infrastructure will create an Azure Function that exposes an HTTP endpoint for queuing events.
The HTTP triggers use anonymous authorization so no Function key is required. Authenticate only with a bearer token.

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

## Authentication API

New endpoints allow registering users and retrieving JWT tokens for authenticated
access to the rest of the service.

### POST /api/register

Create a new user by sending a JSON payload containing an identifier and
password:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"userID": "alice", "password": "secret"}' \
  https://<function-app>.azurewebsites.net/api/register
```

### POST /api/token

Exchange credentials for a signed JWT. Include the same JSON body used during
registration:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"userID": "alice", "password": "secret"}' \
  https://<function-app>.azurewebsites.net/api/token
```

The returned token should be provided in the `Authorization` header when calling
the other API endpoints.

### POST /api/refresh

Send the current token in the `Authorization` header to obtain a new JWT with a
fresh expiration time:

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  https://<function-app>.azurewebsites.net/api/refresh
```

If the token is valid a new token is returned. Invalid or expired tokens result
in a `401` response.

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

- The function requires the following application settings:

- `SERVICEBUS_CONNECTION` – connection string for the Service Bus namespace
  (do **not** include the `EntityPath` property).
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

Deploy the entire infrastructure and application code with Pulumi. Set the required configuration
values for the OpenAI key, JWT signing key and container images:

```bash
cd infra
pip install -r requirements.txt
pulumi config set openaiApiKey <key> --secret
pulumi config set jwtSigningKey <secret> --secret
pulumi config set uiImage lightningacr.azurecr.io/chainlit-client:<tag>
pulumi config set workerImage lightningacr.azurecr.io/worker-task:<tag>
pulumi config set domain agentsmith.in
pulumi up
```

 Pulumi automatically:
 - Creates all Azure resources (Function App, Cosmos DB, Service Bus, Communication Service, Email Service, etc.)
- Packages the Azure Functions code
- Deploys the function code to the Function App
- Grants the Function App's managed identity read access to the deployment
  package and sets `WEBSITE_RUN_FROM_PACKAGE` to the package URL
- Builds and deploys the UI containers
- Configures all environment variables and connections
- Creates an Azure DNS zone with records for the chat UI and API.
  Update your domain registrar to use the zone's name servers manually
  (defaults to `agentsmith.in` if no domain is configured).
  Pulumi exports these servers as `dnsZoneNameServers`.

After `pulumi up` completes copy the values from `dnsZoneNameServers` and
update the nameserver records for your domain in GoDaddy.

The Function App uses the **Python 3.10** runtime. If you deployed an older
stack running Python 3.9 you may see a deprecation warning in the Azure portal.
Redeploy with the updated Pulumi script to upgrade the runtime.

The stack also provisions a container instance running the Chainlit UI and
dashboard. Pulumi exports the container's public URL as `uiUrl`.

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
  to the chat client. Pulumi sets this automatically based on the Chainlit
  container address.
- `JWT_SIGNING_KEY` &mdash; HMAC key used to validate bearer tokens.
- `COSMOS_CONNECTION` &mdash; connection string for the Cosmos DB account.
- `COSMOS_DATABASE` &mdash; database name (defaults to `lightning`).
- `USER_CONTAINER` &mdash; container storing user accounts. Defaults to `users`.
- `REPO_CONTAINER` &mdash; container storing repository URLs. Defaults to `repos`.
- `SCHEDULE_CONTAINER` &mdash; container used by the scheduler. Defaults to `schedules`.
- `TASK_CONTAINER` &mdash; container storing worker task records. Defaults to `tasks`.
- `ACS_CONNECTION` &mdash; connection string for Azure Communication Services email.
- This connection string is retrieved from the Communication Service, while an additional Email Service resource handles domains.
- `ACS_SENDER` &mdash; default sender email address for verification messages. Defaults to `no-reply@<domain>` where `<domain>` comes from the Pulumi `domain` config (set in the GitHub workflow).
- `VERIFY_BASE_URL` &mdash; base URL used to generate verification links.
- `APPINSIGHTS_INSTRUMENTATIONKEY` &mdash; instrumentation key for Application Insights. Pulumi sets this automatically.
- `WEBSITE_RUN_FROM_PACKAGE` &mdash; URL of the function package. Pulumi grants
  the Function App's managed identity read access so the app can download the
  package automatically.

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
    "SERVICEBUS_CONNECTION": "<namespace-connection-string>",
    "SERVICEBUS_QUEUE": "chat-events",
    "NOTIFY_URL": "http://localhost:8000/notify",
    "JWT_SIGNING_KEY": "secret",
    "COSMOS_CONNECTION": "<cosmos-connection-string>",
    "COSMOS_DATABASE": "lightning",
    "USER_CONTAINER": "users",
    "REPO_CONTAINER": "repos",
    "SCHEDULE_CONTAINER": "schedules",
    "TASK_CONTAINER": "tasks"
  }
}
```

### Sample `.env`

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-3.5-turbo
SERVICEBUS_CONNECTION=<namespace-connection-string>
SERVICEBUS_QUEUE=chat-events
NOTIFY_URL=http://localhost:8000/notify
JWT_SIGNING_KEY=secret
COSMOS_CONNECTION=<cosmos-connection-string>
COSMOS_DATABASE=lightning
USER_CONTAINER=users
REPO_CONTAINER=repos
SCHEDULE_CONTAINER=schedules
TASK_CONTAINER=tasks
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

### Azure CLI function test

Use `scripts/test_azure_functions.sh` to verify that your Function App is
running and that the `UserAuth` endpoints respond correctly. The script requires
the Azure CLI to be installed and authenticated.

```bash
bash scripts/test_azure_functions.sh <resource-group> <function-app-name>
```

## Chainlit client

Run the interactive chat client using [Chainlit](https://github.com/Chainlit/chainlit):

```bash
chainlit run chat_client/chainlit_app.py
```

`EVENT_API_URL` should point to the `/api/events` endpoint of the Azure
Function. Configure `AUTH_TOKEN` with your JWT and set `NOTIFY_URL` for the
Azure Functions as `http://<chainlit_host>/notify` so `UserMessenger` can
forward messages back to the client.

## Dashboard

A simple FastAPI dashboard is located in the `dashboard/` directory. It allows
logging in, submitting events, and monitoring worker tasks. Launch it with:

```bash
uvicorn dashboard.app:app --reload
```

Set `API_BASE` to the base URL of your Azure Functions (defaults to
`http://localhost:7071/api`). If `AUTH_TOKEN` is provided the dashboard will use
it for outgoing requests; otherwise use the `/login` page to obtain a token.
Visit `/tasks` to view task status and container logs.

Container logs now include each bash command executed by the agent along with
its output, allowing you to watch task progress in near real-time.


## Worker Agents

The `agents/` directory contains agent implementations that the worker container can
invoke to process tasks. Each agent registers itself in `agents.AGENT_REGISTRY`
and exposes a `run()` method used to handle the commands from a
`WorkerTaskEvent`.

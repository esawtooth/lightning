# Lightening Product Specification

## Overview

Lightening is an event driven AI platform built on Azure Functions. It allows clients to send structured events to a cloud queue, process them with serverless functions, and deliver asynchronous responses. The system supports scheduling, authentication, chat handling through OpenAI, and task execution in container workers.

## Goals

- Provide a simple HTTP API for queuing events and scheduling future events.
- Enable authenticated user access with JWT tokens.
- Process chat events using OpenAI and forward responses back to clients.
- Run custom tasks against user repositories inside Azure Container Instances
  and support long-running asynchronous actions executed inside dedicated VMs
  where a CLI tool can run arbitrary commands.

## Architecture

1. **Event API** – Azure Function `PutEvent` receives JSON events and publishes them to an Azure Service Bus queue.
2. **Scheduler** – Stores future events in Azure Table storage and dispatches them at the scheduled time via `ScheduleWorker`.
3. **ChatResponder** – Listens to chat events (`llm.chat`) and calls OpenAI's ChatCompletion API to generate replies. Replies are published as `llm.chat.response` events.
4. **UserMessenger** – Forwards `user.message` and `llm.chat.response` events to a configured notification URL so chat clients receive messages.
5. **WorkerTaskRunner** – Launches short‑lived container instances to execute commands from `WorkerTaskEvent` messages. Results are sent back as `worker.task.result` events.
6. **Tool Subscribers** – Each CLI‑based tool subscribes to a specific event topic. When an input event arrives the subscriber provisions a VM (or container) and runs the tool. The tool can install packages, execute scripts, or make web requests. Output is published as a new event.
7. **UserAuth** – Provides `/api/register` and `/api/token` endpoints for registering accounts and issuing JWTs.
8. **Dashboard and Client** – A FastAPI dashboard and Chainlit chat client provide example front ends for interacting with the system.
9. **Infrastructure** – Pulumi scripts provision the Azure resources including Service Bus, storage tables, and the Function App.

## API Endpoints

- `POST /api/events` – Queue an event. Requires `Authorization: Bearer <token>` header. Accepts an event payload with `timestamp`, `source`, `type`, `userID`, and optional `metadata` fields. Events are validated and placed on the Service Bus queue.
- `POST /api/schedule` – Schedule a future event. Provide the event payload and either a `timestamp` or `cron` expression. Returns a schedule ID on success.
- `POST /api/register` – Create a new user account with `userID` and `password`.
- `POST /api/token` – Exchange credentials for a JWT used to authenticate other requests.

## Environment Configuration

The Azure Functions rely on several environment variables:

- `OPENAI_API_KEY` – API key for ChatResponder when calling OpenAI.
- `OPENAI_MODEL` – Model name for ChatResponder (defaults to `gpt-3.5-turbo`).
- `SERVICEBUS_CONNECTION` – Connection string for the Service Bus namespace.
- `SERVICEBUS_QUEUE` – Queue name for publishing and receiving events.
- `NOTIFY_URL` – Endpoint that UserMessenger calls to deliver messages to the chat client.
- `JWT_SIGNING_KEY` – Key used to sign and verify JWTs.
- `STORAGE_CONNECTION` – Connection string for Azure Table storage.
- `USER_TABLE` – Table used to store user credentials (default `users`).
- `REPO_TABLE` – Table storing repository URLs (default `repos`).
- `SCHEDULE_TABLE` – Table used by the scheduler (default `schedules`).

## Typical Flow

1. A client obtains a token via `/api/register` and `/api/token`.
2. The client sends a chat event to `/api/events`.
3. `ChatResponder` processes the message with OpenAI and emits a `llm.chat.response` event.
4. `UserMessenger` posts the assistant reply to the client via the configured notification endpoint.
5. If further processing is needed, `ChatResponder` or the user can emit a new event targeting a tool subscriber.
6. The subscriber provisions a VM or container and runs the CLI tool with the requested commands. The tool may run for an extended period and is free to install packages or fetch data as needed.
7. When the tool completes, results are emitted as a new event for downstream consumers.

## Usage Examples

See `README.md` for detailed curl examples and local testing instructions. The repository also includes tests demonstrating expected behavior of each component.

## CLI Tool Execution

Tools are packaged as command line utilities that run inside ephemeral VMs. Each
tool defines the event types it accepts. A subscriber listens for these events,
spins up a VM, and invokes the tool with the event payload. Tools have full
network access and may install packages or execute arbitrary scripts. When the
tool finishes it publishes a result event so other components can continue the
workflow. This enables complex multi‑step tasks that combine online lookups with
long‑running processing.


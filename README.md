# lightening

Event based AI

## Event API

Deploying the infrastructure will create an Azure Function that exposes an HTTP endpoint for queuing events.

### PUT /api/events

Send a JSON body describing the event:

```json
{
  "timestamp": "2023-01-01T00:00:00Z",
  "source": "sensor-1",
  "type": "movement",
  "metadata": {"x": 1, "y": 2}
}
```

The function validates the data and publishes it to the Service Bus queue. The `type` field is used as the topic of the message.

## Python library

The `events` package provides a dataclass `Event` that can be used to structure events before they are sent to the API or processed downstream.

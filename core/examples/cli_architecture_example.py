#!/usr/bin/env python3
"""
CLI Architecture Example: Event-Driven vs Direct Calls
"""

print("""
VEXTIR OS CLI ARCHITECTURE
==========================

❌ WRONG WAY - Direct Service Calls:
------------------------------------

class BadCLI:
    def chat_command(self):
        # Bad: CLI directly calls OpenAI
        client = OpenAI()
        response = client.chat.completions.create(...)
        print(response)
        
    def email_command(self):
        # Bad: CLI directly sends email
        smtp_client.send(...)
        
Problem: CLI is tightly coupled to services!


✅ CORRECT WAY - Event-Driven:
------------------------------

class GoodCLI:
    def __init__(self):
        self.event_bus = runtime.event_bus
        
    async def chat_command(self, message):
        # Good: CLI sends event
        event = EventMessage(
            type="llm.chat",
            data={"messages": [{"role": "user", "content": message}]}
        )
        
        # Publish and wait for response
        response_event = await self.send_and_wait(event)
        print(response_event.data["response"])
        
    async def email_command(self, to, subject, body):
        # Good: CLI sends event
        event = EventMessage(
            type="email.send",
            data={"to": to, "subject": subject, "body": body}
        )
        await self.event_bus.publish(event)


EVENT FLOW:
-----------

1. User types: "vextir chat"
   
2. CLI creates event:
   {
     "type": "llm.chat",
     "data": {"messages": [...]}
   }
   
3. Event Bus routes to ChatAgentDriver
   
4. ChatAgentDriver:
   - Receives event
   - Calls OpenAI API
   - Publishes response event
   
5. CLI receives response event:
   {
     "type": "llm.chat.response",
     "data": {"response": "..."}
   }
   
6. CLI displays to user


BENEFITS:
---------
• CLI doesn't need API keys
• CLI doesn't know about OpenAI
• Easy to swap LLM providers
• All communication is logged
• Works the same locally and in cloud
• Multiple handlers can process events
• CLI stays simple and focused


CURRENT IMPLEMENTATION:
----------------------
The new event-driven CLI (event_driven_cli.py) follows this pattern:
- Only publishes/subscribes to events
- Never calls services directly
- Waits for responses through events
- Pure event-driven architecture
""")
Understood. I’ll now prepare a detailed design document that covers the planner and workflow kernel architecture in the lightning repository, incorporating Petri net foundations, process calculus features (like channel-passing), and LLM-based planning/repair. It will also define how to evolve this into a scalable, distributed orchestration kernel over Azure.

I'll get started and let you know as soon as the design doc and engineering task list are ready.


# AI OS Planning & Workflow Kernel – Technical Design and Task Plan

## Introduction

This document outlines the design of the **AI OS core planning and workflow execution kernel** (Lightning Planner) and a phased engineering plan for its implementation. The kernel is responsible for generating, validating, and executing multi-step AI-driven workflows (plans) in the Vextir OS, using Petri net formalisms and tight integration with Large Language Models (LLMs). The design builds on the existing Lightning codebase and leverages *Petri nets with colored tokens* (inspired by process calculi) to model complex, concurrent workflows. It also details how LLMs will be used in plan creation, validation, repair, and introspection. Key concerns such as event-driven execution, external tool interfacing, state observability, and cloud deployment on Azure are addressed.

## Rationale: Petri Nets with Colored Tokens & Channel Semantics

**Why Petri nets?** Petri nets provide a rigorous model for **concurrent, asynchronous workflows**, capturing the flow of events (places) and actions (transitions) with formal semantics. By modeling each plan as a Petri net, we gain the ability to verify structural properties (e.g. absence of deadlocks or unwanted cycles) and execute steps in parallel when independent. The Lightning Planner already constructs a Petri Net graph for each plan to validate its structure. Petri nets naturally represent event-driven flows: *places* correspond to events or states, and *transitions* correspond to actions/steps that consume and produce events.

**Colored tokens & higher-order processes:** Traditional Petri nets use indistinguishable tokens, but **colored Petri nets** allow tokens to carry data, types, or identifiers. We exploit this to encode *channels* or data payloads within events (tokens), enabling **higher-order process semantics** akin to those in process calculi like the π-calculus. In practice, each event in a plan can carry a payload (e.g. context data, identifiers, even references to callback channels). Guards on transitions can inspect token data, and transitions can emit new tokens with computed data. This approach effectively allows *channel passing*: a workflow step can output a token containing a fresh channel or event name that subsequent steps use for communication. For example, a step could spawn a worker and emit a token containing a unique response event channel; another step listening on that channel will fire when the worker responds. By treating channel identifiers as data passed through tokens, the net’s topology can **dynamically extend** at runtime (new communication links are established through data), achieving higher-order behavior without altering the static plan graph. This combination of Petri nets + channel-colored tokens yields a model that supports dynamic, **composable workflows** with formal underpinnings. It was chosen to ensure complex AI workflows (which may spawn sub-tasks or delegate work) remain analyzable and correct by design.

**Concurrency and synchronization:** Petri nets excel at modeling concurrency. Transitions can fire in parallel if their input events are available, and multiple tokens enable iterative or concurrent flows. Using colored tokens further lets us differentiate concurrent sessions of a workflow by token identity (e.g. separate tokens for separate user tasks or loop iterations). This ensures the kernel can handle multiple instances of workflows and reentrant triggers safely, with each token carrying its context. Synchronization conditions (e.g. waiting for multiple events) are naturally modeled by transitions with multiple input places: the transition “fires” only when all required event tokens are present, providing an AND-synchronization. This aligns with our plan representation where a step’s `on` list may have multiple events that must occur before the step executes. The kernel will leverage these semantics to manage complex trigger conditions. In summary, the Petri net + colored token model offers **formal correctness, concurrency control, and dynamic channel passing**, making it a robust foundation for the AI OS planner.

## Plan Representation and Semantics

Each workflow plan is represented as a JSON structure (and corresponding Pydantic model) capturing the Petri net graph of events and steps. The core schema is defined by `PlanModel` in the code, with fields: `plan_name`, `graph_type` (acyclic or reactive), `events`, and `steps`. Key elements of the representation:

* **Events:** Represented as a dictionary of event names to definitions (the value can hold metadata or schema for that event). Events act as Petri net *places* (conditions or signals). For example, an event could be an external trigger like `"email.received"` or an internal signal like `"task.completed"`. In a plan JSON, events are keys like `"start"`, `"done"`, etc., each mapping to an (possibly empty) object. The presence of an event in this map declares it as a place in the net. Events may carry *data payloads* at runtime (the colored token content), even if the plan definition doesn’t enumerate the data fields. This allows passing context or channel info at execution time.

* **Steps:** Each step is a transition in the Petri net, defined by a unique name and containing:

  * `on`: a list of one or more event names that trigger this step. These correspond to the input places for the transition. All listed events must be available (tokens present) for the step to execute, modeling synchronization. If multiple events are listed, the step acts as a join (waiting for all). If a single event is listed, it’s a simple trigger. For example, `{"on": ["start"]}` means the step waits for the `start` event token.
  * `action`: a string identifying the action or tool to execute for this step (e.g. `"send_email"`, `"web_search"`). This is effectively the **operation** the transition performs when it fires.
  * `args`: a dictionary of arguments for the action. These will be passed to the tool/driver responsible for the action. For instance, `"args": {"to": "...", "subject": "..."}` for `send_email`. The schema for these args is defined per tool in a registry.
  * `emits`: an optional list of events that this step produces upon completion. These correspond to output places for the transition. Emitting an event means the step’s action will generate a token for that event, which can trigger other steps. For example, a step might emit `"done"` to signal the workflow finished.
  * `guard`: an optional condition (expressed as a boolean expression or code snippet) that must evaluate to true for the step to execute. This provides conditional branching within the net. The guard can inspect input token data (colored token properties) to decide if the transition should fire. If the guard fails, the transition is skipped (no tokens consumed or emitted), effectively filtering out certain event occurrences.

* **Graph Types – Acyclic vs Reactive:** `graph_type` is a flag indicating if the plan is a one-off directed acyclic graph or a persistent reactive graph. In an **acyclic** plan, the net is expected not to have cycles. The validator enforces this – if any cycle is found, it raises an error. Acyclic plans are like traditional workflows that start, progress through a DAG, and terminate (e.g. a multi-step task automation). In a **reactive** plan, cycles or repeated triggers are allowed; these represent long-running processes that may not terminate, responding to events indefinitely. For reactive plans, the net can contain loops or a state where it waits for recurring events. For example, a reactive plan might “listen” for an event (like a sensor reading or user action) and perform some step each time it occurs, possibly looping back to wait again. The plan execution engine will handle these two modes differently (discussed below): an acyclic plan instance is completed once it reaches a terminal event marking, whereas a reactive plan remains active, potentially regenerating tokens for initial places or never reaching a final absorption state.

* **Example:** The sample below shows a simple acyclic plan with one step: it waits on event `start`, performs action `send_email`, and emits event `done` on completion. In Petri net terms, `start` is the input place (with an initial token to kick off), `first` is the transition firing to send the email, and `done` is the output place marking completion.

```json
{
  "plan_name": "sample",
  "graph_type": "acyclic",
  "events": {"start": {}, "done": {}},
  "steps": {
    "first": {
      "on": ["start"],
      "action": "send_email",
      "args": {"to": "a@example.com", "subject": "Hi", "body": "Test"},
      "emits": ["done"]
    }
  }
}
```

All plans must conform to the JSON schema (automatically derived from the PlanModel) – this schema is provided to the LLM and used for validation. This ensures plans have the correct structure and required fields before execution.

## Core Execution Engine Architecture

The Plan Execution Engine is the runtime kernel that interprets the plan (Petri net) and drives the actual workflow by dispatching actions and monitoring events. It works closely with the OS’s **Event Bus** to receive and emit events, ensuring **everything is event-driven** per the system design principles. The execution engine’s architecture can be viewed in several sub-components:

### 1. Petri Net State Model

At the heart, the engine maintains an internal representation of the plan as a Petri net graph:

* **Places (Events):** Each defined event in the plan is a place that can hold tokens. At runtime, a token in a place represents an occurrence of that event (including relevant data payload). For example, when an external trigger event arrives (say, an email received), a token is placed in the corresponding event place for any active plan that is waiting for it.
* **Tokens:** Tokens are colored with at least an *event payload* (the event object or data) and possibly a *channel reference* if relevant. The engine doesn’t distinguish between external vs. internal events – both are tokens on places. However, tokens may be flagged with their category (Input, Internal, Output) as per the event spec for logging and permission purposes.
* **Transitions (Steps):** Each step defines input arcs from its `on` events and output arcs to its `emits` events. The engine will track which transitions are **enabled**: a transition is enabled when all its input places have at least one token that meets the guard condition. If multiple tokens are needed (one from each of multiple places), the engine conceptually pairs them (e.g. matching by token attributes if guard logic requires specific combinations) and then fires the transition. If a step has a guard, the guard is evaluated against the candidate tokens (and possibly external context) to decide if it can fire.

The engine’s state can be thought of as the marking of this Petri net – i.e., the set of tokens present in each place at a given time. The Plan Execution Engine will likely maintain this marking in memory for each active plan instance, updating it as events occur and steps fire. For reliability, the marking may also be periodically checkpointed to persistent storage (Cosmos DB or the Context Hub) so that the execution can recover from crashes or be handed off to another node (see High Availability).

### 2. Execution Algorithm

The basic execution loop for an active plan instance is:

1. **Initialize:** When a plan is started, its initial events are seeded with tokens. For an ad-hoc one-off plan, this might mean placing a token in a special `"start"` event place to kick off the flow. If the plan was triggered by an external event (e.g. a user instruction or sensor input), that event token is placed into the corresponding place. For reactive plans, initial places might be empty until something happens.
2. **Enable Transitions:** The engine evaluates all steps to see which are enabled given the current tokens. Any step whose all `on` events have tokens (and whose guard, if any, evaluates true) becomes enabled.
3. **Fire Transitions:** When a step fires, it means the associated action is executed. The engine will *consume* the required input tokens (or mark them as used for that instance of firing) and then dispatch the step’s action for execution. Importantly, the dispatch is done via the event bus or driver interfaces – rather than executing inline, the engine typically **emits an action event** to let the appropriate driver or service handle it (see External Tool Interfacing below). In Petri net terms, the transition produces its output tokens immediately upon firing; in our implementation, we may optimistically emit the intended output events or wait for the action to complete.
4. **Emit Events (Produce Tokens):** Once the step’s action is completed or at least triggered, the engine will produce tokens for each event listed in the step’s `emits`. These tokens are placed on the respective places, often carrying data returned by the action. For example, if a step emits a `"file.saved"` event after writing to disk, the file metadata might be attached to that token. Emitting an event also means broadcasting it on the Event Bus so that other system components (or other plans) are notified of it as a global event. After emitting, those events may immediately enable downstream steps in the same plan or even trigger entirely separate automation.
5. **Iterate:** The engine then repeats the cycle: check which new transitions are enabled by the updated marking, fire them, and so on.

This cycle continues until the plan completes or (for reactive plans) until it is explicitly stopped. An **acyclic plan** completes when there are no enabled transitions and no pending events – typically when it reaches some designated final event (e.g., a `"done"` token is produced and no further steps consume it). A **reactive plan** is expected to idle in a waiting state for new external events even after some steps have fired; it does not terminate on its own as long as it’s needed. The engine will keep the plan’s state alive, possibly with tokens in places that represent waiting subscriptions, until a termination condition or command is given.

**Channel passing realization:** When a transition needs to create a new communication channel to a sub-process, the engine can generate a unique event name or token identifier to represent that channel. For instance, a step might emit an event `task.response` with a payload containing `task_id: 12345`. The `task_id` serves as a channel identifier for that specific task’s response. Another step in the plan could have `on: ["task.response"]` with a guard ensuring the `task_id` matches 12345, effectively linking that particular response to the waiting step. This pattern – emitting an event with an ID and guarding a subsequent step on that ID – is how we implement dynamic channel passing using colored tokens. The engine will provide helper mechanisms to simplify this (e.g., generating unique IDs and mapping them). From the Petri net perspective, the place `task.response` can hold tokens from many tasks, each with a different ID color; the guard on the transition ensures the step “listens” to the correct one. This achieves one-to-one channel communication on top of a broadcast event system.

### 3. Integration with Event Bus & Drivers

All plan execution is tightly integrated with the **Event Bus** (the global publish/subscribe system of the OS). The Event Bus is the medium through which:

* External triggers arrive (as events that might start or continue a plan).
* Internal plan actions are dispatched (as events targeted to capability drivers).
* Plan-emitted events are published (so other system parts or even other plans can respond).

The Plan Engine will interface with the Event Bus in two ways:

* **Event Subscription:** The engine (or an associated Orchestrator) subscribes to events that are relevant to active plans. This can be done by registering filters with the Event Bus (e.g., “subscribe me to any events of type X for user Y”). When a new external event comes in (from user input, sensors, etc.), the Event Bus passes it to the Plan Engine *before* or alongside other drivers. The engine checks if this event corresponds to any place in any active plan’s marking. If yes, it creates a token and updates the plan state, potentially enabling transitions. For efficiency, the engine may maintain an index of “which event types are awaited by which active plans” to quickly route incoming events to the right plan instances.
* **Event Emission:** When the engine decides to fire a transition (step), instead of executing the action logic directly, it typically emits a new event representing the request to perform that action. For example, if a step is `"send_email"` with certain args, the engine will create an `EmailEvent` (an event object) for sending email and dispatch it via the Event Bus (possibly tagging it as an internal event). The system’s **EmailConnectorDriver** is subscribed to such events (it has capabilities for `"email.send"` and will pick up the event) and will carry out the actual email sending. This design maintains a separation between the *planning kernel* and the *actual effectful operations*, which are handled by drivers with appropriate permissions and context. After the driver (tool) completes its task, it may emit a follow-up event (e.g., an `"email.sent"` confirmation event) back onto the bus. The Plan Engine, by virtue of subscribing to internal events, will receive that `"email.sent"` event as well – if the plan had a place for it (say the step emitted `"done"` which corresponds to some event that the driver translates to), it will place a token and continue the plan. In many cases, the plan might consider the action done immediately upon dispatch (fire-and-forget), especially if the tool is asynchronous. In other cases, we might model the completion as a separate event to explicitly wait for (especially if the action can fail or has a delay).

**Tool/Action dispatching:** Not all actions may require heavy lifting by external drivers. Some might be *internal functions* (type `"native"`) that can be executed directly by the planner. The Tool Registry indicates which tools are native vs. external. For native actions (for instance, a context query like `"context_read"`), the Plan Engine could directly call the function handler (which might be a simple Python call into the Context Hub driver) instead of emitting an event. However, even native actions can be treated as events and handled by a specific in-process driver to keep a uniform asynchronous model. The design leans towards emitting events for all actions for consistency – the “drivers” may be implemented as async functions in-process or as separate services, but from the Plan Engine’s perspective it just publishes requests and later receives results.

**Concurrency:** The event-driven approach naturally allows concurrency. If multiple transitions become enabled from distinct events, the engine can fire them in parallel (subject to resource limits). Each fired transition results in events being emitted which drivers handle concurrently (e.g., one step might be sending an email while another step is querying a web API at the same time). The engine needs to guard shared resources and consider race conditions – e.g., if two transitions both consume the same event token, we must decide if the token is *consumable only once* (usual Petri net semantics) or if the event acts more like a broadcast (one occurrence triggers multiple steps). By default, we treat events as consumable (each token should be used by one transition occurrence and then marked or removed). If multiple steps list the same event in `on`, then multiple tokens (separate event occurrences) would be needed to trigger each; or we can model a single event triggering multiple transitions by conceptually cloning the token (this can be achieved by having the event place produce multiple identical tokens for a broadcast, or by special-case logic). This detail will be addressed in implementation by either duplicating events to all interested steps (broadcast mode for certain internal signals) or requiring plans to explicitly model such forks (e.g., one step consumes and then emits a follow-on event that triggers others).

### 4. Workflow Lifecycle and State

The Plan Engine manages the **lifecycle of a plan** from creation to completion:

* **Plan Creation:** via LLM (or static library) – results in a plan JSON which is stored (e.g., in Cosmos DB) and optionally immediately executed. The creation process is described in the LLM integration section. Created plans are saved as templates (status `"template"`) so they can be audited or reused.
* **Plan Activation:** To run a plan, either a user triggers it (e.g., by selecting it) or an instruction rule starts it in response to an event. Activation involves instantiating the plan’s data structure in the engine, setting initial tokens, and possibly launching an orchestration context (for distributed execution, see below). We may assign a unique *Plan Instance ID* (different from the template ID) if the same plan can run multiple times concurrently.
* **Execution & Monitoring:** As described, the engine drives the plan via events. During execution, the plan instance’s state (tokens marking) can be made **observable**. We will expose read-only views of active steps and waiting events for debugging or UI. This could be done by logging state changes or by writing state snapshots to the Context Hub (e.g., updating a “/system/running\_plans/{id}” document with current step statuses). A specialized **TaskMonitorDriver** can listen to task events and update status logs. For instance, each transition firing could emit an internal `"plan.step.started"` and `"plan.step.finished"` event with metadata (step name, success/failure, timestamps), which the TaskMonitorDriver or similar component records for observability.
* **Completion:** When an acyclic plan finishes, the engine will mark it as completed (and possibly update its record in storage with status `"completed"` or archive the history). Any tokens left might be cleaned up. For reactive plans, completion might be manual or conditional; the engine might provide an API to deactivate a plan (removing its subscriptions and state) or a plan may self-terminate if it has a special event that triggers a shutdown (for example, an “off” event loop). On completion, a summary event like `"plan.completed"` (with outcome info) could be emitted, allowing other components (or even the LLM) to introspect results.

**Error handling:** If a step’s action fails (e.g., the email driver raises an exception or returns a failure event), the engine should handle this gracefully. We plan to incorporate **error events** and fallback transitions. For instance, drivers already emit `"email.send.failed"` on failure. The plan can include steps that listen for such failure events to implement retries or alternative paths. If an unexpected error occurs (no explicit event), the engine can catch it and emit a generic `"plan.step.error"` event with details. An LLM-based **repair loop** (see below) may subscribe to these to dynamically modify or restart the plan. The engine should ensure one failing step doesn’t crash the whole plan unless it’s unrecoverable – instead, it should either trigger error-handling steps or pause the plan and await further instructions.

## LLM Integration: Planning, Validation, Repair, Introspection

Large Language Models are central to making the planning system intelligent and adaptive. The design incorporates LLMs at multiple points in the plan’s lifecycle:

### 1. Plan Generation (Planning Phase)

When a user issues a high-level instruction (e.g., “Organize my meetings and notify the team”), the **Planner LLM** translates it into a structured plan (the JSON described above). We use a function-calling approach with GPT-4 (or similar) to ensure the output adheres to the plan schema. In code, `call_planner_llm()` orchestrates this by providing a specialized system prompt and a list of available tools/actions. The LLM is given: (a) the plan JSON schema, and (b) a serialized **Tool Registry subset** describing actions it can use (with descriptions and argument formats). The model then responds with a `create_plan` function call containing `plan_json`. The planner code runs a **critic loop**: it validates the JSON and if parsing fails or the model doesn’t use the function correctly, it gives feedback (as a system message “CRITIC: ...”) and retries. This loop continues until a syntactically valid plan JSON is produced or a max retry is hit. The result is a candidate plan.

**Plan semantic validation:** After generation, the plan is validated both by machine and (optionally) by the LLM:

* The system performs JSON Schema validation and Petri net checks (e.g., ensuring an acyclic plan has no cycles) immediately. If these fail, it’s a hard error – the plan is rejected and the planner could be re-invoked or the user notified.
* We will integrate an **LLM Critic** stage that goes beyond syntax. We can prompt a second LLM pass (or the same model in a new conversation) to review the plan’s logic against the instruction. For instance, we might feed: “Instruction: ... Plan: ... Critique if this plan might not achieve the goal or violates any constraints.” The LLM can highlight logical gaps or risky steps. This is not yet implemented in code but is planned to bolster trust in the AI’s plans. If the critic LLM identifies issues, we could either automatically adjust the plan or have it propose a corrected plan JSON (possibly using function-calling again, e.g., a `modify_plan` function). This step uses the LLM’s reasoning ability to catch things like “The plan didn’t include notifying the team as requested” or “This plan might loop indefinitely”.

Only once a plan passes validation, it is saved (persisted) via the `PlanStore` (in Cosmos DB) with status `template` and then moved to execution if appropriate. The generation process is typically user-initiated (or system-initiated for complex tasks) and is relatively quick (a few GPT calls). We will add caching and reuse of common plans – if a similar instruction was given before, the system might retrieve a stored plan rather than always calling the LLM.

### 2. Plan Execution with LLM Oversight

During execution, LLMs can play a role in **monitoring and adapting** the workflow:

* **Validation at runtime:** If certain decisions in the plan were left implicit, an LLM could be consulted. For example, a step might be “summarize recent emails” without a specified timeframe; the engine could query an LLM to decide how many emails or which date range is relevant, unless the plan explicitly fixed it. However, our plan representation aims to be fully specified. So runtime LLM intervention would more likely be in interpreting vague guard conditions or generating content (like the actual summary text via an LLM call tool). In those cases, the LLM is used as a tool *within* the plan rather than controlling the plan. We will ensure any such usage is via proper tool interfaces (like calling an LLM model function in a step).
* **Progress validation:** We could use an LLM to periodically assess if the plan is on track. For instance, after each major step, we might have a hidden step that asks “Given the goal and what’s done so far, does the plan still make sense to continue?” If the LLM says no (perhaps new context has emerged that invalidates the plan), the system could pause and re-plan.
* **Policy compliance:** An LLM could also double-check steps against policies (though a rule-based policy engine exists). For instance, if a plan step says “send all my data to an external API,” a policy might flag it. Where policies are declarative, they’ll be enforced by the Security Manager. But we might also have an LLM-based policy agent that inspects the plan and warns about potential violations in natural language, augmenting security.

### 3. Dynamic Repair and Replanning

Perhaps the most powerful use of LLMs is in **repairing or adapting plans** on the fly. This addresses cases where:

* The environment changes mid-plan (new events or context changes make the current plan suboptimal).
* A step fails in an unforeseen way (an API is down, a meeting cannot be scheduled as planned, etc.).
* The LLM’s initial plan had a logical flaw that only becomes apparent at runtime.

When such situations occur, the system can invoke a **Repair LLM** routine. This would involve providing the LLM with:

* The original instruction and plan.
* The point of failure or change (e.g., “Step X failed with error Y” or “Requirement Z has changed”).
* Possibly the partial execution log or current state (which steps succeeded, which events are in the marking). We could serialize this as JSON or text.

The LLM would then be asked to propose modifications: e.g., “Suggest how to adjust the plan to handle this.” Ideally, we again use a structured output like a diff or a new plan JSON. However, dynamic changes might be smaller in scope, so a diff or description might need to be interpreted by our system. A safer approach is to have the LLM produce a revised plan JSON (maybe with the same plan\_id or a new id for a new plan) which the engine can then switch to. We would validate the new plan (especially if it introduces new events or steps mid-flight).

In practice, implementing repair could mean:

* If a step fails and the plan has no pre-defined recovery path, pause the plan.
* Call the repair LLM for guidance. If it returns a new plan or instructions, either modify the current plan’s structure in memory (if feasible) or abort and start a new plan instance that continues the task.
* For example, if step “Translate document with API\_A” fails because API\_A is down, the LLM might suggest “try API\_B or delay and retry later.” The system could then either modify the action of that step to API\_B and re-run it, or insert a new step before it to handle the delay.

This is complex to automate fully, so initially we might handle repairs in a semi-automatic way: log the failure, notify a human or a higher-level agent (which could itself be an LLM-based agent) that can replan. As the system matures, closed-loop self-repair via LLM will be more feasible.

### 4. Introspection and Learning

Finally, LLMs can be used for **introspection** – analyzing plans and executions to improve the system over time:

* **Plan Explanation:** We can prompt an LLM to **explain the plan** in plain language for the user or developers. Given the JSON, it can generate a summary like “This plan will first do X, then if Y happens it will do Z...”. This helps in transparency. A function to produce such explanations from plan JSON can be built (either via template or LLM).

* **Execution Summaries:** After a plan (or a period of a reactive plan) completes, an LLM can summarize what was achieved, any problems encountered, and suggest optimizations. This summary can be stored in the Context Hub as a chronicle of what the AI OS did – useful for user trust and auditing.

* **Learning new patterns:** By introspecting many executions, the system can have the LLM suggest new reusable subroutines or better plans. For example, if the LLM notices that every time a meeting is scheduled the plan does A, B, C, it might abstract that as a reusable sub-plan or add a rule for next time. This borders on meta-learning and is a future enhancement.

* **Introspective debugging:** During development, developers can use an LLM to analyze a stuck plan. By feeding the current marking and last few events, a GPT-4-based “debugger” might hypothesize why no transition is firing (“It looks like step2 is waiting for event ‘confirm’ which never gets emitted – likely a logic bug.”). This can speed up development and testing.

Throughout these roles, LLMs act as **advisors and synthesizers** around the core deterministic engine. We maintain a clear boundary: the Petri net execution is the source of truth for what actions happen and when, ensuring reliability and predictability, while the LLM provides flexibility in generating and modifying those nets in response to high-level goals or unexpected situations.

## Distributed & Scalable Execution Architecture (Azure Deployment)

The planning kernel will be deployed in a **cloud-native** fashion on Azure for scalability and resilience. The design builds on the existing Vextir OS cloud architecture, which uses Azure Functions, Cosmos DB, and Service Bus, aligning with the event-driven approach. Key elements of the distributed design are:

### 1. Event-Driven Orchestration with Azure Service Bus

All events, whether external (input) or internal, flow through Azure Service Bus queues or topics. The **Universal Event Processor** is an Azure Function (or set of functions) subscribed to the main event queue. This function acts as a **router and orchestrator**:

* It receives an event message and deserializes it into an `Event` object (with type, user\_id, payload, etc.).
* It looks up which driver(s) should handle it. This is done via a capability registry or simple mapping (for instance, events of category “instruction” go to InstructionEngineDriver, events of type “email.\*” go to EmailConnectorDriver, etc.). The drivers are Python classes already loaded in the function app, each registered via decorators.
* The Processor invokes the driver’s `handle_event` method, passing the event. The driver runs (possibly performing I/O or calling other services) and returns a list of resulting events.
* The Processor then **emits those resulting events** onto the Service Bus, so they can be picked up either by other drivers or by the Plan Execution Engine (if those events correspond to steps in an active plan).

In the new design, the Plan Execution Engine itself can be conceptualized as a special “driver” or orchestrator within this Azure Function. There are two possible approaches:

**Approach A: Orchestrator inside Universal Processor** – We extend the Universal Event Processor logic to incorporate plan execution:

* The InstructionEngineDriver (or a new **PlanOrchestrator** component) intercepts events and checks user-defined instructions *and* active plans. For example, when an event arrives, InstructionEngineDriver might first check “Does this event match a user’s static automation rule?” and execute that logic. Then, it would check “Is this event one of the events awaited by any active plan for this user?”. If yes, it calls into the Plan Execution Engine to handle that token.
* Conversely, when the Plan Engine wants to dispatch an action, it could do so by simply returning a new Event from the `handle_event` call. For instance, if an event triggers a plan step that is `send_email`, the Plan Engine (integrated in the driver) will create an `EmailEvent` and include it in the `output_events` list. The Universal Processor then pushes that onto Service Bus, and eventually the EmailConnectorDriver will pick it up (possibly in the same function invocation or a subsequent one).
* In this approach, a lot of coordination happens within a single Azure Function invocation: one event comes in, triggers possibly multiple plan steps and driver calls, produces multiple outgoing events. We have to be careful to not exceed Azure Function execution time limits, especially if a plan involves many steps or waits. Likely, long waits (like for external input) would break out of a single invocation – see Durable below.

**Approach B: Durable Functions Orchestration** – We leverage Azure Durable Functions (stateful workflows) for each plan instance:

* When a plan is started, we initiate a **Durable Orchestration** (say `PlanExecutorOrchestrator`) with the plan ID. This orchestration runs asynchronously and can maintain state between events.
* The orchestration will wait for external events using Durable’s `WaitForExternalEvent` mechanism. Essentially, when an event relevant to the plan arrives, the Universal Processor (or a binding) signals the orchestrator with that event data. The orchestrator then wakes, updates its local marking, fires any enabled transitions (which might call Durable Activity Functions to perform actions or simply send events).
* Durable Functions provide reliability: the state (marking) is checkpointed to Azure Storage, so if the function app recycles or there’s a failover, the orchestration can resume. Also, it natively supports **timers** – which is useful for implementing time-based triggers (the orchestrator can sleep until a certain time and then generate a timer event).
* The downside is complexity in integrating Durable with our existing event bus: we’d need a mechanism to route events to the correct orchestrator instance. This can be done by using the plan instance ID as a correlation key. For example, when the Plan Engine starts an orchestrator, it might store a mapping (in Cosmos or memory) of “event types -> orchestrator instance” for that plan. More directly, the orchestrator can be configured to listen for events of a specific name like `"plan.{id}.eventname"` and the Plan Engine/InstructionEngine would wrap or copy incoming events to that specific event name to wake the orchestrator.
* Activities within the orchestrator can call out to drivers or external APIs. One model is to still use the event bus: instead of the orchestrator directly calling an API (which could block), it could send an event to Service Bus and then wait for the corresponding response event. However, Durable Functions also allow making direct calls (like an Activity function that invokes a driver code directly). We can mix: use direct calls for short actions (e.g., do a quick context read) and use the event bus for longer or asynchronous actions (like sending an email and waiting for confirmation).

A possible middle ground is to implement the Plan Engine with its own async loop and state storage in Cosmos, without using Durable. However, Durable Functions align well with our need for long-lived workflows that survive restarts, so we lean towards using it for plan instances, especially reactive ones that run indefinitely.

### 2. Scaling Out with Azure Components

**Azure Service Bus Topics & Queues:** We can partition events by function or user to improve throughput. For example, use one **topic** for all events and subscription filters for certain categories. The Universal Processor can then scale out (multiple instances consuming in parallel). Azure Functions can auto-scale based on queue length, so if many events come in, multiple function instances will handle them concurrently. We must ensure ordering for a single plan’s events – if needed, we could use Session-enabled queues with session ID = plan\_id or user\_id to guarantee events for one plan are processed sequentially by the same instance. Alternatively, orchestrators inherently serialize their own events.

**Azure Cosmos DB:** Cosmos serves as our persistent store for plans (templates and possibly runtime state). Each plan template is stored with a user partition key, enabling quick lookup of all plans/instructions for a given user. We may also store **active plan instances** in a separate container or the same one with a different status. This record can hold the current marking (serialized list of tokens or just which steps completed), the last update timestamp, and any result data. If we don’t use Durable Functions, this is crucial for resuming a plan on a different machine after a crash. If we do use Durable, Azure’s storage will keep state, but we might still mirror some info to Cosmos for external visibility (like the UI could read Cosmos to see running workflows).

**Azure Event Hub (optional):** For very high volume of events (especially sensor or IoT data for reactive flows), we might incorporate Event Hubs as an ingestion front-end. The Event Hub consumer would then translate messages to Service Bus events or call the Universal Processor. Given our design, Service Bus might suffice, but it’s worth noting for future scaling (Event Hubs can feed a stream processing job if needed for analytics on events).

**Azure Container Instances / Kubernetes:** Some workflow steps might involve heavy computations or specialized operations that are best run in isolated containers. The planning system can interface with Azure Container Instances (ACI) or Azure Kubernetes Service (AKS) by using drivers that manage containers. For example, if an action is labeled as requiring an isolated environment (maybe running untrusted code or a large ML model), the Plan Engine’s dispatch will call a driver that spins up an ACI container with the task, then emits an event when done. The architecture supports this by design – the driver just needs to handle the lifecycle (which can be done asynchronously, with events for container start and finish).

**Azure Durable Entities:** Another Azure primitive we might consider is Durable Entities (actors). We could model each running plan as a Durable Entity with methods like `ReceiveEvent(event)` and `GetState()`. Entities are less linear than orchestrations and can respond to events one at a time. This could simplify event routing (each event goes to a specific entity based on plan\_id). The entity internally can implement the Petri net enabling logic. However, Durable Entities in Python are not as mature, and orchestrations might suffice.

**Security & Isolation:** Each step that calls a tool will go through the **Security Manager** checks (ensuring the user/agent has permission for that action). In a distributed environment, we enforce this at the entry to any driver or external call. Azure Entra ID (AD) integration ensures tokens are verified for API calls, and any secrets needed (API keys, OAuth tokens) are stored securely (Key Vault or Cosmos) and accessed by drivers at runtime.

**High Availability:** To achieve HA, we run multiple instances of the Universal Event Processor function (as allowed by Azure’s consumption or premium plan). If one instance goes down, others continue processing new events. For plan state continuity, either Durable Functions or Cosmos-stored state allows another instance to pick up where it left off. For example, if using Cosmos, on startup the Plan Engine could scan for any active plans that haven’t reported activity in a while and reinitialize them (this is tricky, but could be done by a heartbeat mechanism where active instances mark their plans periodically; lack of heartbeat triggers a takeover). Using Durable orchestrations automatically handles failover at the function runtime level.

**Throughput and Latency:** The target is to keep event processing latency low (< 2s per event as per product spec). The design ensures that most work is done asynchronously: an event comes in, triggers at most some state updates and emissions, and the heavy operations (like calling an external API or LLM) happen outside the central loop (in drivers or as separate function calls). This prevents the orchestrator from becoming a bottleneck. If needed, we can offload LLM calls to a separate queue or use Azure Functions with GPU backing for model calls, etc. Also, by having a single unified event pipeline, caching and rate limiting can be centralized (for example, an LLM call driver can implement a cache so repeated identical requests within a short time are not recomputed).

### 3. Incorporating the Temporal Scheduler

Time-based triggers are handled by a **SchedulerDriver** (replacing the old Scheduler function). This driver likely uses Azure Durable Timers or Azure Scheduler under the hood. When a plan requires a timed event (say “execute step X at 5pm” or “every hour do Y”), there are two approaches:

* **Explicit scheduling via driver:** The plan can call an action like `"schedule_action"` (as hinted in InstructionEngineDriver code for action\_type == "schedule\_action"). The `schedule_action` could take a config with a time or cron, and the driver will schedule an event for that time (e.g., by creating a timer trigger or using Azure Scheduler). When that time hits, a new event (e.g., `"timer.fired"`) will be emitted into the system, which the plan can listen for. This approach externalizes scheduling to the existing scheduler component.
* **Internal wait (Durable orchestrator):** If using Durable orchestrations for a plan, the orchestrator can simply call `context.create_timer(future_time)` to pause until the time and then resume, effectively generating a timer event internally. That resume can then directly fire the subsequent step. In this case, the step waiting on a time doesn’t even need an external event name – the waiting is handled in the orchestrator logic. However, mixing this with external event-driven steps requires careful design. We might mix models: orchestrator for sequential logic, event bus for external interrupts.

Our design will favor using the **SchedulerDriver approach** for consistency, as it keeps all triggers as first-class events. For example, to support a time trigger in a plan JSON, we could allow a step to specify `on: ["<ISO timestamp>"]` or a special syntax, but better is to have the plan invoke a scheduling action. Concretely: a step could be “Schedule reminder” which emits a `"reminder.due"` event via the scheduler driver after a delay. The next step in the plan would list `"reminder.due"` in its `on`, causing it to execute at the right time. This way, time-based events flow through the same mechanism as others. The SchedulerDriver is designed to handle recurring schedules with cron expressions as well, so a reactive plan that needs a periodic tick can schedule itself a periodic event.

### 4. Containerization & Deployment

We will containerize the core components for flexibility. The drivers and planner kernel (Lightning) can run inside an Azure Container Instance or Kubernetes pod for more fine-grained scaling (especially for stateful long-running tasks). However, since much of our logic is in Azure Functions (which can also run in a container in premium plan), we might not need separate containers unless we have special runtime requirements (like using a custom GPU image for LLM calls).

For now, deployment will be:

* Azure Function App for the **Universal Event Processor**, containing the Lightning Planner and all drivers in one codebase (as is currently the case, with one entry function and drivers registered at import time).
* Azure Cosmos DB for persistent storage (plans, context, etc.).
* Azure Service Bus for messaging.
* Optionally, Azure Event Hub or Storage Queues for other triggers (if high-frequency data needs separate handling).
* Azure Monitoring (App Insights) to gather logs from the function (we’ll instrument events like plan start/stop, step times, LLM usage etc. for metrics).

## External Tool and Service Interfacing

The kernel itself does not implement external operations; it **delegates to tools and drivers**, which constitute the Capability Mesh of the OS. In this design:

* **Tool/Driver Registry:** We maintain a registry of available tools (as JSON or code), mapping action names to either native handlers or external services. For instance, `send_email` is linked to the EmailConnector (which expects certain args), `read_email` might map to a context retrieval or email fetching action, `post_teams` to a Teams webhook driver, etc. This registry is not only used by the LLM to plan but also by the Plan Engine to dispatch actions.

* **Drivers as Executors:** Each driver class (AgentDriver, ToolDriver, IODriver, etc.) encapsulates the logic for performing a set of actions. The Plan Engine doesn’t need to know the details – it just emits an event. For example, an action `send_email` might result in creating an `EmailEvent(type="email.send")` with all necessary fields (recipient, body, etc.). The EmailConnectorDriver’s `handle_event` sees this event and executes sending via SMTP or API. Similarly, a `web_search` action might forward to an MCP (Micro-Compute Process) server via HTTP – the Plan Engine would emit an event or call a driver that wraps the HTTP call.

* **Synchronous vs Asynchronous Tools:** Some tools may return results immediately (within the same function call). For example, a `string_manipulation` tool or a `math.calculate` might be pure functions. We can implement these as **synchronous native drivers** that directly return an output event. E.g., a `MathDriver` could handle events of type `"calc.evaluate"` and return an event `"calc.result"` with the answer. In such cases, the Plan Engine could optimize by calling the function directly. But to keep the design uniform, it might still go through the event bus (the event bus could short-circuit delivery to a local handler if it’s in-process).

* **Long-running external tasks:** If an action involves waiting (e.g., waiting for a human to respond, or a training job to finish), the plan should be structured to handle that asynchronously. That is, the step that initiates the task emits a *start* event and the completion of that task comes as a *different* event which another step listens for. This is inherently supported by our Petri net model (transition for start, transition for finish). The drivers are responsible for emitting the completion events when ready. For example, a `StartVM` driver might emit `vm.started` immediately if fast, or schedule a check and later emit `vm.ready`. The plan can have steps accordingly.

* **Observability of external calls:** Each driver should log its activity and optionally send progress events. Our plan execution logging (via TaskMonitor) will include calls out to external services. This means if a step calls an LLM API via a driver, we’d log token usage, cost, etc., and possibly adjust the plan if a budget policy is violated (the Security Manager can block expensive calls beyond a threshold).

* **Interfacing with the Context Hub:** Many plans will involve reading or writing to the persistent context (CR-SQLite database). We have native functions or drivers for that (`context_read`, `context_write`). These can be executed as part of a plan to fetch needed data or store results. The Plan Engine might call them directly (since they are likely local calls to the Rust context service) or emit an event that the ContextHubDriver picks up. Given the context is fundamental, a slight optimization is acceptable (e.g., a Python binding to call context read directly). But consistency and auditing are improved if we route through events (so every context modification is an event in the log). We will design the drivers such that even internal calls generate events like `"context.updated"` for transparency.

In summary, the Plan Engine will act as a **conductor**, and the drivers/tools are the orchestra performers doing the real work. This separation ensures that adding a new integration or tool doesn’t require altering the planner logic – we just register a new action and provide its implementation in a driver. The LLM can then start using it in plans (once included in the AVAILABLE\_TOOLS prompt), and the plan executor will handle it like any other action event. This modularity and unified driver interface greatly enhance extensibility.

## State Management and Observability

Visibility into the workflow engine’s state is crucial for debugging, user trust, and high availability. The design will include:

* **Plan State Introspection:** We will provide APIs or commands to query the state of an active plan. This could be an admin command or part of the UI where a user sees their ongoing automations. The query would return which steps have fired, which events have been seen/emitted, and which steps are currently waiting (and on which events). Because the plan state (marking) might be distributed (especially if using orchestrator functions), we will maintain a representation in Cosmos or memory that can be queried. If using Durable, we might expose the state via a Durable Entity or via periodic progress events. We might also maintain a *shadow state* in the Context Hub, e.g., a JSON in a known context location that is updated as the plan executes. This can be very useful: agents or users could inspect that context to see progress.

* **Logging and Audit Trails:** Each step execution and important decision will be logged. The logs include timestamps, responsible component, and any outputs. For instance, when an LLM plan is created, we log the prompt and result (with PII protections); when a transition fires, we log “Plan X: Step Y executed, emitted events Z”. Azure Application Insights or Logging can be used to aggregate these logs. For audit, we’ll ensure all external actions (tool calls, data access) are recorded, satisfying the Policy Firewall requirement.

* **Metrics:** We will gather metrics like the number of active plans, steps per plan, average execution time, error rates, LLM token usage per plan, etc. This helps in scaling decisions and performance tuning.

* **High-Level Monitoring:** A possible addition is a **Plan Visualizer** – a component that can render the Petri net diagram of a plan and highlight which places have tokens currently. This can be built by using the plan JSON and overlaying the marking. It’s a development tool but could be extended for users to understand complex workflows.

* **State Checkpointing:** For high availability and debugging, after each step (or each set of concurrently fired steps) the Plan Engine can checkpoint state. If using Durable, this is automatic. If not, we could, for example, update the Cosmos plan record’s status to include “last\_step\_executed” or push an event to an “event history” container. Checkpointing helps in recovery – if the engine crashes after emitting an event but before processing the next, the system on restart can detect incomplete plan instance and decide how to proceed (perhaps by looking at event history and inferring the next needed events). We plan to assign each plan execution an ID and possibly tag all events related to that execution with this ID (for correlation). The Context Hub could also store these IDs for cross-reference, tying plan operations to context changes for a holistic picture.

In essence, we aim for the execution engine to be **observable like a black-box process**: one should be able to observe inputs (trigger events), internal state transitions (places & tokens), and outputs (action events and final outcomes) in a structured way. This not only aids trust and debugging but also allows future ML analysis on logs to further improve plan suggestions.

## Supporting Time Triggers, Reactive Plans, and Cycles

Supporting **time-based triggers** and **reactive (cyclic) workflows** requires careful consideration in both the plan model and execution:

* **Time-based triggers:** As discussed, the primary mechanism will be scheduling events in the future. This preserves the event-driven paradigm. If a plan needs to wait or repeat at intervals, it will incorporate scheduled events. For example, to implement “do X every day at 9 AM,” the plan could either be a reactive one that re-emits a “self-trigger” event every day, or more simply, we rely on the SchedulerDriver to emit an event daily that starts the plan’s step. Another approach for repeating tasks is not to keep the plan alive, but to store it as a template and have the scheduler create a new plan instance each day – however, that loses continuity if the plan accumulates state. So for continuous stateful jobs (like “monitor this sensor and alert on anomaly”), a reactive plan that stays active and uses a loop (or waits on an event repeatedly) is appropriate. We already allow `graph_type: "reactive"` to denote such plans.

* **Reactive plan execution:** In a reactive plan, after firing a transition, tokens might not be “consumed” in the permanent sense. We might choose to **leave tokens in places** to await the next event. Alternatively, the transitions might immediately re-place tokens back in some initial place to form a loop. Consider a simple loop: event A triggers step1 which emits event B, and step2 listens on B and emits A (closing the cycle). If it’s reactive, this can cycle indefinitely as events keep generating each other (with perhaps some external influence breaking the loop). We have to implement safeguards: e.g., a maximum iteration count or time for such loops to avoid runaway. Guards can also be used to break loops (like a guard that checks a condition and if false, stops emitting the event that continues the loop).

Reactive plans also often need to handle **multiple concurrent instances of the cycle** (like if events come in faster than the loop completes, do we queue them or handle concurrently?). A colored token approach helps here: each token can carry an instance ID. If we want to only allow one instance at a time, we might have a place that can only hold one token (a capacity constraint – not in basic Petri nets but we could enforce it). If multiple are allowed, the net can have multiple tokens and multiple concurrent firings of transitions, effectively handling events in parallel.

* **Differentiating acyclic vs reactive in execution:** For acyclic plans, the engine can automatically mark them complete when done and free resources. For reactive, we likely keep them registered indefinitely. Perhaps we’ll introduce a mechanism to **auto-disable** a reactive plan after some period of inactivity (to reclaim resources if no events for a long time). The plan definition might include an expiration or the user might manually stop it.

* **Examples:** A reactive plan example could be an email monitoring workflow: whenever a new email arrives (event `email.received`), if it meets criteria, do something (e.g., send auto-reply, update context). This can be expressed as a plan where `email.received` is an event that triggers steps, and one of the steps might again wait for `email.received` (loop back) or simply not consume the token in a way that removes the subscription. In practice, the InstructionEngine currently handles such rules without a complex plan – but we could express complex reactive behaviors (like “if 3 emails from boss arrive within an hour, do X” requiring counting, which a Petri net could model with places holding multiple tokens).

To implement counting or time windows, we might extend the plan language (e.g., an event place could have a capacity or a time decay on tokens). Those are advanced features that can be considered later. Initially, reactive will mean “we allow cycles and repeated event consumption” and rely on the plan logic to not deadlock or explode – which should be validated (boundedness checks are noted as a placeholder in code).

## High Availability and Fault Tolerance

We’ve touched on HA in the context of Azure scaling, but to summarize the strategies:

* **Stateless compute, stateful store:** Wherever possible, the compute nodes (Azure Function instances) are kept stateless between invocations, relying on external state (Cosmos, Durable, etc.) to recover context. This means any instance can pick up any event. Using queue triggers gives us at-least-once delivery; we must design idempotency so that even if an event is delivered twice (or a step is retried), the outcome remains correct (or at least not catastrophic). Idempotency can be handled by assigning unique IDs to actions (like an email send ID) and having drivers ignore duplicates, or by transactionally marking tokens as consumed in the database.

* **Plan state persistence:** As described, storing plan marking periodically ensures that if an engine process dies mid-execution, a new one can revive the plan. With Durable Functions, Azure takes care of this by replaying the orchestrator up to the last checkpoint. Without Durable, we might implement a **checkpoint after each step** strategy: after firing a transition and before processing the next events, save the updated marking to Cosmos with a version. If the process crashes, a watcher can find that the plan instance is in a non-final state and no engine is handling it (maybe via a lease mechanism) and resume it. This is complex, so Durable is attractive.

* **Multiple engine instances:** In high-load or HA scenarios, we may run multiple instances of the Plan Engine (whether as separate function apps or threads). To avoid conflict (two engines handling the same plan concurrently), we’ll use *partitioning*: typically by user or plan id. For example, include `plan_id` or `user_id` in the Service Bus message session, so only one function instance processes all events for that session at a time. Azure Service Bus sessions ensure order and exclusive handling per session. If that’s not used, we might implement locking via Cosmos (each plan instance record could include a `locked_by` field which an instance atomically sets via optimistic concurrency). Given that events might not always carry plan\_id (some events start a plan), we’ll have to design carefully to avoid two instances starting the same plan twice. Using a single orchestrator per plan naturally avoids that because it’s single-threaded per plan.

* **Driver isolation and failures:** A driver (like an email sender) could encounter an error (exception) which might propagate. We’ll ensure the driver errors are caught and turned into failure events rather than crashing the whole function. The Universal Processor should use try/except around driver calls so one faulty driver doesn’t stop the event pipeline. In worst case, the function might restart but the queue message would be retried. Hence idempotency again – e.g., ensure that sending an email is safe to retry or mark the event as handled in a store.

* **Data backups:** Context Hub holds critical state. It does CRDT-based sync and snapshots (perhaps to an append-only log or Git). Plan definitions in Cosmos can be backed up using Cosmos backup features or exported periodically to storage. These measures ensure that even catastrophic failures (loss of a region) won’t lose the “knowledge” of user workflows.

* **Graceful degradation:** If the LLM service is down or returns errors during planning, the system should inform the user and possibly fall back to a simpler rule-based plan if available. Similarly, if a driver is unavailable (e.g., email API down), the plan might pause and schedule a retry later. These aren’t exactly HA issues, but related to robust operation. We will incorporate policies to catch such failures and either retry with exponential backoff or switch to alternate tools if possible.

Finally, thorough **testing and staging** will be part of reliability: we will test failover scenarios (simulate function crashes, see if orchestration continues correctly, simulate lost events, etc.) before production deployment.

## Engineering Task Breakdown

To implement this design incrementally, we propose the following tasks and milestones:

1. **Plan Model & Schema Enhancements:**

   * *Task:* Review and extend the `PlanModel` schema to cover any new fields needed (e.g. time triggers syntax, explicit channel declarations if any). Initially, the existing schema (events, steps, guard) is sufficient. We might add an optional `description` field for documentation or a `version`.
   * *Deliverable:* Updated `schema.py` and JSON schema. Unit tests for schema validation (including reactive vs acyclic examples).

2. **Core Plan Execution Engine (In-Memory):**

   * *Task:* Implement the PlanExecutor class that can take a Plan (JSON or object) and execute it in-memory with stubbed tools. This involves creating data structures for places and transitions, a loop to track tokens and fire enabled transitions, and applying guards. Use the Petri net logic as reference. Start with simple acyclic execution (no external events mid-run).
   * *Deliverable:* `PlanExecutor.execute_plan(plan) -> result` method implemented (as outlined in the spec). Write unit tests: e.g., a plan with two sequential steps, ensure they execute in order; a plan with parallel steps, ensure both run. Use dummy actions (like increment a counter or append to a log) to verify logic. This stage can simulate the actions rather than use real drivers.

3. **Integration with Event Bus (Prototype):**

   * *Task:* Refactor PlanExecutor to operate in an event-driven manner. This means it should not assume it can run to completion in one go. Instead, it should be able to pause waiting for external events. Develop a mechanism for PlanExecutor to register interest in events (subscribe) and to emit events when actions occur. In the prototype, we can simulate the Event Bus by a simple pub-sub within the same process.
   * *Deliverable:* Demonstration that if an external event is injected (e.g., via a method call or queue), the PlanExecutor picks it up and continues the plan. Create a test where a plan waits for an event that is delivered after a delay (simulate via asyncio sleep in test), and verify the plan completes. This sets the stage for actual Service Bus integration.

4. **Driver Dispatch & Tool Integration:**

   * *Task:* Implement the connection between PlanExecutor actions and the actual driver calls. We can start by using the existing drivers in-process. For example, when PlanExecutor wants to perform `send_email`, it can directly call `EmailConnectorDriver.handle_event(EmailEvent(...))` and wait for the result events it returns. Similarly, for context reads, call `ContextHubDriver` etc. We might create a simple registry mapping action names to a driver instance and method. This is a synchronous/monolithic approach but easier to test initially.
   * *Deliverable:* Extend PlanExecutor to accept a registry or callback for action execution. Write tests where PlanExecutor executes a plan with a fake action that simply returns a known event (simulate a driver). Ensure that the event is correctly fed back into the plan’s flow.

5. **LLM Planning Service Integration:**

   * *Task:* Integrate the LLM planning loop for end-to-end functionality. Use `call_planner_llm` as implemented to generate a plan from an instruction. This likely requires configuring OpenAI API keys and possibly adjusting the model name (the code shows `gpt-4o-mini` which might be a custom deployment). For now, we can mock this in tests (as done in `test_call_planner_llm`). But in staging, ensure the LLM call is live and receives the tool registry.
   * *Deliverable:* A function `create_plan_for_instruction(user_id, instruction) -> plan_id` that ties everything: loads tool registry, calls LLM to get plan, validates it, stores it (using `PlanStore.save()`), and returns the ID or plan. Test with a sample instruction and verify a plausible plan is returned (maybe via a stub LLM that returns a fixed plan for predictability in tests).

6. **Plan Validation & Critique Improvements:**

   * *Task:* Implement the additional LLM-based validation (Critic role). This could be another function `review_plan(instruction, plan) -> feedback` which calls an LLM with a prompt to check the plan. Define criteria or ask the LLM to simulate execution mentally. This is experimental; ensure it doesn’t block main functionality if it fails. Also, add static validations: for reactive plans, possibly warn if no obvious termination or if cycles lack a delay.
   * *Deliverable:* Update `validate_plan()` to incorporate these checks (perhaps as warnings vs errors). Tests could include an intentionally flawed plan and see if the critic catches it (this might require a real model call – possibly skip in automated tests or use a stub logic).

7. **Persistent Execution using Azure Durable Functions:**

   * *Task:* Move from the in-memory event loop to a Durable Functions (DF) model. In Python, this means implementing an Orchestrator function and Activity functions. Alternatively, use the Durable Entities approach. This is a heavy task:

     * Define the orchestrator logic to wait for events. Because DF for Python doesn’t support dynamic wait on arbitrary external events easily, one method is to have the orchestrator poll a queue or check Cosmos for new events. A better pattern: use an external event to wake it. Possibly the Universal Processor function can signal the orchestrator via `raise_event` (Durable function API to send an event to a running orchestration).
     * The orchestrator will contain code similar to PlanExecutor’s loop but broken into yield points that DF can serialize. It may call out to activities for executing actions (or, simpler, let the normal driver event flow happen outside DF and only handle coordination in DF).
     * Manage the interplay: when an external event arrives, ensure `orchestrator.raise_event(planInstanceId, eventType, eventData)` is called. This might be done in the Universal Processor when it finds a plan waiting as described in Approach B earlier.
   * *Deliverable:* At least one working Durable orchestrator for a simple plan. This might be first done for acyclic plans (like implement a linear sequence via DF). Prove that if the function restarts mid-plan, it can continue. Write an integration test using the Azure Functions Python library (which may require running locally with Azure storage emulator – possibly skip in CI but test in staging environment).

8. **Azure Service Bus Integration & Deployment Config:**

   * *Task:* Hook the event flow up to Service Bus for real. That means converting the simulated internal pub-sub to actual message send/receive. Concretely, use the Azure SDK in Python (already used in drivers) to send events from PlanExecutor to a Service Bus queue (e.g. `events-out` queue), and have the Universal Processor listening on the `events-in` queue. We might integrate PlanExecutor into Universal Processor (Approach A) instead if DF not fully done yet. Initially, a simpler path:

     * Extend InstructionEngineDriver: when an event comes in, after checking static instructions, call `PlanExecutor.handle_event(event)` which will load any relevant plan or do nothing if none.
     * Also allow explicit triggering: if the event is of type “instruction.new” with text, call create\_plan and then possibly start it.
     * Use the existing ServiceBusClient in drivers to publish events from drivers. Confirm that sending an event to the queue triggers another function invocation (in testing, might have to simulate as we can’t easily run Azure Functions in unit tests).
   * *Deliverable:* A deployment (perhaps in an Azure test environment) where one can send an event (e.g. via the `PutEvent` function or directly into Service Bus) and observe the system carrying out a plan. This will likely require deploying the code to Azure for full integration testing.

9. **Reactive Plan Support & Testing:**

   * *Task:* Test and refine the engine with reactive scenarios. Create a plan with a cycle (perhaps a self-loop) and ensure the engine doesn’t erroneously flag it as invalid (the JSON schema and validator allow `graph_type="reactive"` to skip cycle check). Then run it: simulate events to drive it multiple iterations. Adjust token handling logic if needed to allow reusing places. For example, ensure that after a transition fires, tokens can either remain or be re-added for a loop. Possibly implement a mechanism where for reactive plans, tokens aren’t removed from certain places (representing continuous subscriptions).

     * Implement time-trigger loops: maybe a plan that emits an event to itself with some delay. If not straightforward, at least verify manual re-triggering works.
   * *Deliverable:* Unit/integration tests for a reactive plan: e.g., a plan that reacts to two occurrences of an event and does an action each time. Verify that after the first cycle, the plan is still active for the second. Also test that a reactive plan can be externally stopped (perhaps simulate by calling a “deactivate” on PlanExecutor).

10. **High-Availability Mechanisms:**

    * *Task:* Implement safety nets like the plan state checkpoint. If using Durable, ensure the configuration is in place for Azure storage (usually automatic). If not using Durable, implement a simple failover test: kill the PlanExecutor mid-run and start a new one that picks up from Cosmos. For example, halfway through a plan, serialize its state, then instantiate a new PlanExecutor with that state and feed the remaining event – it should continue. This could be done in a test by splitting execution steps.
    * *Deliverable:* A documented procedure or script for state handover. Possibly incorporate into the InstructionEngineDriver the ability to resume plans from saved state if found. Test by simulating an outage: mark a plan as active in DB, don’t finish it, call resume function, and see it continues.

11. **Comprehensive Testing & QA:**

    * *Task:* Write end-to-end tests covering typical usage: e.g., a user instruction triggers plan creation, which then executes to completion, involving multiple drivers (could stub external calls to avoid real emails). Also test failure paths (driver returns failure event, plan’s error handling step triggers). Use the `test_lightning_planner.py` as a basis and expand. Create tests for the LLM planning integration (with patched OpenAI calls as already done in tests).
    * *Deliverable:* A test suite (`tests/test_plan_execution.py`, etc.) that covers at least: linear plan, branching plan (if-guard scenario), parallel step plan, reactive repeating plan, time-delayed step (if we can simulate time easily by triggering scheduler events), and LLM plan generation for a sample prompt.

12. **Documentation and Diagrams:**

    * *Task:* Document the architecture and usage. Create markdown docs (similar to product-spec) describing how to write a plan (for developers or even advanced users), how the execution works, and how to add new tools. Include diagrams of the architecture (e.g., an overview of components like Event Bus, Plan Engine, Drivers on Azure) and perhaps a flowchart of plan execution.
    * *Deliverable:* A “Planning Engine Design” doc (could be added to `docs/`) and an “Engineering Guide” for implementing new drivers or debugging plans. This ensures maintainability.

Each of these tasks can be delivered in sequence, enabling incremental integration. For example, tasks 1-5 can be done in a local environment without Azure, focusing on core functionality and LLM integration. Tasks 6-8 move us into the cloud context, and tasks 9-11 add robustness features. Throughout, we will leverage our continuous testing and staging to catch issues early.

The end goal is a **comprehensive, scalable planning kernel** that seamlessly integrates AI reasoning (via LLMs) with deterministic execution, making the AI OS capable of orchestrating complex workflows with confidence and adaptability.

## Testing Strategy

Testing will be performed at multiple levels to ensure reliability of the planning kernel:

* **Unit Tests:** For all new modules (PlanExecutor, Durable orchestrator, etc.), write unit tests with controlled inputs. Use small dummy plans to test enabling and firing logic (e.g., a plan with two steps and ensure the first step’s event triggers second step execution). Test the JSON schema validation by feeding invalid plans to ensure errors are raised appropriately (e.g., missing fields, cycles in acyclic mode). Also test utility functions like guard evaluation (create some guard expressions and test they accept/reject tokens correctly).

* **Integration Tests (Local):** Use the actual drivers in a local test environment where we simulate the event bus. For instance, create an EmailConnectorDriver instance but replace its actual sending method with a stub that returns success. Then simulate a plan that calls `send_email` and verify that the EmailConnectorDriver was invoked and the plan proceeded to emit a completion event. The `lightning` repository already contains tests for planner LLM calls and basic validation; we will extend this to test execution. We should also test the LLM planning end-to-end: feed a sample user request, run `create_verified_plan`, then directly feed that plan into PlanExecutor and verify the expected tool events are produced. This covers the whole loop from instruction to action.

* **Azure Function Tests:** Once deployed or in a function emulator, write tests that send messages to the Service Bus and observe outcomes. This can be done with Azure’s integration testing tools or simply by using the Azure SDK to send an event and then querying the results in Cosmos or context. For example, deploy a test plan that writes something to the context, trigger it via an event, then check the context DB for that write. We will also test error scenarios by, say, forcing a driver to throw an exception and ensuring a failure event is logged and the plan doesn’t hang indefinitely.

* **Performance Tests:** Simulate a heavier load, e.g., multiple events in a short time, or a plan with parallel branches. Measure that events don’t get lost and the latency stays within acceptable bounds. We can use Azure’s load testing or a simple loop to queue many events. This will help tune concurrency (e.g., number of function instances, Service Bus prefetch settings, etc.). Also test memory usage for long reactive plans (ensuring the state doesn’t grow unboundedly).

* **Security Tests:** Ensure that the Security Manager intercepts forbidden actions. This might involve setting a policy (like a cost limit) and then attempting a plan that would break it, verifying it’s blocked. Also test that a plan can’t access another user’s data (this is more on context hub and drivers, but we should simulate multi-user isolation: two plans from different users, an event from user A should not accidentally trigger plan of user B, etc. Partition keys in Cosmos and user\_id tagging of events will help here).

* **Failover Tests:** Manually or via test hooks, simulate a crash. For example, if using Durable, deliberately terminate a function instance mid-execution (maybe by throwing an exception in the orchestrator and seeing if it recovers). Or shut down the function app and restart it with an active plan in DB to see if it resumes. These are hard to automate fully, but we can test the components: e.g., test that our resume logic for a plan in Cosmos works by constructing an artificial state and calling the resume function.

The testing process will be iterative. We’ll utilize the comprehensive test suite structure already present in `lightning` (e.g., `tests/test_lightning_planner.py`) and build out additional tests for new functionality. Each new feature (e.g., time triggers, channel passing) will come with targeted tests. We’ll also ensure we test across the boundary of LLM integration by using mocking for the LLM calls in unit tests (so tests are deterministic), and a few live calls in an isolated environment to verify that our prompts yield well-formed plans (perhaps using a smaller/cheaper model or a sandbox API key).

By following this testing strategy and the phased task plan above, we will incrementally build confidence in the AI OS planning kernel’s correctness, performance, and reliability, leading to a robust deployment that realizes the vision of autonomous, reactive AI workflows orchestrated through Petri net-based plans with LLM intelligence.

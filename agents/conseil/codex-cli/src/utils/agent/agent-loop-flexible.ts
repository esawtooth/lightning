import type { ReviewDecision } from "./review.js";
import type { ApplyPatchCommand, ApprovalPolicy } from "../../approvals.js";
import type { AppConfig } from "../config.js";
import type { ResponseEvent } from "../responses.js";
import type {
  ResponseFunctionToolCall,
  ResponseInputItem,
  ResponseItem,
  ResponseCreateParams,
  FunctionTool,
  Tool,
} from "openai/resources/responses/responses.mjs";
import type { Reasoning } from "openai/resources.mjs";

import { CLI_VERSION } from "../../version.js";
import {
  OPENAI_TIMEOUT_MS,
  OPENAI_ORGANIZATION,
  OPENAI_PROJECT,
  getBaseUrl,
  AZURE_OPENAI_API_VERSION,
} from "../config.js";
import { getUrlContent, searchWeb } from "../firecrawl/client.js";
import { log } from "../logger/log.js";
import { parseToolCallArguments } from "../parsers.js";
import { responsesCreateViaChatCompletions } from "../responses.js";
import {
  ORIGIN,
  getSessionId,
  setCurrentModel,
  setSessionId,
} from "../session.js";
import { applyPatchToolInstructions } from "./apply-patch.js";
import { handleExecCommand } from "./handle-exec-command.js";
import {
  tmuxCreate,
  tmuxDelete,
  tmuxOutput,
  tmuxSend,
} from "./tmux.js";
import { HttpsProxyAgent } from "https-proxy-agent";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import OpenAI, { APIConnectionTimeoutError, AzureOpenAI } from "openai";
import os from "os";

// Job role templates with their specific instructions
export const JOB_ROLE_TEMPLATES = {
  // Default coding role - preserves most of the original functionality
  CODING: {
    title: "Coding Assistant",
    description: `You are an expert coding assistant. You can:
- Edit and create code files using apply_patch
- Run commands to test and validate changes
- Search codebases and understand project structure
- Apply best practices and maintain code quality
- Work with git repositories and version control`,
    guidelines: `- Fix problems at the root cause rather than applying surface-level patches
- Avoid unneeded complexity in your solution
- Keep changes consistent with the style of the existing codebase
- Update documentation as necessary
- Use git log and git blame for additional context when needed
- Never add copyright or license headers unless requested
- Remove unnecessary inline comments
- Run pre-commit checks if available`,
    tools: ["shell", "web_search", "get_url", "tmux_create", "tmux_delete", "tmux_output", "tmux_send"]
  },
  
  LEGAL: {
    title: "Legal Assistant",
    description: `You are a legal document assistant. You can:
- Review and edit legal documents (contracts, agreements, policies)
- Create document templates and standard clauses
- Track document versions and changes
- Organize legal research and case notes
- Maintain compliance checklists and procedures`,
    guidelines: `- Maintain formal, precise language appropriate for legal documents
- Preserve document structure and formatting conventions
- Flag potential legal issues or ambiguities for review
- Create clear audit trails for document changes
- Use industry-standard legal terminology
- Organize documents following legal filing conventions`,
    tools: ["shell", "web_search", "get_url"]
  },
  
  PERSONAL_ASSISTANT: {
    title: "Personal Assistant",
    description: `You are a personal assistant helping with daily tasks and organization. You can:
- Manage todo lists and task tracking
- Organize notes and personal documents
- Create meeting agendas and summaries
- Draft emails and correspondence
- Maintain calendars and schedules
- Research topics and compile information`,
    guidelines: `- Keep information well-organized and easily accessible
- Use clear, concise language in all documents
- Create actionable todo items with clear deadlines
- Maintain consistent formatting across documents
- Prioritize tasks based on urgency and importance
- Create helpful summaries and overviews`,
    tools: ["shell", "web_search", "get_url"]
  },
  
  FINANCE: {
    title: "Finance Assistant",
    description: `You are a financial documentation assistant. You can:
- Create and maintain financial reports and spreadsheets
- Track expenses and budgets
- Organize investment research and analysis
- Create financial projections and models
- Document financial procedures and policies
- Maintain transaction records and receipts`,
    guidelines: `- Ensure accuracy in all numerical data
- Use standard financial formatting and terminology
- Create clear audit trails for financial decisions
- Organize documents by fiscal periods
- Include relevant calculations and formulas
- Maintain data privacy and security`,
    tools: ["shell", "web_search", "get_url"]
  },
  
  RESEARCH: {
    title: "Research Assistant",
    description: `You are a research assistant specializing in information gathering and synthesis. You can:
- Conduct comprehensive research on topics
- Create literature reviews and bibliographies
- Organize research notes and findings
- Draft research reports and summaries
- Maintain reference libraries
- Track sources and citations`,
    guidelines: `- Verify information from multiple sources
- Maintain proper citation formats
- Organize research by themes and topics
- Create clear, objective summaries
- Track research methodology
- Highlight key findings and insights`,
    tools: ["shell", "web_search", "get_url"]
  },
  
  CUSTOM: {
    title: "Custom Assistant",
    description: "", // Will be filled by user
    guidelines: "",  // Will be filled by user
    tools: ["shell", "web_search", "get_url"]
  }
};

export type JobRole = keyof typeof JOB_ROLE_TEMPLATES;

export type CommandConfirmation = {
  review: ReviewDecision;
  applyPatch?: ApplyPatchCommand | undefined;
  customDenyMessage?: string;
  explanation?: string;
};

const alreadyProcessedResponses = new Set();
const alreadyStagedItemIds = new Set<string>();

type AgentLoopParams = {
  model: string;
  provider?: string;
  config?: AppConfig;
  instructions?: string;
  jobRole?: JobRole;
  customJobDescription?: string;
  customGuidelines?: string;
  enableSandbox?: boolean; // Default false for flexibility
  approvalPolicy: ApprovalPolicy;
  disableResponseStorage?: boolean;
  onItem: (item: ResponseItem) => void;
  onLoading: (loading: boolean) => void;
  additionalWritableRoots: ReadonlyArray<string>;
  getCommandConfirmation: (
    command: Array<string>,
    applyPatch: ApplyPatchCommand | undefined,
  ) => Promise<CommandConfirmation>;
  onLastResponseId: (lastResponseId: string) => void;
};

// Tool definitions remain the same...
const shellFunctionTool: FunctionTool = {
  type: "function",
  name: "shell",
  description: "Runs a shell command, and returns its output.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      command: { type: "array", items: { type: "string" } },
      workdir: {
        type: "string",
        description: "The working directory for the command.",
      },
      timeout: {
        type: "number",
        description:
          "The maximum time to wait for the command to complete in milliseconds.",
      },
    },
    required: ["command"],
    additionalProperties: false,
  },
};

const localShellTool: Tool = {
  //@ts-expect-error - waiting on sdk
  type: "local_shell",
};

const webSearchTool: FunctionTool = {
  type: "function",
  name: "web_search",
  description: "Search the web and return results.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      query: { type: "string", description: "Search query" },
      limit: {
        type: "number",
        description: "Maximum number of results",
      },
    },
    required: ["query"],
    additionalProperties: false,
  },
};

const getUrlTool: FunctionTool = {
  type: "function",
  name: "get_url",
  description: "Fetch a URL and return its content as markdown.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      url: { type: "string", description: "URL to fetch" },
    },
    required: ["url"],
    additionalProperties: false,
  },
};

const tmuxCreateTool: FunctionTool = {
  type: "function",
  name: "tmux_create",
  description: "Create a detached tmux session.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      session: { type: "string", description: "Tmux session name" },
    },
    required: ["session"],
    additionalProperties: false,
  },
};

const tmuxDeleteTool: FunctionTool = {
  type: "function",
  name: "tmux_delete",
  description: "Delete a tmux session.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      session: { type: "string", description: "Tmux session name" },
    },
    required: ["session"],
    additionalProperties: false,
  },
};

const tmuxOutputTool: FunctionTool = {
  type: "function",
  name: "tmux_output",
  description: "Get the current output of a tmux session.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      session: { type: "string", description: "Tmux session name" },
    },
    required: ["session"],
    additionalProperties: false,
  },
};

const tmuxSendTool: FunctionTool = {
  type: "function",
  name: "tmux_send",
  description: "Run a command inside a tmux session.",
  strict: false,
  parameters: {
    type: "object",
    properties: {
      session: { type: "string", description: "Tmux session name" },
      command: { type: "string", description: "Command to run" },
    },
    required: ["session", "command"],
    additionalProperties: false,
  },
};

export class FlexibleAgentLoop {
  private model: string;
  private provider: string;
  private instructions?: string;
  private jobRole: JobRole;
  private customJobDescription?: string;
  private customGuidelines?: string;
  private enableSandbox: boolean;
  private approvalPolicy: ApprovalPolicy;
  private config: AppConfig;
  private additionalWritableRoots: ReadonlyArray<string>;
  private readonly disableResponseStorage: boolean;

  private oai: OpenAI;

  private onItem: (item: ResponseItem) => void;
  private onLoading: (loading: boolean) => void;
  private getCommandConfirmation: (
    command: Array<string>,
    applyPatch: ApplyPatchCommand | undefined,
  ) => Promise<CommandConfirmation>;
  private onLastResponseId: (lastResponseId: string) => void;

  private currentStream: unknown | null = null;
  private generation = 0;
  private execAbortController: AbortController | null = null;
  private canceled = false;

  private transcript: Array<ResponseInputItem> = [];
  private pendingAborts: Set<string> = new Set();
  private terminated = false;
  private readonly hardAbort = new AbortController();

  public cancel(): void {
    if (this.terminated) {
      return;
    }

    this.currentStream = null;
    log(
      `FlexibleAgentLoop.cancel() invoked – currentStream=${Boolean(
        this.currentStream,
      )} execAbortController=${Boolean(this.execAbortController)} generation=${
        this.generation
      }`,
    );
    (
      this.currentStream as { controller?: { abort?: () => void } } | null
    )?.controller?.abort?.();

    this.canceled = true;
    this.execAbortController?.abort();
    this.execAbortController = new AbortController();
    log("FlexibleAgentLoop.cancel(): execAbortController.abort() called");

    if (this.pendingAborts.size === 0) {
      try {
        this.onLastResponseId("");
      } catch {
        /* ignore */
      }
    }

    this.onLoading(false);
    this.generation += 1;
    log(`FlexibleAgentLoop.cancel(): generation bumped to ${this.generation}`);
  }

  public terminate(): void {
    if (this.terminated) {
      return;
    }
    this.terminated = true;
    this.hardAbort.abort();
    this.cancel();
  }

  public sessionId: string;

  constructor({
    model,
    provider = "openai",
    instructions,
    jobRole = "CODING",
    customJobDescription,
    customGuidelines,
    enableSandbox = false,
    approvalPolicy,
    disableResponseStorage,
    config,
    onItem,
    onLoading,
    getCommandConfirmation,
    onLastResponseId,
    additionalWritableRoots,
  }: AgentLoopParams & { config?: AppConfig }) {
    this.model = model;
    this.provider = provider;
    this.instructions = instructions;
    this.jobRole = jobRole;
    this.customJobDescription = customJobDescription;
    this.customGuidelines = customGuidelines;
    this.enableSandbox = enableSandbox;
    this.approvalPolicy = approvalPolicy;

    this.config = config ?? {
      model,
      instructions: instructions ?? "",
    };
    this.additionalWritableRoots = additionalWritableRoots;
    this.onItem = onItem;
    this.onLoading = onLoading;
    this.getCommandConfirmation = getCommandConfirmation;
    this.onLastResponseId = onLastResponseId;

    this.disableResponseStorage = disableResponseStorage ?? false;
    this.sessionId = getSessionId() || randomUUID().replaceAll("-", "");

    const timeoutMs = OPENAI_TIMEOUT_MS;
    const apiKey = this.config.apiKey ?? process.env["OPENAI_API_KEY"] ?? "";
    const baseURL = getBaseUrl(this.provider);

    this.oai = new OpenAI({
      ...(apiKey ? { apiKey } : {}),
      baseURL,
      defaultHeaders: {
        originator: ORIGIN,
        version: CLI_VERSION,
        session_id: this.sessionId,
        ...(OPENAI_ORGANIZATION
          ? { "OpenAI-Organization": OPENAI_ORGANIZATION }
          : {}),
        ...(OPENAI_PROJECT ? { "OpenAI-Project": OPENAI_PROJECT } : {}),
      },
      httpAgent: PROXY_URL ? new HttpsProxyAgent(PROXY_URL) : undefined,
      ...(timeoutMs !== undefined ? { timeout: timeoutMs } : {}),
    });

    if (this.provider.toLowerCase() === "azure") {
      this.oai = new AzureOpenAI({
        apiKey,
        baseURL,
        apiVersion: AZURE_OPENAI_API_VERSION,
        defaultHeaders: {
          originator: ORIGIN,
          version: CLI_VERSION,
          session_id: this.sessionId,
          ...(OPENAI_ORGANIZATION
            ? { "OpenAI-Organization": OPENAI_ORGANIZATION }
            : {}),
          ...(OPENAI_PROJECT ? { "OpenAI-Project": OPENAI_PROJECT } : {}),
        },
        httpAgent: PROXY_URL ? new HttpsProxyAgent(PROXY_URL) : undefined,
        ...(timeoutMs !== undefined ? { timeout: timeoutMs } : {}),
      });
    }

    setSessionId(this.sessionId);
    setCurrentModel(this.model);

    this.hardAbort = new AbortController();

    this.hardAbort.signal.addEventListener(
      "abort",
      () => this.execAbortController?.abort(),
      { once: true },
    );
  }

  private getSystemPrompt(): string {
    const userName = os.userInfo().username;
    const workdir = process.cwd();
    
    // Get role configuration
    const roleConfig = this.jobRole === "CUSTOM" 
      ? {
          title: "Custom Assistant",
          description: this.customJobDescription || "You are a helpful assistant.",
          guidelines: this.customGuidelines || ""
        }
      : JOB_ROLE_TEMPLATES[this.jobRole];

    const basePrompt = `You are operating as ${roleConfig.title} within the Conseil CLI, a terminal-based AI assistant. You are expected to be precise, safe, and helpful.

${roleConfig.description}

Current context:
- User: ${userName}
- Working directory: ${workdir}
${spawnSync("rg", ["--version"], { stdio: "ignore" }).status === 0 ? "- Always use rg instead of grep/ls -R because it is much faster and respects gitignore" : ""}

You are an agent - please keep going until the user's query is completely resolved. Only terminate your turn when you are sure that the problem is solved. If you are not sure about file content or structure, use your tools to read files and gather the relevant information.

${this.enableSandbox ? "You are working in a sandboxed environment with rollback support." : "You have direct access to the file system without sandboxing restrictions."}

Key capabilities:
- Use \`apply_patch\` to edit files: {"cmd":["apply_patch","*** Begin Patch\\n*** Update File: path/to/file.py\\n@@ def example():\\n-  pass\\n+  return 123\\n*** End Patch"]}
- Execute shell commands to interact with the system
- Search the web for information when needed
- Manage tmux sessions for long-running processes

Guidelines for your role:
${roleConfig.guidelines}

General guidelines:
- Be concise and direct in your responses
- Focus on accomplishing the user's specific task
- When editing files, reference them as already saved (don't tell users to save manually)
- Don't show full contents of large files unless explicitly requested
- Maintain appropriate tone and style for your role

${this.instructions ? `\nAdditional instructions:\n${this.instructions}` : ""}`;

    return basePrompt;
  }

  private async handleFunctionCall(
    item: ResponseFunctionToolCall,
  ): Promise<Array<ResponseInputItem>> {
    if (this.canceled) {
      return [];
    }

    const isChatStyle =
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (item as any).function != null;

    const name: string | undefined = isChatStyle
      ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (item as any).function?.name
      : // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (item as any).name;

    const rawArguments: string | undefined = isChatStyle
      ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (item as any).function?.arguments
      : // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (item as any).arguments;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const callId: string = (item as any).call_id ?? (item as any).id;

    const args = parseToolCallArguments(rawArguments ?? "{}");
    let jsonArgs: Record<string, unknown> = {};
    try {
      jsonArgs = JSON.parse(rawArguments ?? "{}");
    } catch {
      jsonArgs = {};
    }
    log(
      `handleFunctionCall(): name=${
        name ?? "undefined"
      } callId=${callId} args=${rawArguments}`,
    );

    if (args == null) {
      const outputItem: ResponseInputItem.FunctionCallOutput = {
        type: "function_call_output",
        call_id: item.call_id,
        output: `invalid arguments: ${rawArguments}`,
      };
      return [outputItem];
    }

    const outputItem: ResponseInputItem.FunctionCallOutput = {
      type: "function_call_output",
      call_id: callId,
      output: "no function found",
    };

    const additionalItems: Array<ResponseInputItem> = [];

    if (name === "web_search") {
      try {
        const results = await searchWeb(String(jsonArgs.query || ""), Number(jsonArgs.limit) || 5);
        const formatted = results
          .map((r, i) => `${i + 1}. ${r.title}\n${r.url}\n${r.description}`)
          .join("\n\n");
        outputItem.output = JSON.stringify({
          output: formatted,
          metadata: { exit_code: 0, duration_seconds: 0 },
        });
      } catch (err) {
        outputItem.output = JSON.stringify({
          output: String(err instanceof Error ? err.message : err),
          metadata: { exit_code: 1, duration_seconds: 0 },
        });
      }
    } else if (name === "get_url") {
      try {
        const content = await getUrlContent(String(jsonArgs.url || ""));
        outputItem.output = JSON.stringify({
          output: content,
          metadata: { exit_code: 0, duration_seconds: 0 },
        });
      } catch (err) {
        outputItem.output = JSON.stringify({
          output: String(err instanceof Error ? err.message : err),
          metadata: { exit_code: 1, duration_seconds: 0 },
        });
      }
    } else if (name === "tmux_create") {
      const { output, metadata } = await tmuxCreate(
        String(jsonArgs.session || ""),
        this.config,
      );
      outputItem.output = JSON.stringify({ output, metadata });
    } else if (name === "tmux_delete") {
      const { output, metadata } = await tmuxDelete(
        String(jsonArgs.session || ""),
        this.config,
      );
      outputItem.output = JSON.stringify({ output, metadata });
    } else if (name === "tmux_output") {
      const { output, metadata } = await tmuxOutput(
        String(jsonArgs.session || ""),
        this.config,
      );
      outputItem.output = JSON.stringify({ output, metadata });
    } else if (name === "tmux_send") {
      const { output, metadata } = await tmuxSend(
        String(jsonArgs.session || ""),
        String(jsonArgs.command || ""),
        this.config,
      );
      outputItem.output = JSON.stringify({ output, metadata });
    } else if (name === "container.exec" || name === "shell") {
      // Modified to respect enableSandbox setting
      const modifiedConfig = {
        ...this.config,
        forceSandbox: this.enableSandbox
      };
      
      const {
        outputText,
        metadata,
        additionalItems: additionalItemsFromExec,
      } = await handleExecCommand(
        args,
        modifiedConfig,
        this.approvalPolicy,
        this.additionalWritableRoots,
        this.getCommandConfirmation,
        this.execAbortController?.signal,
      );
      outputItem.output = JSON.stringify({ output: outputText, metadata });

      if (additionalItemsFromExec) {
        additionalItems.push(...additionalItemsFromExec);
      }
    }

    return [outputItem, ...additionalItems];
  }

  // The rest of the methods would be similar to the original AgentLoop
  // but using the flexible system prompt and respecting the sandbox setting
  
  public async run(
    input: Array<ResponseInputItem>,
    previousResponseId: string = "",
  ): Promise<void> {
    // Implementation would be the same as original but using getSystemPrompt()
    // instead of the hardcoded prefix
    
    // ... rest of the run method implementation
  }

  // ... rest of the class implementation
}

// Re-export for backwards compatibility
export const AgentLoop = FlexibleAgentLoop;
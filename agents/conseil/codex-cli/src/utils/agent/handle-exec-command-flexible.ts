import type { CommandConfirmation } from "./agent-loop.js";
import type { ApplyPatchCommand, ApprovalPolicy } from "../../approvals.js";
import type { AppConfig } from "../config.js";
import type { ExecInput } from "./sandbox/interface.js";
import type { ResponseInputItem } from "openai/resources/responses/responses.mjs";

import { canAutoApprove } from "../../approvals.js";
import { formatCommandForDisplay } from "../../format-command.js";
import { FullAutoErrorMode } from "../auto-approval-mode.js";
import { exec, execApplyPatch } from "./exec.js";
import { ReviewDecision } from "./review.js";
import { isLoggingEnabled, log } from "../logger/log.js";
import { SandboxType } from "./sandbox/interface.js";
import fs from "fs/promises";

// Session‑level cache of commands that the user has chosen to always approve
const alwaysApprovedCommands = new Set<string>();

function deriveCommandKey(cmd: Array<string>): string {
  const [maybeShell, maybeFlag, coreInvocation] = cmd;

  if (coreInvocation?.startsWith("apply_patch")) {
    return "apply_patch";
  }

  if (maybeShell === "bash" && maybeFlag === "-lc") {
    const script = coreInvocation ?? "";
    return script.split(/\s+/)[0] || "bash";
  }

  if (coreInvocation) {
    return coreInvocation.split(/\s+/)[0]!;
  }

  return JSON.stringify(cmd);
}

type HandleExecCommandResult = {
  outputText: string;
  metadata: Record<string, unknown>;
  additionalItems?: Array<ResponseInputItem>;
};

// Extended config type to support sandbox override
interface FlexibleAppConfig extends AppConfig {
  forceSandbox?: boolean;
  disableSandbox?: boolean;
}

export async function handleExecCommandFlexible(
  args: ExecInput,
  config: FlexibleAppConfig,
  policy: ApprovalPolicy,
  additionalWritableRoots: ReadonlyArray<string>,
  getCommandConfirmation: (
    command: Array<string>,
    applyPatch: ApplyPatchCommand | undefined,
  ) => Promise<CommandConfirmation>,
  abortSignal?: AbortSignal,
): Promise<HandleExecCommandResult> {
  const { cmd: command, workdir } = args;
  const key = deriveCommandKey(command);

  // Determine sandbox setting
  const shouldSandbox = config.forceSandbox === true || 
    (config.disableSandbox !== true && policy !== "auto");

  // If the user has already said "always approve", skip policy & use determined sandbox setting
  if (alwaysApprovedCommands.has(key)) {
    return execCommand(
      args,
      undefined,
      shouldSandbox,
      additionalWritableRoots,
      config,
      abortSignal,
    ).then(convertSummaryToResult);
  }

  let runInSandbox = shouldSandbox;
  let applyPatch: ApplyPatchCommand | undefined;

  // Special handling for apply_patch
  if (command[0] === "apply_patch" && command.length >= 2) {
    const target = await fs.mkdtemp("/tmp/apply_patch_");
    applyPatch = {
      sandboxRoot: target,
      command,
      workdir: workdir ?? process.cwd(),
    };
  }

  // Check auto-approval
  const canAuto = policy === "auto" || 
    (canAutoApprove(command) && policy !== "manual");

  if (canAuto) {
    runInSandbox = shouldSandbox;
  }

  // If not auto-approved, get user confirmation
  if (!canAuto && policy !== "auto") {
    const confirmation = await getCommandConfirmation(command, applyPatch);
    
    if (confirmation.review === ReviewDecision.ALWAYS_APPROVE) {
      alwaysApprovedCommands.add(key);
      runInSandbox = false; // User trusts this command type
    } else if (confirmation.review === ReviewDecision.APPROVE) {
      runInSandbox = shouldSandbox;
    } else if (confirmation.review === ReviewDecision.DENY) {
      return {
        outputText: confirmation.customDenyMessage || "Command denied by user",
        metadata: { exit_code: 1, duration_seconds: 0 },
      };
    } else if (confirmation.review === ReviewDecision.TERMINATE) {
      const item: ResponseInputItem = {
        type: "message",
        role: "assistant",
        content: [
          {
            type: "input_text",
            text: "I'll stop here. Let me know if you need anything else!",
          },
        ],
      };
      return {
        outputText: "",
        metadata: { exit_code: 0, duration_seconds: 0 },
        additionalItems: [item],
      };
    }

    if (confirmation.applyPatch) {
      applyPatch = confirmation.applyPatch;
    }
  }

  return execCommand(
    args,
    applyPatch,
    runInSandbox,
    additionalWritableRoots,
    config,
    abortSignal,
  ).then(convertSummaryToResult);
}

async function execCommand(
  args: ExecInput,
  applyPatch: ApplyPatchCommand | undefined,
  runInSandbox: boolean,
  additionalWritableRoots: ReadonlyArray<string>,
  config: AppConfig,
  abortSignal?: AbortSignal,
): Promise<ExecSummary> {
  log(`execCommand: runInSandbox=${runInSandbox}, command=${JSON.stringify(args.cmd)}`);
  
  if (applyPatch) {
    return execApplyPatch(
      applyPatch,
      runInSandbox ? SandboxType.Landlock : SandboxType.None,
      additionalWritableRoots,
      config,
      abortSignal,
    );
  }

  return exec(
    args,
    runInSandbox ? SandboxType.Landlock : SandboxType.None,
    additionalWritableRoots,
    config,
    abortSignal,
  );
}

type ExecSummary = {
  output: string;
  metadata: { exit_code: number; duration_seconds: number };
  fileChangesSummary?: string;
};

function convertSummaryToResult(summary: ExecSummary): HandleExecCommandResult {
  return {
    outputText: summary.output,
    metadata: summary.metadata,
  };
}
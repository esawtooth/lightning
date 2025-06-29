/**
 * ContextHub CLI integration for Conseil agent
 * Provides access to the distributed context hub for document management and search
 */

import { spawnSync } from "node:child_process";
import type { AppConfig } from "../config.js";

export interface ContextHubMetadata {
  exit_code: number;
  duration_seconds: number;
  command?: string;
  operation?: string;
}

export interface ContextHubResult {
  output: string;
  metadata: ContextHubMetadata;
}

/**
 * Execute contexthub CLI command with proper error handling
 */
async function executeContextHub(
  args: string[],
  config: AppConfig,
  timeout = 30000
): Promise<ContextHubResult> {
  const startTime = Date.now();
  
  try {
    // Use contexthub-cli.py directly from the context-hub directory
    const contextHubPath = process.env.CONTEXT_HUB_CLI_PATH || 
      "/home/sam/lightning/context-hub/contexthub-cli.py";
    
    const result = spawnSync("python3", [contextHubPath, ...args], {
      encoding: "utf8",
      timeout,
      maxBuffer: 10 * 1024 * 1024, // 10MB buffer
      env: {
        ...process.env,
        // Ensure proper environment for contexthub
        PYTHONPATH: "/home/sam/lightning/context-hub",
      },
    });

    const duration = (Date.now() - startTime) / 1000;
    const command = `contexthub ${args.join(" ")}`;

    if (result.error) {
      return {
        output: `Error executing contexthub command: ${result.error.message}`,
        metadata: {
          exit_code: 1,
          duration_seconds: duration,
          command,
          operation: args[0] || "unknown",
        },
      };
    }

    // Combine stdout and stderr for complete output
    const output = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    
    return {
      output: output || "(no output)",
      metadata: {
        exit_code: result.status || 0,
        duration_seconds: duration,
        command,
        operation: args[0] || "unknown",
      },
    };
  } catch (error) {
    const duration = (Date.now() - startTime) / 1000;
    return {
      output: `Unexpected error: ${error instanceof Error ? error.message : String(error)}`,
      metadata: {
        exit_code: 1,
        duration_seconds: duration,
        command: `contexthub ${args.join(" ")}`,
        operation: args[0] || "unknown",
      },
    };
  }
}

/**
 * Pull documents/folders from contexthub to local filesystem
 */
export async function contexthubPull(
  hubPath: string,
  localPath: string,
  force = false,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["pull", hubPath, localPath];
  if (force) args.push("--force");
  
  return executeContextHub(args, config);
}

/**
 * Push local changes back to contexthub
 */
export async function contexthubPush(
  localPath: string,
  dryRun = false,
  noConfirm = false,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["push", localPath];
  if (dryRun) args.push("--dry-run");
  if (noConfirm) args.push("--no-confirm");
  
  return executeContextHub(args, config);
}

/**
 * Check sync status of a local directory
 */
export async function contexthubSyncStatus(
  localPath: string,
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["sync_status", localPath], config);
}

/**
 * Read document with optional line numbers
 */
export async function contexthubRead(
  path: string,
  numbered = false,
  lines?: number,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = numbered ? ["llm", "read", path, "--lines"] : ["llm", "read", path];
  if (lines && numbered) args.push(String(lines));
  
  return executeContextHub(args, config);
}

/**
 * Write content to a document (create or update)
 */
export async function contexthubWrite(
  path: string,
  content: string,
  patchMode = false,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["llm", "write", path, content];
  if (patchMode) args.push("--patch-mode");
  
  return executeContextHub(args, config);
}

/**
 * Search documents with structured output
 */
export async function contexthubFind(
  query: string,
  limit?: number,
  includeContent = false,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["llm", "find", query];
  if (limit) args.push("--limit", String(limit));
  if (includeContent) args.push("--include-content");
  
  return executeContextHub(args, config);
}

/**
 * Get detailed information about a path
 */
export async function contexthubInspect(
  path: string,
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["llm", "inspect", path], config);
}

/**
 * List directory contents
 */
export async function contexthubLs(
  path?: string,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["ls"];
  if (path) args.push(path);
  
  return executeContextHub(args, config);
}

/**
 * Show current workspace status
 */
export async function contexthubStatus(
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["status"], config);
}

/**
 * Change current directory in workspace
 */
export async function contexthubCd(
  path: string,
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["cd", path], config);
}

/**
 * Get current working directory
 */
export async function contexthubPwd(
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["pwd"], config);
}

/**
 * Apply a unified diff patch to a document
 */
export async function contexthubPatch(
  path: string,
  patch: string,
  dryRun = false,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["patch", path, "--patch", patch];
  if (dryRun) args.push("--dry-run");
  
  return executeContextHub(args, config);
}

/**
 * Generate diff between hub document and local file
 */
export async function contexthubDiff(
  path: string,
  localFile?: string,
  context = 3,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["diff", path];
  if (localFile) args.push(localFile);
  args.push("--context", String(context));
  
  return executeContextHub(args, config);
}

/**
 * Full-text search across all documents
 */
export async function contexthubSearch(
  query: string,
  limit?: number,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["search", query];
  if (limit) args.push("--limit", String(limit));
  
  return executeContextHub(args, config);
}

/**
 * Create a new file or folder
 */
export async function contexthubNew(
  name: string,
  isFolder = false,
  content?: string,
  edit = false,
  config: AppConfig
): Promise<ContextHubResult> {
  const args = ["new", name];
  if (isFolder) args.push("--folder");
  if (content) args.push("--content", content);
  if (edit) args.push("--edit");
  
  return executeContextHub(args, config);
}

/**
 * Move/rename files or folders
 */
export async function contexthubMv(
  source: string,
  dest: string,
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["mv", source, dest], config);
}

/**
 * Delete files or folders
 */
export async function contexthubRm(
  path: string,
  config: AppConfig
): Promise<ContextHubResult> {
  return executeContextHub(["rm", path], config);
}
import type { AppConfig } from "../config.js";
import { exec } from "./exec.js";
import { SandboxType } from "./sandbox/interface.js";

export type TmuxResult = { output: string; metadata: { exit_code: number; duration_seconds: number } };

async function runTmux(
  cmd: Array<string>,
  config: AppConfig,
): Promise<TmuxResult> {
  const start = Date.now();
  const { stdout, stderr, exitCode } = await exec(
    { cmd, workdir: undefined, timeoutInMillis: undefined, additionalWritableRoots: [] },
    SandboxType.NONE,
    config,
  );
  const duration = Date.now() - start;
  return {
    output: stdout || stderr,
    metadata: { exit_code: exitCode, duration_seconds: Math.round(duration / 100) / 10 },
  };
}

export function tmuxCreate(session: string, config: AppConfig): Promise<TmuxResult> {
  return runTmux(["tmux", "new-session", "-d", "-s", session], config);
}

export function tmuxDelete(session: string, config: AppConfig): Promise<TmuxResult> {
  return runTmux(["tmux", "kill-session", "-t", session], config);
}

export function tmuxOutput(session: string, config: AppConfig): Promise<TmuxResult> {
  return runTmux(["tmux", "capture-pane", "-p", "-t", session], config);
}

export function tmuxSend(session: string, command: string, config: AppConfig): Promise<TmuxResult> {
  return runTmux(["tmux", "send-keys", "-t", session, command, "C-m"], config);
}

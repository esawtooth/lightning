/**
 * Channel Manager for Conseil Agent
 * Provides channel communication with VextirOS backend
 */

import { EventEmitter } from "events";

export enum ChannelType {
  STATUS = "status",
  COMMAND = "command", 
  HEALTH = "health",
  ACTIVITY = "activity",
  ERROR = "error",
}

export interface ChannelMessage {
  channel_type: ChannelType;
  agent_id: string;
  data: Record<string, any>;
  timestamp?: string;
  message_id?: string;
}

export interface ChannelConfig {
  agent_id: string;
  vextir_url?: string; // URL to VextirOS backend
  enabled?: boolean;
}

export class Channel extends EventEmitter {
  private agentId: string;
  private channelType: ChannelType;
  private config: ChannelConfig;

  constructor(agentId: string, channelType: ChannelType, config: ChannelConfig) {
    super();
    this.agentId = agentId;
    this.channelType = channelType;
    this.config = config;
  }

  async publish(data: Record<string, any>): Promise<void> {
    if (!this.config.enabled) {
      return;
    }

    const message: ChannelMessage = {
      channel_type: this.channelType,
      agent_id: this.agentId,
      data,
      timestamp: new Date().toISOString(),
      message_id: `${this.agentId}-${this.channelType}-${Date.now()}`,
    };

    // Emit locally for immediate handling
    this.emit('message', message);

    // Send to VextirOS backend if configured
    if (this.config.vextir_url) {
      try {
        await this.sendToVextirOS(message);
      } catch (error) {
        console.warn(`Failed to send channel message to VextirOS: ${error}`);
      }
    }
  }

  private async sendToVextirOS(message: ChannelMessage): Promise<void> {
    // Convert to VextirOS event format
    const event = {
      type: `agent.${message.agent_id}.${message.channel_type}`,
      data: message.data,
      id: message.message_id,
      timestamp: message.timestamp,
      source: `agent.${message.agent_id}`,
      metadata: {
        channel_type: message.channel_type,
        agent_id: message.agent_id,
      },
    };

    // Send HTTP request to VextirOS event endpoint
    const response = await fetch(`${this.config.vextir_url}/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(event),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
  }

  subscribe(callback: (message: ChannelMessage) => void): void {
    this.on('message', callback);
  }

  unsubscribe(callback: (message: ChannelMessage) => void): void {
    this.off('message', callback);
  }
}

export class StatusChannel extends Channel {
  constructor(agentId: string, config: ChannelConfig) {
    super(agentId, ChannelType.STATUS, config);
  }

  async reportStatus(status: string, activity: string = "", details?: Record<string, any>): Promise<void> {
    const data = {
      status,
      activity,
      timestamp: new Date().toISOString(),
      ...details,
    };
    await this.publish(data);
  }
}

export class CommandChannel extends Channel {
  constructor(agentId: string, config: ChannelConfig) {
    super(agentId, ChannelType.COMMAND, config);
  }

  async sendCommand(command: string, params?: Record<string, any>): Promise<void> {
    const data = {
      command,
      params: params || {},
      timestamp: new Date().toISOString(),
    };
    await this.publish(data);
  }
}

export class HealthChannel extends Channel {
  constructor(agentId: string, config: ChannelConfig) {
    super(agentId, ChannelType.HEALTH, config);
  }

  async reportHealth(memoryUsageMb?: number, cpuUsagePercent?: number, customMetrics?: Record<string, any>): Promise<void> {
    const data = {
      heartbeat: new Date().toISOString(),
      memory_usage_mb: memoryUsageMb,
      cpu_usage_percent: cpuUsagePercent,
      ...customMetrics,
    };
    await this.publish(data);
  }
}

export class ActivityChannel extends Channel {
  constructor(agentId: string, config: ChannelConfig) {
    super(agentId, ChannelType.ACTIVITY, config);
  }

  async reportActivity(activityType: string, description: string, details?: Record<string, any>): Promise<void> {
    const data = {
      activity_type: activityType,
      description,
      timestamp: new Date().toISOString(),
      ...details,
    };
    await this.publish(data);
  }
}

export class ErrorChannel extends Channel {
  constructor(agentId: string, config: ChannelConfig) {
    super(agentId, ChannelType.ERROR, config);
  }

  async reportError(
    errorType: string,
    message: string,
    stackTrace?: string,
    recoverable: boolean = true,
    context?: Record<string, any>
  ): Promise<void> {
    const data = {
      error_type: errorType,
      message,
      stack_trace: stackTrace,
      recoverable,
      timestamp: new Date().toISOString(),
      ...context,
    };
    await this.publish(data);
  }
}

export class AgentChannelManager {
  private agentId: string;
  private config: ChannelConfig;
  public status: StatusChannel;
  public command: CommandChannel;
  public health: HealthChannel;
  public activity: ActivityChannel;
  public error: ErrorChannel;
  private customChannels: Map<string, Channel> = new Map();

  constructor(agentId: string, config: Partial<ChannelConfig> = {}) {
    this.agentId = agentId;
    this.config = {
      agent_id: agentId,
      enabled: config.enabled !== false, // Default to enabled
      vextir_url: config.vextir_url || process.env.VEXTIR_OS_URL,
    };

    // Create standard channels
    this.status = new StatusChannel(agentId, this.config);
    this.command = new CommandChannel(agentId, this.config);
    this.health = new HealthChannel(agentId, this.config);
    this.activity = new ActivityChannel(agentId, this.config);
    this.error = new ErrorChannel(agentId, this.config);
  }

  addCustomChannel(name: string, channel: Channel): void {
    this.customChannels.set(name, channel);
  }

  getCustomChannel(name: string): Channel | undefined {
    return this.customChannels.get(name);
  }

  async setupCommandHandler(commandHandler: (command: string, params: Record<string, any>) => Promise<void>): Promise<void> {
    this.command.subscribe(async (message: ChannelMessage) => {
      const { command, params } = message.data;
      if (command) {
        try {
          await commandHandler(command, params || {});
        } catch (error) {
          await this.error.reportError(
            "command_handler_error",
            `Error handling command ${command}: ${error}`,
            error instanceof Error ? error.stack : undefined,
            true,
            { command, params }
          );
        }
      }
    });
  }

  async initialize(): Promise<void> {
    await this.status.reportStatus("initializing", "Conseil agent starting up");
    await this.health.reportHealth();
  }

  async shutdown(): Promise<void> {
    await this.status.reportStatus("shutting_down", "Conseil agent stopping");
  }

  async setReady(): Promise<void> {
    await this.status.reportStatus("ready", "Conseil agent ready for commands");
  }

  async setBusy(activity: string): Promise<void> {
    await this.status.reportStatus("busy", activity);
  }

  async setIdle(): Promise<void> {
    await this.status.reportStatus("idle", "Ready for next command");
  }

  async reportToolExecution(toolName: string, args: Record<string, any>, success: boolean, output?: string): Promise<void> {
    await this.activity.reportActivity(
      "tool_execution",
      `Executed tool: ${toolName}`,
      {
        tool_name: toolName,
        arguments: args,
        success,
        output: output ? output.substring(0, 1000) : undefined, // Limit output size
      }
    );
  }

  isEnabled(): boolean {
    return this.config.enabled || false;
  }

  enable(): void {
    this.config.enabled = true;
  }

  disable(): void {
    this.config.enabled = false;
  }
}
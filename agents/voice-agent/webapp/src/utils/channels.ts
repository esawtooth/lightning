/**
 * Channel integration for Voice Agent
 * Reuses the same TypeScript channel system as Conseil
 */

import { AgentChannelManager } from "./channel-manager.js";

// Re-export the channel system for voice agent
export { AgentChannelManager, ChannelType } from "./channel-manager.js";

// Voice-specific channel extensions
export class VoiceAgentChannels extends AgentChannelManager {
  constructor(agentId: string, config: any = {}) {
    super(agentId, config);
  }

  async reportConversationState(state: "idle" | "listening" | "processing" | "speaking" | "ended", details?: any): Promise<void> {
    await this.activity.reportActivity(
      "conversation_state",
      `Voice conversation state: ${state}`,
      { state, ...details }
    );
  }

  async reportAudioEvent(eventType: "input_start" | "input_end" | "output_start" | "output_end", details?: any): Promise<void> {
    await this.activity.reportActivity(
      "audio_event",
      `Audio event: ${eventType}`,
      { event_type: eventType, ...details }
    );
  }

  async reportTTSEvent(eventType: "synthesis_start" | "synthesis_complete" | "playback_start" | "playback_complete", text?: string, details?: any): Promise<void> {
    await this.activity.reportActivity(
      "tts_event",
      `TTS event: ${eventType}`,
      { event_type: eventType, text: text?.substring(0, 100), ...details }
    );
  }
}

// Singleton for easy use across the voice agent
let voiceChannels: VoiceAgentChannels | null = null;

export function getVoiceChannels(): VoiceAgentChannels {
  if (!voiceChannels) {
    voiceChannels = new VoiceAgentChannels("voice-agent", {
      vextir_url: process.env.NEXT_PUBLIC_VEXTIR_OS_URL || process.env.VEXTIR_OS_URL,
      enabled: process.env.NEXT_PUBLIC_VEXTIR_CHANNELS_ENABLED !== "false",
    });
  }
  return voiceChannels;
}

export async function initializeVoiceChannels(): Promise<void> {
  const channels = getVoiceChannels();
  if (channels.isEnabled()) {
    await channels.initialize();
    await channels.setReady();
  }
}

export async function shutdownVoiceChannels(): Promise<void> {
  const channels = getVoiceChannels();
  if (channels.isEnabled()) {
    await channels.shutdown();
  }
}
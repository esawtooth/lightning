import React, { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Code, Send, Shield, Bot, Zap, Settings } from "lucide-react";

interface AgentControlPanelProps {
  ws: WebSocket | null;
  onHooksUpdate?: (hooks: any) => void;
}

const AgentControlPanel: React.FC<AgentControlPanelProps> = ({
  ws,
  onHooksUpdate,
}) => {
  // Control states
  const [vadEnabled, setVadEnabled] = useState(true);
  const [autoResponse, setAutoResponse] = useState(true);
  const [moderationEnabled, setModerationEnabled] = useState(false);
  const [customInstructions, setCustomInstructions] = useState("");
  const [responseDelay, setResponseDelay] = useState(0);
  const [selectedVoice, setSelectedVoice] = useState("ash");
  const [selectedModalities, setSelectedModalities] = useState<string[]>(["text", "audio"]);
  
  // Out-of-band response states
  const [oobInstructions, setOobInstructions] = useState("");
  const [oobMetadata, setOobMetadata] = useState("{}");
  
  // Hook states
  const [beforeResponseHook, setBeforeResponseHook] = useState("");
  const [onSpeechEndHook, setOnSpeechEndHook] = useState("");
  const [routingEnabled, setRoutingEnabled] = useState(false);

  const sendControlMessage = useCallback((action: string, data: any = {}) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "agent.control",
        action,
        ...data
      }));
    }
  }, [ws]);

  const updateHooks = useCallback(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    const hooks: any = {};

    // Before response hook
    if (beforeResponseHook || customInstructions || responseDelay > 0 || !autoResponse) {
      hooks.beforeResponse = `
        async (context) => {
          const control = { proceed: ${autoResponse} };
          ${customInstructions ? `control.instructions = "${customInstructions}";` : ''}
          ${responseDelay > 0 ? `control.delay = ${responseDelay};` : ''}
          ${selectedVoice !== 'ash' ? `control.voice = "${selectedVoice}";` : ''}
          ${selectedModalities.length === 1 ? `control.modalities = ${JSON.stringify(selectedModalities)};` : ''}
          ${beforeResponseHook}
          return control;
        }
      `;
    }

    // Speech end hook
    if (onSpeechEndHook || moderationEnabled) {
      hooks.onSpeechEnd = `
        async (context) => {
          const control = {
            createResponse: ${autoResponse},
            addToConversation: true
          };
          ${moderationEnabled ? `
          if (context.transcript.toLowerCase().includes('payment') || 
              context.transcript.toLowerCase().includes('credit card')) {
            control.validateFirst = {
              instructions: "Determine if this is a legitimate payment request. Respond with 'legitimate' or 'suspicious'.",
              onValidation: async (result) => result.includes('legitimate')
            };
          }` : ''}
          ${onSpeechEndHook}
          return control;
        }
      `;
    }

    // Routing hook
    if (routingEnabled) {
      hooks.routeResponse = `
        async (context) => {
          if (context.input.toLowerCase().includes('support')) {
            return { route: 'custom', metadata: { department: 'support' } };
          }
          if (context.input.toLowerCase().includes('sales')) {
            return { route: 'custom', metadata: { department: 'sales' } };
          }
          return { route: 'default' };
        }
      `;
    }

    ws.send(JSON.stringify({
      type: "agent.updateHooks",
      hooks
    }));

    if (onHooksUpdate) {
      onHooksUpdate(hooks);
    }
  }, [ws, beforeResponseHook, onSpeechEndHook, customInstructions, responseDelay, 
      selectedVoice, selectedModalities, autoResponse, moderationEnabled, 
      routingEnabled, onHooksUpdate]);

  const handleVadToggle = (enabled: boolean) => {
    setVadEnabled(enabled);
    sendControlMessage(enabled ? "enableVAD" : "disableVAD");
  };

  const handleAutoResponseToggle = (enabled: boolean) => {
    setAutoResponse(enabled);
    sendControlMessage("setResponseBehavior", { createResponse: enabled });
    updateHooks();
  };

  const sendOutOfBandResponse = () => {
    if (!oobInstructions.trim()) return;
    
    let metadata = {};
    try {
      metadata = JSON.parse(oobMetadata);
    } catch {
      console.error("Invalid metadata JSON");
      return;
    }

    sendControlMessage("createOutOfBandResponse", {
      instructions: oobInstructions,
      metadata
    });
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Settings className="h-5 w-5" />
          Agent Control
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden p-0">
        <Tabs defaultValue="basic" className="h-full flex flex-col">
          <TabsList className="mx-4 mb-2">
            <TabsTrigger value="basic">Basic</TabsTrigger>
            <TabsTrigger value="hooks">Hooks</TabsTrigger>
            <TabsTrigger value="oob">Out-of-Band</TabsTrigger>
          </TabsList>
          
          <TabsContent value="basic" className="flex-1 overflow-hidden px-4">
            <ScrollArea className="h-full pr-3">
              <div className="space-y-4">
                {/* VAD Control */}
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Voice Activity Detection</Label>
                    <p className="text-xs text-muted-foreground">
                      Auto-detect when user is speaking
                    </p>
                  </div>
                  <Switch
                    checked={vadEnabled}
                    onCheckedChange={handleVadToggle}
                  />
                </div>

                {/* Auto Response */}
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Auto Response</Label>
                    <p className="text-xs text-muted-foreground">
                      Automatically generate responses
                    </p>
                  </div>
                  <Switch
                    checked={autoResponse}
                    onCheckedChange={handleAutoResponseToggle}
                  />
                </div>

                {/* Moderation */}
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Content Moderation</Label>
                    <p className="text-xs text-muted-foreground">
                      Validate sensitive content
                    </p>
                  </div>
                  <Switch
                    checked={moderationEnabled}
                    onCheckedChange={(enabled) => {
                      setModerationEnabled(enabled);
                      updateHooks();
                    }}
                  />
                </div>

                {/* Custom Instructions */}
                <div className="space-y-2">
                  <Label>Per-Response Instructions</Label>
                  <Textarea
                    placeholder="Override instructions for each response"
                    className="min-h-[80px] text-sm"
                    value={customInstructions}
                    onChange={(e) => setCustomInstructions(e.target.value)}
                    onBlur={updateHooks}
                  />
                </div>

                {/* Response Delay */}
                <div className="space-y-2">
                  <Label>Response Delay (ms)</Label>
                  <Input
                    type="number"
                    min="0"
                    max="5000"
                    step="100"
                    value={responseDelay}
                    onChange={(e) => setResponseDelay(parseInt(e.target.value) || 0)}
                    onBlur={updateHooks}
                  />
                </div>

                {/* Voice Selection */}
                <div className="space-y-2">
                  <Label>Voice Override</Label>
                  <Select
                    value={selectedVoice}
                    onValueChange={(voice) => {
                      setSelectedVoice(voice);
                      updateHooks();
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"].map((v) => (
                        <SelectItem key={v} value={v}>
                          {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Modalities */}
                <div className="space-y-2">
                  <Label>Response Modalities</Label>
                  <div className="flex gap-2">
                    <Button
                      variant={selectedModalities.includes("text") ? "default" : "outline"}
                      size="sm"
                      onClick={() => {
                        setSelectedModalities(prev =>
                          prev.includes("text")
                            ? prev.filter(m => m !== "text")
                            : [...prev, "text"]
                        );
                        updateHooks();
                      }}
                    >
                      Text
                    </Button>
                    <Button
                      variant={selectedModalities.includes("audio") ? "default" : "outline"}
                      size="sm"
                      onClick={() => {
                        setSelectedModalities(prev =>
                          prev.includes("audio")
                            ? prev.filter(m => m !== "audio")
                            : [...prev, "audio"]
                        );
                        updateHooks();
                      }}
                    >
                      Audio
                    </Button>
                  </div>
                </div>

                {/* Routing */}
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Smart Routing</Label>
                    <p className="text-xs text-muted-foreground">
                      Route queries by content
                    </p>
                  </div>
                  <Switch
                    checked={routingEnabled}
                    onCheckedChange={(enabled) => {
                      setRoutingEnabled(enabled);
                      updateHooks();
                    }}
                  />
                </div>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="hooks" className="flex-1 overflow-hidden px-4">
            <ScrollArea className="h-full pr-3">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Code className="h-4 w-4" />
                    Before Response Hook
                  </Label>
                  <Textarea
                    placeholder="// Modify control object
// Example: control.instructions = 'Be concise';"
                    className="min-h-[120px] font-mono text-xs"
                    value={beforeResponseHook}
                    onChange={(e) => setBeforeResponseHook(e.target.value)}
                    onBlur={updateHooks}
                  />
                </div>

                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Zap className="h-4 w-4" />
                    On Speech End Hook
                  </Label>
                  <Textarea
                    placeholder="// Modify control object
// Example: if (context.transcript.length < 10) control.createResponse = false;"
                    className="min-h-[120px] font-mono text-xs"
                    value={onSpeechEndHook}
                    onChange={(e) => setOnSpeechEndHook(e.target.value)}
                    onBlur={updateHooks}
                  />
                </div>

                <Button 
                  onClick={updateHooks} 
                  className="w-full"
                  variant="secondary"
                >
                  Apply Hooks
                </Button>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="oob" className="flex-1 overflow-hidden px-4">
            <ScrollArea className="h-full pr-3">
              <div className="space-y-4">
                <div className="bg-muted/50 p-3 rounded-lg">
                  <p className="text-sm text-muted-foreground">
                    Out-of-band responses allow you to generate responses outside
                    the main conversation flow for classification, moderation, or
                    other purposes.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label>Instructions</Label>
                  <Textarea
                    placeholder="Classify the user's intent as 'support' or 'sales'"
                    className="min-h-[100px]"
                    value={oobInstructions}
                    onChange={(e) => setOobInstructions(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Metadata (JSON)</Label>
                  <Textarea
                    placeholder='{"type": "classification"}'
                    className="min-h-[60px] font-mono text-xs"
                    value={oobMetadata}
                    onChange={(e) => setOobMetadata(e.target.value)}
                  />
                </div>

                <Button
                  onClick={sendOutOfBandResponse}
                  className="w-full"
                  disabled={!oobInstructions.trim()}
                >
                  <Send className="h-4 w-4 mr-2" />
                  Send Out-of-Band Response
                </Button>

                <div className="space-y-2 pt-4 border-t">
                  <h4 className="text-sm font-medium">Quick Actions</h4>
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setOobInstructions("Classify this conversation's topic. Output one of: support, sales, general");
                        setOobMetadata('{"type": "classification"}');
                      }}
                    >
                      Classify Topic
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setOobInstructions("Analyze sentiment. Output: positive, negative, or neutral");
                        setOobMetadata('{"type": "sentiment"}');
                      }}
                    >
                      Check Sentiment
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setOobInstructions("Summarize the conversation so far in 2-3 sentences");
                        setOobMetadata('{"type": "summary"}');
                      }}
                    >
                      Summarize
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setOobInstructions("Extract any action items from the conversation");
                        setOobMetadata('{"type": "actions"}');
                      }}
                    >
                      Extract Actions
                    </Button>
                  </div>
                </div>
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};

export default AgentControlPanel;
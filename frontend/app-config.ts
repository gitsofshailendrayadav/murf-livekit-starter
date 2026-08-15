export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';
  audioVisualizerColor?: `#${string}`;
  audioVisualizerColorDark?: `#${string}`;
  audioVisualizerColorShift?: number;
  audioVisualizerBarCount?: number;
  audioVisualizerGridRowCount?: number;
  audioVisualizerGridColumnCount?: number;
  audioVisualizerRadialBarCount?: number;
  audioVisualizerRadialRadius?: number;
  audioVisualizerWaveLineWidth?: number;

  // agent dispatch configuration
  agentName?: string;

  // LiveKit Cloud Sandbox configuration
  sandboxId?: string;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'FinSaathi',

  pageTitle: 'FinSaathi - AI Financial Voice Assistant',

  pageDescription:
    'Your voice-first financial assistant for simple, safe and accessible financial guidance.',

  supportsChatInput: true,
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '/fin-saathi.svg',

  startButtonText: 'Start Talking',

  accent: '#0F766E',

  logoDark: '/fin-saathi.svg',

  accentDark: '#14B8A6',

  audioVisualizerType: 'aura',
  audioVisualizerColor: '#0F766E',
  audioVisualizerColorDark: '#14B8A6',

  agentName: process.env.AGENT_NAME ?? undefined,

  sandboxId: undefined,
};

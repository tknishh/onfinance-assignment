export type IntentName =
  | "revise"
  | "edit_diagrams"
  | "add_diagrams"
  | "remove_diagrams"
  | "question"
  | "new_design";

export interface DesignModel {
  system_name: string;
  summary?: string;
  actors: { name: string; description?: string }[];
  components: { name: string; layer: string; responsibility?: string }[];
  data_stores: { name: string; technology?: string; holds?: string }[];
  external_systems: { name: string; description?: string }[];
  entities: {
    name: string;
    attributes: string[];
    related_to: string[];
  }[];
  main_flow: {
    step: number;
    source: string;
    target: string;
    message: string;
    reply?: string | null;
  }[];
  deployment: {
    name: string;
    node_type?: string;
    hosts: string[];
  }[];
  lifecycle_entity?: string;
  lifecycle_states?: string[];
}

export interface DiagramResult {
  diagram_id: number;
  kind: string;
  title: string;
  plantuml: string;
  svg: string | null;
  is_valid: boolean;
  error: string | null;
  attempts: number;
  latency_ms: number;
  reused: boolean;
  warnings: string[];
  version_id?: number | null;
}

export interface MessageOut {
  id: number;
  role: string;
  content: string;
  intent: string | null;
  version_id: number | null;
  created_at: string;
}

export interface VersionOut {
  id: number;
  version_no: number;
  prompt: string;
  revisions: string[];
  instruction: string | null;
  change_summary: string | null;
  diagram_types: string[];
  design_model: DesignModel | null;
  diagrams: DiagramResult[];
  created_at: string;
}

export interface ConversationOut {
  id: number;
  title: string;
  base_prompt: string | null;
  latest_version_no: number | null;
  created_at: string;
}

export interface TimelineOut {
  conversation: ConversationOut;
  messages: MessageOut[];
  versions: VersionOut[];
}

export interface DiagramTypeInfo {
  value: string;
  category: string;
  description: string;
}

export interface ExampleInfo {
  label: string;
  prompt: string;
  diagram_types: string[];
}

export interface DiagramEvent {
  kind: string;
  title: string;
  is_valid: boolean;
  error: string | null;
  attempts: number;
  latency_ms: number;
  reused: boolean;
  warnings: string[];
  plantuml: string;
  svg: string | null;
}

export type LiveDiagramStatus = "queued" | "done" | "failed";

export interface LiveState {
  userMessage: string;
  intent?: { intent: string; instruction: string; target_kinds: string[] };
  designModel?: DesignModel | null;
  diagrams: Record<
    string,
    { status: LiveDiagramStatus; data?: DiagramEvent }
  >;
  answer?: string;
  error?: string;
}

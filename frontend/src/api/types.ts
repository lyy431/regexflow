// Shapes of the Django API's JSON responses and requests.

export type ColumnKind = "text" | "numeric" | "boolean" | "date" | "empty";

export type RegexFlag = "IGNORECASE" | "MULTILINE" | "DOTALL";
export const REGEX_FLAGS: RegexFlag[] = ["IGNORECASE", "MULTILINE", "DOTALL"];

/** The kinds of step: find and replace, standardise a format, normalise values. */
export type StepKind = "regex_replace" | "reformat" | "normalize_values";

export interface Column {
  name: string;
  kind: ColumnKind;
}

export interface ReplacementStats {
  matches: number;
  cells_changed: number;
  rows_affected: number;
  matches_by_column: Record<string, number>;
}

interface StepBase {
  id: number;
  version: number;
  instruction: string;
  explanation: string;
  source: string;
  stats: ReplacementStats;
  created_at: string;
}

export type Transformation =
  | (StepBase & {
      kind: "regex_replace";
      params: { pattern: string; flags: RegexFlag[]; replacement: string; columns: string[] };
    })
  | (StepBase & {
      kind: "reformat";
      params: { pattern: string; flags: RegexFlag[]; template: string; columns: string[] };
    })
  | (StepBase & { kind: "normalize_values"; params: { column: string; mapping: Record<string, string> } });

export interface Dataset {
  id: string;
  name: string;
  file_format: "csv" | "xlsx" | "xls";
  row_count: number;
  columns: Column[];
  current_version: number;
  transformations: Transformation[];
  created_at: string;
  updated_at: string;
}

export interface RowsPage {
  page: number;
  page_size: number;
  total_pages: number;
  total_rows: number;
  version: number;
  columns: string[];
  rows: string[][];
  /** For each row, the indexes of cells changed by the latest step (null before any step). */
  changed_cells: number[][] | null;
}

/** [start, end) offsets in Unicode code points. */
export type Span = [number, number];

export interface PreviewSample {
  row: number;
  column: string;
  before: string;
  after: string | null;
  spans: Span[];
}

interface PreviewBase {
  columns: string[];
  explanation: string;
  /** The LLM that wrote the step ("gemini:gemini-3.1-flash-lite"), or "manual". */
  source: string;
  cached: boolean;
  stats: ReplacementStats;
  samples: PreviewSample[];
}

export interface FindReplacePreview extends PreviewBase {
  kind: "regex_replace";
  pattern: string;
  flags: RegexFlag[];
  /** null when neither the user nor their instruction said what to replace matches with. */
  replacement: string | null;
}

export interface ReformatPreview extends PreviewBase {
  kind: "reformat";
  pattern: string;
  flags: RegexFlag[];
  /** Rewritten text; \g<name> inserts a captured group. */
  template: string;
}

export interface MappingRow {
  from: string;
  to: string;
  count: number;
}

export interface NormalizePreview extends PreviewBase {
  kind: "normalize_values";
  column: string;
  /** The proposed changes, most common value first. */
  mapping: MappingRow[];
}

export type Preview = FindReplacePreview | ReformatPreview | NormalizePreview;

/** Either a plain-English `instruction` (sent to the LLM) or an explicit regex `pattern`. */
export interface FindReplaceRequest {
  kind: "regex_replace";
  instruction?: string;
  pattern?: string;
  flags?: RegexFlag[];
  /** null = not specified (take it from the instruction); "" = remove the matches. */
  replacement?: string | null;
  columns?: string[];
}

/** Either a plain-English `instruction` or an explicit `pattern` with its `template`. */
export interface ReformatRequest {
  kind: "reformat";
  instruction?: string;
  pattern?: string;
  flags?: RegexFlag[];
  template?: string;
  columns?: string[];
}

/** A column and an optional goal; a `mapping` (old value -> new value) skips the LLM. */
export interface NormalizeRequest {
  kind: "normalize_values";
  column: string;
  instruction?: string;
  mapping?: Record<string, string> | null;
}

export type StepRequest = FindReplaceRequest | ReformatRequest | NormalizeRequest;

/** A step to apply, with what its preview showed. */
export type ApplyRequest = StepRequest & { explanation?: string; source?: string };

export interface ServerInfo {
  status: string;
  llm_providers: string[];
  max_upload_size_mb: number;
  dataset_ttl_hours: number;
}

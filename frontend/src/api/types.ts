// Shapes of the Django API's JSON responses and requests.

export type ColumnKind = "text" | "numeric" | "boolean" | "date" | "empty";

export type RegexFlag = "IGNORECASE" | "MULTILINE" | "DOTALL";
export const REGEX_FLAGS: RegexFlag[] = ["IGNORECASE", "MULTILINE", "DOTALL"];

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

export interface Transformation {
  id: number;
  version: number;
  kind: "regex_replace";
  instruction: string;
  params: { pattern: string; flags: RegexFlag[]; replacement: string; columns: string[] };
  explanation: string;
  source: string;
  stats: ReplacementStats;
  created_at: string;
}

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

export interface Preview {
  pattern: string;
  flags: RegexFlag[];
  columns: string[];
  /** null when neither the user nor their instruction said what to replace matches with. */
  replacement: string | null;
  explanation: string;
  /** The LLM that wrote the pattern ("gemini:gemini-3.1-flash-lite"), or "manual". */
  source: string;
  cached: boolean;
  stats: ReplacementStats;
  samples: PreviewSample[];
}

/** Either a plain-English `instruction` (sent to the LLM) or an explicit regex `pattern`. */
export interface ReplacementRequest {
  instruction?: string;
  pattern?: string;
  flags?: RegexFlag[];
  /** null = not specified (take it from the instruction); "" = remove the matches. */
  replacement?: string | null;
  columns?: string[];
}

export interface ApplyRequest extends ReplacementRequest {
  explanation?: string;
  source?: string;
}

export interface ServerInfo {
  status: string;
  llm_providers: string[];
  max_upload_size_mb: number;
  dataset_ttl_hours: number;
}

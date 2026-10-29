import { REGEX_FLAGS, type RegexFlag } from "../api/types";

const LABELS: Record<RegexFlag, string> = {
  IGNORECASE: "Ignore case",
  MULTILINE: "^ and $ match at line breaks",
  DOTALL: ". matches line breaks",
};

interface Props {
  value: RegexFlag[];
  onChange: (flags: RegexFlag[]) => void;
}

export function FlagToggles({ value, onChange }: Props) {
  function toggle(flag: RegexFlag, on: boolean) {
    onChange(REGEX_FLAGS.filter((f) => (f === flag ? on : value.includes(f))));
  }

  return (
    <div className="flags">
      {REGEX_FLAGS.map((flag) => (
        <label key={flag} className="checkbox">
          <input type="checkbox" checked={value.includes(flag)} onChange={(e) => toggle(flag, e.target.checked)} />
          {LABELS[flag]}
        </label>
      ))}
    </div>
  );
}

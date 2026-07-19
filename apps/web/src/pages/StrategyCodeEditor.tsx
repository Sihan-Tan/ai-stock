import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { oneDark } from "@codemirror/theme-one-dark";
import CodeMirror from "@uiw/react-codemirror";
import { useEffect, useMemo, useState } from "react";
import { readStoredTheme, type ThemeId } from "../theme/theme";

type EditorLanguage = "python" | "yaml";

type Props = {
  value: string;
  language: EditorLanguage;
  onChange: (value: string) => void;
  /** 编辑器高度，如 360px */
  height?: string;
  readOnly?: boolean;
};

/**
 * 策略代码编辑器：Python / YAML 语法高亮。
 * @param props 值、语言与变更回调
 */
export function StrategyCodeEditor({
  value,
  language,
  onChange,
  height = "360px",
  readOnly = false,
}: Props) {
  const [theme, setTheme] = useState<ThemeId>(() => readStoredTheme());

  useEffect(() => {
    /**
     * 跟随壳层 data-theme 变化切换编辑器主题。
     */
    const sync = () => {
      const attr = document.documentElement.getAttribute("data-theme");
      setTheme(attr === "desk-light" ? "desk-light" : "desk-dark");
    };
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    return () => obs.disconnect();
  }, []);

  const extensions = useMemo(
    () => [language === "python" ? python() : yaml()],
    [language]
  );

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--desk-line)]">
      <CodeMirror
        value={value}
        height={height}
        theme={theme === "desk-dark" ? oneDark : "light"}
        extensions={extensions}
        editable={!readOnly}
        basicSetup={{
          lineNumbers: true,
          foldGutter: true,
          highlightActiveLine: true,
          history: true,
        }}
        onChange={onChange}
        className="text-sm"
      />
    </div>
  );
}

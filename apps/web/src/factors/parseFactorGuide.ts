/** 因子详述分节。 */
export type FactorGuideSection = {
  title: string;
  body: string;
};

/**
 * 将【标题】正文拆成章节；无标记时整段作为无标题正文。
 * @param text API description
 */
export function parseFactorGuide(text: string): FactorGuideSection[] {
  const raw = (text || "").trim();
  if (!raw) return [{ title: "", body: "暂无说明" }];
  const re = /【([^】]+)】/g;
  const indices: { title: string; start: number; bodyStart: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    indices.push({ title: m[1], start: m.index, bodyStart: m.index + m[0].length });
  }
  if (indices.length === 0) return [{ title: "", body: raw }];

  const sections: FactorGuideSection[] = [];
  if (indices[0].start > 0) {
    const head = raw.slice(0, indices[0].start).trim();
    if (head) sections.push({ title: "", body: head });
  }
  for (let i = 0; i < indices.length; i++) {
    const end = i + 1 < indices.length ? indices[i + 1].start : raw.length;
    const body = raw.slice(indices[i].bodyStart, end).trim();
    sections.push({ title: indices[i].title, body });
  }
  return sections;
}

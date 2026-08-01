/**
 * 通达信 SMA(X,N,1)：递推 Y = (X + (N-1) * Y') / N。
 * @param values 输入序列
 * @param n 周期 N
 * @returns 与输入等长的 SMA 序列
 */
export function smaTdx(values: number[], n: number): number[] {
  if (values.length === 0) return [];
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    if (i === 0) {
      out.push(values[0]!);
    } else {
      out.push((values[i]! + (n - 1) * out[i - 1]!) / n);
    }
  }
  return out;
}

/**
 * 滚动最高 HHV；窗口不足时使用已有前缀。
 * @param values 输入序列
 * @param n 窗口长度
 */
export function hhv(values: number[], n: number): number[] {
  return values.map((_, i) => {
    const start = Math.max(0, i - n + 1);
    let max = values[start]!;
    for (let j = start + 1; j <= i; j++) {
      max = Math.max(max, values[j]!);
    }
    return max;
  });
}

/**
 * 滚动最低 LLV；窗口不足时使用已有前缀。
 * @param values 输入序列
 * @param n 窗口长度
 */
export function llv(values: number[], n: number): number[] {
  return values.map((_, i) => {
    const start = Math.max(0, i - n + 1);
    let min = values[start]!;
    for (let j = start + 1; j <= i; j++) {
      min = Math.min(min, values[j]!);
    }
    return min;
  });
}

/**
 * REF(X,N) 在下标 i 处的值；越界返回 null。
 * @param values 输入序列
 * @param i 当前下标
 * @param n 回溯根数
 */
export function refAt(
  values: number[],
  i: number,
  n: number,
): number | null {
  const j = i - n;
  if (j < 0 || j >= values.length) return null;
  return values[j]!;
}

/**
 * FILTER(cond,N)：条件为真时输出真，随后 N 根内不再触发。
 * @param cond 条件序列
 * @param n 抑制根数（通达信 FILTER 第二参数）
 */
export function filterSignal(cond: boolean[], n: number): boolean[] {
  const out = cond.map(() => false);
  let suppressUntil = -1;
  for (let i = 0; i < cond.length; i++) {
    if (i <= suppressUntil) continue;
    if (cond[i]) {
      out[i] = true;
      suppressUntil = i + n;
    }
  }
  return out;
}

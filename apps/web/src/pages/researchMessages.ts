/** 将历史与用户输入组装为 API messages */
export function buildChatMessages(
  history: Array<{ role: "user" | "assistant"; content: string }>,
  userText: string,
): Array<{ role: string; content: string }> {
  return [...history.map((m) => ({ role: m.role, content: m.content })), { role: "user", content: userText }];
}

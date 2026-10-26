import type { ReplyVariants } from '../../shared/api/api';

/** Never turn a malformed/stale family into navigation to another answer by array position. */
export function validReplyVariants(value: unknown, conversationId: string | null, messageId?: number): ReplyVariants | undefined {
  if (!value || typeof value !== 'object' || !conversationId || !messageId) return;
  const data = value as Partial<ReplyVariants>;
  if (!Array.isArray(data.choices) || data.choices.length < 2 || data.choices.length > 20 || !Number.isInteger(data.index)
    || data.index! < 0 || data.index! >= data.choices.length) return;
  const seen = new Set<string>();
  for (const choice of data.choices) {
    if (!choice || typeof choice.conversation_id !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(choice.conversation_id)
      || !Number.isSafeInteger(choice.message_id) || choice.message_id <= 0) return;
    const key = `${choice.conversation_id}:${choice.message_id}`;
    if (seen.has(key)) return;
    seen.add(key);
  }
  const current = data.choices[data.index!];
  if (current.conversation_id !== conversationId || current.message_id !== messageId) return;
  return data as ReplyVariants;
}

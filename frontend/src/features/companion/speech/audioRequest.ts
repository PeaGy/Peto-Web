/** Giới hạn thời gian chờ tiếng/chép lời; hủy vẫn kết thúc ngay dù nguồn không xử lý tín hiệu hủy. */
export function audioRequest<T>(task: (signal: AbortSignal) => Promise<T>, parent: AbortSignal,
  timeoutMs: number, timeoutError: Error): Promise<T> {
  if (parent.aborted) return Promise.reject(parent.reason);
  return new Promise<T>((resolve, reject) => {
    const controller = new AbortController();
    let finished = false;
    const finish = (error: unknown, value?: T) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      parent.removeEventListener('abort', aborted);
      controller.abort(error);
      if (error !== undefined) reject(error);
      else resolve(value as T);
    };
    const aborted = () => finish(parent.reason ?? new DOMException('Đã dừng.', 'AbortError'));
    const timer = setTimeout(() => finish(timeoutError), timeoutMs);
    parent.addEventListener('abort', aborted, { once: true });
    Promise.resolve().then(() => {
      controller.signal.throwIfAborted();
      return task(controller.signal);
    }).then(value => finish(undefined, value), error => finish(error));
  });
}

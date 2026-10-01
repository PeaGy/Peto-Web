// Bộ gom âm thanh micro cho phần Peto nghe: chạy trong luồng âm thanh của trình duyệt, gom 2048 mẫu (khoảng 43 ms
// ở 48 kHz) rồi mới gửi sang trang, để trang không phải nhận vài trăm tin mỗi giây.
class PetoMicCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      let offset = 0;
      while (offset < channel.length) {
        const count = Math.min(channel.length - offset, this.buffer.length - this.filled);
        this.buffer.set(channel.subarray(offset, offset + count), this.filled);
        this.filled += count;
        offset += count;
        if (this.filled === this.buffer.length) {
          this.port.postMessage(this.buffer.slice(0));
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("peto-mic-capture", PetoMicCapture);

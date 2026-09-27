import { afterEach, vi } from 'vitest';
import { cleanup, configure } from '@testing-library/react';

// findBy/waitFor chờ tối đa 3 giây thay vì 1: phần tải riêng (React.lazy) hiện sau một nhịp, lâu hơn khi máy đang chạy
// cả bộ test song song.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
if (typeof Element !== 'undefined') {
  Element.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.show = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
}

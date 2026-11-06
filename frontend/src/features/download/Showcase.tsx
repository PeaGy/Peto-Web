import { useState, type ReactNode } from 'react';
import { Icon } from '../docs/docsShared';
import { PETO_MARK_PATH, PETO_MARK_VIEWBOX } from './petoMark';

/** Hình Peto một màu của ứng dụng (như thanh bên của Peto Agent). */
export function PetoMark({ size }: { size: number }) {
  return <svg className="dl-mark" width={size} height={Math.round(size * 94 / 138)} viewBox={PETO_MARK_VIEWBOX}
    aria-hidden="true" focusable="false"><path fill="currentColor" fillRule="evenodd" d={PETO_MARK_PATH} /></svg>;
}

/**
 * Cửa sổ Peto Agent dựng bằng HTML (không phải ảnh chụp), co theo bề rộng khung bằng đơn vị --u. Chữ giao diện giữ tiếng
 * Anh như ứng dụng thật; hội thoại là ví dụ. Nghiêng theo cuộn nhờ data-tilt (xem scrollMotion.ts).
 */
export function AppPreview() {
  return <div className="dl-app" role="img"
    aria-label="Ảnh minh họa Peto Agent: thanh bên có logo Peto, phiên “Sửa lỗi build” với các bước Peto đã chạy và câu trả lời.">
    <div className="dl-app-win" data-tilt="" aria-hidden="true">
      <div className="dl-app-cap"><span>Application</span><span>Edit</span><span className="dl-app-ctl"><span>—</span><span>☐</span><span>✕</span></span></div>
      <div className="dl-app-side">
        <div className="dl-app-brand"><PetoMark size={26} /><span>Peto Agent</span></div>
        <div className="dl-app-new">＋ New Session</div>
        <div className="dl-app-item">◇ Plugins</div>
        <div className="dl-app-item">◷ Automation tasks</div>
        <div className="dl-app-item">⊞ More</div>
        <div className="dl-app-label">Workspaces</div>
        <div className="dl-app-item">▭ peto-web</div>
        <div className="dl-app-item dl-app-sub" data-on="">Sửa lỗi build</div>
        <div className="dl-app-item dl-app-sub">Báo cáo tuần</div>
        <div className="dl-app-item dl-app-sub">Dọn ảnh trùng</div>
        <div className="dl-app-item">▭ do-an-tot-nghiep</div>
        <div className="dl-app-me"><i />Bạn</div>
      </div>
      <div className="dl-app-main">
        <div className="dl-app-head">Sửa lỗi build <span>Workspace Write</span></div>
        <div className="dl-app-chat">
          <div className="dl-app-user">Build bị lỗi ở bước typecheck, sửa giúp mình rồi chạy test lại nhé.</div>
          <div className="dl-app-done">Completed in 48s ›</div>
          <div className="dl-app-tools">
            <span>Đọc 4 tệp</span><span>Sửa <code>src/api/client.ts</code></span>
            <span>Chạy <code>pnpm test</code> · <b>128 qua</b></span>
          </div>
          <div className="dl-app-answer">Đã sửa xong. Lỗi do <code>fetchUser</code> có thể trả về <code>undefined</code>, nhưng
            chỗ gọi coi như luôn có dữ liệu.
            <ul><li>Thêm kiểm tra rỗng trong <code>client.ts</code>.</li><li>Chạy lại typecheck và test: không còn lỗi.</li></ul>
          </div>
          <div className="dl-app-diff">
            <div className="dl-app-diff-head">src/api/client.ts</div>
            <div data-kind="del">-  return user.name</div>
            <div data-kind="add">+  if (user === undefined) return null</div>
            <div data-kind="add">+  return user.name</div>
          </div>
        </div>
        <div className="dl-app-foot">
          <div className="dl-app-compose">
            <p>Message or run a task, / commands, @ files or sessions</p>
            <div className="dl-app-row"><span>＋</span><span>⛉ <b>Workspace Write</b></span>
              <span className="dl-app-model"><b>Peto</b> Default</span><span className="dl-app-send">↑</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>;
}

/** Thẻ tính năng có minh họa chạy lặp; nút ở góc dừng và chạy lại minh họa (chuyển động dài hơn 5 giây phải dừng được). */
function DemoCard({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  const [paused, setPaused] = useState(false);
  return <article className="dl-card" data-reveal="30" data-paused={paused ? '' : undefined}>
    <h3>{title}</h3>
    <p>{text}</p>
    <button type="button" className="dl-pause" aria-pressed={paused}
      aria-label={paused ? 'Chạy lại minh họa' : 'Tạm dừng minh họa'} onClick={() => setPaused(value => !value)}>
      <Icon name={paused ? 'play' : 'pause'} size={14} />
    </button>
    <div className="dl-demo" aria-hidden="true">{children}</div>
  </article>;
}

export function FeatureCards() {
  return <div className="dl-cards">
    <DemoCard title="Làm việc trong thư mục dự án"
      text="Peto đọc mã và tài liệu, sửa đúng chỗ cần sửa, tạo tệp mới khi bạn yêu cầu. Thay đổi nào cũng hiện rõ để bạn duyệt.">
      <div className="dl-files">
        <div className="dl-file"><span style={{ background: '#7a74d8' }}>MD</span><code>README.md</code><em>Đã đọc</em></div>
        <div className="dl-file"><span style={{ background: '#3299ed' }}>TS</span><code>src/api/client.ts</code><em><b>+4</b> −1</em></div>
        <div className="dl-file"><span style={{ background: '#40ac7a' }}>TS</span><code>tests/client.test.ts</code><em><b>Mới</b></em></div>
      </div>
    </DemoCard>
    <DemoCard title="Chạy lệnh và tự kiểm tra"
      text="Peto chạy build, test hay script của bạn, đọc kết quả rồi sửa tiếp cho tới khi xong việc.">
      <div className="dl-term">
        <div>PS&gt; pnpm test</div><div data-dim="">RUN  v4.1.11</div>
        <div data-ok="">✓ src/api/client.test.ts (12)</div><div data-ok="">✓ src/app.test.ts (9)</div>
        <div>Test Files  <span data-ok="">2 passed</span></div><div>Tests  <span data-ok="">128 passed</span> · 3.4s</div>
      </div>
    </DemoCard>
    <DemoCard title="Tài khoản Peto, không cần khóa API"
      text="Đăng nhập một lần bằng tài khoản Peto Web rồi chọn Peto, Luna hay Haiku. Bước dùng tính chung hạn mức hằng ngày với Peto Agent CLI.">
      <div className="dl-acct">
        <div className="dl-who"><i /><span>Đã đăng nhập Peto<small>Thiết bị: Laptop-cua-ban</small></span></div>
        <div className="dl-pick"><span>Peto</span><span>Luna</span><span>Haiku</span></div>
      </div>
    </DemoCard>
    <DemoCard title="Bạn quyết định Peto được làm gì"
      text="Read Only để Peto chỉ đọc, Workspace Write để sửa trong thư mục dự án, Full access khi bạn tin việc đang giao.">
      <div className="dl-modes">
        <span><Icon name="file" size={15} />Read Only</span>
        <span><Icon name="code" size={15} />Workspace Write</span>
        <span><Icon name="spark" size={15} />Full access</span>
      </div>
    </DemoCard>
  </div>;
}

/** Hộp cảnh báo SmartScreen thu nhỏ cho bước 2. Chữ tiếng Anh như Windows hiện. */
export function SmartScreen() {
  return <div className="dl-smart" aria-hidden="true">
    <b>Windows protected your PC</b>
    Microsoft Defender SmartScreen prevented an unrecognized app from starting.
    <div><span>More info</span><span data-run="">Run anyway</span></div>
  </div>;
}

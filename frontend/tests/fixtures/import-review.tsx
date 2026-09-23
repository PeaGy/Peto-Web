// Development-only visual fixture; contains no user model or saved assets.
import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import CharacterImportReview from '../../src/CharacterImportReview';
import type { Live2DImportReport } from '../../src/characterImport';
import '../../src/styles.css';
const report: Live2DImportReport = {
  name: 'Model mẫu', entry: 'Nhân vật/model.model3.json', bytes: 55 * 1024 * 1024, files: 25,
  motions: { found: ['motions/idle.motion3.json'], referenced: [] },
  expressions: { found: ['expressions/smile.exp3.json', 'expressions/sad.exp3.json'], referenced: [] },
  textures: Array.from({ length: 11 }, (_, i) => `textures/${i}.png`), parameters: 197, physics: true,
  issues: [{ severity: 'warning', message: 'Tệp MOC lớn hơn 10 MB, có thể tải chậm hoặc giảm độ mượt trên điện thoại.' },
    { severity: 'warning', message: '2 tệp biểu cảm chưa được khai báo trong .model3.json nên sẽ không được nhập. Hãy bổ sung khai báo nếu muốn sử dụng.', paths: ['expressions/smile.exp3.json', 'expressions/sad.exp3.json'] }],
  prepared: { model: { id: 'fixture', name: 'Model mẫu', format: 'live2d', bytes: 0, createdAt: 0 }, assets: { id: 'fixture', entry: '', files: [] } },
};
function Fixture() {
  const [open, setOpen] = useState(true);
  return <><button onClick={() => setOpen(true)}>Mở xem trước</button>{open && <CharacterImportReview report={report} busy={false} error="" onCancel={() => setOpen(false)} onConfirm={() => setOpen(false)} />}</>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);

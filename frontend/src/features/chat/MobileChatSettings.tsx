import { useState } from 'react';
import type { Effort, ModelOption } from '../../shared/api/api';
import { ComposerSheet } from './ComposerSheet';

export default function MobileChatSettings({ model, models, onModelChange, effort, efforts, onEffortChange, disabled }: {
  model: string; models: ModelOption[]; onModelChange: (model: string) => void;
  effort: Effort; efforts: { value: Effort; label: string; hint: string }[]; onEffortChange: (effort: Effort) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const modelLabel = models.find(item => item.key === model)?.label ?? 'Peto';
  const effortLabel = efforts.find(item => item.value === effort)?.label;
  return <>
    <button type="button" className="mobile-model-trigger" aria-haspopup="dialog" aria-expanded={open && !disabled}
      aria-label={`Model: ${modelLabel}, Mức suy nghĩ: ${effortLabel}`} disabled={disabled} onClick={() => setOpen(true)}>
      <strong>{modelLabel}</strong> <span>{effortLabel}</span>
    </button>
    <ComposerSheet open={open && !disabled} label="Model và mức suy nghĩ" onClose={() => setOpen(false)}>
      {models.length > 0 && <div role="group" aria-label="Model">
        {models.map(item => <button type="button" className="sheet-option" key={item.key}
          aria-pressed={item.key === model} onClick={() => { onModelChange(item.key); setOpen(false); }}>
          <span>{item.label}<small>{item.description}</small></span>
        </button>)}
      </div>}
      <p className="sheet-heading">Mức suy nghĩ</p>
      <div role="group" aria-label="Mức suy nghĩ">
        {efforts.map(item => <button type="button" className="sheet-option" key={item.value}
          aria-pressed={item.value === effort} onClick={() => { onEffortChange(item.value); setOpen(false); }}>
          {item.label}
        </button>)}
      </div>
    </ComposerSheet>
  </>;
}

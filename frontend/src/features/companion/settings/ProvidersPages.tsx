/**
 * Cài đặt Companion → Nhà cung cấp và Mô-đun → Bộ não (chủ web chọn biến thể "Như AIRI" ngày 13/10/2026, theo Settings →
 * Providers và Modules → Consciousness của AIRI).
 *
 * - Nhà cung cấp: tab Bộ não / Giọng nói / Nghe, mỗi nhà một thẻ có chấm "đã kết nối"; bấm thẻ thì mở trang của nhà đó để
 *   nhập khóa. Khóa giọng nói và nghe trước đây nhập ngay ở trang Giọng nói và Nghe; giờ nhập ở đây, hai trang kia chỉ còn
 *   chọn nguồn, model và giọng.
 * - Bộ não: chọn Peto (mặc định) hay một nhà đã kết nối, và model. Lượt dùng khóa riêng không đọc, không ghi Trí nhớ.
 * - Khóa Tavily cho nhà không có tìm kiếm riêng nằm ở trang Tra web, như AIRI.
 */
import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { checkProvider } from '../../../shared/api/api';
import { Dropdown, Field } from '../speech/voiceUi';
import { KEY_PROVIDERS, updateKeyConfig, useKeyConfigs, keyReady, type KeyConfig } from '../speech/voiceProviders';
import { HEARING_PROVIDERS, hearingKeyReady } from '../speech/hearingProviders';
import { CHAT_PROVIDERS, chatProvider, providerName, providerUses, type ChatProviderInfo } from '../providers/catalog';
import { connected, useBrain, useModels, writeBrain, writeModels } from '../providers/brain';
import { SettingsGroup, SettingsRow } from '../../settings/settingsUi';
import { useCompanionSearch } from '../companionSearch';

type Tab = 'chat' | 'voice' | 'hearing';
type Price = 'all' | 'free' | 'paid';
// Tab đang xem, giữ khi mở một nhà cung cấp rồi quay lại.
let lastTab: Tab = 'chat';

const TABS: { id: Tab; label: string }[] = [
  { id: 'chat', label: 'Bộ não' }, { id: 'voice', label: 'Giọng nói' }, { id: 'hearing', label: 'Nghe' },
];

const RELAY: Partial<Record<string, string>> = {
  stepfun: 'StepFun không cho trình duyệt gọi thẳng',
  qwen: 'Alibaba Cloud không cho trình duyệt tự lấy âm thanh',
};

interface CardData {
  id: string;
  name: string;
  site: string;
  badges: string[];
  on: boolean;
  /** Đã có khóa nhưng chưa kiểm tra (bộ não cần kiểm tra mới chọn được). */
  unchecked?: boolean;
  recommended?: boolean;
  free?: boolean;
  /** Thẻ không cần khóa: mở trang mô-đun thay cho trang nhà cung cấp. */
  module?: 'brain' | 'voice' | 'hearing';
}

function ProviderCard({ card, index, onOpen }: { card: CardData; index: number; onOpen: () => void }) {
  return (
    <button type="button" className="companion-provider-card" style={{ '--delay': `${index * 40}ms` } as CSSProperties}
      onClick={onOpen}>
      <span className="companion-provider-body">
        <strong>{card.name}</strong>
        <span>{card.site}</span>
        <span className="companion-provider-badges">
          {card.recommended && <b className="companion-provider-badge rec">Gợi ý</b>}
          {card.badges.map(badge => <b key={badge} className="companion-provider-badge">{badge}</b>)}
        </span>
      </span>
      <span className="companion-provider-foot">
        <i className={card.on ? 'companion-provider-dot on' : 'companion-provider-dot'} aria-hidden="true" />
        {card.module ? 'Không cần khóa' : card.on ? 'Đã kết nối' : card.unchecked ? 'Chưa kiểm tra' : 'Chưa có khóa'}
      </span>
    </button>
  );
}

export function ProvidersPage({ onOpenProvider, onOpenModule }: {
  onOpenProvider: (id: string) => void;
  onOpenModule: (page: 'brain' | 'voice' | 'hearing') => void;
}) {
  const [tab, setTab] = useState<Tab>(lastTab);
  const [price, setPrice] = useState<Price>('all');
  const keys = useKeyConfigs();
  const models = useModels();
  const pick = (next: Tab) => { lastTab = next; setTab(next); setPrice('all'); };
  const cards: CardData[] = tab === 'chat' ? [
    { id: 'peto', name: 'Peto', site: 'Grok qua tài khoản Peto', badges: ['Có trí nhớ', 'Tra web'], on: true, recommended: true,
      free: true, module: 'brain' },
    ...CHAT_PROVIDERS.map(item => ({
      id: item.id, name: item.name, site: item.site, free: item.free, on: connected(item.id, keys[item.id], models),
      unchecked: Boolean(keys[item.id]?.key?.trim()),
      badges: [item.free ? 'Có gói miễn phí' : 'Trả phí', item.search === 'native' ? 'Tra web có sẵn' : 'Tra web qua Tavily'],
    })),
  ] : tab === 'voice' ? [
    { id: 'official', name: 'Giọng Peto', site: 'Tài khoản Peto, có hạn mức mỗi tháng', badges: ['Miễn phí'], on: true,
      recommended: true, free: true, module: 'voice' },
    { id: 'home', name: 'Máy nhà của Peto', site: 'Khi máy nhà đang bật', badges: ['Miễn phí'], on: true, free: true,
      module: 'voice' },
    ...KEY_PROVIDERS.map(item => ({
      id: item.id, name: item.name, site: item.desc, on: keyReady(item, keys[item.id]),
      badges: [item.route === 'relay' ? 'Qua máy chủ Peto' : 'Gọi thẳng'],
    })),
  ] : [
    { id: 'browser', name: 'Có sẵn trong trình duyệt', site: 'Chrome, Edge, Safari', badges: ['Miễn phí'], on: true,
      recommended: true, free: true, module: 'hearing' },
    ...HEARING_PROVIDERS.map(item => ({
      id: item.id, name: item.name, site: item.desc, free: item.free, on: hearingKeyReady(item, keys[item.id]),
      badges: [item.free ? 'Có gói miễn phí' : 'Trả phí'],
    })),
  ];
  // Danh sách giọng nói không có thông tin gói miễn phí, nên tab đó không có bộ lọc giá.
  const filtering = tab !== 'voice';
  const shown = cards.filter(card => !filtering || price === 'all' || (price === 'free') === Boolean(card.free));
  return (
    <>
      <div className="companion-provider-intro">
        <strong>Mới dùng lần đầu?</strong>
        <span>Không cần làm gì: Peto trả lời bằng Grok qua tài khoản Peto. Có khóa API riêng thì thêm ở đây, rồi chọn trong
          Mô-đun → Bộ não, Giọng nói hay Nghe.</span>
      </div>
      <div className="companion-provider-tabs" role="tablist" aria-label="Loại nhà cung cấp">
        {TABS.map(item => (
          <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? 'on' : ''}
            onClick={() => pick(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      {filtering && (
        <div className="companion-provider-filters" role="group" aria-label="Lọc theo giá">
          <span>Giá:</span>
          {(['all', 'free', 'paid'] as Price[]).map(item => (
            <button key={item} type="button" aria-pressed={price === item} className={price === item ? 'on' : ''}
              onClick={() => setPrice(item)}>
              {item === 'all' ? 'Tất cả' : item === 'free' ? 'Có gói miễn phí' : 'Trả phí'}
            </button>
          ))}
        </div>
      )}
      <div className="companion-provider-grid" role="tabpanel">
        {shown.map((card, index) => (
          <ProviderCard key={`${tab}-${card.id}`} card={card} index={index}
            onOpen={() => (card.module ? onOpenModule(card.module) : onOpenProvider(card.id))} />
        ))}
      </div>
    </>
  );
}

function useIds() {
  return { endpoint: useId(), key: useId(), deployment: useId(), url: useId(), region: useId() };
}

/** Trang một nhà cung cấp: các ô khóa, nút kiểm tra (bộ não), và khóa này dùng cho những gì. */
export function ProviderPage({ id, onOpenModule }: { id: string; onOpenModule: (page: 'brain' | 'voice' | 'hearing') => void }) {
  const ids = useIds();
  const keys = useKeyConfigs();
  const models = useModels();
  const config: KeyConfig = keys[id] ?? {};
  const chat = chatProvider(id);
  const voice = KEY_PROVIDERS.find(item => item.id === id);
  const hearing = HEARING_PROVIDERS.find(item => item.id === id);
  const uses = providerUses(id);
  const name = providerName(id);
  const saved = Object.values(config).some(value => typeof value === 'string' && value.trim());
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const update = (patch: KeyConfig) => {
    updateKeyConfig(id, { ...config, ...patch });
    setError('');
    // Đổi khóa hay địa chỉ thì lần kiểm tra cũ không còn đúng.
    if (chat && ('key' in patch || 'endpoint' in patch) && models[id]) writeModels(id, null);
  };
  const forget = () => {
    updateKeyConfig(id, null);
    writeModels(id, null);
    setError('');
  };
  async function check() {
    if (!chat) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setChecking(true);
    setError('');
    try {
      const result = await checkProvider(id, (config.key ?? '').trim(), config.endpoint?.trim(), controller.signal);
      writeModels(id, result.models);
    } catch (reason) {
      if (controller.signal.aborted) return;
      writeModels(id, null);
      setError(reason instanceof Error ? reason.message : 'Chưa kiểm tra được khóa. Thử lại sau nhé.');
    } finally {
      if (abort.current === controller) setChecking(false);
    }
  }

  const ready = chat ? connected(id, config, models) : voice ? keyReady(voice, config) : hearing ? hearingKeyReady(hearing, config) : false;
  const region = voice?.region ?? (hearing?.needsRegion ? { label: 'Vùng', placeholder: 'southeastasia' } : undefined);
  const keyOptional = voice?.keyOptional || hearing?.keyOptional;
  const site = chat?.keySite ?? voice?.site ?? hearing?.site ?? '';
  const keyHint = chat?.keyHint ?? voice?.keyHint ?? hearing?.keyHint ?? '';
  const needsBaseUrl = voice?.needsBaseUrl || hearing?.needsBaseUrl;
  const checked = chat ? models[id] : undefined;

  return (
    <div className="companion-settings-groups">
      <SettingsGroup title="Khóa API">
        <div className="companion-provider-form">
          {chat?.fields.includes('endpoint') && (
            <Field id={ids.endpoint} label="Địa chỉ tài nguyên" hint="Dạng https://<tên>.openai.azure.com, ở trang tài nguyên trên Azure.">
              <input id={ids.endpoint} type="url" inputMode="url" placeholder="https://<tên>.openai.azure.com" spellCheck={false}
                autoComplete="off" value={config.endpoint ?? ''} onChange={event => update({ endpoint: event.target.value })} />
            </Field>
          )}
          {needsBaseUrl && (
            <Field id={ids.url} label="Địa chỉ máy chủ" hint="Địa chỉ gốc của API, thường kết thúc bằng /v1.">
              <input id={ids.url} type="url" inputMode="url" placeholder="https://…/v1" spellCheck={false} autoComplete="off"
                value={config.baseUrl ?? ''} onChange={event => update({ baseUrl: event.target.value })} />
            </Field>
          )}
          <Field id={ids.key} label={keyOptional ? 'Khóa API (nếu máy chủ cần)' : `Khóa API ${name}`}
            hint={(
              <span className="voice-key-hint">
                <span>{keyOptional ? 'Để trống nếu máy chủ không cần khóa.' : `Lấy khóa ở ${site}.`}</span>
                {saved && <button type="button" className="voice-link" onClick={forget}>Xóa khóa khỏi trình duyệt</button>}
              </span>
            )}>
            <input id={ids.key} type="password" placeholder={keyHint} spellCheck={false} autoComplete="off"
              value={config.key ?? ''} onChange={event => update({ key: event.target.value })} />
          </Field>
          {region?.options ? (
            <Field id={ids.region} label={region.label}>
              <Dropdown id={ids.region} value={config.region || region.options[0].value}
                onChange={value => update({ region: value })} options={region.options} />
            </Field>
          ) : region && (
            <Field id={ids.region} label={region.label} hint="Vùng của tài nguyên Speech trên Azure.">
              <input id={ids.region} type="text" placeholder={region.placeholder} spellCheck={false} autoComplete="off"
                value={config.region ?? ''} onChange={event => update({ region: event.target.value })} />
            </Field>
          )}
          {chat?.fields.includes('deployment') && (
            <Field id={ids.deployment} label="Tên bản triển khai" hint="Tên bạn đặt khi triển khai model trong Azure AI Foundry.">
              <input id={ids.deployment} type="text" placeholder="gpt-4o-mini" spellCheck={false} autoComplete="off"
                value={config.deployment ?? ''} onChange={event => update({ deployment: event.target.value })} />
            </Field>
          )}
          {chat && (
            <div className="companion-provider-check">
              <button type="button" className="voice-primary" disabled={!config.key?.trim() || checking} onClick={() => void check()}>
                {checking ? 'Đang kiểm tra…' : 'Kiểm tra kết nối'}
              </button>
              {ready && <span className="voice-line" role="status"><i className="voice-dot on" />
                {checked?.length ? `Đã kết nối · ${checked.length} model` : 'Đã kết nối'}</span>}
              {checked && !ready && chat.id === 'azure-openai' && (
                <span className="voice-line" role="status"><i className="voice-dot" />Khóa dùng được; điền tên bản triển khai.</span>
              )}
              {error && <span className="voice-error" role="alert">{error}</span>}
            </div>
          )}
          <p className="voice-note">
            Khóa chỉ lưu trong trình duyệt này.
            {chat && ` Bộ não: mỗi lượt, khóa đi qua máy chủ Peto tới ${chat.name} rồi bị bỏ, không lưu và không ghi log.`}
            {(voice || hearing) && (RELAY[id]
              ? ` Giọng nói: ${RELAY[id]}, nên khóa đi qua máy chủ Peto, không lưu và không ghi log.`
              : ` ${uses.includes('voice') && uses.includes('hearing') ? 'Giọng nói và nghe' : uses.includes('voice') ? 'Giọng nói' : 'Nghe'}:`
                + ` trình duyệt gọi thẳng ${name}, máy chủ Peto không nhận khóa.`)}
          </p>
        </div>
      </SettingsGroup>
      <SettingsGroup title="Dùng cho">
        {uses.includes('chat') && (
          <SettingsRow label="Bộ não Companion"
            desc={`Tra web: ${chat!.search === 'native' ? `dùng tìm kiếm có sẵn của ${chat!.name}` : 'cần khóa Tavily ở Mô-đun → Tra web'}.`}>
            <button type="button" className="voice-primary" disabled={!ready} onClick={() => onOpenModule('brain')}>Chọn ở Bộ não</button>
          </SettingsRow>
        )}
        {uses.includes('voice') && (
          <SettingsRow label="Giọng nói" desc="Chọn model và giọng, rồi nghe thử ở Mô-đun → Giọng nói.">
            <button type="button" className="voice-primary" onClick={() => onOpenModule('voice')}>Mở Giọng nói</button>
          </SettingsRow>
        )}
        {uses.includes('hearing') && (
          <SettingsRow label="Nghe" desc="Chọn nguồn nghe và nghe thử ở Mô-đun → Nghe.">
            <button type="button" className="voice-primary" onClick={() => onOpenModule('hearing')}>Mở Nghe</button>
          </SettingsRow>
        )}
      </SettingsGroup>
    </div>
  );
}

/** Mô-đun → Bộ não: ai trả lời trong Companion. */
export function BrainPage({ onOpenProviders }: { onOpenProviders: () => void }) {
  const providerId = useId();
  const modelId = useId();
  const brain = useBrain();
  const keys = useKeyConfigs();
  const models = useModels();
  const search = useCompanionSearch();
  const available = CHAT_PROVIDERS.filter(item => connected(item.id, keys[item.id], models));
  const current = brain.provider === 'peto' ? undefined : available.find(item => item.id === brain.provider);
  const list = current ? current.id === 'azure-openai' ? [keys[current.id]?.deployment?.trim() ?? ''] : models[current.id] ?? [] : [];
  const model = current ? (current.id === 'azure-openai' ? list[0] : list.includes(brain.model) ? brain.model : list[0] ?? '') : '';
  return (
    <div className="companion-settings-groups">
      <SettingsGroup title="Ai trả lời trong Companion">
        <SettingsRow label="Nhà cung cấp" htmlFor={providerId} labelId={`${providerId}-label`}
          desc={available.length ? undefined : 'Chưa có nhà cung cấp nào đã kết nối, nên chỉ có Peto.'}>
          <div className="settings-dropdown">
            <Dropdown id={providerId} value={current?.id ?? 'peto'}
              onChange={value => {
                const next = available.find(item => item.id === value);
                writeBrain(next ? { provider: next.id, model: models[next.id]?.[0] ?? '' } : { provider: 'peto', model: '' });
              }}
              options={[{ value: 'peto', label: 'Peto (mặc định)', hint: 'Grok qua tài khoản Peto, có trí nhớ' },
                ...available.map(item => ({ value: item.id, label: item.name, hint: 'Khóa của bạn' }))]} />
          </div>
        </SettingsRow>
        {current && (
          <SettingsRow label={current.id === 'azure-openai' ? 'Bản triển khai' : 'Model'} htmlFor={modelId} labelId={`${modelId}-label`}
            desc={list.length ? undefined : `Chưa có model nào. Mở ${current.name} trong Nhà cung cấp rồi kiểm tra lại.`}>
            <div className="settings-dropdown">
              <Dropdown id={modelId} value={model} disabled={current.id === 'azure-openai' || !list.length}
                onChange={value => writeBrain({ provider: current.id, model: value })}
                options={list.map(item => ({ value: item, label: item }))} />
            </div>
          </SettingsRow>
        )}
        <SettingsRow label="Thêm nhà cung cấp"
          desc="Dùng khóa API bạn đang có: xAI, Anthropic, OpenAI, DeepSeek, Ollama, Gemini, Azure OpenAI hay Mistral.">
          <button type="button" className="voice-primary" onClick={() => { lastTab = 'chat'; onOpenProviders(); }}>Mở Nhà cung cấp</button>
        </SettingsRow>
      </SettingsGroup>
      <BrainNotice provider={current} search={search} tavily={Boolean(keys.tavily?.key?.trim())} />
    </div>
  );
}

function BrainNotice({ provider, search, tavily }: { provider?: ChatProviderInfo; search: boolean; tavily: boolean }) {
  if (!provider) {
    return <p className="companion-settings-note">Peto ghi nhớ điều đáng nhớ về bạn (Trí nhớ) và tra web khi bật Tra web.</p>;
  }
  const searchText = !search ? 'Tra web đang tắt (Mô-đun → Tra web).'
    : provider.search === 'native' ? `Tra web dùng tìm kiếm có sẵn của ${provider.name}.`
      : tavily ? 'Tra web dùng khóa Tavily của bạn.' : 'Tra web cần khóa Tavily ở Mô-đun → Tra web; chưa có nên Peto chưa tra được.';
  return (
    <div className="companion-provider-callout" role="note">
      <strong>Đang dùng khóa {provider.name} của bạn</strong>
      <span>Lượt trò chuyện tính vào tài khoản {provider.name} của bạn. Trong lúc dùng khóa riêng, Peto không ghi nhớ và không
        đọc Trí nhớ; lịch sử trò chuyện vẫn lưu như thường.</span>
      <span>{searchText}</span>
    </div>
  );
}

/** Trang Tra web: khóa Tavily cho nhà cung cấp không có tìm kiếm riêng (như Modules → Web Search của AIRI). */
export function TavilySection() {
  const id = useId();
  const keys = useKeyConfigs();
  const brain = useBrain();
  const models = useModels();
  const search = useCompanionSearch();
  const config = keys.tavily ?? {};
  const current = brain.provider === 'peto' ? undefined : chatProvider(brain.provider);
  const missing = search && current?.search === 'tavily' && connected(current.id, keys[current.id], models) && !config.key?.trim();
  return (
    <SettingsGroup title="Khóa Tavily">
      <div className="companion-provider-form">
        <p className="companion-settings-note">
          Peto, xAI, Anthropic, OpenAI và Gemini có sẵn tìm kiếm. DeepSeek, Mistral, Azure OpenAI và Ollama cần khóa Tavily
          (có gói miễn phí ở tavily.com).
        </p>
        {missing && <p className="voice-error" role="alert">Bộ não đang dùng {current!.name} mà chưa có khóa Tavily, nên Peto chưa tra web được.</p>}
        <Field id={id} label="Khóa API Tavily" hint={(
          <span className="voice-key-hint">
            <span>Lấy khóa ở app.tavily.com. Khóa chỉ lưu trong trình duyệt này; mỗi lần tra, khóa đi qua máy chủ Peto tới Tavily rồi bị bỏ.</span>
            {config.key && <button type="button" className="voice-link" onClick={() => updateKeyConfig('tavily', null)}>Xóa khóa khỏi trình duyệt</button>}
          </span>
        )}>
          <input id={id} type="password" placeholder="tvly-…" spellCheck={false} autoComplete="off" value={config.key ?? ''}
            onChange={event => updateKeyConfig('tavily', { key: event.target.value })} />
        </Field>
      </div>
    </SettingsGroup>
  );
}

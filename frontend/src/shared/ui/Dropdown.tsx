import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import './dropdown.css';

export interface DropdownOption {
  value: string;
  label: string;
  /** Dòng phụ mờ dưới tên (mô tả giọng). */
  hint?: string;
  /** Nhóm; các lựa chọn cùng nhóm phải đứng liền nhau. */
  group?: string;
}

interface DropdownProps {
  /** Mã của ô, trùng với `id` của Field bọc ngoài để nhãn trỏ tới đúng ô. */
  id: string;
  value: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Cho gõ mã tự do (giọng tự tạo, máy chủ riêng): danh sách chỉ là gợi ý, lọc theo chữ đang gõ. */
  editable?: boolean;
  /** Ô gõ được mà để trống thì dùng giá trị này (giọng mặc định): bảng đánh dấu nó là lựa chọn hiện tại. */
  emptyValue?: string;
  /** Tên đọc khi ô không có <label> hiện ra (thanh công cụ). Có nhãn thì để trống: nhãn phải có id `${id}-label`. */
  ariaLabel?: string;
  /** Lớp thêm cho khung ngoài, ví dụ `compact` cho ô gọn trên thanh công cụ, cộng lớp riêng của từng chỗ. */
  className?: string;
}

const LIST_MAX_HEIGHT = 300;
const LIST_MIN_HEIGHT = 120;
const LIST_GAP = 8;

/** Khung gần nhất cắt phần tràn (vùng cuộn của Cài đặt, cột chat Companion), giới hạn trong cửa sổ. */
function clipBounds(node: HTMLElement): { top: number; bottom: number } {
  for (let element = node.parentElement; element; element = element.parentElement) {
    if (/auto|scroll|hidden|clip|overlay/.test(getComputedStyle(element).overflowY)) {
      const rect = element.getBoundingClientRect();
      return { top: Math.max(rect.top, 0), bottom: Math.min(rect.bottom, window.innerHeight) };
    }
  }
  return { top: 0, bottom: window.innerHeight };
}

interface Placement {
  above: boolean;
  maxHeight: number;
}

/**
 * Bảng mở dưới ô, hay lật lên trên khi phía dưới không đủ chỗ mà phía trên rộng hơn, như AIRI. Bảng nằm ngay trong
 * trang (position: absolute) nên cuộn tới đâu nó đi theo ô tới đó; mỗi lần cuộn chỉ tính lại nên mở lên hay xuống.
 */
function usePlacement(
  wrap: RefObject<HTMLElement | null>,
  list: RefObject<HTMLElement | null>,
  open: boolean,
  count: number,
): Placement {
  const [placement, setPlacement] = useState<Placement>({ above: false, maxHeight: LIST_MAX_HEIGHT });
  useLayoutEffect(() => {
    const node = wrap.current;
    if (!open || !node) return;
    const update = () => {
      const rect = node.getBoundingClientRect();
      const bounds = clipBounds(node);
      const below = bounds.bottom - rect.bottom - LIST_GAP;
      const aboveRoom = rect.top - bounds.top - LIST_GAP;
      // scrollHeight là chiều cao đủ mọi dòng, kể cả khi max-height đang cắt bớt.
      const needed = Math.min(LIST_MAX_HEIGHT, list.current?.scrollHeight ?? LIST_MAX_HEIGHT);
      const above = below < needed && aboveRoom > below;
      const maxHeight = Math.max(LIST_MIN_HEIGHT, Math.min(LIST_MAX_HEIGHT, above ? aboveRoom : below));
      setPlacement((current) => (current.above === above && current.maxHeight === maxHeight ? current : { above, maxHeight }));
    };
    update();
    // Sự kiện cuộn không nổi bọt, nhưng pha capture trên window bắt được mọi vùng cuộn.
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [wrap, list, open, count]);
  return placement;
}

/** Bấm ra ngoài hay tiêu điểm rời khỏi ô thì đóng bảng. */
function useDismiss(wrap: RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const outside = (event: Event) => {
      if (!wrap.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
    };
  }, [wrap, open, close]);
}

/** Cuộn riêng bảng để dòng đang chọn hiện ra; scrollIntoView sẽ cuộn cả Cài đặt theo. */
function revealOption(list: HTMLElement | null, index: number, center: boolean) {
  const item = index >= 0 ? list?.querySelector<HTMLElement>(`[data-index="${index}"]`) : null;
  if (!list || !item) return;
  const top = item.offsetTop;
  const bottom = top + item.offsetHeight;
  if (top >= list.scrollTop && bottom <= list.scrollTop + list.clientHeight) return;
  if (center) list.scrollTop = top - (list.clientHeight - item.offsetHeight) / 2;
  else list.scrollTop = top < list.scrollTop ? top : bottom - list.clientHeight;
}

function ChevronIcon() {
  return (
    <svg className="dropdown-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="dropdown-check" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

function OptionList({ id, label, listRef, options, value, active, placement, onPick, onHover }: {
  id: string;
  label?: string;
  listRef: RefObject<HTMLUListElement | null>;
  options: DropdownOption[];
  value: string;
  active: number;
  placement: Placement;
  onPick: (option: DropdownOption) => void;
  onHover: (index: number) => void;
}) {
  const rows: ReactNode[] = [];
  options.forEach((option, index) => {
    if (option.group && option.group !== options[index - 1]?.group) {
      rows.push(<li key={`group-${option.group}`} role="presentation" className="dropdown-group">{option.group}</li>);
    }
    const selected = option.value === value;
    rows.push(
      <li
        key={`${option.value}-${index}`}
        id={`${id}-option-${index}`}
        data-index={index}
        role="option"
        aria-selected={selected}
        className={index === active ? "active" : undefined}
        onPointerMove={() => onHover(index)}
        onClick={() => onPick(option)}
      >
        <span className="dropdown-text">
          <span>{option.label}</span>
          {option.hint && <small>{option.hint}</small>}
        </span>
        {selected && <CheckIcon />}
      </li>,
    );
  });
  return (
    <ul
      ref={listRef}
      id={`${id}-list`}
      role="listbox"
      aria-labelledby={label ? undefined : `${id}-label`}
      aria-label={label}
      className={placement.above ? "dropdown-list above" : "dropdown-list"}
      style={{ maxHeight: placement.maxHeight }}
      // Giữ tiêu điểm ở ô khi bấm vào bảng (kể cả thanh cuộn của bảng), để ô không mất tiêu điểm rồi đóng bảng.
      onMouseDown={(event) => event.preventDefault()}
    >
      {rows}
    </ul>
  );
}

function useList(count: number, disabled: boolean | undefined) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const wrap = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const centered = useRef(false);
  const close = useCallback(() => {
    setOpen(false);
    setActive(-1);
  }, []);
  const openAt = (index: number) => {
    setOpen(true);
    setActive(index);
  };
  const clamp = (index: number) => Math.max(0, Math.min(count - 1, index));
  const showing = open && !disabled && count > 0;
  const placement = usePlacement(wrap, list, showing, count);
  useDismiss(wrap, showing, close);
  // Mới mở thì đưa lựa chọn hiện tại vào giữa bảng; sau đó chỉ cuộn vừa đủ theo phím mũi tên.
  useLayoutEffect(() => {
    if (!showing) {
      centered.current = false;
      return;
    }
    revealOption(list.current, active, !centered.current);
    centered.current = true;
  }, [showing, active, placement.maxHeight]);
  return { showing, active, setActive, close, openAt, clamp, wrap, list, placement };
}

/**
 * Ô chọn thay cho <select> và <datalist> trong mục Giọng nói. Bảng gợi ý của <datalist> là cửa sổ riêng của trình
 * duyệt, không đi theo ô khi cuộn Cài đặt (chủ web báo ngày 2026-09-25); bảng này nằm ngay dưới ô, trong trang.
 */
export function Dropdown(props: DropdownProps) {
  return props.editable ? <EditableDropdown {...props} /> : <SelectDropdown {...props} />;
}

function SelectDropdown({ id, value, options, onChange, placeholder, disabled, ariaLabel, className }: DropdownProps) {
  const { showing, active, setActive, close, openAt, clamp, wrap, list, placement } = useList(options.length, disabled);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = options[selectedIndex];

  function pick(option: DropdownOption) {
    close();
    if (option.value !== value) onChange(option.value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const move = (index: number) => {
      event.preventDefault();
      if (showing) setActive(clamp(index));
      else openAt(clamp(index));
    };
    switch (event.key) {
      case "ArrowDown":
        return move(showing ? active + 1 : Math.max(selectedIndex, 0));
      case "ArrowUp":
        return move(showing ? active - 1 : selectedIndex >= 0 ? selectedIndex : options.length - 1);
      case "Home":
        return move(0);
      case "End":
        return move(options.length - 1);
      case "Enter":
      case " ":
        event.preventDefault();
        if (showing && options[active]) pick(options[active]);
        else openAt(Math.max(selectedIndex, 0));
        return;
      case "Escape":
        if (!showing) return;
        // Chỉ đóng bảng: Esc không được đóng luôn hộp Cài đặt hay bảng Micro bên ngoài.
        event.preventDefault();
        event.stopPropagation();
        close();
        return;
      case "Tab":
        close();
        return;
      default: {
        // Gõ một chữ cái thì nhảy tới lựa chọn kế tiếp bắt đầu bằng chữ đó.
        if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey || !options.length) return;
        const letter = event.key.toLocaleLowerCase("vi");
        const from = (showing ? active : selectedIndex) + 1;
        for (let step = 0; step < options.length; step += 1) {
          const index = (from + step) % options.length;
          if (options[index].label.toLocaleLowerCase("vi").startsWith(letter)) return move(index);
        }
      }
    }
  }

  return (
    <div ref={wrap} className={["dropdown", className, showing && "open"].filter(Boolean).join(" ")}>
      <button
        id={id}
        type="button"
        role="combobox"
        className="dropdown-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={showing}
        aria-controls={`${id}-list`}
        aria-activedescendant={showing && active >= 0 ? `${id}-option-${active}` : undefined}
        disabled={disabled}
        onClick={() => (showing ? close() : openAt(Math.max(selectedIndex, 0)))}
        onKeyDown={onKeyDown}
        // Phím cách bấm nút khi nhả phím; keydown đã mở bảng rồi thì chặn để nó không đóng lại ngay.
        onKeyUp={(event) => { if (event.key === " ") event.preventDefault(); }}
      >
        <span className={selected ? "dropdown-value" : "dropdown-value placeholder"}>{selected?.label ?? placeholder ?? ""}</span>
        <ChevronIcon />
      </button>
      {showing && (
        <OptionList
          id={id}
          label={ariaLabel}
          listRef={list}
          options={options}
          value={value}
          active={active}
          placement={placement}
          onPick={pick}
          onHover={setActive}
        />
      )}
    </div>
  );
}

function EditableDropdown({ id, value, options, onChange, placeholder, disabled, emptyValue, ariaLabel, className }: DropdownProps) {
  const input = useRef<HTMLInputElement>(null);
  const current = value.trim() || emptyValue || "";
  const [filtering, setFiltering] = useState(false);
  const [focused, setFocused] = useState(false);
  // Mã giọng khác tên hiện (CosyVoice: "longwan_v2" là "龙婉 · Long Wan"): lúc không gõ thì hiện tên như ô chọn, lúc
  // đang sửa thì hiện mã thật.
  const named = options.find((option) => option.value === value && option.label !== value);
  const display = !focused && named ? named.label : value;
  const typed = value.trim().toLocaleLowerCase("vi");
  // Mới mở thì hiện đủ; đang gõ thì chỉ hiện gợi ý chứa chữ đã gõ.
  const shown = filtering && typed
    ? options.filter((option) => `${option.value} ${option.label} ${option.hint ?? ""}`.toLocaleLowerCase("vi").includes(typed))
    : options;
  const { showing, active, setActive, close, openAt, clamp, wrap, list, placement } = useList(shown.length, disabled);

  function openAll() {
    setFiltering(false);
    openAt(Math.max(options.findIndex((option) => option.value === current), 0));
  }

  function pick(option: DropdownOption) {
    close();
    setFiltering(false);
    if (option.value !== current) onChange(option.value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      if (!showing) openAll();
      else setActive(clamp(active < 0 && step < 0 ? shown.length - 1 : active + step));
    } else if (event.key === "Enter" && showing && shown[active]) {
      event.preventDefault();
      pick(shown[active]);
    } else if (event.key === "Escape" && showing) {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === "Tab") {
      close();
    }
  }

  return (
    <div ref={wrap} className={["dropdown editable", className, showing && "open"].filter(Boolean).join(" ")}>
      <input
        ref={input}
        id={id}
        type="text"
        role="combobox"
        className="dropdown-trigger"
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-expanded={showing}
        aria-controls={`${id}-list`}
        aria-activedescendant={showing && active >= 0 ? `${id}-option-${active}` : undefined}
        spellCheck={false}
        autoComplete="off"
        placeholder={placeholder}
        disabled={disabled}
        value={display}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onClick={() => { if (!showing) openAll(); }}
        onChange={(event) => {
          onChange(event.target.value);
          setFiltering(true);
          openAt(-1);
        }}
        onKeyDown={onKeyDown}
      />
      <button
        type="button"
        className="dropdown-toggle"
        aria-label="Xem danh sách gợi ý"
        tabIndex={-1}
        disabled={disabled}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          if (showing) close();
          else openAll();
          input.current?.focus();
        }}
      >
        <ChevronIcon />
      </button>
      {showing && (
        <OptionList
          id={id}
          label={ariaLabel}
          listRef={list}
          options={shown}
          value={current}
          active={active}
          placement={placement}
          onPick={pick}
          onHover={setActive}
        />
      )}
    </div>
  );
}


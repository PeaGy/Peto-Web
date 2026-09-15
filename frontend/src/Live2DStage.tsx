import { useEffect, useRef, useState } from "react";
import type { Application } from "pixi.js";
import { CHARACTER } from "./characterConfig";
import {
  COMPACT_QUERY,
  DEFAULT_VIEW,
  lookTarget,
  motionEnabled,
  panBy,
  placement,
  readCharacterView,
  wheelZoomFactor,
  writeCharacterView,
  zoomAt,
  type CharacterMotion,
  type CharacterView,
  type StageBox,
} from "./characterView";
import { voiceMouth } from "./voiceActivity";

let coreReady: Promise<void> | undefined;
function loadCore() {
  if ("Live2DCubismCore" in window) return Promise.resolve();
  if (!coreReady) {
    coreReady = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = CHARACTER.coreUrl;
      const timer = window.setTimeout(() => fail(), 20000);
      const fail = () => {
        clearTimeout(timer);
        script.remove();
        coreReady = undefined;
        reject(new Error("Chưa tải được bộ hiển thị nhân vật."));
      };
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = fail;
      document.head.append(script);
    });
  }
  return coreReady;
}

/**
 * Sân khấu Live2D của Companion.
 *
 * Máy tính: cuộn chuột hoặc chụm hai ngón để phóng to/thu nhỏ quanh chỗ đang chỉ, giữ chuột giữa kéo để dời, bấm đúp để về
 * cỡ vừa khung; góc nhìn được nhớ trong trình duyệt. Điện thoại (`COMPACT_QUERY`): khung khóa cứng như AIRI,
 * giữ ngón tay trên màn hình thì nhân vật nhìn theo ngón tay. Khi được cử động (`motionEnabled`), nhân vật
 * chạy motion Idle, thở, chớp mắt và nhìn theo con trỏ. Miệng luôn theo âm thanh đang phát.
 */
export default function Live2DStage({ fallbackUrl, name, motion = "system" }: {
  fallbackUrl?: string;
  name: string;
  motion?: CharacterMotion;
}) {
  const host = useRef<HTMLDivElement>(null);
  const motionRef = useRef(motion);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    motionRef.current = motion;
  }, [motion]);

  useEffect(() => {
    const container = host.current!;
    let disposed = false;
    let app: Application | undefined;
    let observer: ResizeObserver | undefined;
    let removeEvents = () => {};
    setStatus("loading");

    async function start() {
      await loadCore();
      const [{ Application: PixiApp }, { Live2DModel: Model, MotionPreloadStrategy }] = await Promise.all([
        import("pixi.js"), import("pixi-live2d-display/cubism4"),
      ]);
      if (disposed) return;
      app = new PixiApp({ width: 1, height: 1, backgroundAlpha: 0, antialias: true,
        resolution: Math.min(window.devicePixelRatio || 1, 1.5), autoDensity: true, autoStart: false });
      const canvas = app.view as HTMLCanvasElement;
      canvas.setAttribute("aria-hidden", "true");
      container.append(canvas);
      const current = await Model.from(CHARACTER.modelUrl, { autoUpdate: false, autoInteract: false, motionPreload: MotionPreloadStrategy.IDLE });
      if (disposed) { current.destroy({ children: true, texture: true, baseTexture: true }); return; }
      app.stage.addChild(current);
      const originalWidth = current.width;
      const originalHeight = current.height;
      current.anchor.set(0.5, 1);

      const compact = window.matchMedia(COMPACT_QUERY);
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
      const moving = () => motionEnabled(motionRef.current, reducedMotion.matches);

      // Máy tính: phóng và dời chỉ nhân thêm lên cỡ vừa khung, nên đổi cỡ cửa sổ vẫn giữ đúng góc nhìn đã chọn.
      let view = readCharacterView();
      const box: StageBox = { width: 1, height: 1, baseX: 0, baseY: 0, baseScale: 1 };
      const place = () => {
        const { scale, x, y } = placement(compact.matches ? DEFAULT_VIEW : view, box);
        current.scale.set(scale);
        current.position.set(x, y);
      };
      // Bàn phím điện thoại làm sân khấu thấp đi nhưng bề ngang giữ nguyên. Khung điện thoại tính theo chiều cao
      // lớn nhất đã thấy ở bề ngang hiện tại, để mở bàn phím không làm nhân vật nhỏ lại hay trôi mặt đi.
      let frameWidth = 0;
      let frameHeight = 0;
      const fit = () => {
        if (!app) return;
        const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
        app.renderer.resize(width, height);
        box.width = width;
        box.height = height;
        box.baseX = width / 2;
        if (compact.matches) {
          if (width !== frameWidth) {
            frameWidth = width;
            frameHeight = height;
          } else {
            frameHeight = Math.max(frameHeight, height);
          }
          // Điện thoại: nửa trên nhân vật phủ màn hình, đỉnh đầu nằm ngay dưới hàng nút.
          box.baseScale = frameHeight * CHARACTER.compactHeight / originalHeight;
          box.baseY = frameHeight * CHARACTER.compactTop + originalHeight * box.baseScale;
        } else {
          box.baseScale = Math.min(width * 0.94 / originalWidth, height * 0.96 / originalHeight);
          box.baseY = height * 0.99;
        }
        place();
      };
      observer = new ResizeObserver(fit);
      observer.observe(container);
      fit();

      let saveTimer: number | undefined;
      const changeView = (next: CharacterView) => {
        view = next;
        place();
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(() => {
          saveTimer = undefined;
          writeCharacterView(view);
        }, 300);
      };
      const local = (event: MouseEvent) => {
        const rect = container.getBoundingClientRect();
        return { x: event.clientX - rect.left, y: event.clientY - rect.top };
      };

      const onWheel = (event: WheelEvent) => {
        if (compact.matches) return;
        event.preventDefault();
        const point = local(event);
        changeView(zoomAt(view, wheelZoomFactor(event.deltaY, event.deltaMode), point.x, point.y, box));
      };
      const pointers = new Map<number, { x: number; y: number }>();
      // Chuột dời nhân vật bằng nút giữa theo lựa chọn của chủ web, để chuột trái rảnh; chạm vẫn kéo bằng một ngón.
      const onPointerDown = (event: PointerEvent) => {
        if (compact.matches || (event.pointerType === "mouse" && event.button !== 1)) return;
        pointers.set(event.pointerId, local(event));
        container.setPointerCapture?.(event.pointerId);
        container.classList.add("dragging");
      };
      const onPointerMove = (event: PointerEvent) => {
        const previous = pointers.get(event.pointerId);
        if (!previous) return;
        // Nhả nút giữa trong lúc vẫn giữ nút khác thì trình duyệt không bắn pointerup, nên tự dừng kéo.
        if (event.pointerType === "mouse" && (event.buttons & 4) === 0) return onPointerEnd(event);
        const point = local(event);
        const other = [...pointers].find(([id]) => id !== event.pointerId)?.[1];
        pointers.set(event.pointerId, point);
        if (pointers.size === 1) {
          changeView(panBy(view, point.x - previous.x, point.y - previous.y, box));
        } else if (pointers.size === 2 && other) {
          // Hai ngón: phóng theo khoảng cách giữa hai ngón, dời theo điểm giữa của chúng.
          const before = Math.hypot(previous.x - other.x, previous.y - other.y);
          const after = Math.hypot(point.x - other.x, point.y - other.y);
          const zoomed = before > 0
            ? zoomAt(view, after / before, (point.x + other.x) / 2, (point.y + other.y) / 2, box)
            : view;
          changeView(panBy(zoomed, (point.x - previous.x) / 2, (point.y - previous.y) / 2, box));
        }
      };
      const onPointerEnd = (event: PointerEvent) => {
        pointers.delete(event.pointerId);
        if (!pointers.size) container.classList.remove("dragging");
      };
      const onDoubleClick = () => {
        if (!compact.matches) changeView(DEFAULT_VIEW);
      };
      // Nhấn nút giữa: Chrome trên Windows bật cuộn tự động, Linux dán chữ. Chặn trên sân khấu để kéo được nhân vật.
      const onMiddleButton = (event: MouseEvent) => {
        if (event.button === 1 && !compact.matches) event.preventDefault();
      };

      const internal = current.internalModel;
      let touchId: number | null = null;
      // Nhìn theo con trỏ ở mọi chỗ trên trang như AIRI. Trên điện thoại, ngón tay đang giữ trên màn hình đóng
      // vai con trỏ; trên máy tính thì chạm dùng để kéo nhân vật nên không tính.
      const onLook = (event: PointerEvent) => {
        if (!moving()) return;
        if (event.pointerType === "touch") {
          if (!compact.matches) return;
          if (event.type === "pointerdown") touchId = event.pointerId;
          if (event.pointerId !== touchId) return;
        }
        const point = local(event);
        const headY = current.position.y - originalHeight * current.scale.y * CHARACTER.headHeight;
        const target = lookTarget(point.x, point.y, current.position.x, headY, box.width, box.height);
        internal.focusController.focus(target.x, target.y);
      };
      const onTouchEnd = (event: PointerEvent) => {
        if (touchId === null || event.pointerId !== touchId) return;
        touchId = null;
        internal.focusController.focus(0, 0);
      };
      const onLookAway = () => internal.focusController.focus(0, 0);

      const core = internal.coreModel as { setParameterValueById: (id: string, value: number) => void };
      let mouth = 0;
      internal.on("beforeModelUpdate", () => {
        const target = voiceMouth();
        mouth += (target - mouth) * (target > mouth ? 0.7 : 0.45);
        // Ép trạng thái miệng sau motion để model không nói khi âm thanh đang im lặng.
        core.setParameterValueById(CHARACTER.mouthParameter, mouth < 0.01 ? 0 : mouth);
      });
      app.ticker.maxFPS = 30;
      let still = false;
      app.ticker.add(() => {
        if (moving()) {
          still = false;
          current.update(Math.min(app!.ticker.deltaMS, 50));
          return;
        }
        if (!still) {
          internal.focusController.focus(0, 0, true);
          still = true;
        }
        // Vẫn áp dụng pose (ẩn tư thế tay thay thế) và miệng theo âm thanh, nhưng giữ thời gian motion đứng yên.
        internal.update(0, 0);
      });

      const visible = () => document.hidden ? app?.stop() : app?.start();
      const lost = (event: Event) => { event.preventDefault(); app?.stop(); setStatus("error"); };
      container.addEventListener("wheel", onWheel, { passive: false });
      container.addEventListener("pointerdown", onPointerDown);
      container.addEventListener("pointermove", onPointerMove);
      container.addEventListener("pointerup", onPointerEnd);
      container.addEventListener("pointercancel", onPointerEnd);
      container.addEventListener("dblclick", onDoubleClick);
      container.addEventListener("mousedown", onMiddleButton);
      container.addEventListener("auxclick", onMiddleButton);
      window.addEventListener("pointerdown", onLook);
      window.addEventListener("pointermove", onLook);
      window.addEventListener("pointerup", onTouchEnd);
      window.addEventListener("pointercancel", onTouchEnd);
      window.addEventListener("blur", onLookAway);
      document.documentElement.addEventListener("pointerleave", onLookAway);
      document.addEventListener("visibilitychange", visible);
      canvas.addEventListener("webglcontextlost", lost);
      compact.addEventListener?.("change", fit);
      removeEvents = () => {
        container.removeEventListener("wheel", onWheel);
        container.removeEventListener("pointerdown", onPointerDown);
        container.removeEventListener("pointermove", onPointerMove);
        container.removeEventListener("pointerup", onPointerEnd);
        container.removeEventListener("pointercancel", onPointerEnd);
        container.removeEventListener("dblclick", onDoubleClick);
        container.removeEventListener("mousedown", onMiddleButton);
        container.removeEventListener("auxclick", onMiddleButton);
        container.classList.remove("dragging");
        window.removeEventListener("pointerdown", onLook);
        window.removeEventListener("pointermove", onLook);
        window.removeEventListener("pointerup", onTouchEnd);
        window.removeEventListener("pointercancel", onTouchEnd);
        window.removeEventListener("blur", onLookAway);
        document.documentElement.removeEventListener("pointerleave", onLookAway);
        document.removeEventListener("visibilitychange", visible);
        canvas.removeEventListener("webglcontextlost", lost);
        compact.removeEventListener?.("change", fit);
        if (saveTimer !== undefined) {
          window.clearTimeout(saveTimer);
          writeCharacterView(view);
        }
      };
      visible();
      setStatus("ready");
    }
    void start().catch(() => {
      if (!disposed) {
        app?.stop();
        setStatus("error");
      }
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      removeEvents();
      app?.destroy(true, { children: true, texture: true, baseTexture: true });
    };
  }, [attempt]);

  return <div className="character-stage">
    <div className="character-glow" aria-hidden="true" />
    <div ref={host} className="character-canvas" style={{ visibility: status === "ready" ? "visible" : "hidden" }} />
    {status !== "ready" && <div className="character-fallback">
      {fallbackUrl ? <img src={fallbackUrl} alt={name} /> : <span>{name.charAt(0)}</span>}
      <p role="status">{status === "loading" ? "Đang đưa nhân vật lên sân khấu…" : "Chưa hiển thị được nhân vật. Bạn vẫn có thể nhắn và nghe Peto."}</p>
      {status === "error" && <button className="settings-button" onClick={() => setAttempt((v) => v + 1)}>Thử tải lại nhân vật</button>}
    </div>}
    <a className="character-credit" href={CHARACTER.creditUrl} target="_blank" rel="noopener noreferrer">Model mẫu {CHARACTER.name} · © Live2D Inc.</a>
  </div>;
}

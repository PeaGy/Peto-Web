import { useEffect, useRef, useState } from "react";
import type { Application } from "pixi.js";
import type { Live2DModel } from "pixi-live2d-display/cubism4";
import { CHARACTER } from "./characterConfig";
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

export default function Live2DStage({ fallbackUrl, name }: { fallbackUrl?: string; name: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const container = host.current!;
    let disposed = false;
    let app: Application | undefined;
    let model: Live2DModel | undefined;
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
      const loaded = await Model.from(CHARACTER.modelUrl, { autoUpdate: false, autoInteract: false, motionPreload: MotionPreloadStrategy.IDLE });
      if (disposed) { loaded.destroy({ children: true, texture: true, baseTexture: true }); return; }
      model = loaded;
      app.stage.addChild(model);
      const originalWidth = model.width;
      const originalHeight = model.height;
      model.anchor.set(0.5, 1);
      const fit = () => {
        if (!app || !model) return;
        const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
        app.renderer.resize(width, height);
        const closeUp = width < 720 && height < 400;
        const scale = Math.min(width * 0.94 / originalWidth, height * (closeUp ? 1.65 : 0.96) / originalHeight);
        model.scale.set(scale);
        model.position.set(width / 2, closeUp ? originalHeight * scale + height * 0.02 : height * 0.99);
      };
      observer = new ResizeObserver(fit);
      observer.observe(container);
      fit();
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
      const internal = model.internalModel;
      const core = internal.coreModel as { setParameterValueById: (id: string, value: number) => void; update: () => void };
      let mouth = 0;
      internal.on("beforeModelUpdate", () => {
        const target = voiceMouth();
        mouth += (target - mouth) * (target > mouth ? 0.7 : 0.45);
        // Ép trạng thái miệng sau motion để model không nói khi âm thanh đang im lặng.
        core.setParameterValueById(CHARACTER.mouthParameter, mouth < 0.01 ? 0 : mouth);
      });
      app.ticker.maxFPS = 30;
      app.ticker.add(() => {
        if (reducedMotion.matches) {
          // Vẫn áp dụng pose (ẩn tư thế tay thay thế), nhưng giữ thời gian motion đứng yên.
          internal.update(0, 0);
        } else model?.update(Math.min(app!.ticker.deltaMS, 50));
      });
      const visible = () => document.hidden ? app?.stop() : app?.start();
      document.addEventListener("visibilitychange", visible);
      const lost = (event: Event) => { event.preventDefault(); app?.stop(); setStatus("error"); };
      canvas.addEventListener("webglcontextlost", lost);
      removeEvents = () => {
        document.removeEventListener("visibilitychange", visible);
        canvas.removeEventListener("webglcontextlost", lost);
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

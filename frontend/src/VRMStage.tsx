import { useEffect, useRef, useState } from 'react';
import type { WebGLRenderer } from 'three';
import type { VRM } from '@pixiv/three-vrm';
import { characterThumbnail, getCharacterAssets, type CharacterModel } from './characterLibrary';
import { COMPACT_QUERY, motionEnabled, type CharacterMotion } from './characterView';
import { voiceMouth } from './voiceActivity';

export default function VRMStage({ character, motion, onPreview }: {
  character: CharacterModel; motion: CharacterMotion; onPreview?: (id: string, image: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const motionRef = useRef(motion); motionRef.current = motion;
  const previewRef = useRef(onPreview); previewRef.current = onPreview;
  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const container = host.current!;
    let disposed = false, frame = 0;
    let renderer: WebGLRenderer | undefined;
    let cleanup = () => {};
    let disposeModel = () => {};
    setStatus('loading'); setError('');
    async function start() {
      const [THREE, { GLTFLoader }, { VRMLoaderPlugin, VRMUtils }, { OrbitControls }, { validateVRM }, assets] = await Promise.all([
        import('three'), import('three/addons/loaders/GLTFLoader.js'), import('@pixiv/three-vrm'),
        import('three/addons/controls/OrbitControls.js'), import('./characterImport'), getCharacterAssets(character.id),
      ]);
      if (disposed) return;
      const file = assets?.files.find(file => file.path === assets.entry);
      if (!file) throw new Error('Không còn tìm thấy model. Hãy nhập lại tệp .vrm.');
      const buffer = await file.blob.arrayBuffer();
      validateVRM(buffer);
      if (disposed) return;
      const manager = new THREE.LoadingManager();
      manager.setURLModifier(url => {
        if (url.startsWith('blob:')) return url;
        throw new Error('Model trỏ tới tài nguyên bên ngoài tệp VRM.');
      });
      const loader = new GLTFLoader(manager);
      loader.register(parser => new VRMLoaderPlugin(parser));
      const gltf = await loader.parseAsync(buffer, '');
      const loaded = gltf.userData.vrm as VRM | undefined;
      if (!loaded || disposed) { VRMUtils.deepDispose(gltf.scene); if (!disposed) throw new Error('Không đọc được nhân vật VRM.'); return; }
      disposeModel = () => VRMUtils.deepDispose(loaded.scene);
      VRMUtils.rotateVRM0(loaded);
      // Hạ hai cánh tay khỏi tư thế chữ T, dùng bộ xương chuẩn hóa cho cả VRM 0 và 1.
      loaded.humanoid.setNormalizedPose({ leftUpperArm: { rotation: [0, 0, Math.sin(-0.55), Math.cos(-0.55)] }, rightUpperArm: { rotation: [0, 0, Math.sin(0.55), Math.cos(0.55)] } });
      loaded.update(0);
      const scene = new THREE.Scene();
      scene.add(loaded.scene);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x9f9bad, 2.2));
      const key = new THREE.DirectionalLight(0xffffff, 2.5); key.position.set(1, 3, 4); scene.add(key);
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.setClearColor(0x000000, 0);
      const canvas = renderer.domElement; canvas.setAttribute('aria-hidden', 'true'); container.append(canvas);
      const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100);
      const controls = new OrbitControls(camera, canvas);
      controls.enableDamping = true; controls.enablePan = true;
      controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.ROTATE };
      const bounds = new THREE.Box3().setFromObject(loaded.scene), size = bounds.getSize(new THREE.Vector3()), center = bounds.getCenter(new THREE.Vector3());
      const height = Math.max(0.1, size.y);
      const compact = window.matchMedia(COMPACT_QUERY), reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
      const fit = () => {
        if (!renderer) return;
        const width = Math.max(1, container.clientWidth), h = Math.max(1, container.clientHeight);
        renderer.setSize(width, h); camera.aspect = width / h; camera.updateProjectionMatrix();
        const frameHeight = height * (compact.matches ? 0.62 : 1.1);
        const distance = Math.max(frameHeight / (2 * Math.tan(Math.PI / 12)), size.x / (2 * Math.tan(Math.PI / 12) * camera.aspect));
        controls.target.set(center.x, bounds.min.y + height * (compact.matches ? 0.72 : 0.52), center.z);
        camera.position.set(center.x, controls.target.y, center.z + distance);
        controls.minDistance = height * 0.4; controls.maxDistance = height * 6;
        controls.enabled = !compact.matches; controls.update();
      };
      const observer = new ResizeObserver(fit); observer.observe(container); fit();
      const look = new THREE.Object3D(); scene.add(look); look.position.copy(camera.position);
      if (loaded.lookAt) loaded.lookAt.target = look;
      const pointer = (event: PointerEvent) => {
        if (event.pointerType === 'touch' && !compact.matches) return;
        const rect = container.getBoundingClientRect();
        look.position.set(center.x + ((event.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * height, controls.target.y - ((event.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * height, camera.position.z);
      };
      const away = () => look.position.copy(camera.position);
      const reset = () => fit();
      const lost = (event: Event) => { event.preventDefault(); cancelAnimationFrame(frame); setStatus('error'); setError('Trình duyệt đã tạm dừng hiển thị 3D. Bạn có thể thử tải lại.'); };
      let last = 0, elapsed = 0, mouth = 0, captured = false;
      const tick = (now: number) => {
        if (disposed || document.hidden) return;
        frame = requestAnimationFrame(tick);
        if (now - last < 1000 / 30) return;
        const dt = Math.min((now - last) / 1000, 0.05); last = now;
        const moving = motionEnabled(motionRef.current, reduced.matches);
        if (moving) elapsed += dt;
        const blinkPhase = elapsed % 4.3;
        const blink = moving && blinkPhase > 4.05 ? Math.sin((blinkPhase - 4.05) / 0.25 * Math.PI) : 0;
        const target = voiceMouth(); mouth += (target - mouth) * (target > mouth ? 0.7 : 0.45);
        loaded.expressionManager?.setValue('aa', mouth < 0.01 ? 0 : mouth);
        loaded.expressionManager?.setValue('blink', blink);
        const spine = loaded.humanoid.getNormalizedBoneNode('spine');
        if (spine) spine.rotation.z = moving ? Math.sin(elapsed * 1.4) * 0.014 : 0;
        if (!moving) away();
        loaded.update(moving ? dt : 0); controls.update(); renderer!.render(scene, camera);
        if (!captured && previewRef.current) {
          captured = true;
          try { previewRef.current(character.id, characterThumbnail(canvas)); } catch { /* Thumbnail không chặn hiển thị. */ }
        }
      };
      const visibility = () => { cancelAnimationFrame(frame); if (!document.hidden) { last = performance.now(); frame = requestAnimationFrame(tick); } };
      window.addEventListener('pointermove', pointer); window.addEventListener('blur', away);
      document.addEventListener('visibilitychange', visibility); canvas.addEventListener('webglcontextlost', lost);
      canvas.addEventListener('dblclick', reset); compact.addEventListener?.('change', fit);
      cleanup = () => {
        observer.disconnect(); controls.dispose();
        window.removeEventListener('pointermove', pointer); window.removeEventListener('blur', away);
        document.removeEventListener('visibilitychange', visibility); canvas.removeEventListener('webglcontextlost', lost);
        canvas.removeEventListener('dblclick', reset); compact.removeEventListener?.('change', fit);
      };
      visibility(); setStatus('ready');
    }
    void start().catch(reason => {
      if (!disposed) { setError(reason instanceof Error ? reason.message : 'Chưa tải được model VRM.'); setStatus('error'); }
    });
    return () => {
      disposed = true; cancelAnimationFrame(frame); cleanup(); disposeModel();
      renderer?.dispose(); renderer?.forceContextLoss(); renderer?.domElement.remove();
    };
  }, [character.id, attempt]);
  return <div className="character-stage">
    <div className="character-glow" aria-hidden="true" />
    <div ref={host} className="character-canvas" style={{ visibility: status === 'ready' ? 'visible' : 'hidden' }} />
    {status !== 'ready' && <div className="character-fallback"><p role="status">{status === 'loading' ? 'Đang đưa nhân vật 3D lên sân khấu…' : error}</p>{status === 'error' && <button className="settings-button" onClick={() => setAttempt(value => value + 1)}>Thử tải lại nhân vật</button>}</div>}
    <span className="character-credit">{character.name}{character.author ? ` · ${character.author}` : ' · Model của bạn'}</span>
  </div>;
}

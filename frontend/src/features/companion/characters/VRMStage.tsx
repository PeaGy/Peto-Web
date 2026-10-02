import { useRenderQuality } from './renderQuality';
import { useEffect, useRef, useState } from 'react';
import type { Vector3, WebGLRenderer } from 'three';
import type { VRM } from '@pixiv/three-vrm';
import { characterThumbnail, faceThumbnail, getCharacterAssets, type CharacterModel } from './characterLibrary';
import { COMPACT_QUERY, motionEnabled, type CharacterMotion } from './characterView';
import { voiceMouth, voicePlaying } from '../speech/voiceActivity';
import { relaxVRMArms } from './vrmPose';
import { CompanionMotion, VoiceMouthBlend, stageQuality, type CompanionActivity } from './companionMotion';
import { publishSnapshot, readExpressions, watchExpressions, type StageCue, type StageEmotion } from './characterExpressions';
import { FaceBlend, vrmFace } from './builtinFaces';
import { Blinker, IdleEyes } from './idleEyes';

// Góc liếc lớn nhất khi chờ. VRM chỉ quay mắt một phần góc nhìn (thường 10° mắt cho 90° nhìn), nên góc nhỏ thì không thấy.
const IDLE_YAW = Math.PI / 3, IDLE_PITCH = Math.PI * 2 / 9;

export default function VRMStage({ character, motion, onPreview, activity = 'idle', emotion }: {
  activity?: CompanionActivity;
  /** Cảm xúc đang hiện (Companion quyết lúc nào đổi, lúc nào về bình thường bằng null). */
  emotion?: StageCue | null;
  character: CharacterModel; motion: CharacterMotion; onPreview?: (id: string, image: string) => void;
}) {
  const qualityPreference = useRenderQuality();
  const host = useRef<HTMLDivElement>(null);
  const activityRef = useRef(activity); activityRef.current = activity;
  const motionRef = useRef(motion); motionRef.current = motion;
  const previewRef = useRef(onPreview); previewRef.current = onPreview;
  const emotionRef = useRef(emotion); emotionRef.current = emotion;
  const faceBlend = useRef(new FaceBlend());
  const preferences = useRef(readExpressions(character.id));
  const previewTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  /** Mặt vừa bấm thử và lúc chụp: vòng vẽ chụp quanh đầu khi mặt đã hiện hẳn (bảng Nhân vật che sân khấu). */
  const snapshotDue = useRef<{ emotion: StageEmotion; at: number } | null>(null);
  const showEmotion = (value: StageEmotion | null, preview = false) => {
    clearTimeout(previewTimer.current);
    snapshotDue.current = preview && value ? { emotion: value, at: performance.now() + 1200 } : null;
    faceBlend.current.show(value && (preview || preferences.current.enabled) ? value : null);
    if (preview) previewTimer.current = setTimeout(() => showEmotion(emotionRef.current?.emotion ?? null), 6000);
  };
  useEffect(() => { showEmotion(emotion?.emotion ?? null); }, [emotion]);
  useEffect(() => {
    preferences.current = readExpressions(character.id);
    const unwatch = watchExpressions(character.id, value => {
      preferences.current = value;
      showEmotion(emotionRef.current?.emotion ?? null);
    }, value => showEmotion(value, true));
    return () => { unwatch(); clearTimeout(previewTimer.current); };
  }, [character.id]);
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
      relaxVRMArms(loaded.humanoid);
      loaded.update(0);
      const scene = new THREE.Scene();
      scene.add(loaded.scene);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x9f9bad, 2.2));
      const key = new THREE.DirectionalLight(0xffffff, 2.5); key.position.set(1, 3, 4); scene.add(key);
      const compact = window.matchMedia(COMPACT_QUERY), reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: !compact.matches || qualityPreference.sharp });
      renderer.setPixelRatio(stageQuality(compact.matches, window.devicePixelRatio, qualityPreference).resolution);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.setClearColor(0x000000, 0);
      const canvas = renderer.domElement; canvas.setAttribute('aria-hidden', 'true'); container.append(canvas);
      const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100);
      const controls = new OrbitControls(camera, canvas);
      controls.enableDamping = true; controls.enablePan = true;
      controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.ROTATE };
      const bounds = new THREE.Box3().setFromObject(loaded.scene), size = bounds.getSize(new THREE.Vector3()), center = bounds.getCenter(new THREE.Vector3());
      const height = Math.max(0.1, size.y);
      const fit = () => {
        if (!renderer) return;
        renderer.setPixelRatio(stageQuality(compact.matches, window.devicePixelRatio, qualityPreference).resolution);
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
      // Chỗ con trỏ trên sân khấu. Chưa có, hay con trỏ đã rời trang, thì nhìn thẳng người xem (camera).
      const pointed = new THREE.Vector3();
      let pointing = false, lastPointer = -Infinity;
      const pointer = (event: PointerEvent) => {
        if (event.pointerType === 'touch' && !compact.matches) return;
        const rect = container.getBoundingClientRect();
        pointed.set(center.x + ((event.clientX - rect.left) / Math.max(1, rect.width) - 0.5) * height, controls.target.y - ((event.clientY - rect.top) / Math.max(1, rect.height) - 0.5) * height, camera.position.z);
        pointing = true; lastPointer = performance.now();
      };
      const away = () => { pointing = false; lastPointer = -Infinity; };
      const headPoint = new THREE.Vector3(), neckPoint = new THREE.Vector3(), gazeDirection = new THREE.Vector3();
      const headBone = loaded.humanoid.getRawBoneNode('head'), neckBone = loaded.humanoid.getRawBoneNode('neck');
      /** Nhìn về điểm gốc, lệch thêm theo góc liếc khi chờ (tính quanh đầu để góc không phụ thuộc khoảng cách). */
      const gaze = (base: Vector3, eyes: { x: number; y: number; weight: number }) => {
        if (!headBone || eyes.weight < 0.001) { look.position.copy(base); return; }
        headBone.getWorldPosition(headPoint);
        gazeDirection.subVectors(base, headPoint);
        const reach = Math.max(0.5, gazeDirection.length());
        const yaw = Math.atan2(gazeDirection.x, gazeDirection.z) + eyes.x * eyes.weight * IDLE_YAW;
        const pitch = Math.atan2(gazeDirection.y, Math.hypot(gazeDirection.x, gazeDirection.z)) + eyes.y * eyes.weight * IDLE_PITCH;
        look.position.set(headPoint.x + reach * Math.sin(yaw) * Math.cos(pitch), headPoint.y + reach * Math.sin(pitch),
          headPoint.z + reach * Math.cos(yaw) * Math.cos(pitch));
      };
      const reset = () => fit();
      let contextLost = false;
      const lost = (event: Event) => { event.preventDefault(); contextLost = true; cancelAnimationFrame(frame); setStatus('error'); setError('Trình duyệt đã tạm dừng hiển thị 3D. Bạn có thể thử tải lại.'); };
      let last = 0, nextFrame = 0, elapsed = 0, captured = false;
      const conversationMotion = new CompanionMotion();
      const mouthBlend = new VoiceMouthBlend();
      const idleEyes = new IdleEyes(), blinker = new Blinker();
      const head = loaded.humanoid.getNormalizedBoneNode('head');
      const headRest = head ? { x: head.rotation.x, y: head.rotation.y, z: head.rotation.z } : undefined;
      let faceNames = new Set<string>();
      const hasExpression = (name: string) => !!loaded.expressionManager?.getExpression(name);
      const tick = (now: number) => {
        if (disposed || document.hidden || contextLost) return;
        frame = requestAnimationFrame(tick);
        const interval = 1000 / stageQuality(compact.matches, window.devicePixelRatio, qualityPreference).fps;
        if (now < nextFrame) return;
        nextFrame = now + interval - Math.max(0, now - nextFrame) % interval;
        const dt = Math.min((now - last) / 1000, 0.05); last = now;
        const moving = motionEnabled(motionRef.current, reduced.matches);
        if (moving) elapsed += dt;
        const blink = moving ? blinker.step(dt) : 0;
        const target = voiceMouth();
        const mouth = mouthBlend.step(target, dt, voicePlaying());
        // Cảm xúc: biểu cảm có sẵn của VRM pha theo lớp mặt, biểu cảm vừa tan hết thì trả về 0.
        const face = vrmFace(faceBlend.current.step(dt), hasExpression);
        loaded.expressionManager?.setValue('aa', Math.max(mouth < 0.01 ? 0 : mouth, face.mouth));
        loaded.expressionManager?.setValue('blink', blink);
        for (const name of faceNames) if (!face.values.has(name)) loaded.expressionManager?.setValue(name, 0);
        for (const [name, value] of face.values) loaded.expressionManager?.setValue(name, value);
        faceNames = new Set(face.values.keys());
        const pose = conversationMotion.step(activityRef.current, dt, target);
        // Như Live2D (AIRI: idle eye movement): con trỏ đứng yên 3 giây thì mắt tự liếc quanh, đầu nghiêng theo một chút.
        // Giảm chuyển động thì không nhìn theo con trỏ, đầu đứng yên, nhưng mắt vẫn liếc như bên Live2D.
        const eyes = idleEyes.step(dt, !(moving && now - lastPointer < 3000));
        gaze(moving && pointing ? pointed : camera.position, eyes);
        const glance = moving ? eyes.weight : 0;
        if (head && headRest) {
          head.rotation.x = headRest.x + ((moving ? pose.pitch : 0) - eyes.y * glance * 5) * Math.PI / 180;
          head.rotation.y = headRest.y + eyes.x * glance * 8 * Math.PI / 180;
          head.rotation.z = headRest.z + ((moving ? pose.roll : 0) + face.roll) * Math.PI / 180;
        }
        const spine = loaded.humanoid.getNormalizedBoneNode('spine');
        if (spine) spine.rotation.z = moving ? Math.sin(elapsed * 1.4) * 0.014 : 0;
        loaded.update(moving ? dt : 0); controls.update(); renderer!.render(scene, camera);
        const due = snapshotDue.current;
        if (due && now >= due.at && headBone) {
          snapshotDue.current = null;
          try {
            headBone.getWorldPosition(headPoint).project(camera);
            const x = (headPoint.x + 1) / 2 * canvas.width, y = (1 - headPoint.y) / 2 * canvas.height;
            const neck = neckBone ? neckBone.getWorldPosition(neckPoint).project(camera) : null;
            const reach = neck ? Math.hypot((neck.x - headPoint.x) * canvas.width, (neck.y - headPoint.y) * canvas.height) / 2 : 0;
            publishSnapshot(character.id, due.emotion, faceThumbnail(canvas, x, y, Math.max(reach * 5, canvas.height * 0.12)));
          } catch { /* Ảnh xem thử không chặn hiển thị. */ }
        }
        if (!captured && previewRef.current) {
          captured = true;
          try { previewRef.current(character.id, characterThumbnail(canvas)); } catch { /* Thumbnail không chặn hiển thị. */ }
        }
      };
      const visibility = () => { cancelAnimationFrame(frame); if (!document.hidden && !contextLost) { last = performance.now(); nextFrame = last; frame = requestAnimationFrame(tick); } };
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
  }, [character.id, attempt, qualityPreference.sharp, qualityPreference.smooth]);
  return <div className="character-stage">
    <div className="character-glow" aria-hidden="true" />
    <div ref={host} className="character-canvas" style={{ visibility: status === 'ready' ? 'visible' : 'hidden' }} />
    {status !== 'ready' && <div className="character-fallback"><p role="status">{status === 'loading' ? 'Đang đưa nhân vật 3D lên sân khấu…' : error}</p>{status === 'error' && <button className="settings-button" onClick={() => setAttempt(value => value + 1)}>Thử tải lại nhân vật</button>}</div>}
  </div>;
}

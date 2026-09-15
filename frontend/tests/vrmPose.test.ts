// @vitest-environment node
import { expect, it } from 'vitest';
import { Object3D, Vector3 } from 'three';
import { VRMHumanoid, type VRMHumanBones, type VRMHumanBoneName } from '@pixiv/three-vrm';
import { relaxVRMArms } from '../src/vrmPose';

// Use the real humanoid normalization and raw-bone update, including rotated
// local bone axes. VRM 0 faces -Z at import; the stage turns its root around.
function skeleton(version: '0' | '1') {
  const scene = new Object3D();
  const bones: Partial<VRMHumanBones> = {};
  const add = (name: VRMHumanBoneName, parent: Object3D, position: number[]) => {
    const node = new Object3D();
    node.position.copy(parent.worldToLocal(new Vector3().fromArray(position)));
    node.rotation.z = 0.37;
    parent.add(node); bones[name] = { node };
    return node;
  };
  const hips = add('hips', scene, [0, 1, 0]);
  const spine = add('spine', hips, [0, 1.2, 0]);
  const direction = version === '0' ? -1 : 1;
  for (const side of ['left', 'right'] as const) {
    const x = direction * (side === 'left' ? 1 : -1);
    const arm = add(`${side}UpperArm`, spine, [x * 0.2, 1.4, 0]);
    const elbow = add(`${side}LowerArm`, arm, [x * 0.5, 1.4, 0]);
    add(`${side}Hand`, elbow, [x * 0.75, 1.4, 0]);
  }
  const humanoid = new VRMHumanoid(bones as VRMHumanBones);
  scene.add(humanoid.normalizedHumanBonesRoot);
  if (version === '0') scene.rotation.y = Math.PI;
  const position = (name: VRMHumanBoneName) => humanoid.getRawBoneNode(name)!.getWorldPosition(new Vector3());
  return { humanoid, position };
}

it.each(['0', '1'] as const)('VRM %s: hai khuỷu và bàn tay hạ dưới vai, giữ độ dài và đối xứng', version => {
  const { humanoid, position } = skeleton(version);
  const hipsBefore = position('hips');
  relaxVRMArms(humanoid);
  humanoid.update();
  for (const side of ['left', 'right'] as const) {
    const shoulder = position(`${side}UpperArm`);
    const elbow = position(`${side}LowerArm`);
    const hand = position(`${side}Hand`);
    expect(elbow.y).toBeLessThan(shoulder.y - 0.2);
    expect(hand.y).toBeLessThan(elbow.y - 0.15);
    expect(shoulder.distanceTo(elbow)).toBeCloseTo(0.3);
    expect(elbow.distanceTo(hand)).toBeCloseTo(0.25);
    expect(Math.abs(hand.x)).toBeGreaterThan(Math.abs(shoulder.x));
  }
  expect(position('leftHand').y).toBeCloseTo(position('rightHand').y);
  expect(position('leftHand').x).toBeCloseTo(-position('rightHand').x);
  expect(position('hips').distanceTo(hipsBefore)).toBeLessThan(1e-6);
});

it('không sinh góc quay lỗi khi thiếu xương hoặc hai khớp trùng nhau', () => {
  const { humanoid } = skeleton('0');
  const arm = humanoid.getNormalizedBoneNode('leftUpperArm')!;
  humanoid.getNormalizedBoneNode('leftLowerArm')!.position.set(0, 0, 0);
  delete humanoid.normalizedHumanBones.rightLowerArm;
  relaxVRMArms(humanoid);
  expect(arm.quaternion.toArray()).toEqual([0, 0, 0, 1]);
});

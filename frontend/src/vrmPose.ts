import type { VRMHumanoid } from '@pixiv/three-vrm';

/** Apply once at load, while the normalized skeleton is still in its rest pose. */
export function relaxVRMArms(humanoid: VRMHumanoid) {
  for (const side of ['left', 'right'] as const) {
    const upperArm = humanoid.getNormalizedBoneNode(`${side}UpperArm`);
    const lowerArm = humanoid.getNormalizedBoneNode(`${side}LowerArm`);
    if (!upperArm || !lowerArm) continue;

    // Normalization preserves the rest bone directions: VRM 0 and VRM 1 can
    // point along opposite X axes. Aim the actual upper-arm-to-elbow vector
    // downwards instead of assuming a rotation sign from the bone's name.
    const restDirection = lowerArm.position.clone().normalize();
    const relaxedDirection = restDirection.clone().setY(0);
    if (relaxedDirection.lengthSq() < 1e-8) continue;
    relaxedDirection.normalize().multiplyScalar(Math.cos(1.1));
    relaxedDirection.y = -Math.sin(1.1);
    upperArm.quaternion.setFromUnitVectors(restDirection, relaxedDirection);
  }
}

/** Chỉ dùng tài nguyên đi kèm ứng dụng; thay model tại đây khi có nhân vật riêng. */
export const CHARACTER = {
  id: "hiyori",
  name: "Hiyori Momose",
  modelUrl: "/characters/hiyori/Hiyori.model3.json",
  coreUrl: "/vendor/live2d/live2dcubismcore.min.js",
  mouthParameter: "ParamMouthOpenY",
  /** Tâm đầu nằm ở tỉ lệ này tính từ chân lên theo chiều cao model; dùng để nhìn theo con trỏ. */
  headHeight: 0.85,
  /** Khung khóa trên điện thoại: chiều cao model so với màn hình, và đỉnh model cách mép trên bao nhiêu phần. */
  compactHeight: 1.15,
  compactTop: 0.13,
  creditUrl: "/characters/NOTICE.html",
};

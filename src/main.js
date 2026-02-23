import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMHumanBoneName } from "@pixiv/three-vrm";

let scene, camera, renderer, clock;
let vrm = null;
let frameData = null;
let currentFrameIndex = 0;
let playing = false;
let accumulatedTime = 0;
let playbackSpeed = 0.5;
let flipX = false;
let flipY = false;
let flipZ = false;
let axisHelpers = [];
const FPS = 30;
const flipXQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
const flipYQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI);
const flipZQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI);
const _q = new THREE.Quaternion();
const FRAME_DT = 1 / FPS;
const IDENTITY_QUAT = [0, 0, 0, 1];

function pascalToCamel(str) {
  return str.charAt(0).toLowerCase() + str.slice(1);
}

function toVrmBoneName(jsonKey) {
  return VRMHumanBoneName[jsonKey] ?? pascalToCamel(jsonKey);
}

function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe8eaf0);

  camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.01, 100);
  camera.position.set(0, 1.2, 2.5);
  camera.lookAt(0, 0.9, 0);

  const hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 0.8);
  scene.add(hemi);
  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(1, 2, 2);
  scene.add(dir);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  document.body.appendChild(renderer.domElement);

  clock = new THREE.Clock();

  const panel = document.createElement("div");
  panel.style.cssText = "position:absolute;left:12px;top:12px;z-index:100;display:flex;flex-direction:column;gap:6px;background:rgba(255,255,255,0.95);padding:10px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:sans-serif;font-size:14px;color:#111;";
  panel.id = "sign-language-controls";

  const btnPlay = document.createElement("button");
  btnPlay.textContent = "播放手语动画";
  btnPlay.style.cssText = "padding:8px 12px;cursor:pointer;";
  btnPlay.addEventListener("click", () => {
    if (!frameData || frameData.length === 0) {
      console.warn("动画数据未加载");
      return;
    }
    playing = true;
    currentFrameIndex = 0;
  });
  panel.appendChild(btnPlay);

  const speedWrap = document.createElement("div");
  speedWrap.style.cssText = "display:flex;align-items:center;gap:8px;";
  speedWrap.innerHTML = "<label>播放速度</label>";
  const speedSelect = document.createElement("select");
  [["0.25x", 0.25], ["0.5x", 0.5], ["1x", 1], ["2x", 2]].forEach(([label, val]) => {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = label;
    if (val === 0.5) opt.selected = true;
    speedSelect.appendChild(opt);
  });
  speedSelect.addEventListener("change", () => { playbackSpeed = Number(speedSelect.value); });
  speedWrap.appendChild(speedSelect);
  panel.appendChild(speedWrap);

  const btnTpose = document.createElement("button");
  btnTpose.textContent = "显示 T 姿（模型原始朝向）";
  btnTpose.style.cssText = "padding:8px 12px;cursor:pointer;";
  btnTpose.addEventListener("click", () => {
    playing = false;
    applyIdentityToAllBones();
    if (vrm?.update) vrm.update(0);
  });
  panel.appendChild(btnTpose);

  const labelAxes = document.createElement("label");
  labelAxes.style.cssText = "display:flex;align-items:center;gap:6px;cursor:pointer;";
  const axesCheck = document.createElement("input");
  axesCheck.type = "checkbox";
  axesCheck.addEventListener("change", () => toggleBoneAxes(axesCheck.checked));
  labelAxes.appendChild(axesCheck);
  labelAxes.appendChild(document.createTextNode("显示骨骼轴向（红=X 绿=Y 蓝=Z）"));
  panel.appendChild(labelAxes);

  const flipRow = document.createElement("div");
  flipRow.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;align-items:center;";
  const applyFlip = () => {
    if (playing && frameData?.length) applyFrame(currentFrameIndex);
    else if (!playing && frameData?.length && vrm?.humanoid) applyIdentityToAllBones();
    if (vrm?.update) vrm.update(0);
  };
  ["X", "Y", "Z"].forEach((axis) => {
    const lab = document.createElement("label");
    lab.style.cssText = "display:flex;align-items:center;gap:4px;cursor:pointer;";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.axis = axis;
    cb.addEventListener("change", () => {
      if (axis === "X") flipX = cb.checked;
      if (axis === "Y") flipY = cb.checked;
      if (axis === "Z") flipZ = cb.checked;
      applyFlip();
    });
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(axis + " 取反"));
    flipRow.appendChild(lab);
  });
  panel.appendChild(flipRow);
  const hint = document.createElement("div");
  hint.style.cssText = "font-size:11px;color:#666;max-width:260px;";
  hint.textContent = "说明：数据未重算，仅前端对旋转做轴翻转。若 X/Y/Z 各种组合仍不对，需改 Python 坐标系或 rest 姿态后重跑并替换 JSON。";
  panel.appendChild(hint);

  document.body.appendChild(panel);

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}

function loadVRM() {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const vrmUrl = "/test_spiderman.vrm";
  loader.load(
    vrmUrl,
    (gltf) => {
      vrm = gltf.userData.vrm;
      scene.add(vrm.scene);
      if (vrm.lookAt) {
        vrm.lookAt.autoUpdate = false;
      }
    },
    undefined,
    (err) => {
      const msg = err?.message || String(err);
      if (msg.includes("<!DOCTYPE") || msg.includes("Unexpected token '<'")) {
        console.error("VRM 加载失败: 未找到模型文件。请将 test_spider.vrm 放入 public 目录，或修改 vrmUrl 为实际文件名（如 /test_spiderman.vrm）。", err);
      } else {
        console.error("VRM 加载失败:", err);
      }
    }
  );
}

function loadStrokeData() {
  fetch("/stroke_data_vrm_quaternions.json")
    .then((r) => r.json())
    .then((data) => {
      frameData = data;
      console.log("手语数据已加载，帧数:", data.length);
    })
    .catch((err) => console.error("手语数据加载失败:", err));
}

function applyFrame(index) {
  if (!vrm?.humanoid || !frameData || index < 0 || index >= frameData.length) return;
  const frame = frameData[index];
  const quaternions = frame.quaternions;
  if (!quaternions) return;

  for (const pascalName of Object.keys(quaternions)) {
    const qArr = quaternions[pascalName];
    if (!Array.isArray(qArr) || qArr.length !== 4) continue;
    const vrmName = toVrmBoneName(pascalName);
    const boneNode = vrm.humanoid.getNormalizedBoneNode(vrmName);
    if (!boneNode) continue;
    _q.set(qArr[0], qArr[1], qArr[2], qArr[3]);
    if (flipZ) _q.premultiply(flipZQuat);
    if (flipY) _q.premultiply(flipYQuat);
    if (flipX) _q.premultiply(flipXQuat);
    boneNode.quaternion.copy(_q);
  }
}

function applyIdentityToAllBones() {
  if (!vrm?.humanoid || !frameData?.length) return;
  const quaternions = frameData[0].quaternions;
  if (!quaternions) return;
  for (const pascalName of Object.keys(quaternions)) {
    const vrmName = toVrmBoneName(pascalName);
    const boneNode = vrm.humanoid.getNormalizedBoneNode(vrmName);
    if (!boneNode) continue;
    _q.set(...IDENTITY_QUAT);
    if (flipZ) _q.premultiply(flipZQuat);
    if (flipY) _q.premultiply(flipYQuat);
    if (flipX) _q.premultiply(flipXQuat);
    boneNode.quaternion.copy(_q);
  }
}

function makeThickAxes(length = 0.4, radius = 0.022) {
  const group = new THREE.Group();
  const coneH = length * 0.25;
  const bodyLen = length - coneH;
  const bodyHalf = bodyLen / 2;
  const coneHalf = coneH / 2;
  const matX = new THREE.MeshBasicMaterial({ color: 0xe53935 });
  const matY = new THREE.MeshBasicMaterial({ color: 0x43a047 });
  const matZ = new THREE.MeshBasicMaterial({ color: 0x1e88e5 });
  const bodyGeo = new THREE.CylinderGeometry(radius, radius, bodyLen, 10);
  const coneGeo = new THREE.ConeGeometry(radius * 1.2, coneH, 10);

  const bodyY = new THREE.Mesh(bodyGeo.clone(), matY);
  bodyY.position.set(0, bodyHalf, 0);
  group.add(bodyY);
  const coneY = new THREE.Mesh(coneGeo.clone(), matY);
  coneY.position.set(0, bodyLen + coneHalf, 0);
  group.add(coneY);

  const bodyX = new THREE.Mesh(bodyGeo.clone(), matX);
  bodyX.rotation.z = -Math.PI / 2;
  bodyX.position.set(bodyHalf, 0, 0);
  group.add(bodyX);
  const coneX = new THREE.Mesh(coneGeo.clone(), matX);
  coneX.rotation.z = -Math.PI / 2;
  coneX.position.set(bodyLen + coneHalf, 0, 0);
  group.add(coneX);

  const bodyZ = new THREE.Mesh(bodyGeo.clone(), matZ);
  bodyZ.rotation.x = -Math.PI / 2;
  bodyZ.position.set(0, 0, bodyHalf);
  group.add(bodyZ);
  const coneZ = new THREE.Mesh(coneGeo.clone(), matZ);
  coneZ.rotation.x = -Math.PI / 2;
  coneZ.position.set(0, 0, bodyLen + coneHalf);
  group.add(coneZ);

  return group;
}

const AXES_BONES = [
  "spine", "chest", "neck", "head",
  "leftShoulder", "rightShoulder",
  "leftUpperArm", "rightUpperArm",
  "leftLowerArm", "rightLowerArm",
  "leftHand", "rightHand",
  "leftThumbMetacarpal", "rightThumbMetacarpal",
  "leftIndexProximal", "rightIndexProximal",
  "leftMiddleProximal", "rightMiddleProximal",
  "leftRingProximal", "rightRingProximal",
  "leftLittleProximal", "rightLittleProximal",
];

function toggleBoneAxes(show) {
  axisHelpers.forEach((h) => h.parent?.remove(h));
  axisHelpers.length = 0;
  if (!show || !vrm?.humanoid) return;
  const size = 0.32;
  const radius = 0.018;
  AXES_BONES.forEach((name) => {
    const node = vrm.humanoid.getNormalizedBoneNode(name);
    if (!node) return;
    const axes = makeThickAxes(size, radius);
    node.add(axes);
    axisHelpers.push(axes);
  });
}

function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();

  if (playing && frameData && frameData.length > 0) {
    const frameDt = FRAME_DT / playbackSpeed;
    accumulatedTime += delta;
    while (accumulatedTime >= frameDt) {
      accumulatedTime -= frameDt;
      currentFrameIndex += 1;
      if (currentFrameIndex >= frameData.length) currentFrameIndex = 0;
    }
    applyFrame(currentFrameIndex);
    if (vrm?.update) vrm.update(delta);
  }

  renderer.render(scene, camera);
}

init();
loadVRM();
loadStrokeData();
animate();

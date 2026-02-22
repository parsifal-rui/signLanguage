/**
 * Phase 3: 加载 timeline JSON，按序加载 BVH，在 Three.js 中播放骨骼动画。
 * BVH 仅含骨骼+动画，不含蒙皮网格；完整人形需另加载 glTF 等并做骨骼重定向。
 * 此处用骨骼线 + 关节球 + 肢体圆柱 拼出可辨认的人形。
 */

import * as THREE from "three";
import { BVHLoader } from "three/addons/loaders/BVHLoader.js";

const DATA_BASE = "/data/text2gloss";
const TIMELINE_URL = `${DATA_BASE}/mockTimeline.json`;

let scene, camera, renderer, clock;
let currentGroup = null;
let mixer = null;
let timeline = null;
let clipIndex = 0;

function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe8eaf0);
  camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.01, 100);
  camera.position.set(0, 3, 2.5);
  camera.lookAt(0, 2.0, 0);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  document.body.appendChild(renderer.domElement);
  clock = new THREE.Clock();
  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}

function loadTimeline() {
  return fetch(TIMELINE_URL).then((r) => r.json());
}

function loadBVH(url) {
  return new Promise((resolve, reject) => {
    const loader = new BVHLoader();
    loader.load(
      url,
      (result) => resolve(result),
      undefined,
      (e) => reject(e)
    );
  });
}

function normalizeMixamorigBonesAndClip(result) {
  const skeleton = result.skeleton;
  skeleton.bones.forEach((b) => {
    if (b.name.startsWith("mixamorig:")) b.name = b.name.replace(/^mixamorig:/, "");
  });
  const newTracks = result.clip.tracks.map((track) => {
    const path = track.name;
    const dot = path.indexOf(".");
    const nodeName = dot >= 0 ? path.slice(0, dot) : path;
    const rest = dot >= 0 ? path.slice(dot) : "";
    const name = nodeName.startsWith("mixamorig:") ? nodeName.replace(/^mixamorig:/, "") : nodeName;
    if (name === nodeName) return track;
    return new THREE.KeyframeTrack(name + rest, track.times, track.values);
  });
  result.clip = new THREE.AnimationClip(result.clip.name, result.clip.duration, newTracks);
  return result;
}

function playClip(result, duration, gloss) {
  if (currentGroup) {
    scene.remove(currentGroup);
  }
  result = normalizeMixamorigBonesAndClip(result);
  const root = result.skeleton.bones[0];
  const clip = result.clip;
  const limbMat = new THREE.MeshBasicMaterial({ color: 0x2d5a3d });
  const jointMat = new THREE.MeshBasicMaterial({ color: 0x5c4a1a });
  const jointGeo = new THREE.SphereGeometry(2.5, 10, 8);
  const limbGeo = new THREE.CylinderGeometry(1.2, 1.2, 1, 8);
  root.traverse((node) => {
    if (!node.isBone) return;
    const joint = new THREE.Mesh(jointGeo, jointMat);
    joint.position.set(0, 0, 0);
    node.add(joint);
    node.children.forEach((child) => {
      if (!child.isBone) return;
      const len = child.position.length();
      if (len < 1e-5) return;
      const cyl = new THREE.Mesh(limbGeo, limbMat);
      cyl.scale.set(1, len, 1);
      cyl.position.copy(child.position).multiplyScalar(0.5);
      cyl.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        child.position.clone().normalize()
      );
      node.add(cyl);
    });
  });
  currentGroup = new THREE.Group();
  currentGroup.add(root);
  currentGroup.scale.setScalar(0.01);
  currentGroup.position.set(0, 0, 0);
  scene.add(currentGroup);

  mixer = new THREE.AnimationMixer(root);
  const action = mixer.clipAction(clip);
  action.play();
  document.getElementById("gloss").textContent = gloss ? `Gloss: ${gloss}` : "";

  const start = clock.getElapsedTime();
  function checkEnd() {
    if (clock.getElapsedTime() - start >= duration) {
      return true;
    }
    mixer.update(clock.getDelta());
    return false;
  }
  return checkEnd;
}

async function runTimeline() {
  const info = document.getElementById("info");
  try {
    timeline = await loadTimeline();
    info.textContent = `时间线: ${timeline.gloss_list?.join(" → ") || "无"}，共 ${timeline.timeline?.length || 0} 段`;
  } catch (e) {
    info.textContent = "加载 timeline 失败: " + e.message;
    return;
  }

  const clips = timeline.timeline || [];
  if (clips.length === 0) {
    info.textContent = "时间线为空";
    return;
  }

  clipIndex = 0;

  function playNext() {
    if (clipIndex >= clips.length) {
      clipIndex = 0;
    }
    const item = clips[clipIndex];
    const bvhUrl = `${DATA_BASE}/${item.bvh}`;
    const gloss = item.gloss || "";

    loadBVH(bvhUrl)
      .then((result) => {
        const duration = result.clip.duration;
        playClip(result, duration, gloss);
        clipIndex++;
        setTimeout(playNext, duration * 1000);
      })
      .catch((e) => {
        info.textContent = `加载 BVH 失败: ${item.bvh} - ${e.message}`;
        clipIndex++;
        setTimeout(playNext, 2000);
      });
  }

  playNext();
}

function animate() {
  requestAnimationFrame(animate);
  if (mixer) {
    mixer.update(clock.getDelta());
  }
  renderer.render(scene, camera);
}

init();
runTimeline();
animate();

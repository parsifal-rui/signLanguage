# Phase 3：库与模型说明

## 需要安装的库

在 **web** 目录下执行：

```bash
cd web
npm install
```

会安装：

- **three**：Three.js 核心 + 示例（含 `BVHLoader`），用于 3D 场景、相机、渲染与 BVH 动画加载。

无需再单独安装 BVH 解析库，Three 自带 `examples/jsm/loaders/BVHLoader.js`。

---

## 当前使用的“模型”

- **骨骼显示**：未使用独立 3D 人物模型文件，仅用 BVH 自带的骨骼 + Three.js 的 `SkeletonHelper` 在场景里画骨架线，用于先跑通「时间线 → BVH → 播放」流程。

---

## 可选：带皮肤的 3D 人物模型（后续替换用）

若之后要换成带皮肤的真人形，可考虑（需自行下载，本仓库不包含）：

| 来源 | 说明 | 格式 |
|------|------|------|
| **Mixamo** | 选一个角色（如 X Bot），下载 FBX 或 glTF，与现有 BVH 骨骼做重定向后驱动 | FBX / glTF |
| **Quaternius** | 免费低面数角色，部分带骨骼 | glTF |
| **Three.js 示例** | 如 `models/gltf/XBot.glb` 等，用于测试重定向管线 | GLB |

把下载的模型放到 `web/public/models/`（或你指定的目录），再在代码里加载该模型并改为用 timeline 的 BVH 驱动其骨骼即可。

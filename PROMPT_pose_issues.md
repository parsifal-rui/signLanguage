# 手语 VRM 播放 — 当前问题总结（待改 Prompt）

## 现状

- **前端**：Three.js + @pixiv/three-vrm，加载 VRM 模型，用 `stroke_data_vrm_quaternions.json` 驱动骨骼（每帧对 normalized 骨骼 `quaternion.set(x,y,z,w)`）。
- **数据来源**：`stroke_to_vrm_quaternions.py` 从 `stroke_data.json`（MediaPipe pose + 双手 21 点）算出 VRM Humanoid 的**局部旋转四元数** [x,y,z,w]，再写入 JSON。
- **前端试错**：已加 X/Y/Z 取反（各 180° 旋转）共 8 种组合，均未得到正确姿态。

## 已暴露的问题

1. **姿态错误**
   - 默认播放：姿态明显不对。
   - 仅 Z 取反：另一种错误，仍不对。
   - X/Y/Z 各种取反组合试过仍不行 → 怀疑不只是「某一轴方向反了」，而是**整套坐标系或 rest 姿态**与 VRM 不一致。

2. **动作/轴向不连续、扭曲**
   - 一旦开始动：手的 X 轴向上、上半身 Y 轴左右扭曲。
   - 坐标轴移动看起来不连续。
   - 手的角度很奇怪。

3. **轴向显示**
   - 已给躯干+手臂+手+手指根节共 22 个骨骼画轴向（红=X 绿=Y 蓝=Z，带锥尖）。
   - 蓝轴垂直于屏幕时无法分辨锥尖/锥底（已知，影响不大）。

## 可能原因（待排查）

1. **Python 侧坐标系**
   - `mediapipe_to_webgl` 当前：`[x, -y, -z]`（Y、Z 翻转）。是否应与 VRM/Three 完全一致？是否需要尝试 `[x, -y, z]` 或其它组合？
   - 大臂/小臂 rest 向量：`RIGHT_UPPER_ARM_REST = [-1,0,0]`，`LEFT = [1,0,0]` 等，是否与当前 VRM 的 T 姿一致？（不同模型可能 A 姿或轴向不同。）

2. **局部旋转参考系**
   - Python 用「世界旋转 → 父子链求局部」得到四元数；VRM normalized 骨骼的「局部」是否同一套约定？（左手系/右手系、父子顺序、rest 是否为 identity。）

3. **手部/手指**
   - 手指用 `rest_dir = [0, 0, 1]` 等约定；与 VRM 手部骨骼的 rest 轴向是否一致？
   - 手部关节多，若 rest 或轴向不一致，容易表现为「手的角度很奇怪」和扭曲。

4. **数据未重算**
   - 前端 X/Y/Z 取反只是在播放时乘 180° 旋转，**没有改 Python、也没有重新生成 JSON**。若要对齐坐标系或 rest，必须在 Python 里改逻辑后重跑 `stroke_to_vrm_quaternions.py`，用新 JSON 替换 `public/stroke_data_vrm_quaternions.json`。

## 建议的下一步（明日改时用）

1. **确认 VRM 的 T 姿与轴向**
   - 在前端用「显示 T 姿」+「显示骨骼轴向」看当前模型：手臂/躯干/手的 +X、+Y、+Z 实际朝向。
   - 与 Python 里假设的（如右大臂 -X、左大臂 +X、Y 上、Z 朝相机）逐项对比。

2. **在 Python 里做坐标系/rest 修正**
   - 若 VRM 的 +Z 与 Python 假设相反：在 `mediapipe_to_webgl` 中尝试不翻 Z（或只翻 Y），或对最终四元数乘 180°（绕 Y 或绕 X）再导出。
   - 若手臂 rest 不是 ±X：根据 VRM 轴向修改 `*_UPPER_ARM_REST`、`*_LOWER_ARM_REST` 等。
   - 改完后重跑：  
     `python stroke_to_vrm_quaternions.py stroke_data.json`  
     将生成结果覆盖 `public/stroke_data_vrm_quaternions.json`，再在前端播放验证。

3. **可选：前端保留试错能力**
   - 保留或简化 X/Y/Z 取反开关，用于快速验证「只差一轴方向」的情况。
   - 若确认问题在 Python，以后可去掉或收起到「调试」里。

4. **手部单独核对**
   - 对照 VRM 手部骨骼的 rest 方向，检查 `stroke_to_vrm_quaternions.py` 里手指的 `rest_dir`、链式局部旋转是否与 VRM 一致；必要时为手部单独做轴向或符号修正。

---

*生成自当前问题总结，供明日按此 prompt 修改 Python 与数据流程。*

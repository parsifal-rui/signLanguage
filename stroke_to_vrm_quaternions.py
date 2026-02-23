"""
将 MediaPipe 提取的 stroke_data.json 转为 VRM Humanoid 局部旋转四元数。
仅输出：Spine, Chest, Neck, Head, 左右 Shoulder/UpperArm/LowerArm/Hand，及 30 根手指骨骼。
完全忽略下半身。使用 scipy.spatial.transform.Rotation 处理四元数。
"""
import json
import numpy as np
from scipy.spatial.transform import Rotation
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. 坐标系转换：MediaPipe -> WebGL (Three.js / VRM)
# ---------------------------------------------------------------------------
# MediaPipe：通常 X 右、Y 下（图像）、Z 朝里（深度负值朝相机）。
# WebGL/Three.js：X 右、Y 上、Z 朝相机。故需翻转 Y 和 Z。
def mediapipe_to_webgl(p):
    """将单点 [x,y,z] 从 MediaPipe 坐标系转到 WebGL 右手系。"""
    return [float(p[0]), float(-p[1]), float(-p[2])]


def apply_webgl(pose, left_hand, right_hand):
    """将 pose(33点) 与双手(各21点) 全部转到 WebGL 系。"""
    pose_w = [mediapipe_to_webgl(pt) for pt in pose] if pose else []
    left_w = [mediapipe_to_webgl(pt) for pt in left_hand] if left_hand else []
    right_w = [mediapipe_to_webgl(pt) for pt in right_hand] if right_hand else []
    return pose_w, left_w, right_w


# ---------------------------------------------------------------------------
# 2. MediaPipe Pose 33 点索引（仅用到的）
# ---------------------------------------------------------------------------
class PoseIdx:
    NOSE = 0
    L_SHOULDER, R_SHOULDER = 11, 12
    L_ELBOW, R_ELBOW = 13, 14
    L_WRIST, R_WRIST = 15, 16
    L_HIP, R_HIP = 23, 24


def _v(p):
    return np.array(p, dtype=float)


def _normalize(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-8 else v


def _safe_rotation_from_directions(from_dir, to_dir):
    """从 from_dir 旋转到 to_dir 的单轴旋转（用于骨骼朝向）。"""
    f = _normalize(np.array(from_dir, dtype=float))
    t = _normalize(np.array(to_dir, dtype=float))
    c = np.dot(f, t)
    if c >= 1.0 - 1e-6:
        return Rotation.identity()
    if c <= -1.0 + 1e-6:
        axis = np.cross(f, np.array([0, 1, 0]))
        if np.linalg.norm(axis) < 1e-8:
            axis = np.cross(f, np.array([1, 0, 0]))
        return Rotation.from_rotvec(np.pi * _normalize(axis))
    axis = _normalize(np.cross(f, t))
    angle = np.arccos(np.clip(c, -1, 1))
    return Rotation.from_rotvec(axis * angle)


def _rotation_from_orthogonal(forward, up):
    """由前向与上向构造旋转矩阵（列向量为轴），再转为四元数。"""
    f = _normalize(np.array(forward, dtype=float))
    u = _normalize(np.array(up, dtype=float))
    r = _normalize(np.cross(f, u))
    u = _normalize(np.cross(r, f))
    R = np.eye(3)
    R[:, 0] = r
    R[:, 1] = u
    R[:, 2] = -f
    return Rotation.from_matrix(R)


# ---------------------------------------------------------------------------
# 3. VRM T-Pose 基准向量（WebGL 系）
# ---------------------------------------------------------------------------
# 右大臂默认朝向 -X，左大臂默认朝向 +X（手心朝下）。
RIGHT_UPPER_ARM_REST = np.array([-1.0, 0.0, 0.0])
LEFT_UPPER_ARM_REST = np.array([1.0, 0.0, 0.0])
RIGHT_LOWER_ARM_REST = np.array([-1.0, 0.0, 0.0])
LEFT_LOWER_ARM_REST = np.array([1.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# 4. 躯干与手臂：世界旋转 -> 局部旋转（层级）
# ---------------------------------------------------------------------------
def _world_rotation_spine_chain(pose_w):
    """Spine -> Chest -> Neck -> Head 的世界旋转（简化：用方向向量估计）。"""
    hip_c = (_v(pose_w[PoseIdx.L_HIP]) + _v(pose_w[PoseIdx.R_HIP])) / 2
    shoulder_c = (_v(pose_w[PoseIdx.L_SHOULDER]) + _v(pose_w[PoseIdx.R_SHOULDER])) / 2
    nose = _v(pose_w[PoseIdx.NOSE])

    spine_vec = _normalize(shoulder_c - hip_c)
    chest_vec = spine_vec
    neck_vec = _normalize(nose - shoulder_c)
    head_vec = neck_vec

    up = np.array([0, 1, 0])
    def _to_rot(v):
        if np.linalg.norm(v) < 1e-8:
            return Rotation.identity()
        f = _normalize(v)
        r = _normalize(np.cross(up, f))
        if np.linalg.norm(r) < 1e-8:
            r = np.array([1, 0, 0])
        u = np.cross(f, r)
        R = np.eye(3)
        R[:, 0], R[:, 1], R[:, 2] = r, u, -f
        return Rotation.from_matrix(R)

    return {
        "Spine": _to_rot(spine_vec),
        "Chest": _to_rot(chest_vec),
        "Neck": _to_rot(neck_vec),
        "Head": _to_rot(head_vec),
    }


def _world_rotation_arm(pose_w, side):
    """一侧手臂：Shoulder, UpperArm, LowerArm, Hand 的世界旋转。"""
    if side == "left":
        sh, el, wr = PoseIdx.L_SHOULDER, PoseIdx.L_ELBOW, PoseIdx.L_WRIST
        upper_rest, lower_rest = LEFT_UPPER_ARM_REST, LEFT_LOWER_ARM_REST
    else:
        sh, el, wr = PoseIdx.R_SHOULDER, PoseIdx.R_ELBOW, PoseIdx.R_WRIST
        upper_rest, lower_rest = RIGHT_UPPER_ARM_REST, RIGHT_LOWER_ARM_REST

    p_sh = _v(pose_w[sh])
    p_el = _v(pose_w[el])
    p_wr = _v(pose_w[wr])

    shoulder_center = (_v(pose_w[PoseIdx.L_SHOULDER]) + _v(pose_w[PoseIdx.R_SHOULDER])) / 2
    to_el = _normalize(p_el - p_sh)
    to_wr_from_el = _normalize(p_wr - p_el)

    R_shoulder = _safe_rotation_from_directions(upper_rest, to_el)
    R_upper = _safe_rotation_from_directions(upper_rest, to_el)
    R_lower = _safe_rotation_from_directions(lower_rest, to_wr_from_el)
    R_hand = Rotation.identity()
    return {
        "Shoulder": R_shoulder,
        "UpperArm": R_upper,
        "LowerArm": R_lower,
        "Hand": R_hand,
    }, (p_sh, p_el, p_wr)


def _hand_world_rotation_from_palm(hand_w):
    """用手部 0(腕)、5(食指根)、17(小指根) 建手掌坐标系，得到 Hand 的世界旋转。"""
    if not hand_w or len(hand_w) < 18:
        return Rotation.identity()
    p0 = _v(hand_w[0])
    p5 = _v(hand_w[5])
    p17 = _v(hand_w[17])
    palm_normal = np.cross(p5 - p0, p17 - p0)
    if np.linalg.norm(palm_normal) < 1e-8:
        return Rotation.identity()
    up = _normalize(palm_normal)
    forward = _normalize((p5 + p17) / 2 - p0)
    if np.linalg.norm(forward) < 1e-8:
        return Rotation.identity()
    return _rotation_from_orthogonal(forward, up)


def _world_rotations_arms_with_hand_twist(pose_w, left_hand_w, right_hand_w):
    """手臂 + 手腕扭转：LowerArm/Hand 用肘-腕方向 + 手掌法线。"""
    left_arm, (_, p_el_l, p_wr_l) = _world_rotation_arm(pose_w, "left")
    right_arm, (_, p_el_r, p_wr_r) = _world_rotation_arm(pose_w, "right")

    def set_hand_twist(arm_dict, hand_pts, elbow_pt, wrist_pt, upper_rest_vec):
        to_wrist = _normalize(wrist_pt - elbow_pt)
        arm_dict["LowerArm"] = _safe_rotation_from_directions(
            upper_rest_vec if np.dot(to_wrist, upper_rest_vec) >= 0 else -upper_rest_vec,
            to_wrist,
        )
        R_hand = _hand_world_rotation_from_palm(hand_pts)
        arm_dict["Hand"] = R_hand

    if left_hand_w and len(left_hand_w) >= 18:
        set_hand_twist(left_arm, left_hand_w, p_el_l, p_wr_l, LEFT_LOWER_ARM_REST)
    if right_hand_w and len(right_hand_w) >= 18:
        set_hand_twist(right_arm, right_hand_w, p_el_r, p_wr_r, RIGHT_LOWER_ARM_REST)

    return left_arm, right_arm


def _to_local_chain(parent_names, world_rots):
    """父子链：Local_Q = Inv(Parent_World_Q) * Current_World_Q。"""
    out = {}
    prev_inv = None
    for name in parent_names:
        W = world_rots[name]
        if prev_inv is None:
            local = W
        else:
            local = prev_inv * W
        out[name] = local
        prev_inv = (W.inv() * prev_inv) if prev_inv is not None else W.inv()
    return out


def _quat_xyzw(r):
    """scipy Rotation 的 as_quat() 为 xyzw，返回 [x,y,z,w] 列表。"""
    q = r.as_quat()
    return [float(q[0]), float(q[1]), float(q[2]), float(q[3])]


# ---------------------------------------------------------------------------
# 5. 手指：15 根/手，局部四元数（T-Pose 伸直为 identity）
# ---------------------------------------------------------------------------
# MediaPipe 手 21 点：0 腕, 1-4 拇指, 5-8 食指, 9-12 中指, 13-16 无名指, 17-20 小指。
# VRM：Thumb Metacarpal/Proximal/Distal；其余 Proximal/Intermediate/Distal。
FINGER_CHAINS = [
    ("Thumb", [1, 2, 3, 4], ["LeftThumbMetacarpal", "LeftThumbProximal", "LeftThumbDistal"]),
    ("Index", [5, 6, 7, 8], ["LeftIndexProximal", "LeftIndexIntermediate", "LeftIndexDistal"]),
    ("Middle", [9, 10, 11, 12], ["LeftMiddleProximal", "LeftMiddleIntermediate", "LeftMiddleDistal"]),
    ("Ring", [13, 14, 15, 16], ["LeftRingProximal", "LeftRingIntermediate", "LeftRingDistal"]),
    ("Little", [17, 18, 19, 20], ["LeftLittleProximal", "LeftLittleIntermediate", "LeftLittleDistal"]),
]
FINGER_CHAINS_RIGHT = [
    ("Thumb", [1, 2, 3, 4], ["RightThumbMetacarpal", "RightThumbProximal", "RightThumbDistal"]),
    ("Index", [5, 6, 7, 8], ["RightIndexProximal", "RightIndexIntermediate", "RightIndexDistal"]),
    ("Middle", [9, 10, 11, 12], ["RightMiddleProximal", "RightMiddleIntermediate", "RightMiddleDistal"]),
    ("Ring", [13, 14, 15, 16], ["RightRingProximal", "RightRingIntermediate", "RightRingDistal"]),
    ("Little", [17, 18, 19, 20], ["RightLittleProximal", "RightLittleIntermediate", "RightLittleDistal"]),
]


def _finger_local_rotations(hand_w, chains, prefix=""):
    """根据手部 21 点计算每节相对父节点的局部四元数。T-Pose 下手指伸直，局部 rest 为 +Z 或约定轴。"""
    out = {}
    if not hand_w or len(hand_w) < 21:
        for chain in chains:
            for name in chain[2]:
                out[name] = _quat_xyzw(Rotation.identity())
        return out

    for (_, indices, bone_names) in chains:
        rest_dir = np.array([0, 0, 1])
        parent_inv = None
        for i in range(len(bone_names)):
            a, b = indices[i], indices[i + 1]
            pa = _v(hand_w[a])
            pb = _v(hand_w[b])
            seg_dir = _normalize(pb - pa)
            R_world = _safe_rotation_from_directions(rest_dir, seg_dir)
            if parent_inv is None:
                R_local = R_world
            else:
                R_local = parent_inv * R_world
            out[bone_names[i]] = _quat_xyzw(R_local)
            parent_inv = R_world.inv() * parent_inv if parent_inv is not None else R_world.inv()
    return out


# ---------------------------------------------------------------------------
# 6. 单帧：从 pose + left_hand + right_hand 到 VRM 四元数 JSON
# ---------------------------------------------------------------------------
def frame_to_vrm_quaternions(pose, left_hand, right_hand):
    """
    输入：pose (33点), left_hand / right_hand (各21点)，均为 [x,y,z] 列表。
    输出：仅包含指定骨骼的局部四元数 [x,y,z,w] 的字典。
    """
    pose_w, left_w, right_w = apply_webgl(pose, left_hand, right_hand)
    if len(pose_w) < 33:
        pose_w = pose_w + [[0.0, 0.0, 0.0]] * (33 - len(pose_w))

    # 躯干链世界旋转 -> 局部
    spine_world = _world_rotation_spine_chain(pose_w)
    spine_chain = ["Spine", "Chest", "Neck", "Head"]
    spine_local = _to_local_chain(spine_chain, spine_world)

    # 手臂链（含手腕扭转）
    left_arm_w, right_arm_w = _world_rotations_arms_with_hand_twist(
        pose_w, left_w, right_w
    )
    chest_w = spine_world["Chest"]
    # 层级: Chest -> Shoulder -> UpperArm -> LowerArm -> Hand
    result = {}

    for name in spine_chain:
        result[name] = _quat_xyzw(spine_local[name])

    result["LeftShoulder"] = _quat_xyzw(chest_w.inv() * left_arm_w["Shoulder"])
    result["LeftUpperArm"] = _quat_xyzw(left_arm_w["Shoulder"].inv() * left_arm_w["UpperArm"])
    result["LeftLowerArm"] = _quat_xyzw(left_arm_w["UpperArm"].inv() * left_arm_w["LowerArm"])
    result["LeftHand"] = _quat_xyzw(left_arm_w["LowerArm"].inv() * left_arm_w["Hand"])
    result["RightShoulder"] = _quat_xyzw(chest_w.inv() * right_arm_w["Shoulder"])
    result["RightUpperArm"] = _quat_xyzw(right_arm_w["Shoulder"].inv() * right_arm_w["UpperArm"])
    result["RightLowerArm"] = _quat_xyzw(right_arm_w["UpperArm"].inv() * right_arm_w["LowerArm"])
    result["RightHand"] = _quat_xyzw(right_arm_w["LowerArm"].inv() * right_arm_w["Hand"])

    left_fingers = _finger_local_rotations(left_w, FINGER_CHAINS, "Left")
    right_fingers = _finger_local_rotations(right_w, FINGER_CHAINS_RIGHT, "Right")
    for k, v in left_fingers.items():
        result[k] = v
    for k, v in right_fingers.items():
        result[k] = v

    return result


# ---------------------------------------------------------------------------
# 7. 批量处理 stroke_data.json 并写回 JSON
# ---------------------------------------------------------------------------
def stroke_data_to_vrm_quaternions(stroke_data_path, out_path=None):
    """
    读取 stroke_data.json（每项含 frame, pose, left_hand, right_hand），
    逐帧计算 VRM 局部四元数，写入 JSON。
    """
    path = Path(stroke_data_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]

    out_list = []
    for item in data:
        frame = item.get("frame", len(out_list))
        pose = item.get("pose", [])
        left_hand = item.get("left_hand", [])
        right_hand = item.get("right_hand", [])
        quats = frame_to_vrm_quaternions(pose, left_hand, right_hand)
        out_list.append({"frame": frame, "quaternions": quats})

    if out_path is None:
        out_path = path.parent / (path.stem + "_vrm_quaternions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_list, f, ensure_ascii=False, indent=2)
    return out_list


if __name__ == "__main__":
    import sys
    inp = sys.argv[1] if len(sys.argv) > 1 else "stroke_data.json"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    stroke_data_to_vrm_quaternions(inp, out)
    print("已写入 VRM 局部四元数 JSON。")

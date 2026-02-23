"""
手语视频 → Holistic 骨骼 + 面部锚点 + 手腕速度 + Stroke 检测 → stroke_data.json
依赖: opencv-python, mediapipe, numpy, scipy, matplotlib
"""
import json
import cv2
import numpy as np
import mediapipe as mp
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt
from pathlib import Path

VIDEO_PATH = "test_video1.mp4"
OUT_JSON = "stroke_data.json"
OUT_PLOT = "velocity_stroke.png"

FACE_ANCHOR_INDICES = [1, 152, 162, 389, 9, 61, 291]
FACE_ANCHOR_NAMES = ["nose_tip", "chin", "left_temple", "right_temple", "glabella", "mouth_left", "mouth_right"]
POSE_LEFT_WRIST, POSE_RIGHT_WRIST = 15, 16

SAVGOL_WINDOW = 11
SAVGOL_POLY = 3
STROKE_VELOCITY_THRESHOLD_RATIO = 0.15
STROKE_MIN_FRAMES = 3

HAND_LANDMARKS_COUNT = 21
PLACEHOLDER_HAND = [[0.0, 0.0, 0.0]] * HAND_LANDMARKS_COUNT


def landmark_to_list(lm):
    return [lm.x, lm.y, lm.z]


def extract_pose(pose_landmarks):
    if pose_landmarks is None:
        return None
    return [landmark_to_list(lm) for lm in pose_landmarks.landmark]


def extract_hand(hand_landmarks):
    if hand_landmarks is None:
        return None
    return [landmark_to_list(lm) for lm in hand_landmarks.landmark]


def extract_face_anchors(face_landmarks):
    if face_landmarks is None:
        return None
    out = []
    for j, idx in enumerate(FACE_ANCHOR_INDICES):
        lm = face_landmarks.landmark[idx]
        out.append({"name": FACE_ANCHOR_NAMES[j], "xyz": [lm.x, lm.y, lm.z]})
    return out


def fill_or_keep(current, last):
    if current is not None:
        return current
    return last


def euclidean3d(a, b):
    return float(np.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))


def run_holistic_on_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"无法打开视频: {video_path}")
    mp_holistic = mp.solutions.holistic
    all_frames_data = []
    last_pose = last_face = None
    last_good_left_hand = None
    last_good_right_hand = None

    with mp_holistic.Holistic(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as holistic:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = holistic.process(rgb)

            pose = fill_or_keep(extract_pose(results.pose_landmarks), last_pose)
            face_anchors = fill_or_keep(extract_face_anchors(results.face_landmarks), last_face)

            raw_left = extract_hand(results.left_hand_landmarks)
            raw_right = extract_hand(results.right_hand_landmarks)

            if raw_left is not None and len(raw_left) == HAND_LANDMARKS_COUNT:
                left_hand = raw_left
                last_good_left_hand = raw_left
            else:
                left_hand = last_good_left_hand if last_good_left_hand is not None else PLACEHOLDER_HAND

            if raw_right is not None and len(raw_right) == HAND_LANDMARKS_COUNT:
                right_hand = raw_right
                last_good_right_hand = raw_right
            else:
                right_hand = last_good_right_hand if last_good_right_hand is not None else PLACEHOLDER_HAND

            if pose is None:
                pose = last_pose if last_pose is not None else []
            if face_anchors is None:
                face_anchors = last_face if last_face is not None else []

            last_pose, last_face = pose, face_anchors
            all_frames_data.append({
                "pose": pose,
                "left_hand": left_hand,
                "right_hand": right_hand,
                "face_anchors": face_anchors,
            })
    cap.release()
    return all_frames_data


def compute_wrist_velocity(all_frames_data):
    n = len(all_frames_data)
    v_left = np.zeros(n)
    v_right = np.zeros(n)
    for i in range(1, n):
        p_prev = all_frames_data[i - 1]["pose"]
        p_curr = all_frames_data[i]["pose"]
        if len(p_prev) > max(POSE_LEFT_WRIST, POSE_RIGHT_WRIST) and len(p_curr) > max(POSE_LEFT_WRIST, POSE_RIGHT_WRIST):
            v_left[i] = euclidean3d(p_curr[POSE_LEFT_WRIST], p_prev[POSE_LEFT_WRIST])
            v_right[i] = euclidean3d(p_curr[POSE_RIGHT_WRIST], p_prev[POSE_RIGHT_WRIST])
    velocity = (v_left + v_right) / 2.0
    return velocity


def smooth_velocity(velocity):
    n = len(velocity)
    w = min(SAVGOL_WINDOW, n if n % 2 == 1 else n - 1)
    if w < SAVGOL_POLY + 2:
        return velocity
    return savgol_filter(velocity, window_length=w, polyorder=min(SAVGOL_POLY, w - 1))


def detect_stroke_segments(smoothed_velocity):
    thresh = float(np.percentile(smoothed_velocity, 20))
    thresh = max(thresh, np.median(smoothed_velocity) * STROKE_VELOCITY_THRESHOLD_RATIO)
    below = smoothed_velocity < thresh
    segments = []
    i = 0
    while i < len(below):
        if below[i]:
            start = i
            while i < len(below) and below[i]:
                i += 1
            if i - start >= STROKE_MIN_FRAMES:
                segments.append((start, i - 1))
        else:
            i += 1
    return segments, thresh


def plot_velocity_and_strokes(frames, smoothed_velocity, segments, thresh, out_path):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(frames, smoothed_velocity, color="steelblue", linewidth=1, label="velocity")
    ax.axhline(thresh, color="gray", linestyle="--", alpha=0.7, label="Stroke threshold")
    for start, end in segments:
        ax.axvspan(start, end + 1, alpha=0.35, color="coral", label="Stroke" if start == segments[0][0] else "")
    ax.set_xlabel("frame")
    ax.set_ylabel("wrist velocity (smoothed)")
    ax.legend(loc="upper right")
    ax.set_title("Wrist Velocity & Stroke Phases")
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    plt.close()


def frame_to_export_item(frame_idx, data):
    return {
        "frame": frame_idx,
        "pose": data["pose"],
        "left_hand": data["left_hand"],
        "right_hand": data["right_hand"],
        "face_anchors": data["face_anchors"],
    }


def main():
    video_path = Path(VIDEO_PATH)
    if not video_path.is_file():
        raise FileNotFoundError(f"请将测试视频放在: {video_path.absolute()}")

    print("1. 逐帧 Holistic 推理...")
    all_frames_data = run_holistic_on_video(str(video_path))
    n_frames = len(all_frames_data)
    print(f"   共 {n_frames} 帧")

    print("2. 计算手腕速度并平滑...")
    velocity = compute_wrist_velocity(all_frames_data)
    smoothed = smooth_velocity(velocity)

    print("3. Stroke 阶段检测...")
    segments, thresh = detect_stroke_segments(smoothed)
    stroke_frames = set()
    for start, end in segments:
        for f in range(start, end + 1):
            stroke_frames.add(f)
    print(f"   阈值={thresh:.6f}, Stroke 区间数={len(segments)}, Stroke 总帧数={len(stroke_frames)}")

    print("4. 可视化...")
    plot_velocity_and_strokes(
        list(range(n_frames)), smoothed, segments, thresh, OUT_PLOT
    )

    print("5. 导出 stroke_data.json...")
    stroke_list = [
        frame_to_export_item(i, all_frames_data[i])
        for i in sorted(stroke_frames)
    ]
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(stroke_list, f, ensure_ascii=False, indent=2)

    print("完成.")


if __name__ == "__main__":
    main()

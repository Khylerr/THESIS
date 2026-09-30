import os

import cv2
import mediapipe as mp
import numpy as np
from mediapipe import solutions
from mediapipe.framework.formats import landmark_pb2
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time


mp_hands = solutions.hands
mp_drawing = solutions.drawing_utils
mp_drawing_styles = solutions.drawing_styles

MARGIN = 10  # pixels
FONT_SIZE = 1
FONT_THICKNESS = 1
HANDEDNESS_TEXT_COLOR = (88, 205, 54)  # vibrant green (RGB)

BASE_DIR = r'C:\Users\Khyler\Desktop\THESIS\MediaPipe'
MODEL_PATH = os.path.join(BASE_DIR, 'hand_landmarker.task')
VIDEO_PATH = os.path.join(BASE_DIR, 'C:\\Users\\Khyler\\Desktop\\THESIS\\MediaPipe\\images\\video.mp4')  
OUTPUT_PATH = os.path.join(BASE_DIR, 'C:\\Users\\Khyler\\Desktop\\THESIS\\MediaPipe\\images\\output.mp4')
SHOW_PREVIEW = True  # press 'q' in the preview window to stop early


def draw_landmarks_on_image(rgb_image, detection_result):
    hand_landmarks_list = detection_result.hand_landmarks
    handedness_list = detection_result.handedness
    annotated_image = np.copy(rgb_image)

    for idx in range(len(hand_landmarks_list)):
        hand_landmarks = hand_landmarks_list[idx]
        handedness = handedness_list[idx]

        # Convert Tasks API landmarks into the protobuf format draw_landmarks expects
        hand_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
        hand_landmarks_proto.landmark.extend([
            landmark_pb2.NormalizedLandmark(x=lm.x, y=lm.y, z=lm.z)
            for lm in hand_landmarks
        ])

        mp_drawing.draw_landmarks(
            annotated_image,
            hand_landmarks_proto,
            mp_hands.HAND_CONNECTIONS,
            mp_drawing_styles.get_default_hand_landmarks_style(),
            mp_drawing_styles.get_default_hand_connections_style())

        height, width, _ = annotated_image.shape
        x_coordinates = [lm.x for lm in hand_landmarks]
        y_coordinates = [lm.y for lm in hand_landmarks]
        text_x = int(min(x_coordinates) * width)
        text_y = max(int(min(y_coordinates) * height) - MARGIN, 20)  # keep label on-screen

        cv2.putText(annotated_image, f"{handedness[0].category_name}",
                    (text_x, text_y), cv2.FONT_HERSHEY_DUPLEX,
                    FONT_SIZE, HANDEDNESS_TEXT_COLOR, FONT_THICKNESS, cv2.LINE_AA)

    return annotated_image


def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at: {MODEL_PATH}")
    if not os.path.exists(VIDEO_PATH):
        raise FileNotFoundError(f"Video not found at: {VIDEO_PATH}")

    # Create a HandLandmarker in VIDEO mode (enables temporal tracking between frames)
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.3,
        min_tracking_confidence = 0.5    )

    cap = cv2.VideoCapture(VIDEO_PATH)
    cap.set(cv2.CAP_PROP_FPS, 30)  # Set FPS to 30 for consistent timestamping

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {VIDEO_PATH}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0  # fallback if the container doesn't report FPS
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    writer = cv2.VideoWriter(
        OUTPUT_PATH, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    frame_idx = 0
    frames_with_hands = 0

    with vision.HandLandmarker.create_from_options(options) as detector:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            # OpenCV gives BGR; MediaPipe expects RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

            # Timestamp in ms, must be strictly increasing
            timestamp_ms = int(frame_idx * 1000 / fps)
            detection_result = detector.detect_for_video(mp_image, timestamp_ms)

            if detection_result.hand_landmarks:
                frames_with_hands += 1
                annotated_rgb = draw_landmarks_on_image(frame_rgb, detection_result)
            else:
                annotated_rgb = frame_rgb

            annotated_bgr = cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)
            writer.write(annotated_bgr)

            if SHOW_PREVIEW:
                cv2.imshow("Hand Landmarks (q to quit)", annotated_bgr)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            frame_idx += 1
            if frame_idx % 30 == 0:
                print(f"Processed {frame_idx}/{total_frames} frames")

    cap.release()
    writer.release()
    cv2.destroyAllWindows()

    print(f"Done. {frame_idx} frames processed, hands detected in {frames_with_hands}.")
    print(f"Saved annotated video to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()


def countdown(seconds):
    for i in range(seconds, 0, -1):
        print(f"Starting in {i} seconds...", end="\r")
        time.sleep(1)
    print("Starting now!            ")
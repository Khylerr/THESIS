import mediapipe as mp
import numpy as np
import cv2
import os
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.framework.formats import landmark_pb2
from mediapipe import solutions

mp_hands = solutions.hands
mp_drawing = solutions.drawing_utils
mp_drawing_styles = solutions.drawing_styles

MARGIN = 10  # pixels
FONT_SIZE = 1
FONT_THICKNESS = 1
HANDEDNESS_TEXT_COLOR = (88, 205, 54)  # vibrant green

BASE_DIR = r'C:\Users\Khyler\Desktop\THESIS\MediaPipe'
MODEL_PATH = os.path.join(BASE_DIR, 'hand_landmarker.task')
IMAGE_PATH = os.path.join(BASE_DIR, 'C:\\Users\\Khyler\\Desktop\\THESIS\\MediaPipe\\images\\glove2jpg')  


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
        x_coordinates = [landmark.x for landmark in hand_landmarks]
        y_coordinates = [landmark.y for landmark in hand_landmarks]
        text_x = int(min(x_coordinates) * width)
        text_y = int(min(y_coordinates) * height) - MARGIN

        cv2.putText(annotated_image, f"{handedness[0].category_name}",
                    (text_x, text_y), cv2.FONT_HERSHEY_DUPLEX,
                    FONT_SIZE, HANDEDNESS_TEXT_COLOR, FONT_THICKNESS, cv2.LINE_AA)

    return annotated_image


def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at: {MODEL_PATH}")
    if not os.path.exists(IMAGE_PATH):
        raise FileNotFoundError(f"Image not found at: {IMAGE_PATH}")

    # STEP 2: Create a HandLandmarker object.
    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=2, min_hand_detection_confidence=0.3)
    detector = vision.HandLandmarker.create_from_options(options)

    # STEP 3: Load the input image.
    image = mp.Image.create_from_file(IMAGE_PATH)

    # STEP 4: Detect hand landmarks.
    detection_result = detector.detect(image)
    print(detection_result)

    if not detection_result.hand_landmarks:
        print("No hands detected in the image.")
        return

    # STEP 5: Visualize.
    annotated_image = draw_landmarks_on_image(image.numpy_view(), detection_result)
    cv2.imshow("Annotated Image", cv2.resize(cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR), (700,500)))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
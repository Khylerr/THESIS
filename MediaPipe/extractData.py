import csv
import time
import cv2
import mediapipe as mp

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FPS, 30)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

csv_data = []
countdown_sec = 3
recording_sec = 4

with mp_hands.Hands(
    model_complexity=0,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
) as hands:

    init_time = time.time()
    recording_started = False
    start_time = None
    frame_count = 0

    while cap.isOpened():
        success, image = cap.read()
        if not success:
            continue

        elapsed_init = time.time() - init_time

        # Flip display image for intuitive selfie view
        image = cv2.flip(image, 1)

        # STAGE 1: Live Countdown Phase
        if elapsed_init < countdown_sec:
            remaining = int(countdown_sec - elapsed_init) + 1
            cv2.putText(
                image,
                f"Get Ready: {remaining}",
                (180, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                2,
                (0, 0, 255),
                4,
                cv2.LINE_AA,
            )
            cv2.imshow("MediaPipe Hands", image)
            if cv2.waitKey(5) & 0xFF == 27:
                break
            continue

        # STAGE 2: Start Recording Timer (Runs once after countdown)
        if not recording_started:
            start_time = time.time()
            recording_started = True
            print("Recording started!")

        # Process MediaPipe
        image.flags.writeable = False
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = hands.process(image_rgb)
        image.flags.writeable = True

        timestamp = time.time() - start_time

        if results.multi_hand_landmarks:
            for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                GLOVE_HAND = "Right"   # set per signer; save it in the metadata
                row = [frame_count, t_rec, 0] + [float("nan")] * 63
                for lms, hd in zip(results.multi_hand_landmarks or [], results.multi_handedness or []):
                    if hd.classification[0].label == GLOVE_HAND:
                        row = [frame_count, t_rec, 1] + [v for p in lms.landmark for v in (p.x, p.y, p.z)]
                csv_data.append(row)

                mp_drawing.draw_landmarks(
                    image,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style(),
                )

        # Overlay recording indicator
        cv2.putText(
            image,
            "REC",
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow("MediaPipe Hands", image)
        frame_count += 1

        if cv2.waitKey(5) & 0xFF == 27:
            break

        if time.time() - start_time >= recording_sec:
            break

cap.release()
cv2.destroyAllWindows()

# Export CSV
csv_filename = "hand_landmarks.csv"
headers = ["frame", "timestamp_sec", "hand_index", "landmark_index", "x", "y", "z"]

with open(csv_filename, mode="w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(csv_data)

print(f"Successfully exported {len(csv_data)} landmark rows to '{csv_filename}'.")
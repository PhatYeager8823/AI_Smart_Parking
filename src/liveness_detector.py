import cv2
import numpy as np
import mediapipe as mp
import time

class LivenessDetector:
    def __init__(self):
        # MediaPipe Face Mesh for eye tracking
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Eye landmark indices (MediaPipe)
        self.LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
        self.RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
        self.LEFT_EYE_TOP_BOTTOM = [386, 374]
        self.RIGHT_EYE_TOP_BOTTOM = [159, 145]
        
        # Blink detection variables
        self.blink_count = 0
        self.is_blinking = False
        self.EAR_THRESHOLD = 0.22 # Eye Aspect Ratio threshold for blink
        
    def calculate_ear(self, landmarks, eye_indices):
        # Simplified EAR for performance
        p1 = landmarks[eye_indices[12]] # Top
        p2 = landmarks[eye_indices[4]]  # Bottom
        
        # Distance between top and bottom landmarks
        dist = np.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)
        return dist

    def check_liveness(self, frame):
        """
        Check for liveness based on Laplacian variance (texture) and 
        blink detection (requires multiple frames, here we provide logic for a single frame check).
        """
        # 1. Laplacian Variance (Texture check)
        # Low variance usually means a photo/screen (blur or uniform texture)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 2. Face Mesh Processing
        results = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        is_live = False
        status_msg = "Checking..."
        
        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            
            # Check EAR for both eyes
            left_ear = self.calculate_ear(landmarks, self.LEFT_EYE)
            right_ear = self.calculate_ear(landmarks, self.RIGHT_EYE)
            avg_ear = (left_ear + right_ear) / 2.0
            
            # Simple logic: If texture is high and landmarks are found
            if laplacian_var > 100: # Threshold for texture
                is_live = True
                status_msg = f"LIVE (Texture: {int(laplacian_var)}, EAR: {avg_ear:.3f})"
            else:
                is_live = False
                status_msg = f"POSSIBLE SPOOF (Low Texture: {int(laplacian_var)})"
        else:
            status_msg = "No Face Detected"

        return is_live, status_msg, laplacian_var

if __name__ == "__main__":
    # Test with webcam
    cap = cv2.VideoCapture(0)
    detector = LivenessDetector()
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        is_live, msg, var = detector.check_liveness(frame)
        
        color = (0, 255, 0) if is_live else (0, 0, 255)
        cv2.putText(frame, msg, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        cv2.imshow("Liveness Test", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
        
    cap.release()
    cv2.destroyAllWindows()

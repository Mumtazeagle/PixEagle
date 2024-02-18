from classes.app_controller import AppController
from classes.parameters import Parameters
import cv2

# src/main.py

from classes.app_controller import AppController
import cv2

def main():
    controller = AppController()

    while True:
        frame = controller.video_handler.get_frame()
        if frame is None:
            break  # End of video or camera feed error
        
        frame = controller.update_frame(frame)
        cv2.imshow("Video", frame)

        key = cv2.waitKey(controller.video_handler.delay_frame) & 0xFF
        if key == ord('q'):  # Quit program
            break
        else:
            controller.handle_key_input(key, frame)

    controller.video_handler.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

import cv2
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import fftconvolve

import function_Tracking_video as fc
from function_Tracking_video import calibrate_fps



if __name__ == '__main__':
    # Open video
    root = './'
    video_file = '../examples/tracking/essai_2.mp4'
    calibrate_fps(video_file)
    video_file = 'output.mp4'
    video = cv2.VideoCapture(root+video_file)

    # Check if the video is properly open
    if not video.isOpened():
        print('Impossible to open the video file')
        exit()

    # Metadata from the input video
    fps = video.get(cv2.CAP_PROP_FPS)
    nb_total_frame = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'fps = {fps:.2f}')
    # print(f'{nb_total_frame = }')
    
    # INPUT Parameters
    #frame_step = 0.5*np.round(fps)
    #print(frame_step)
    #exit()
    frame_step = 1
    show_each_index = 1
    actualize_ref_each_index = 50
    scaling_ZR = 1

    # Extract frame at indicated time
    frame_start = 0

    # Frame stop defined by total frame number 
    frame_stop = nb_total_frame
    
    index_frame = np.arange(frame_start, frame_stop, frame_step)

    # Extract initial ROIs
    gray_ref, positions_ref = fc.get_ref(video, frame_start)
    gray_0 = gray_ref.copy()
    nb_roi = positions_ref.shape[0]

    # Main loop => Tracking   
    new_position, last_frame = fc.tracking_ROIs(video, gray_ref, positions_ref, index_frame, scaling_ZR, actualize_ref_each_index, show_each_index )
    
    # Check results
    fc.check_results(gray_0, last_frame, new_position, nb_roi)

    # Save results
    fc.save_parameters(root+video_file+'_tracking.csv', new_position, nb_roi, fps, frame_step)
    
# %%

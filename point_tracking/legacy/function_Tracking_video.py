import cv2
import numpy as np
import matplotlib.pyplot as plt

def calibrate_fps(input_file, output_file='output.mp4', target_fps = 5):

    cap = cv2.VideoCapture(input_file)

    # Get the original video's frames per second (fps)
    original_fps = cap.get(cv2.CAP_PROP_FPS)

    # Calculate the frame interval required for the conversion
    frame_interval = round(original_fps / target_fps)

    # Create an output video file
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    output_size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    out = cv2.VideoWriter(output_file, fourcc, target_fps, output_size)
    frame_counter = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_counter % frame_interval == 0:
            out.write(frame)

        frame_counter += 1

    cap.release()
    out.release()

    print("Video conversion completed!")


def get_ref(video, frame_start):
    # Lire la première image
    video.set(cv2.CAP_PROP_POS_FRAMES, frame_start) # Position de l'image à lire
    _, frame_ref = video.read()
    gray_ref = cv2.cvtColor(frame_ref, cv2.COLOR_BGR2GRAY)
    gray_0 = cv2.cvtColor(frame_ref, cv2.COLOR_BGR2GRAY)

    # Select ROI
    rois = cv2.selectROIs('Make a rectangular selection for each ROI - Press space or enter after each selection - Pres ESC when finished', frame_ref)
    cv2.destroyAllWindows()

    # Afficher les zones d'intérêt sélectionnées
    positions_ref = np.zeros((len(rois), len(rois[0])), dtype='int')
    for index, roi in enumerate(rois):
        x, y, w, h = roi
        positions_ref[index,:]= roi
        cv2.rectangle(frame_ref, (x, y), (x+w, y+h), (0, 255, 0), 2)

    # Afficher l'image avec les zones d'intérêt sélectionnées
    cv2.imshow('These are the ROI you have selected - Press ESC to close the window and continue', frame_ref)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    test = input('Intial ROIs are well defined? (y/n) ')

    if test == 'n':
        print('\n/!\ Wrong definition of ROIs.')
        print('    Try again')
        input('\n<Hit Enter To Exit>')
        exit()
    
    return gray_ref, positions_ref

def tracking_ROIs(video, gray_ref, positions_ref, index_frame, scaling_ZR, actualize_ref_each_index, show_each_index ):
    nb_roi = positions_ref.shape[0]    
    nb_traited_frame = len(index_frame)
    
    new_position = np.zeros((nb_traited_frame, nb_roi*positions_ref.shape[1]))
    all_frame_ref = []
    for index, roi in enumerate(positions_ref):
        new_position[0,4*index:4*index+4] = roi
        new_position[:,4*index+2] = roi[2]*np.ones(new_position.shape[0])
        new_position[:,4*index+3] = roi[3]*np.ones(new_position.shape[0])
        x_ref, y_ref, w_ref, h_ref = roi
        frame_ref = gray_ref[y_ref:y_ref+h_ref, x_ref:x_ref+w_ref]
        all_frame_ref.append(frame_ref)

    count=1
    count_Delta = 1
    count_show = 1
    Color_green = True
    for sub_frame in index_frame[1:]:
        print('frame loaded: ', sub_frame, end='\r')
        video.set(cv2.CAP_PROP_POS_FRAMES, sub_frame)
        _, frame = video.read()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        tmp_rects = np.zeros(positions_ref.shape)
        for index, _ in enumerate(positions_ref):
            x, y, w, h = new_position[count-1, 4*index:4*index+4].astype(int)       # Last postion of the ROI
            x_ref, y_ref, w_ref, h_ref = positions_ref[index, :]
            w_scale = int(scaling_ZR*w)
            h_scale = int(scaling_ZR*h)
                   
            frame_ref = all_frame_ref[index]                                    # pattern to find
            frame_ZR = gray[y-h_scale:y+h+h_scale, x-w_scale:x+w+w_scale]       # area where to search (bigger than frame_ref)
            
            result = cv2.matchTemplate(frame_ZR, frame_ref, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            top_left = (x-w_scale + max_loc[0], y-h_scale + max_loc[1])
            # bottom_right = (top_left[0] + w, top_left[1] + h)
                        
            new_position[count, 4*index:4*index+4] = np.array([top_left[0], top_left[1], w, h])
            tmp_rects[index,:] = new_position[count, 4*index:4*index+4]
            
        # Actualisation de l'image de référance
        if count_Delta == actualize_ref_each_index:
            gray_ref = gray
            all_frame_ref = []
            for index, roi in enumerate(tmp_rects):
                x, y, w, h = roi
                positions_ref[index,:]= roi
                x_ref, y_ref, w_ref, h_ref = roi.astype(int)
                frame_ref = gray_ref[y_ref:y_ref+h_ref, x_ref:x_ref+w_ref]
                all_frame_ref.append(frame_ref)
            count_Delta = 1
            Color_green = not(Color_green)
        else:
            count_Delta += 1
        
        if count_show == show_each_index:    
            for index, roi in enumerate(tmp_rects):    
                x, y, w, h = tmp_rects[index,:].astype(int)
                if Color_green:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                else:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
            cv2.imshow('Tracking...', frame)
            # cv2.waitKey(0)
            # cv2.waitKey(int(1/fps * 1000))   
            cv2.waitKey(1)   
            count_show = 1
        else:
            count_show += 1
        count += 1
        
    # cv2.waitKey(0)    
    cv2.destroyAllWindows()
    
    return new_position, gray

def check_results(gray_0, last_frame, new_position, nb_roi):
    plt.figure(1, figsize=(8*16/9,8))
    plt.clf()
    plt.subplot(221)
    plt.imshow(gray_0, cmap='gray')
    for n in range(nb_roi):
        plt.plot(new_position[0,4*n]+0.5*new_position[0,4*n+2], new_position[0,4*n+1]+0.5*new_position[0,4*n+3], 'r.', markersize = 5)
    plt.title('Reference points')

    plt.subplot(222)
    plt.imshow(last_frame, cmap='gray')
    for n in range(nb_roi):
        plt.plot(new_position[-1,4*n]+0.5*new_position[-1,4*n+2], new_position[-1,4*n+1]+0.5*new_position[-1,4*n+3], 'b.', markersize = 5)
    plt.title(f'Last identified points')
    plt.show(block=False)

    # plt.figure(2,figsize=(16,8))
    plt.subplot(212)
    plt.imshow(gray_0, cmap='gray')
    for n in range(nb_roi):
        plt.plot(new_position[:,4*n]+0.5*new_position[:,4*n+2], new_position[:,4*n+1]+0.5*new_position[:,4*n+3], '.')
        plt.plot(new_position[0,4*n]+0.5*new_position[0,4*n+2], new_position[0,4*n+1]+0.5*new_position[0,4*n+3], 'r.', markersize = 5)
        plt.plot(new_position[-1,4*n]+0.5*new_position[-1,4*n+2], new_position[-1,4*n+1]+0.5*new_position[-1,4*n+3], 'b*', markersize = 5)
    # plt.grid()
    plt.title('Displacements of followed points')
    plt.show(block=False)
    
    test = input('Convergence Ok? (y/n) ')

    if test == 'n':
        print('\n/!\ Tracking failed.')
        print('    Try other parameters and/or ROIs')
        input('\n<Hit Enter To Exit>')
        exit()
    else:
        plt.close('all')

def save_parameters(root, new_position, nb_roi, fps, frame_step):
    s = input('\nSave ? (y/n) ')
    
    if s == 'y':
        time_vector = np.zeros(new_position.shape[0])
        for index, _ in enumerate(time_vector[1:]):
            time_vector[index+1] = time_vector[index]+1000*frame_step/fps
        
        w_h_index = []
        for i in range(nb_roi):
            if i == 0:
                Myheader1 = 'w \t h'
                Myheader2 = 'x \t y'
            else:
                Myheader1 += ' \t w \t h'
                Myheader2 += ' \t x \t y'
            w_h_index.append(i*4+2)
            w_h_index.append(i*4+3)
        L = new_position[0,w_h_index]
        L_str = '\t'.join(str(int(item)) for item in L)
        
        with open(root, 'w') as f:
            x_w_index = [item-2 for item in w_h_index]
            f.write(f'time(s) \t {Myheader2} \n')
            for index, row in enumerate(new_position):
                L =  time_vector[index] / 1000
                L = np.append(L,row[x_w_index])
                L_str = '\t'.join(str(item) for item in L)
                f.write(L_str+'\n')

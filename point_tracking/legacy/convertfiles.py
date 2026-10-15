# Convert files
import csv
import numpy as np

import matplotlib.pyplot as plt


# Parameters
root = 'dossier/'
file1 = 'mesures_force_1.txt'
file2 = 'video_1.mp4_tracking.csv'
time_offset = 0

data1 = np.genfromtxt(root+file1, delimiter='\t',skip_header=1)
data2 = np.genfromtxt(root+file2, delimiter='\t',skip_header=1)

data2out = np.zeros((data1.shape[0],data2.shape[1]))
data2out[:,0] = data1[:,0] + time_offset

for i in range(1,data2.shape[1]):
    data2out[:,i] = np.interp(data1[:,0],data2[:,0], data2[:,i])

np.savetxt(root+file2+'_resampled.csv', data2out, delimiter='\t', newline='\n', header='time \t x \t y \t x \t y')

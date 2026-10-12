import time

import numpy as np

from actiCHampConnect import ActiCHampDevice

if __name__ == '__main__':
    # Set up parameters
    fs = 1000            # sampling rate in Hz (100 ... 100000, see README)
    recTime = 5          # in seconds
    impedanceTime = 10   # how long impedances are shown, in seconds
    numEEG = 32          # EEG channels of your actiCHamp (Plus)
    samples = fs * recTime

    # Connect with actiCHamp (starts Producer/EEG_SharedMemoryProducer.exe)
    actichamp = ActiCHampDevice()
    actichamp.connect()

    try:
        # Get impedances. Only possible BEFORE the acquisition is started.
        # Values in Ohm: [GND, REF, Ch1, Ch2, ...], -1 = not available
        for _ in range(impedanceTime):
            impedances = actichamp.get_impedances()
            if impedances.size:
                kOhm = np.round(impedances / 1000, 1)
                print('GND', kOhm[0], '| REF', kOhm[1], '| Ch 1-%d' % numEEG, kOhm[2:2 + numEEG], 'kOhm')
            time.sleep(1)

        # Start acquisition (ends the impedance measurement)
        actichamp.start_acquisition(fs)

        # Get data: samples x 43 columns
        # columns 0-31: EEG / µV, columns 32-39: AUX 1-8, see README
        print('Start collecting %d samples...' % samples)
        data = actichamp.get_data(samples)
        eeg = data[:, :numEEG]

        # Do something with data
        print(data.shape, 'lost samples:', actichamp.lost_samples())
    finally:
        # Stop data acquisition and close the producer
        actichamp.disconnect()

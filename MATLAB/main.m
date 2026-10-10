% Run this script from inside the MATLAB folder.
clear
clc

% Set up parameters
fs = 1000;            % sampling rate in Hz (100 ... 100000, see README)
recTime = 5;          % in seconds
impedanceTime = 10;   % how long impedances are shown, in seconds
numEEG = 32;          % EEG channels of your actiCHamp (Plus)

timeout = 10;         % wait until the producer responds
sampels = fs * recTime;
producerDir = fullfile(fileparts(pwd), 'Producer');

% Connect with actiCHamp (starts Producer\EEG_SharedMemoryProducer.exe)
proc = ActiCHampConnect(producerDir, timeout);

%% Get impedances
% Only possible BEFORE the sampling rate is set with WriteFs.
% Values in Ohm: [GND, REF, Ch1, Ch2, ...], -1 = not available
for k = 1:impedanceTime
    impedances = GetImpedances();
    if ~isempty(impedances)
        kOhm = impedances / 1000;
        fprintf('GND %.1f | REF %.1f | Ch 1-%d: %s kOhm\n', ...
            kOhm(1), kOhm(2), numEEG, mat2str(kOhm(3:numEEG+2), 3));
    end
    pause(1);
end

%% Start acquisition
% Setting the sampling rate ends the impedance measurement and starts the stream.
WriteFs(fs);
ReadHybridMemory(10);   % blocks until the first samples arrive

%% Get Data
% sampels x 43 columns
% columns 1-32: EEG / µV, columns 33-40: AUX 1-8, see README
data = ReadHybridMemory(sampels);
eeg = data(:, 1:numEEG);

% Do Something with data
% .
% .
% .
disp(size(data))

%% Stop data acquisition
ActiCHampDisconnect(proc, timeout);

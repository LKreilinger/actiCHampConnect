% Rebuild the MEX functions that read/write the shared memory.
% Run this script from inside the MATLAB folder.
%
% Needed after every change of ..\Producer\SharedBuffer.h (the producer and
% all MEX functions must use the identical memory layout) or after a change
% of one of the *.cpp files in this folder.
%
% Requires a C++ compiler for MEX (check with: mex -setup cpp).
% The producer must not be running and no MEX function may be in use.

clear mex   % release the old .mexw64 files so they can be overwritten

includeDir = ['-I' fullfile(fileparts(pwd), 'Producer')];   % SharedBuffer.h
sources = {'GetImpedances.cpp', 'WriteFs.cpp', 'ReadHybridMemory.cpp', ...
    'ClearSharedBuffer.cpp', 'StopProducer.cpp'};

for k = 1:numel(sources)
    mex(includeDir, sources{k});
end
disp('All MEX functions built.');

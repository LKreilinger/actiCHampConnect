function proc = ActiCHampConnect(producerDir, timeout)
% ACTICHAMPCONNECT Start EEG_SharedMemoryProducer.exe and wait until it is ready.
%   proc = ActiCHampConnect(producerDir, timeout)
%
%   producerDir  folder with EEG_SharedMemoryProducer.exe and the SDK DLLs
%   timeout      seconds to wait for the producer
%   proc         .NET process handle, needed for ActiCHampDisconnect(proc)
%
%   After this call the amplifier measures impedances (see GetImpedances)
%   until a sampling rate is set with WriteFs(fs).

exeName = 'EEG_SharedMemoryProducer';
exeFile = fullfile(producerDir, [exeName '.exe']);
if ~isfile(exeFile)
    error('Producer not found: %s', exeFile);
end

NET.addAssembly('System');
if System.Diagnostics.Process.GetProcessesByName(exeName).Length > 0
    error(['%s.exe is already running. Stop it first with StopProducer() ' ...
        'or end it in the Task Manager.'], exeName);
end

% Start the producer. It needs its own folder as working directory
% (SDK DLLs and *.bit files are loaded from there).
proc = System.Diagnostics.Process();
proc.StartInfo.FileName = exeFile;
proc.StartInfo.WorkingDirectory = producerDir;
proc.StartInfo.UseShellExecute = false;
proc.Start();

% Wait until the shared memory exists (the MEX functions throw until then).
tStart = tic;
ready = false;
while ~ready
    try
        ClearSharedBuffer();   % also resets leftovers of a previous run
        ready = true;
    catch
        if proc.HasExited || toc(tStart) > timeout
            error('Producer did not create the shared memory. See its console output.');
        end
        pause(0.05);
    end
end

% The producer exits by itself if it finds no amplifier.
pause(1);
if proc.HasExited
    error(['Producer exited. Is the actiCHamp connected via USB, powered and not ' ...
        'in use by another program (e.g. BrainVision Recorder)?']);
end
disp('actiCHamp producer started.');
end
